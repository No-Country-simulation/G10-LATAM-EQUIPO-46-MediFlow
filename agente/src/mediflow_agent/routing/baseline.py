"""Enrutamiento de linea base.

ALCANCE. Esto NO es el grafo de decision definitivo. El grafo completo, con la
deteccion de urgencia por doble via y los umbrales configurables desde archivo,
son las tareas 3.1 y 3.2 de la semana 3.

Esta version existe porque el contrato del enunciado exige que la respuesta
traiga `decision_enrutamiento` con una justificacion no vacia: sin algo que
decida, el endpoint de la tarea 1.3 no puede devolver una respuesta valida.
Es deliberadamente simple y esta pensada para ser reemplazada entera.

Respeta las dos reglas que el proyecto no negocia:

  1. Ante duda, fallo del modelo o documento ilegible, el caso escala a una
     persona. Nunca hay aprobacion automatica por defecto.
  2. El sesgo es siempre a escalar. Ante dos lecturas posibles, se elige la que
     pone a un humano a mirar.

El peor fallo posible de este sistema es que un hallazgo urgente se clasifique
como rutina. Por eso la deteccion de urgencia corre ANTES que cualquier otra
regla y, cuando dispara, no hay ruta que la anule.
"""

import unicodedata

from mediflow_agent.config import ajuste

from mediflow_agent.ingestion.base import DocumentoNormalizado
from mediflow_agent.routing.urgencia import detectar as detectar_urgencia
from mediflow_agent.schemas.models import ClassificationResult, ExtractedData
from mediflow_agent.serialization.contract import (
    DecisionEnrutamientoContrato,
    DestinoEnrutamiento,
    NivelPrioridad,
    NotificacionContrato,
    StatusTriaje,
)

# Por debajo de esta confianza, el caso va a revision humana pase lo que pase.
# Es un valor propuesto, no medido: la calibracion con datos propios es la
# tarea 4.2. Configurable por entorno para poder moverlo sin tocar codigo.
UMBRAL_CONFIANZA = ajuste(
    "confianza", "umbral", 0.70, "MEDIFLOW_UMBRAL_CONFIANZA"
)

# Canales que, por si solos, elevan la prioridad. Que un documento venga de
# guardia es una senal, no una prueba: sube a Prioritario, no a Urgente.
CANALES_PRIORITARIOS = frozenset(
    ajuste(
        "urgencia",
        "canales_prioritarios",
        ["guardia_emergencias", "urgencias", "emergencias"],
    )
)

# Destino por tipo de documento, segun el grafo de decision del README.
# Marca que el transcriptor multimodal deja donde no pudo leer. Su presencia
# significa que hay un dato del documento que NADIE leyo: ni el modelo ni,
# todavia, una persona. En una receta puede ser la dosis.
MARCA_ILEGIBLE = "[ilegible]"

DESTINO_POR_TIPO: dict[str, DestinoEnrutamiento] = {
    "receta_medica": "Farmacia_Hospitalaria",
    "orden_procedimiento": "Auditoria_Autorizaciones",
    "informe_estudio_diagnostico": "Historia_Clinica_Electronica",
    "epicrisis": "Historia_Clinica_Electronica",
    "certificado_medico": "Historia_Clinica_Electronica",
}


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
    umbral_confianza: float = UMBRAL_CONFIANZA,
    documento: DocumentoNormalizado | None = None,
    llm: object | None = None,
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
    texto = (documento.texto if documento else "") or _texto_clinico(datos)
    canal_prioritario = _normalizar(canal_origen) in CANALES_PRIORITARIOS
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
    if documento is not None and MARCA_ILEGIBLE in documento.texto:
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

    # ---- 5. Ruta normal por tipo de documento. ----------------------------
    destino = DESTINO_POR_TIPO.get(clasificacion.document_type)

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

    return (
        "Prioritario" if canal_prioritario else "Rutina",
        DecisionEnrutamientoContrato(
            destino_principal=destino,
            requiere_auditoria_humana=False,
            justificacion_enrutamiento=(
                f"Documento clasificado como '{clasificacion.document_type}' con "
                f"confianza {clasificacion.confidence:.2f}, por encima del umbral "
                f"({umbral_confianza:.2f}). Sin hallazgos criticos en el texto. "
                f"Se deriva al destino habitual para este tipo de documento."
            ),
            notificacion_generada=None,
        ),
        "procesado",
    )
