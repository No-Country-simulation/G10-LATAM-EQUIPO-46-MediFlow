import json

import pytest
from pydantic import ValidationError

from src.mediflow_agent.schemas.models import (
    AgentResult,
    ClassificationResult,
    Doctor,
    ExtractedData,
    Patient,
)


def _resultado_valido() -> AgentResult:
    return AgentResult(
        document_id="DOC-CLIN-2026-8942",
        classification=ClassificationResult(
            document_type="informe_estudio_diagnostico",
            specialty="Radiologia",
            confidence=0.99,
        ),
        extracted_data=ExtractedData(
            patient=Patient(name="Carlos Eduardo Mendes", age=52),
            doctor=Doctor(name="Dra. Renata Silveira", license_number="145892"),
            study="Tomografia de torax con contraste",
        ),
    )


def test_agent_result_se_construye_con_las_partes_validadas():
    result = _resultado_valido()

    assert result.document_id == "DOC-CLIN-2026-8942"
    assert result.classification.document_type == "informe_estudio_diagnostico"
    assert result.extracted_data.patient.age == 52


def test_agent_result_rechaza_un_tipo_de_documento_inexistente():
    # La salida final tiene que validarse igual que sus partes. Si alguien
    # arma el resultado a mano con una categoria que no existe, tiene que
    # fallar aca y no llegar a la API.
    with pytest.raises(ValidationError):
        AgentResult(
            document_id="DOC-1",
            classification=ClassificationResult(
                document_type="picrisis",
                confidence=0.9,
            ),
            extracted_data=ExtractedData(),
        )


def test_agent_result_rechaza_una_confianza_fuera_de_rango():
    with pytest.raises(ValidationError):
        AgentResult(
            document_id="DOC-1",
            classification=ClassificationResult(
                document_type="epicrisis",
                confidence=1.4,
            ),
            extracted_data=ExtractedData(),
        )


def test_los_campos_ausentes_van_en_null_y_no_se_omiten():
    # Regla del proyecto: el consumidor tiene que poder distinguir
    # "no estaba en el documento" de "no lo supimos leer". Si el campo
    # desapareciera del JSON, esa distincion se pierde.
    result = AgentResult(
        document_id="DOC-1",
        classification=ClassificationResult(
            document_type="desconocido",
            confidence=0.2,
        ),
        extracted_data=ExtractedData(),
    )

    payload = json.loads(result.model_dump_json())

    assert "suggested_icd10" in payload["extracted_data"]
    assert payload["extracted_data"]["suggested_icd10"] is None
    assert payload["extracted_data"]["patient"]["name"] is None
    assert payload["classification"]["specialty"] is None


def test_el_json_conserva_los_acentos_sin_escapar():
    # La salida se lee en consola y se guarda en OCI. Un nombre con acento
    # escapado como é es ilegible para el auditor humano.
    result = AgentResult(
        document_id="DOC-1",
        classification=ClassificationResult(
            document_type="receta_medica",
            confidence=0.9,
        ),
        extracted_data=ExtractedData(
            patient=Patient(name="José Ramírez"),
        ),
    )

    crudo = result.model_dump_json()

    assert "José Ramírez" in crudo
