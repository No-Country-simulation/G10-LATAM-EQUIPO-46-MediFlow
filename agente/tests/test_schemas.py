import pytest
from pydantic import ValidationError

from src.mediflow_agent.schemas.models import (
    ClassificationResult,
    ExtractedData,
)


def test_classification_confidence_valid():

    result = ClassificationResult(
        document_type="receta_medica",
        specialty="medicina_general",
        confidence=0.95,
    )

    assert result.document_type == "receta_medica"
    assert 0 <= result.confidence <= 1


def test_classification_confidence_invalid():

    with pytest.raises(ValidationError):

        ClassificationResult(
            document_type="receta_medica",
            specialty=None,
            confidence=1.5,
        )


def test_extracted_data_allows_missing_values():

    result = ExtractedData()

    assert result.patient.name is None
    assert result.doctor.name is None
    assert result.diagnosis is None