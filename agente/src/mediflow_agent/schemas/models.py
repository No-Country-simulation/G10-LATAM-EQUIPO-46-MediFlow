from typing import Literal, Optional
from pydantic import BaseModel, Field


DocumentType = Literal[
    "receta_medica",
    "informe_estudio_diagnostico",
    "orden_procedimiento",
    "epicrisis",
    "certificado_medico",
    "desconocido",
]


class Patient(BaseModel):
    name: Optional[str] = Field(
        default=None,
        description="Nombre completo del paciente. Null si no aparece."
    )

    age: Optional[int] = Field(
        default=None,
        description="Edad del paciente. Null si no aparece."
    )


class Doctor(BaseModel):
    # Se llama Doctor por compatibilidad con el contrato, pero representa al
    # profesional responsable del documento. Pedir literalmente "el médico"
    # dejaba sin profesional a una hoja de triaje firmada por el enfermero
    # evaluador, que es quien responde por ese documento.
    name: Optional[str] = Field(
        default=None,
        description=(
            "Nombre del profesional de salud responsable del documento. "
            "Preferí el médico que lo firma o lo solicita. Si el documento no "
            "menciona ningún médico pero sí otro profesional responsable (por "
            "ejemplo el enfermero que realiza un triaje), usá ese. Null si no "
            "aparece ninguno."
        )
    )

    license_number: Optional[str] = Field(
        default=None,
        description=(
            "Número de matrícula o registro profesional de esa misma persona. "
            "Null si no aparece. Nunca lo tomes de otro número del documento, "
            "como el código de registro del formulario o la identificación "
            "del paciente."
        )
    )


class ClassificationResult(BaseModel):
    document_type: DocumentType = Field(
        description="Tipo de documento identificado."
    )

    specialty: Optional[str] = Field(
        default=None,
        description="Especialidad médica si puede identificarse."
    )

    confidence: float = Field(
        ge=0,
        le=1,
        description="Confianza estimada de la clasificación entre 0 y 1."
    )


class ExtractedData(BaseModel):
    patient: Patient = Field(
        default_factory=Patient
    )

    doctor: Doctor = Field(
        default_factory=Doctor
    )

    study: Optional[str] = Field(
        default=None,
        description="Nombre del estudio o examen realizado."
    )

    diagnosis: Optional[str] = Field(
        default=None,
        description="Diagnóstico explícitamente mencionado en el documento."
    )

    findings: Optional[str] = Field(
        default=None,
        description="Hallazgos explícitamente mencionados."
    )

    conclusion: Optional[str] = Field(
        default=None,
        description="Conclusión del documento."
    )

    medications: Optional[list[str]] = Field(
        default=None,
        description="Medicamentos mencionados en el documento."
    )

    procedure: Optional[str] = Field(
        default=None,
        description="Procedimiento solicitado o realizado."
    )

    suggested_icd10: Optional[str] = Field(
        default=None,
        description=(
            "Código ICD-10 sugerido únicamente si existe evidencia "
            "suficiente y explícita. No representa un diagnóstico definitivo."
        )
    )


class AgentResult(BaseModel):
    document_id: str

    classification: ClassificationResult

    extracted_data: ExtractedData