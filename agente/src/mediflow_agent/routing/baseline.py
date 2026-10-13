"""El grafo de decision del agente.

Nueve pasos en orden, cada uno con su razon de estar donde esta. El diagrama
que los dibuja vive en el README; si se toca el orden de aqui, hay que tocarlo
alla tambien.

Lo que se decide fuera del codigo, en `config/triaje.toml`: el umbral de
confianza, los canales que elevan la prioridad y el destino de cada tipo de
documento. Es el diferencial que pide el enunciado —que un gestor hospitalario
ajuste el triaje sin tocar el codigo fuente— y por eso no hay ninguna de esas
tres cosas escrita a mano aca.

Respeta las dos reglas que el proyecto no negocia:

  1. Ante duda, fallo del modelo o documento ilegible, el caso escala a una
     persona. Nunca hay aprobacion automatica por defecto.
  2. El sesgo es siempre a escalar. Ante dos lecturas posibles, se elige la que
     pone a un humano a mirar.

El peor fallo posible de este sistema es que un hallazgo urgente se clasifique
como rutina. Por eso la deteccion de urgencia corre ANTES que cualquier otra
regla y, cuando dispara, no hay ruta que la anule.
"""

import logging
import unicodedata
from typing import get_args

from mediflow_agent.config import ajuste, cargar_archivo

from mediflow_agent.ingestion.base import DocumentoNormalizado
from mediflow_agent.routing.reglas_documento import (
    campos_faltantes,
    es_certificado_de_junta,
    es_receta_controlada,
)
from mediflow_agent.routing.urgencia import detectar as detectar_urgencia
from mediflow_agent.schemas.models import ClassificationResult, ExtractedData
from mediflow_agent.serialization.contract import (
    DecisionEnrutamientoContrato,
    DestinoEnrutamiento,
    NivelPrioridad,
    NotificacionContrato,
    StatusTriaje,
)

_log = logging.getLogger(__name__)

# Las tres reglas configurables se leen en CADA decision, no al importar el
# modulo. Es lo que hace que un cambio desde la pantalla de configuracion
# tenga efecto en el documento siguiente: si se leyeran una vez al arrancar,
# la pantalla mostraria un valor y el agente usaria otro hasta el proximo
# reinicio. `cargar_archivo` solo vuelve a parsear el TOML cuando cambio su
# fecha, asi que el costo por documento es un `stat` del sistema de archivos.

UMBRAL_POR_DEFECTO = 0.70

CANALES_POR_DEFECTO = ("guardia_emergencias", "urgencias", "emergencias")


def umbral_configurado() -> float:
    """Por debajo de esto, el caso va a revision humana pase lo que pase.

    La evidencia detras del valor, y sus limites, estan en
    `config/triaje.toml`.
    """
    return float(
        ajuste(
            "confianza", "umbral", UMBRAL_POR_DEFECTO, "MEDIFLOW_UMBRAL_CONFIANZA"
        )
    )


def canales_prioritarios() -> frozenset[str]:
    """Canales que, por si solos, elevan la prioridad.

    Que un documento venga de guardia es una senal, no una prueba: sube a
    Prioritario, no a Urgente.
    """
    return frozenset(
        ajuste("urgencia", "canales_prioritarios", list(CANALES_POR_DEFECTO))
    )

# Destino por tipo de documento, segun el grafo de decision del README.
# Marca que el transcriptor multimodal deja donde no pudo leer. Su presencia
# significa que hay un dato del documento que NADIE leyo: ni el modelo ni,
# todavia, una persona. En una receta puede ser la dosis.
MARCA_ILEGIBLE = "[ilegible]"

DESTINOS_POR_DEFECTO: dict[str, DestinoEnrutamiento] = {
    "receta_medica": "Farmacia_Hospitalaria",
    "orden_procedimiento": "Auditoria_Autorizaciones",
    "informe_estudio_diagnostico": "Historia_Clinica_Electronica",
    "epicrisis": "Historia_Clinica_Electronica",
    "certificado_medico": "Historia_Clinica_Electronica",
}


def destinos_configurados(ruta=None) -> dict[str, DestinoEnrutamiento]:
    """Mapa de tipo de documento a destino, leido de `config/triaje.toml`.

    Es lo que habilita el diferencial del enunciado: que un gestor hospitalario
    cambie a donde va cada tipo de documento sin tocar el codigo fuente.

    La seccion `[destinos]` del archivo, cuando existe, MANDA: un tipo que no
    figure en ella se queda sin ruta y escala a revision humana. Es a
    proposito. Si se completara con el valor por defecto, quitar una linea del
    archivo no tendria ningun efecto visible y el gestor no podria desactivar
    una ruta automatica, que es justo lo que querria hacer ante un destino que
    todavia no esta listo para recibir documentos solo.

    Un destino mal escrito se descarta con un aviso en el log en lugar de
    tumbar el arranque: un error de tipeo en la configuracion no puede dejar
    al hospital sin triaje. Ese tipo se queda sin ruta y, por lo tanto,
    escala.
    """
    seccion = cargar_archivo(ruta).get("destinos")

    if not isinstance(seccion, dict) or not seccion:
        return dict(DESTINOS_POR_DEFECTO)

    validos = set(get_args(DestinoEnrutamiento))
    mapa: dict[str, DestinoEnrutamiento] = {}

    for tipo, destino in seccion.items():
        if destino in validos:
            mapa[tipo] = destino
        else:
            _log.warning(
                "Destino invalido en config/triaje.toml para '%s': %r. Los "
                "destinos validos son %s. Ese tipo escalara a revision "
                "humana.",
                tipo,
                destino,
                ", ".join(sorted(validos)),
            )

    return mapa





def _normalizar(texto: str) -> str:
    """Minusculas y sin acentos, para comparar sin depender de la tilde."""
    sin_tilde = unicodedata.normalize("NFKD", texto)
    sin_tilde = "".join(c for c in sin_tilde if not unicodedata.combining(c))
    return sin_tilde.lower()


def _texto_clinico(datos: ExtractedData) -> str:
    """Concatena los campos donde puede aparecer un hallazgo critico."""
    partes = [
        datos.diagnosis,
        datos.findings,
        datos.conclusion,
        datos.study,
        datos.procedure,
    ]
    return " ".join(p for p in partes if p)


def decidir_enrutamiento(
    documento_id: str,
    clasificacion: ClassificationResult,
    datos: ExtractedData,
    canal_origen: str,
    umbral_confianza: float | None = None,
    documento: DocumentoNormalizado | None = None,
    llm: object | None = None,
    especifico: object | None = None,
    revisado_por_humano: bool = False,
) -> tuple[NivelPrioridad, DecisionEnrutamientoContrato, StatusTriaje]:
    """Decide prioridad, destino y estado del triaje.

    Devuelve la terna que la capa de serializacion necesita para armar la
    respuesta del contrato. No toca el almacenamiento ni llama al modelo: es
    una funcion pura, y por eso se puede probar exhaustivamente.
    """
    # La deteccion de urgencia mira el documento ORIGINAL, no solo los campos
    # extraidos. Una receta no tiene hallazgos ni conclusion, asi que el texto
    # reconstruido quedaba vacio y el modelo, forzado a opinar sobre la nada,
    # respondia "urgente". Los campos extraidos quedan como respaldo para
    # cuando no hay documento (por ejemplo al llamar al grafo desde una
    # prueba).
    # El umbral llega por parametro solo en las pruebas y en los scripts de
    # evaluacion. En la aplicacion llega None y se lee del archivo, para que
    # un cambio desde la pantalla valga desde el documento siguiente.
    if umbral_confianza is None:
        umbral_confianza = umbral_configurado()

    texto = (documento.texto if documento else "") or _texto_clinico(datos)
    canal_prioritario = _normalizar(canal_origen) in canales_prioritarios()
    nombre_paciente = datos.patient.name or "paciente sin identificar"

    # ---- 1. Urgencia. Corre primero y gana sobre todo lo demas. -----------
    # Doble via: lista de terminos y modelo. Basta con que UNA diga urgente.
    # Medido sobre 95 frases: la lista sola dejaba escapar 28 de 30 cuadros
    # descritos sin nombrar la patologia; con las dos vias, ninguno.
    urgencia = detectar_urgencia(texto, llm=llm)

    if urgencia.es_urgente:
        return (
            "Urgente",
            DecisionEnrutamientoContrato(
                destino_principal="Cola_Emergencia_Medica",
                requiere_auditoria_humana=False,
                justificacion_enrutamiento=(
                    f"Hallazgo critico detectado (via: {urgencia.via}). "
                    f"{urgencia.explicacion()} Se prioriza la atencion "
                    "inmediata por encima de la ruta habitual del tipo de "
                    "documento."
                ),
                notificacion_generada=NotificacionContrato(
                    canal="Alerta_Guardia_Medica",
                    mensaje=(
                        f"ALERTA URGENTE: hallazgo critico en el documento "
                        f"{documento_id} del paciente {nombre_paciente}. "
                        "Requiere revision clinica inmediata."
                    ),
                ),
            ),
            "procesado",
        )

    # ---- 2. Transcripcion con partes ilegibles. ---------------------------
    # Va despues de la urgencia (un hallazgo critico legible se atiende aunque
    # el resto del documento este borroso) y antes de la ruta por tipo: una
    # receta con la dosis ilegible NO puede ir a farmacia sola.
    #
    # No se aplica a un caso que ya paso por el panel. La regla existe para
    # que un humano mire el documento; el original conserva sus marcas de
    # [ilegible] para siempre, asi que volver a aplicarla despues de que lo
    # miro deja el caso girando en revision sin salida posible. Lo que falte
    # de verdad lo sigue atajando el paso 6, que mira los campos.
    if (
        not revisado_por_humano
        and documento is not None
        and MARCA_ILEGIBLE in documento.texto
    ):
        return (
            "Prioritario" if canal_prioritario else "Rutina",
            DecisionEnrutamientoContrato(
                destino_principal="Cola_Revision_Humana",
                requiere_auditoria_humana=True,
                justificacion_enrutamiento=(
                    "La transcripcion del documento dejo partes ilegibles. Se "
                    "deriva a un auditor humano para que complete los datos "
                    "faltantes antes de cualquier accion."
                ),
                notificacion_generada=None,
            ),
            "derivado_revision_humana",
        )

    # ---- 3. Documento desconocido o ilegible. -----------------------------
    # Va a la Cola de Revision Humana, no a la de Emergencia. No poder
    # clasificar un documento no es evidencia de que sea urgente: la urgencia
    # ya se evaluo en el paso 1 sobre el texto que si se pudo leer. Mandar cada
    # fax borroso a la cola de emergencia la llenaria de casos que no lo son, y
    # una cola de emergencia saturada deja de mirarse con urgencia.
    #
    # Se marca como Prioritario para que quede arriba en la bandeja de
    # revision, y requiere_auditoria_humana en True: nunca se aprueba solo.
    if clasificacion.document_type == "desconocido":
        return (
            "Prioritario",
            DecisionEnrutamientoContrato(
                destino_principal="Cola_Revision_Humana",
                requiere_auditoria_humana=True,
                justificacion_enrutamiento=(
                    "No se pudo determinar el tipo de documento. Se escala a "
                    "un auditor humano en lugar de asignar una ruta "
                    "automatica, con prioridad alta dentro de la cola de "
                    "revision."
                ),
                notificacion_generada=None,
            ),
            "derivado_revision_humana",
        )

    # ---- 4. Confianza por debajo del umbral. ------------------------------
    if clasificacion.confidence < umbral_confianza:
        return (
            "Prioritario" if canal_prioritario else "Rutina",
            DecisionEnrutamientoContrato(
                destino_principal="Cola_Revision_Humana",
                requiere_auditoria_humana=True,
                justificacion_enrutamiento=(
                    f"La confianza de la clasificacion ({clasificacion.confidence:.2f}) "
                    f"esta por debajo del umbral configurado ({umbral_confianza:.2f}). "
                    "Se deriva a un auditor humano antes de cualquier accion."
                ),
                notificacion_generada=None,
            ),
            "derivado_revision_humana",
        )

    # ---- 5. Destino segun el tipo. Un tipo sin ruta escala. ---------------
    destino = destinos_configurados().get(clasificacion.document_type)

    if destino is None:
        # Categoria nueva sin ruta asignada. No se inventa un destino: se
        # escala. Esto pasa si alguien agrega un tipo al Literal y se olvida
        # de mapearlo aca.
        return (
            "Prioritario",
            DecisionEnrutamientoContrato(
                destino_principal="Cola_Revision_Humana",
                requiere_auditoria_humana=True,
                justificacion_enrutamiento=(
                    f"El tipo de documento '{clasificacion.document_type}' no "
                    "tiene ruta de enrutamiento asignada. Se escala a revision "
                    "humana en lugar de elegir un destino arbitrario."
                ),
                notificacion_generada=None,
            ),
            "derivado_revision_humana",
        )

    # ---- 6. Datos minimos para actuar sin un humano. ----------------------
    # Un documento solo sigue su ruta automatica si trae lo que su destino
    # necesita para actuar. Una receta sin matricula no puede ir sola a
    # farmacia: nadie puede verificar que la firmo un profesional habilitado.
    faltantes = campos_faltantes(clasificacion.document_type, datos)

    if faltantes:
        detalle = "; ".join(f"falta {f.campo} ({f.motivo})" for f in faltantes)

        return (
            "Prioritario" if canal_prioritario else "Rutina",
            DecisionEnrutamientoContrato(
                destino_principal="Cola_Revision_Humana",
                requiere_auditoria_humana=True,
                justificacion_enrutamiento=(
                    "Al documento le faltan datos que su destino necesita para "
                    f"actuar: {detalle}. Se deriva a un auditor humano para que "
                    "los complete; los campos ausentes quedan en null."
                ),
                notificacion_generada=None,
            ),
            "derivado_revision_humana",
        )

    # ---- 7. Receta controlada: exige verificar la firma. ------------------
    # Que sea controlada NO la vuelve urgente: la vuelve no automatizable.
    if es_receta_controlada(especifico):
        return (
            "Prioritario",
            DecisionEnrutamientoContrato(
                destino_principal="Cola_Revision_Humana",
                requiere_auditoria_humana=True,
                justificacion_enrutamiento=(
                    "Receta controlada: exige verificar la firma del profesional "
                    "antes de dispensar. Se deriva a revision humana. Ser "
                    "controlada no la convierte en una emergencia."
                ),
                notificacion_generada=None,
            ),
            "derivado_revision_humana",
        )

    # ---- 8. Certificado para junta evaluadora. ----------------------------
    # Tiene consecuencias administrativas y previsionales, y el proyecto aun
    # no acordo un destino propio. Hasta entonces lo mira una persona.
    if clasificacion.document_type == "certificado_medico" and es_certificado_de_junta(
        texto
    ):
        return (
            "Prioritario",
            DecisionEnrutamientoContrato(
                destino_principal="Cola_Revision_Humana",
                requiere_auditoria_humana=True,
                justificacion_enrutamiento=(
                    "Certificado destinado a una junta evaluadora. Todavia no "
                    "hay un destino acordado para este tipo, asi que se deriva "
                    "a revision humana en lugar de archivarlo solo."
                ),
                notificacion_generada=None,
            ),
            "derivado_revision_humana",
        )

    # ---- 9. Ruta normal por tipo de documento. ----------------------------
    return (
        "Prioritario" if canal_prioritario else "Rutina",
        DecisionEnrutamientoContrato(
            destino_principal=destino,
            requiere_auditoria_humana=False,
            justificacion_enrutamiento=(
                f"Documento clasificado como '{clasificacion.document_type}' con "
                f"confianza {clasificacion.confidence:.2f}, por encima del umbral "
                f"({umbral_confianza:.2f}). Sin hallazgos criticos y con los datos "
                "minimos completos. Se deriva al destino habitual para este tipo."
            ),
            notificacion_generada=None,
        ),
        "procesado",
    )
