"""Orquestacion del triaje: de la solicitud a la respuesta del contrato.

Es el unico lugar donde se ve el flujo completo de punta a punta:

    recibir -> guardar original -> ingerir -> clasificar -> extraer
            -> decidir -> guardar resultado en su prefijo -> responder

Las cuatro dependencias (ingestor, clasificador, extractor y almacenamiento) se
inyectan. No se construyen aca a proposito: asi las pruebas usan dobles y no
consumen cuota de Gemini ni escriben en un bucket real.
"""

import logging
import time
from concurrent.futures import ThreadPoolExecutor

from mediflow_agent.ingestion.base import DocumentoNormalizado, ErrorDeIngesta
from mediflow_agent.ingestion.ingestor import Ingestor
from mediflow_agent.modelos import PRESUPUESTO_SEGUNDOS
from mediflow_agent.notificaciones import enviar_alerta
from mediflow_agent.routing.baseline import decidir_enrutamiento
from mediflow_agent.schemas.models import (
    AgentResult,
    ClassificationResult,
    ExtractedData,
)
from mediflow_agent.serialization.contract import (
    AlmacenamientoOciContrato,
    DecisionEnrutamientoContrato,
    RespuestaTriaje,
    SolicitudTriaje,
    a_respuesta_triaje,
)
from mediflow_agent.storage.base import (
    PREFIJO_AUDITORIA,
    PREFIJO_RECIBIDOS,
    PREFIJO_RUTINA,
    PREFIJO_URGENTES,
    AlmacenamientoDocumentos,
)

_log = logging.getLogger(__name__)

# Extension con la que se archiva el original segun como llego.
EXTENSION_ORIGINAL = {"PDF": "pdf", "IMAGEN": "png", "TEXTO": "txt", "JSON": "json"}


def _prefijo_destino(
    nivel_prioridad: str,
    decision: DecisionEnrutamientoContrato,
) -> str:
    """Traduce la decision de enrutamiento al prefijo del almacen.

    El orden importa: la urgencia manda sobre la auditoria. Un caso urgente que
    ademas necesita revision humana va a `procesados/urgentes/`, porque es la
    carpeta que alguien mira primero.
    """
    if nivel_prioridad == "Urgente":
        return PREFIJO_URGENTES

    if decision.requiere_auditoria_humana:
        return PREFIJO_AUDITORIA

    return PREFIJO_RUTINA


class ServicioTriaje:

    def __init__(
        self,
        clasificador,
        extractor,
        almacenamiento: AlmacenamientoDocumentos,
        ingestor: Ingestor | None = None,
        llm_urgencia=None,
        notificador=None,
    ):
        self._clasificador = clasificador
        self._extractor = extractor
        self._almacenamiento = almacenamiento
        self._ingestor = ingestor or Ingestor()

        # Segunda via de la deteccion de urgencia. Sin modelo, el sistema
        # sigue triando con la via por lista: es el piso que queda en pie si
        # se agota la cuota.
        self._llm_urgencia = llm_urgencia

        # Entrega de la alerta de guardia. Se inyecta para poder probar el
        # envio sin abrir una conexion de red en las pruebas.
        self._notificar = notificador or enviar_alerta

    # -- pasos ----------------------------------------------------------

    def _guardar_original(
        self,
        solicitud: SolicitudTriaje,
        contenido: bytes | None,
    ) -> None:
        """Archiva el documento tal como llego, en `recibidos/`.

        Es lo unico que permite auditar despues si el agente leyo mal o si el
        documento ya venia ilegible. Si falla, se registra y se sigue: perder
        la copia es malo, pero no tanto como no triar el documento.
        """
        extension = EXTENSION_ORIGINAL.get(solicitud.tipo_archivo, "bin")
        nombre = f"{solicitud.documento_id}.{extension}"

        if contenido is not None:
            resultado = self._almacenamiento.guardar_binario(
                PREFIJO_RECIBIDOS, nombre, contenido
            )
        elif solicitud.documento_texto:
            resultado = self._almacenamiento.guardar_texto(
                PREFIJO_RECIBIDOS,
                nombre,
                solicitud.documento_texto,
                tipo_contenido="text/plain; charset=utf-8",
            )
        else:
            return

        if not resultado.exito:
            _log.warning(
                "No se guardo el original de %s: %s",
                solicitud.documento_id,
                resultado.detalle_error,
            )

    def _ingerir(
        self,
        solicitud: SolicitudTriaje,
        contenido: bytes | None,
    ) -> tuple[DocumentoNormalizado | None, str | None]:
        """Normaliza el documento. Devuelve (documento, motivo_de_fallo)."""
        try:
            documento = self._ingestor.ingerir(
                tipo_archivo=solicitud.tipo_archivo,
                contenido=contenido,
                texto=solicitud.documento_texto,
            )
            return documento, None

        except ErrorDeIngesta as err:
            _log.warning("Fallo la ingesta de %s: %s", solicitud.documento_id, err)
            return None, str(err)

    def _extraer(self, texto: str, tipo_documento: str):
        """Llama al extractor, sea el generico o el especifico por tipo.

        El extractor por tipo (tarea 2.2) recibe el tipo de documento y
        devuelve un `ResultadoExtraccion` con avisos; el generico recibe solo
        el texto y devuelve `ExtractedData`. Se admiten los dos para no
        obligar a cambiar todas las pruebas de golpe, y porque el generico
        sigue siendo util como respaldo.
        """
        try:
            resultado = self._extractor.extract(texto, tipo_documento)
        except TypeError:
            # Extractor generico: no acepta el tipo.
            return self._extractor.extract(texto), (), None

        datos = getattr(resultado, "datos", resultado)
        avisos = tuple(getattr(resultado, "avisos", ()))
        # El objeto especifico por tipo trae campos que la forma comun no
        # tiene, como es_receta_controlada, y el enrutamiento los necesita.
        especifico = getattr(resultado, "especifico", None)

        return datos, avisos, especifico

    def _analizar(self, texto: str):
        """Clasifica y despues extrae segun el tipo encontrado.

        **Por que en serie y no en paralelo.** El extractor por tipo necesita
        saber que clase de documento es para elegir su esquema y su prompt: de
        una receta importan los medicamentos con su dosis, de un informe los
        hallazgos. Esa dependencia impide lanzar las dos llamadas a la vez.

        Se probo el camino paralelo con el extractor generico y tardaba 1,1
        segundos contra 2,1 de este. Se eligio este igual, por dos razones: el
        generico devolvia los medicamentos sin la dosis, que es el dato mas
        critico de una receta, y la verificacion del codigo CIE-10 contra el
        catalogo vive dentro del extractor por tipo. Un segundo de diferencia
        no se nota contra un presupuesto de diez.

        Un fallo del modelo no es una excepcion que sube hasta el cliente: es
        exactamente el caso que la regla del proyecto manda escalar a una
        persona. Se devuelve una clasificacion vacia con confianza cero, que el
        enrutamiento va a derivar a revision humana.
        """
        inicio = time.perf_counter()

        try:
            clasificacion = self._clasificador.classify(texto)
            datos, avisos, especifico = self._extraer(
                texto, clasificacion.document_type
            )

            transcurrido = time.perf_counter() - inicio

            if transcurrido > PRESUPUESTO_SEGUNDOS:
                # No se corta el triaje: ya esta resuelto y la respuesta sirve.
                # Pero queda registrado, porque un modelo que se pasa del
                # presupuesto de forma sostenida hay que cambiarlo.
                _log.warning(
                    "El analisis tardo %.1fs, por encima del presupuesto de %.1fs.",
                    transcurrido,
                    PRESUPUESTO_SEGUNDOS,
                )

            return clasificacion, datos, avisos, especifico, False

        except Exception as err:  # noqa: BLE001 - cualquier fallo escala igual
            _log.exception("Fallo el modelo al procesar el documento: %s", err)

            return (
                ClassificationResult(document_type="desconocido", confidence=0.0),
                ExtractedData(),
                (),
                None,
                True,
            )

    # -- flujo completo -------------------------------------------------

    def procesar(
        self,
        solicitud: SolicitudTriaje,
        contenido: bytes | None = None,
    ) -> RespuestaTriaje:
        self._guardar_original(solicitud, contenido)

        documento, fallo_ingesta = self._ingerir(solicitud, contenido)

        if documento is None:
            # No se pudo leer el documento. No se intenta clasificar algo que
            # no se leyo: se escala tal como manda la regla del proyecto.
            clasificacion = ClassificationResult(
                document_type="desconocido", confidence=0.0
            )
            datos = ExtractedData()
            avisos_extraccion: tuple[str, ...] = ()
            especifico = None
            fallo_modelo = False
        else:
            (
                clasificacion,
                datos,
                avisos_extraccion,
                especifico,
                fallo_modelo,
            ) = self._analizar(documento.texto)

        nivel_prioridad, decision, status = decidir_enrutamiento(
            documento_id=solicitud.documento_id,
            clasificacion=clasificacion,
            datos=datos,
            canal_origen=solicitud.canal_origen,
            documento=documento,
            llm=self._llm_urgencia,
            especifico=especifico,
        )

        motivo = None

        if fallo_ingesta:
            motivo = (
                f"No se pudo leer el documento ({fallo_ingesta}). Se escala a "
                "revision humana sin intentar una clasificacion automatica."
            )
        elif fallo_modelo:
            motivo = (
                "El modelo de lenguaje fallo al procesar el documento. Se "
                "escala a revision humana sin intentar una clasificacion "
                "automatica."
            )

        # Avisos de la ingesta (paginas truncadas, imagen reducida, capa de
        # texto pobre) y de la extraccion (un codigo CIE-10 descartado por no
        # existir). Llegan hasta el auditor: le dicen que el agente pudo haber
        # visto menos de lo que el documento traia, o que descarto un dato.
        avisos = tuple(documento.avisos if documento else ()) + avisos_extraccion

        if motivo:
            decision = decision.model_copy(
                update={"justificacion_enrutamiento": motivo}
            )
            status = "error"

        elif avisos:
            decision = decision.model_copy(
                update={
                    "justificacion_enrutamiento": (
                        decision.justificacion_enrutamiento
                        + " Avisos: "
                        + " ".join(avisos)
                    )
                }
            )

        prefijo = _prefijo_destino(nivel_prioridad, decision)
        nombre_objeto = f"{solicitud.documento_id}.json"

        respuesta = a_respuesta_triaje(
            resultado=AgentResult(
                document_id=solicitud.documento_id,
                classification=clasificacion,
                extracted_data=datos,
            ),
            nivel_prioridad=nivel_prioridad,
            decision_enrutamiento=decision,
            almacenamiento_oci=AlmacenamientoOciContrato(
                bucket=self._almacenamiento.bucket,
                ruta_objeto=f"{prefijo}/{nombre_objeto}",
                status_backup="exito",
            ),
            status=status,
        )

        # Se guarda la respuesta ya armada, para que el objeto persistido sea
        # exactamente lo que vio el cliente.
        guardado = self._almacenamiento.guardar_texto(
            prefijo=prefijo,
            nombre_objeto=nombre_objeto,
            contenido=respuesta.model_dump_json(indent=2),
        )

        if not guardado.exito:
            # El triaje se resolvio igual. Se informa el fallo del respaldo sin
            # invalidar la decision clinica.
            respuesta = respuesta.model_copy(
                update={
                    "almacenamiento_oci": respuesta.almacenamiento_oci.model_copy(
                        update={"status_backup": "fallo"}
                    )
                }
            )

        # La alerta se manda DESPUES de persistir. Al reves, un webhook lento
        # retrasaria el guardado, y una guardia avisada de un caso que todavia
        # no esta en el bucket no tendria donde ir a verlo. `enviar_alerta` no
        # levanta excepciones: un canal caido no invalida un triaje resuelto.
        if decision.notificacion_generada is not None:
            try:
                self._notificar(
                    mensaje=decision.notificacion_generada.mensaje,
                    documento_id=solicitud.documento_id,
                )
            except Exception:
                # `enviar_alerta` ya atrapa lo suyo, pero el notificador es
                # inyectable y manana puede ser otro. La garantia de que un
                # canal caido no tumba un triaje se defiende aca, en el
                # limite, y no en la buena conducta de quien se enchufe.
                _log.exception(
                    "Fallo el envio de la alerta de %s. El triaje se completo "
                    "igual y el documento ya esta guardado.",
                    solicitud.documento_id,
                )

        return respuesta
