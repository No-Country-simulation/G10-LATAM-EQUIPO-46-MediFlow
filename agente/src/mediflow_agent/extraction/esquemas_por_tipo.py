"""Esquemas de extraccion especificos por tipo de documento.

Hasta ahora habia un unico esquema para todo. El problema de eso no es que sea
feo: es que al modelo se le pide lo mismo para una receta que para un informe
radiologico, y entonces o se le piden campos que no existen en el documento
—lo que empuja a inventar— o se dejan afuera campos que si existen.

De una receta importan los medicamentos con su dosis y frecuencia. De un
informe importan los hallazgos y la conclusion. De una orden, el procedimiento
solicitado y si es urgente. Cada tipo tiene su esquema y su prompt.

Todos los esquemas terminan convertidos a `ExtractedData`, que es la forma
comun que consume el resto del sistema. La riqueza extra (la dosis separada de
la frecuencia, por ejemplo) queda disponible para quien la quiera usar en el
panel de auditoria.
"""

from typing import Optional

from pydantic import BaseModel, Field

from mediflow_agent.schemas.models import Doctor, ExtractedData, Patient


class Medicamento(BaseModel):
    """Un farmaco prescripto, con lo que haga falta para dispensarlo.

    La dosis va separada del nombre a proposito: es el dato que mas importa
    verificar y el que mas caro sale leer mal.
    """

    nombre: str = Field(description="Nombre del farmaco tal como figura.")

    dosis: Optional[str] = Field(
        default=None,
        description=(
            "Dosis con su unidad, por ejemplo '500 mg'. Null si no figura o "
            "si es ilegible. NUNCA deducirla del nombre comercial."
        ),
    )

    frecuencia: Optional[str] = Field(
        default=None,
        description="Cada cuanto se toma, por ejemplo 'cada 8 horas'. Null si no figura.",
    )

    duracion: Optional[str] = Field(
        default=None,
        description="Por cuanto tiempo, por ejemplo 'por 7 dias'. Null si no figura.",
    )

    def como_texto(self) -> str:
        partes = [self.nombre, self.dosis, self.frecuencia, self.duracion]
        return " ".join(p for p in partes if p)


class _Base(BaseModel):
    """Campos que todo documento clinico comparte."""

    paciente: Patient = Field(default_factory=Patient)
    medico: Doctor = Field(default_factory=Doctor)


class DatosReceta(_Base):
    medicamentos: list[Medicamento] = Field(
        default_factory=list,
        description="Farmacos prescriptos. Lista vacia si no se puede leer ninguno.",
    )

    diagnostico: Optional[str] = Field(
        default=None, description="Diagnostico que justifica la prescripcion, si figura."
    )

    es_receta_controlada: bool = Field(
        default=False,
        description=(
            "True solo si el documento dice explicitamente que es controlada, "
            "o si prescribe un opioide o psicotropico."
        ),
    )


class DatosInforme(_Base):
    estudio: Optional[str] = Field(default=None, description="Estudio realizado.")
    indicacion: Optional[str] = Field(default=None, description="Motivo del estudio.")
    hallazgos: Optional[str] = Field(default=None, description="Hallazgos descritos.")
    conclusion: Optional[str] = Field(default=None, description="Conclusion del informe.")

    diagnostico: Optional[str] = Field(
        default=None, description="Diagnostico explicito. Null si solo hay sospecha."
    )

    cie10_sugerido: Optional[str] = Field(
        default=None,
        description=(
            "Codigo CIE-10 que corresponde al cuadro descrito. El campo es una "
            "SUGERENCIA, no un diagnostico: si la conclusion nombra una "
            "condicion clinica, sugeri su codigo aunque el informe diga "
            "'compatible con' o 'sospecha de'. Null solo cuando el documento "
            "no describe ninguna condicion codificable. Nunca inventes un "
            "codigo: si no sabes cual es, null."
        ),
    )


class DatosOrden(_Base):
    procedimiento: Optional[str] = Field(
        default=None, description="Procedimiento o estudio solicitado."
    )

    diagnostico: Optional[str] = Field(
        default=None, description="Hipotesis diagnostica que motiva la solicitud."
    )

    caracter: Optional[str] = Field(
        default=None,
        description="Caracter de la solicitud tal como figura: urgente, programado, ambulatorio.",
    )


class DatosEpicrisis(_Base):
    diagnostico: Optional[str] = Field(default=None, description="Diagnostico de egreso.")
    evolucion: Optional[str] = Field(default=None, description="Evolucion durante la internacion.")
    conclusion: Optional[str] = Field(default=None, description="Indicacion al alta.")

    medicamentos: list[Medicamento] = Field(
        default_factory=list, description="Medicacion indicada al alta."
    )

    cie10_sugerido: Optional[str] = Field(
        default=None,
        description=(
            "Codigo CIE-10 del diagnostico de egreso, como sugerencia. Null si "
            "no hay un diagnostico codificable. Nunca inventes un codigo."
        ),
    )


class DatosCertificado(_Base):
    diagnostico: Optional[str] = Field(default=None, description="Motivo del certificado.")

    conclusion: Optional[str] = Field(
        default=None, description="Lo que se certifica: reposo, aptitud, constancia."
    )


ESQUEMA_POR_TIPO: dict[str, type[BaseModel]] = {
    "receta_medica": DatosReceta,
    "informe_estudio_diagnostico": DatosInforme,
    "orden_procedimiento": DatosOrden,
    "epicrisis": DatosEpicrisis,
    "certificado_medico": DatosCertificado,
}


def a_datos_comunes(especifico: BaseModel) -> ExtractedData:
    """Convierte cualquier esquema por tipo a la forma comun del sistema.

    Los medicamentos se aplanan a texto porque `ExtractedData.medications` es
    una lista de cadenas. No se pierde informacion: el texto conserva dosis y
    frecuencia, y el objeto rico sigue disponible para quien lo necesite.
    """
    obtener = lambda campo: getattr(especifico, campo, None)  # noqa: E731

    medicamentos = obtener("medicamentos") or []

    return ExtractedData(
        patient=especifico.paciente,
        doctor=especifico.medico,
        study=obtener("estudio"),
        diagnosis=obtener("diagnostico"),
        findings=obtener("hallazgos"),
        conclusion=obtener("conclusion"),
        medications=[m.como_texto() for m in medicamentos] or None,
        procedure=obtener("procedimiento"),
        suggested_icd10=obtener("cie10_sugerido"),
    )
