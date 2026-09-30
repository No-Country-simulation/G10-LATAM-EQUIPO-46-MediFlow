"""Orquestacion del triaje: de la solicitud a la respuesta del contrato.

Es el unico lugar donde se ve el flujo completo de punta a punta, y por eso
conviene que se lea de corrido:

    recibir -> guardar original -> clasificar -> extraer -> decidir
            -> guardar resultado en el prefijo que corresponde -> responder

Las tres dependencias (clasificador, extractor y almacenamiento) se inyectan.
No se construyen aca a proposito: asi las pruebas usan dobles y no consumen
cuota de Gemini ni escriben en un bucket real.
"""

import logging

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

FORMATOS_CON_TEXTO = frozenset({"TEXTO", "JSON"})


class FormatoNoSoportado(Exception):
    """El documento llego en un formato que la ingesta todavia no lee."""


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
    ):
        self._clasificador = clasificador
        self._extractor = extractor
        self._almacenamiento = almacenamiento

    # -- pasos ----------------------------------------------------------

    def _guardar_original(self, solicitud: SolicitudTriaje) -> None:
        """Deja el documento tal como llego en `recibidos/`.

        Es lo que permite reprocesar un caso o auditar que vio el agente. Si
        falla, se registra y se sigue: perder la copia del original es malo,
        pero no tanto como no triar el documento.
        """
        if not solicitud.documento_texto:
            return

        resultado = self._almacenamiento.guardar_texto(
            prefijo=PREFIJO_RECIBIDOS,
            nombre_objeto=f"{solicitud.documento_id}.txt",
            contenido=solicitud.documento_texto,
            tipo_contenido="text/plain; charset=utf-8",
        )

        if not resultado.exito:
            _log.warning(
                "No se guardo el original de %s: %s",
                solicitud.documento_id,
                resultado.detalle_error,
            )

    def _analizar(self, texto: str) -> tuple[ClassificationResult, ExtractedData, bool]:
        """Clasifica y extrae. Devuelve tambien si el modelo fallo.

        Un fallo del modelo no es una excepcion que sube hasta el cliente: es
        exactamente el caso que la regla del proyecto manda escalar a una
        persona. Se devuelve una clasificacion vacia con confianza cero, que
        el enrutamiento va a derivar a revision humana.
        """
        try:
            clasificacion = self._clasificador.classify(texto)
            datos = self._extractor.extract(texto)
            return clasificacion, datos, False

        except Exception as err:  # noqa: BLE001 - cualquier fallo escala igual
            _log.exception("Fallo el modelo al procesar el documento: %s", err)

            return (
                ClassificationResult(document_type="desconocido", confidence=0.0),
                ExtractedData(),
                True,
            )

    # -- flujo completo -------------------------------------------------

    def procesar(self, solicitud: SolicitudTriaje) -> RespuestaTriaje:
        if solicitud.tipo_archivo not in FORMATOS_CON_TEXTO:
            # PDF e imagen son la tarea 2.1. Se rechaza de forma explicita en
            # lugar de devolver un triaje vacio que parezca valido.
            raise FormatoNoSoportado(
                f"La ingesta de {solicitud.tipo_archivo} todavia no esta "
                "implementada (tarea 2.1). Por ahora solo TEXTO y JSON."
            )

        texto = solicitud.documento_texto or ""

        self._guardar_original(solicitud)

        clasificacion, datos, fallo_modelo = self._analizar(texto)

        nivel_prioridad, decision, status = decidir_enrutamiento(
            documento_id=solicitud.documento_id,
            clasificacion=clasificacion,
            datos=datos,
            canal_origen=solicitud.canal_origen,
        )

        if fallo_modelo:
            # Se conserva la ruta que eligio el enrutamiento (revision humana,
            # por confianza cero) pero se dice la verdad sobre por que.
            decision = decision.model_copy(
                update={
                    "justificacion_enrutamiento": (
                        "El modelo de lenguaje fallo al procesar el documento. "
                        "Se escala a revision humana sin intentar una "
                        "clasificacion automatica."
                    )
                }
            )
            status = "error"

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

        return respuesta
