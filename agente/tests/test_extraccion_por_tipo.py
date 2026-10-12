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
from mediflow_agent.schemas.models import Doctor, ExtractedData, Patient


class LlmDoble:
    """Doble del modelo. Devuelve lo que se le indique, sin llamar a nadie."""

    def __init__(self, respuesta, respuesta_generica=None):
        self.respuesta = respuesta
        self.respuesta_generica = respuesta_generica or ExtractedData()
        self.prompts: list[str] = []
        self.esquemas: list[type] = []

    def with_structured_output(self, esquema):
        self.esquemas.append(esquema)
        return self

    def invoke(self, prompt):
        self.prompts.append(prompt)

        # La via generica pide ExtractedData, no el esquema del tipo. Se le
        # responde con la forma que corresponde para que el doble siga
        # sirviendo cuando se dispara la red de seguridad.
        if self.esquemas[-1] is ExtractedData:
            return self.respuesta_generica

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
    llm = LlmDoble(DatosReceta(medicamentos=[Medicamento(nombre="Metformina")]))
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


def test_la_via_generica_lleva_las_mismas_reglas_que_la_via_por_tipo():
    # La primera version de la red no las llevaba, y la extraccion generica
    # invento lo que estas reglas prohiben: una dosis suelta en un documento
    # ilegible y un estudio sacado de un correo administrativo.
    llm = LlmDoble(DatosReceta())
    ExtractorPorTipo(llm=llm).extract("texto", "desconocido")

    prompt = llm.prompts[0]
    assert "[ilegible]" in prompt, "falta la regla de lo ilegible"
    assert "sin el nombre del farmaco" in prompt, "falta la regla del dato suelto"
    assert "administrativo" in prompt, "falta la regla del documento no clinico"


def test_un_tipo_desconocido_se_extrae_con_el_esquema_generico():
    # Antes no se extraia nada. El problema de eso: un documento fuera de la
    # taxonomia (una hoja de triaje, una interconsulta) salia con todos los
    # campos vacios aunque el texto los tuviera a la vista.
    llm = LlmDoble(
        DatosReceta(),
        respuesta_generica=ExtractedData(diagnosis="Sindrome coronario agudo"),
    )
    resultado = ExtractorPorTipo(llm=llm).extract("texto", "desconocido")

    assert llm.esquemas == [ExtractedData]
    assert resultado.datos.diagnosis == "Sindrome coronario agudo"
    assert "generico" in resultado.avisos[0]


def test_si_el_esquema_del_tipo_no_cosecha_nada_se_reintenta_sin_suponer_el_tipo():
    # El caso real: una hoja de triaje clasificada como epicrisis. Al prompt
    # de epicrisis se le pide el diagnostico "de egreso", que no existe, y el
    # modelo responde null a todo. La red lo rescata.
    llm = LlmDoble(
        ESQUEMA_POR_TIPO["epicrisis"](),
        respuesta_generica=ExtractedData(
            patient=Patient(name="Gomez Perez, Juan Carlos", age=45),
            diagnosis="Posible sindrome coronario agudo",
        ),
    )
    resultado = ExtractorPorTipo(llm=llm).extract("hoja de triaje", "epicrisis")

    assert resultado.datos.diagnosis == "Posible sindrome coronario agudo"
    assert resultado.datos.patient.age == 45
    assert "no corresponda" in resultado.avisos[0]
    assert llm.esquemas[-1] is ExtractedData


def test_si_el_esquema_del_tipo_cosecha_algo_no_se_vuelve_a_llamar_al_modelo():
    # La red no puede costar una llamada extra en el camino normal: la cuota
    # gratuita son 15 pedidos por minuto.
    llm = LlmDoble(DatosInforme(estudio="Angio-TC de torax"))
    resultado = ExtractorPorTipo(llm=llm).extract("t", "informe_estudio_diagnostico")

    assert len(llm.prompts) == 1
    assert resultado.datos.study == "Angio-TC de torax"
    assert resultado.avisos == ()


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
    llm = LlmDoble(DatosInforme(estudio="Radiografia de torax"))
    resultado = ExtractorPorTipo(llm=llm).extract("t", "informe_estudio_diagnostico")

    assert resultado.datos.suggested_icd10 is None
    assert resultado.avisos == ()


@pytest.mark.parametrize("tipo", ["orden_procedimiento", "certificado_medico"])
def test_los_tipos_sin_cie10_no_lo_reportan(tipo):
    llm = LlmDoble(ESQUEMA_POR_TIPO[tipo]())
    resultado = ExtractorPorTipo(llm=llm).extract("t", tipo)

    assert resultado.datos.suggested_icd10 is None
