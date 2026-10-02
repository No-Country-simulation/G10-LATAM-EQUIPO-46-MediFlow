"""Pruebas de la extraccion guiada por tipo de documento (tarea 2.2).

El modelo se sustituye por un doble: no llaman a Gemini ni consumen cuota.
"""

import pytest

from mediflow_agent.extraction.esquemas_por_tipo import (
    ESQUEMA_POR_TIPO,
    DatosInforme,
    DatosReceta,
    Medicamento,
    a_datos_comunes,
)
from mediflow_agent.extraction.extractor_por_tipo import ExtractorPorTipo
from mediflow_agent.schemas.models import Doctor, Patient


class LlmDoble:
    """Doble del modelo. Devuelve lo que se le indique, sin llamar a nadie."""

    def __init__(self, respuesta):
        self.respuesta = respuesta
        self.prompts: list[str] = []
        self.esquemas: list[type] = []

    def with_structured_output(self, esquema):
        self.esquemas.append(esquema)
        return self

    def invoke(self, prompt):
        self.prompts.append(prompt)
        return self.respuesta


# --- Esquemas -------------------------------------------------------------

def test_hay_un_esquema_por_cada_tipo_clasificable():
    from typing import get_args

    from mediflow_agent.schemas.models import DocumentType

    tipos = set(get_args(DocumentType)) - {"desconocido"}

    assert set(ESQUEMA_POR_TIPO) == tipos, (
        "cada tipo clasificable necesita su esquema de extraccion"
    )


def test_un_medicamento_se_aplana_conservando_la_dosis():
    m = Medicamento(
        nombre="Amoxicilina", dosis="500 mg", frecuencia="cada 8 horas", duracion="por 7 dias"
    )

    assert m.como_texto() == "Amoxicilina 500 mg cada 8 horas por 7 dias"


def test_un_medicamento_sin_dosis_no_la_inventa():
    m = Medicamento(nombre="Metformina")

    assert m.dosis is None
    assert m.como_texto() == "Metformina"


def test_los_datos_de_receta_se_convierten_a_la_forma_comun():
    receta = DatosReceta(
        paciente=Patient(name="Marta Quintana", age=34),
        medico=Doctor(name="Dra. Liliana Ferreyra", license_number="38421"),
        medicamentos=[
            Medicamento(nombre="Amoxicilina", dosis="500 mg", frecuencia="cada 8 horas"),
            Medicamento(nombre="Ibuprofeno", dosis="400 mg"),
        ],
    )

    comunes = a_datos_comunes(receta)

    assert comunes.patient.name == "Marta Quintana"
    assert comunes.doctor.license_number == "38421"
    assert comunes.medications == [
        "Amoxicilina 500 mg cada 8 horas",
        "Ibuprofeno 400 mg",
    ]
    # Una receta no tiene hallazgos: el campo comun queda en null, no vacio.
    assert comunes.findings is None
    assert comunes.study is None


def test_una_receta_sin_medicamentos_deja_el_campo_en_null():
    # Lista vacia no es lo mismo que [] en la salida: el contrato pide null
    # cuando no hay dato.
    comunes = a_datos_comunes(DatosReceta())

    assert comunes.medications is None


# --- Extractor ------------------------------------------------------------

def test_cada_tipo_usa_su_propio_esquema():
    llm = LlmDoble(DatosReceta())
    ExtractorPorTipo(llm=llm).extract("texto", "receta_medica")

    assert llm.esquemas == [DatosReceta]


def test_el_prompt_cambia_segun_el_tipo():
    llm = LlmDoble(DatosInforme())
    ExtractorPorTipo(llm=llm).extract("texto", "informe_estudio_diagnostico")

    prompt = llm.prompts[0]
    assert "INFORME DE ESTUDIO DIAGNOSTICO" in prompt
    assert "no conviertas" in prompt.lower() or "No conviertas" in prompt


def test_todos_los_prompts_llevan_las_reglas_que_no_se_negocian():
    for tipo, esquema in ESQUEMA_POR_TIPO.items():
        llm = LlmDoble(esquema())
        ExtractorPorTipo(llm=llm).extract("texto", tipo)

        prompt = llm.prompts[0]
        assert "usa null" in prompt, f"{tipo}: falta la regla del null"
        assert "[ilegible]" in prompt, f"{tipo}: falta la regla de lo ilegible"


def test_un_tipo_desconocido_no_extrae_nada_y_avisa():
    llm = LlmDoble(DatosReceta())
    resultado = ExtractorPorTipo(llm=llm).extract("texto", "desconocido")

    assert llm.prompts == [], "no se debe llamar al modelo sin esquema"
    assert resultado.datos.patient.name is None
    assert resultado.avisos
    assert "revision humana" in resultado.avisos[0]


# --- Verificacion del CIE-10 dentro de la extraccion ----------------------

def test_un_cie10_valido_sobrevive():
    llm = LlmDoble(DatosInforme(cie10_sugerido="I26.9"))
    resultado = ExtractorPorTipo(llm=llm).extract("t", "informe_estudio_diagnostico")

    assert resultado.datos.suggested_icd10 == "I26.9"
    assert resultado.avisos == ()


def test_un_cie10_inventado_se_descarta_y_se_avisa():
    # El caso que esto ataja: forma perfecta, categoria inexistente.
    llm = LlmDoble(DatosInforme(cie10_sugerido="I29.4"))
    resultado = ExtractorPorTipo(llm=llm).extract("t", "informe_estudio_diagnostico")

    assert resultado.datos.suggested_icd10 is None
    assert resultado.avisos and "no existe" in resultado.avisos[0]


def test_un_cie10_mal_escrito_se_normaliza():
    llm = LlmDoble(DatosInforme(cie10_sugerido="i269"))
    resultado = ExtractorPorTipo(llm=llm).extract("t", "informe_estudio_diagnostico")

    assert resultado.datos.suggested_icd10 == "I26.9"


def test_sin_cie10_no_se_genera_un_aviso_innecesario():
    llm = LlmDoble(DatosInforme())
    resultado = ExtractorPorTipo(llm=llm).extract("t", "informe_estudio_diagnostico")

    assert resultado.datos.suggested_icd10 is None
    assert resultado.avisos == ()


@pytest.mark.parametrize("tipo", ["orden_procedimiento", "certificado_medico"])
def test_los_tipos_sin_cie10_no_lo_reportan(tipo):
    llm = LlmDoble(ESQUEMA_POR_TIPO[tipo]())
    resultado = ExtractorPorTipo(llm=llm).extract("t", tipo)

    assert resultado.datos.suggested_icd10 is None
