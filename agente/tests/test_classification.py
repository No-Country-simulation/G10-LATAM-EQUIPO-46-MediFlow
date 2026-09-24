import pytest

from src.mediflow_agent.schemas.models import ClassificationResult


@pytest.mark.parametrize(
    "document_type",
    [
        "receta_medica",
        "informe_estudio_diagnostico",
        "orden_procedimiento",
        "epicrisis",
        "certificado_medico",
        "desconocido",
    ],
)
def test_supported_document_types(document_type):

    result = ClassificationResult(
        document_type=document_type,
        confidence=0.9,
    )

    assert result.document_type == document_type