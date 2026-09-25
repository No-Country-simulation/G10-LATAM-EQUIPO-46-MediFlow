"""Contrato publico de la API de triaje.

El enunciado del hackathon fija la forma exacta del JSON de entrada y de salida,
con los nombres de campo en espanol (`documento_id`, `clasificacion`,
`datos_extraidos`...). Los modelos internos de `schemas/models.py` estan en
ingles, que es la convencion correcta para el codigo.

Este modulo es el puente entre los dos. Traduce en el borde, no en el nucleo:

  - el modulo del agente puede evolucionar sus modelos sin romper la API;
  - el contrato publico vive en un solo archivo, facil de auditar contra el PDF;
  - nadie tiene que renombrar el trabajo ya hecho.

La definicion en prosa, con los valores admitidos de cada campo, esta en
`docs/CONTRATO.md`. Si este archivo y ese documento no coinciden, manda el
documento.
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field

from mediflow_agent.schemas.models import AgentResult, DocumentType


# ---------------------------------------------------------------------------
# Vocabularios cerrados del contrato
# ---------------------------------------------------------------------------

StatusTriaje = Literal[
    "procesado",
    "derivado_revision_humana",
    "error",
]

NivelPrioridad = Literal[
    "Rutina",
    "Prioritario",
    "Urgente",
]

DestinoEnrutamiento = Literal[
    "Cola_Emergencia_Medica",
    "Auditoria_Autorizaciones",
    "Farmacia_Hospitalaria",
    "Historia_Clinica_Electronica",
    "Cola_Revision_Humana",
]

StatusBackup = Literal["exito", "fallo"]


# Los slugs internos no son nombres presentables. El contrato publica etiquetas
# legibles porque es lo que se muestra en el panel de auditoria y en la demo.
#
# Nota abierta: el enunciado distingue "Informe de Estudio por Imagenes" de un
# informe de laboratorio, pero la taxonomia interna todavia tiene una sola
# categoria para los dos. Hasta que se separen (tarea 2.2), ambos salen como
# "Informe de Estudio Diagnostico". Preferimos una etiqueta honesta y general
# antes que afirmar "por Imagenes" sobre un informe de laboratorio.
TIPO_DOCUMENTO_PUBLICO: dict[str, str] = {
    "receta_medica": "Receta Medica",
    "informe_estudio_diagnostico": "Informe de Estudio Diagnostico",
    "orden_procedimiento": "Orden de Solicitud de Procedimiento",
    "epicrisis": "Epicrisis",
    "certificado_medico": "Certificado Medico",
    "desconocido": "Desconocido",
}


# ---------------------------------------------------------------------------
# Entrada
# ---------------------------------------------------------------------------

class SolicitudTriaje(BaseModel):
    """Cuerpo de `POST /triaje`."""

    documento_id: str = Field(
        description="Identificador que asigna el sistema emisor."
    )

    tipo_archivo: Literal["PDF", "IMAGEN", "TEXTO", "JSON"] = Field(
        description="Formato en el que llega el documento."
    )

    documento_texto: Optional[str] = Field(
        default=None,
        description=(
            "Contenido cuando el tipo es texto. Para PDF o imagen el binario "
            "llega por otra via y este campo puede venir vacio."
        ),
    )

    canal_origen: str = Field(
        description=(
            "De donde llego el documento. Alimenta la deteccion de urgencia: "
            "'Guardia_Emergencias' es una senal de prioridad, no una prueba."
        )
    )


# ---------------------------------------------------------------------------
# Salida
# ---------------------------------------------------------------------------

class PacienteContrato(BaseModel):
    nombre: Optional[str] = None
    edad: Optional[int] = None


class MedicoSolicitanteContrato(BaseModel):
    nombre: Optional[str] = None
    matricula: Optional[str] = None


class ClasificacionContrato(BaseModel):
    tipo_documento: str
    especialidad: Optional[str] = None
    nivel_prioridad: NivelPrioridad
    score_confianza_clasificacion: float = Field(ge=0, le=1)


class DatosExtraidosContrato(BaseModel):
    paciente: PacienteContrato
    medico_solicitante: MedicoSolicitanteContrato
    estudio_realizado: Optional[str] = None
    diagnostico_principal: Optional[str] = None
    cie10_sugerido: Optional[str] = None
    medicamentos: Optional[list[str]] = None


class NotificacionContrato(BaseModel):
    canal: str
    mensaje: str


class DecisionEnrutamientoContrato(BaseModel):
    destino_principal: DestinoEnrutamiento

    requiere_auditoria_humana: bool

    justificacion_enrutamiento: str = Field(
        min_length=1,
        description=(
            "Por que se tomo esta ruta. Nunca viene vacio: es lo que demuestra "
            "que el agente razona y no solo extrae, y es lo que se muestra en "
            "pantalla al auditor."
        ),
    )

    notificacion_generada: Optional[NotificacionContrato] = Field(
        default=None,
        description="Null cuando la ruta no genera alerta.",
    )


class AlmacenamientoOciContrato(BaseModel):
    bucket: str
    ruta_objeto: str
    status_backup: StatusBackup


class RespuestaTriaje(BaseModel):
    """Respuesta de `POST /triaje`, tal como la fija el enunciado."""

    status: StatusTriaje
    documento_id: str
    clasificacion: ClasificacionContrato
    datos_extraidos: DatosExtraidosContrato
    decision_enrutamiento: DecisionEnrutamientoContrato
    almacenamiento_oci: AlmacenamientoOciContrato


# ---------------------------------------------------------------------------
# Traduccion desde el modelo interno
# ---------------------------------------------------------------------------

def tipo_documento_publico(document_type: DocumentType) -> str:
    """Etiqueta legible de una categoria interna.

    Cae en "Desconocido" ante un slug que no conoce, en lugar de fallar: una
    categoria nueva sin etiqueta es un problema de presentacion, y no una razon
    para tumbar un triaje que ya se resolvio.
    """
    return TIPO_DOCUMENTO_PUBLICO.get(document_type, "Desconocido")


def a_respuesta_triaje(
    resultado: AgentResult,
    nivel_prioridad: NivelPrioridad,
    decision_enrutamiento: DecisionEnrutamientoContrato,
    almacenamiento_oci: AlmacenamientoOciContrato,
    status: StatusTriaje = "procesado",
) -> RespuestaTriaje:
    """Traduce el resultado interno del agente al contrato publico.

    La prioridad, el enrutamiento y el almacenamiento llegan como argumentos
    porque los calculan otras piezas (tareas 3.1, 3.2 y 1.2). Esta funcion no
    decide nada: solo cambia la forma. Mantenerla sin logica es lo que permite
    probarla exhaustivamente sin llamar al modelo ni a OCI.
    """
    clasificacion_interna = resultado.classification
    datos_internos = resultado.extracted_data

    return RespuestaTriaje(
        status=status,
        documento_id=resultado.document_id,
        clasificacion=ClasificacionContrato(
            tipo_documento=tipo_documento_publico(
                clasificacion_interna.document_type
            ),
            especialidad=clasificacion_interna.specialty,
            nivel_prioridad=nivel_prioridad,
            score_confianza_clasificacion=clasificacion_interna.confidence,
        ),
        datos_extraidos=DatosExtraidosContrato(
            paciente=PacienteContrato(
                nombre=datos_internos.patient.name,
                edad=datos_internos.patient.age,
            ),
            medico_solicitante=MedicoSolicitanteContrato(
                nombre=datos_internos.doctor.name,
                matricula=datos_internos.doctor.license_number,
            ),
            estudio_realizado=datos_internos.study,
            diagnostico_principal=datos_internos.diagnosis,
            cie10_sugerido=datos_internos.suggested_icd10,
            medicamentos=datos_internos.medications,
        ),
        decision_enrutamiento=decision_enrutamiento,
        almacenamiento_oci=almacenamiento_oci,
    )
