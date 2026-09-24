from src.mediflow_agent.schemas.models import (
    Doctor,
    ExtractedData,
    Patient,
)


def test_patient_data():

    patient = Patient(
        name="Carlos Eduardo Mendes",
        age=52,
    )

    assert patient.name == "Carlos Eduardo Mendes"
    assert patient.age == 52


def test_doctor_data():

    doctor = Doctor(
        name="Dra. Renata Silveira",
    )

    assert doctor.name == "Dra. Renata Silveira"
    assert doctor.license_number is None


def test_extracted_data():

    data = ExtractedData(
        patient=Patient(
            name="Carlos Eduardo Mendes",
            age=52,
        ),
        doctor=Doctor(
            name="Dra. Renata Silveira",
        ),
        study="Tomografia de torax con contraste",
    )

    assert data.patient.name == "Carlos Eduardo Mendes"
    assert data.study == "Tomografia de torax con contraste"