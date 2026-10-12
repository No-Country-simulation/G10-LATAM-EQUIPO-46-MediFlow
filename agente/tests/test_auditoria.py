"""Pruebas del panel de auditoria humana (tarea 4.1).

Cierran el escenario 3 del enunciado: un documento derivado a revision
humana no se queda ahi. El auditor completa lo que faltaba, aprueba, y **el
agente vuelve a decidir** con los datos corregidos.
"""

import json

import pytest

from mediflow_agent.api.auditoria import Correcciones, ServicioAuditoria
from mediflow_agent.schemas.models import (
    AgentResult,
    ClassificationResult,
    Doctor,
    ExtractedData,
    Patient,
)
from mediflow_agent.serialization.contract import (
    AlmacenamientoOciContrato,
    DecisionEnrutamientoContrato,
    a_respuesta_triaje,
)
from mediflow_agent.storage.base import (
    PREFIJO_AUDITORIA,
    PREFIJO_RECIBIDOS,
    PREFIJO_RUTINA,
)
from mediflow_agent.storage.local import AlmacenamientoLocal

ORIGINAL = (
    "CONSULTORIO EXTERNO - RECETA MANUSCRITA\n"
    "Paciente: Rosa Mabel Aguero, 58 anos\n"
    "Rp/ Metformina [ilegible] mg - [ilegible] veces al dia\n"
    "Dr. Ernesto Caballero - MP [ilegible]"
)


def _guardar_caso_pendiente(almacen, documento_id="DOC-AMB-1"):
    """Deja en el almacen una receta derivada a revision humana."""
    respuesta = a_respuesta_triaje(
        resultado=AgentResult(
            document_id=documento_id,
            classification=ClassificationResult(
                document_type="receta_medica", specialty=None, confidence=0.95
            ),
            extracted_data=ExtractedData(
                patient=Patient(name="Rosa Mabel Aguero", age=58),
                doctor=Doctor(name="Dr. Ernesto Caballero"),
                medications=["Metformina"],
            ),
        ),
        nivel_prioridad="Rutina",
        decision_enrutamiento=DecisionEnrutamientoContrato(
            destino_principal="Cola_Revision_Humana",
            requiere_auditoria_humana=True,
            justificacion_enrutamiento="La transcripcion dejo partes ilegibles.",
        ),
        almacenamiento_oci=AlmacenamientoOciContrato(
            bucket="b", ruta_objeto=f"auditoria_humana/{documento_id}.json",
            status_backup="exito",
        ),
        status="derivado_revision_humana",
    )

    almacen.guardar_texto(
        PREFIJO_AUDITORIA, f"{documento_id}.json", respuesta.model_dump_json()
    )
    almacen.guardar_texto(PREFIJO_RECIBIDOS, f"{documento_id}.txt", ORIGINAL)


@pytest.fixture
def almacen(tmp_path):
    return AlmacenamientoLocal(tmp_path, nombre_bucket="bucket-de-prueba")


@pytest.fixture
def auditoria(almacen):
    _guardar_caso_pendiente(almacen)
    # Sin llm: la via por lista alcanza y las pruebas no consumen cuota.
    return ServicioAuditoria(almacen)


# --- bandeja --------------------------------------------------------------

def test_la_bandeja_muestra_el_caso_pendiente(auditoria):
    casos = auditoria.bandeja(PREFIJO_AUDITORIA)

    assert len(casos) == 1
    assert casos[0].documento_id == "DOC-AMB-1"
    assert casos[0].paciente == "Rosa Mabel Aguero"
    assert "ilegibles" in casos[0].justificacion


def test_la_bandeja_ordena_urgente_primero(almacen):
    # Es el unico lugar donde "Prioritario" cambia algo observable: el orden.
    for identificador, prioridad in (
        ("DOC-C", "Rutina"),
        ("DOC-A", "Urgente"),
        ("DOC-B", "Prioritario"),
    ):
        respuesta = a_respuesta_triaje(
            resultado=AgentResult(
                document_id=identificador,
                classification=ClassificationResult(
                    document_type="receta_medica", confidence=0.9
                ),
                extracted_data=ExtractedData(),
            ),
            nivel_prioridad=prioridad,
            decision_enrutamiento=DecisionEnrutamientoContrato(
                destino_principal="Cola_Revision_Humana",
                requiere_auditoria_humana=True,
                justificacion_enrutamiento="motivo",
            ),
            almacenamiento_oci=AlmacenamientoOciContrato(
                bucket="b", ruta_objeto="x", status_backup="exito"
            ),
            status="derivado_revision_humana",
        )
        almacen.guardar_texto(
            PREFIJO_AUDITORIA, f"{identificador}.json", respuesta.model_dump_json()
        )

    orden = [c.documento_id for c in ServicioAuditoria(almacen).bandeja()]

    assert orden == ["DOC-A", "DOC-B", "DOC-C"]


def test_una_bandeja_vacia_no_falla(almacen):
    assert ServicioAuditoria(almacen).bandeja(PREFIJO_RUTINA) == []


def test_el_panel_muestra_el_documento_original(auditoria):
    assert auditoria.original("DOC-AMB-1") == ORIGINAL


def test_un_documento_inexistente_devuelve_none(auditoria):
    assert auditoria.documento("NO-EXISTE") is None
    assert auditoria.aprobar("NO-EXISTE", Correcciones()) is None


# --- aprobacion: el escenario 3 del enunciado -----------------------------

def test_al_completar_la_dosis_y_la_matricula_el_documento_sigue_a_farmacia(
    auditoria, almacen
):
    nueva = auditoria.aprobar(
        "DOC-AMB-1",
        Correcciones(
            medico_matricula="41883",
            medicamentos=["Metformina 850 mg cada 12 horas"],
            auditor="Neri Ferreira",
        ),
    )

    assert nueva.decision_enrutamiento.destino_principal == "Farmacia_Hospitalaria"
    assert nueva.decision_enrutamiento.requiere_auditoria_humana is False
    assert nueva.status == "procesado"
    assert nueva.almacenamiento_oci.ruta_objeto.startswith("procesados/rutina/")


def test_la_justificacion_registra_quien_aprobo(auditoria):
    nueva = auditoria.aprobar(
        "DOC-AMB-1",
        Correcciones(
            medico_matricula="41883",
            medicamentos=["Metformina 850 mg"],
            auditor="Neri Ferreira",
        ),
    )

    assert "Neri Ferreira" in nueva.decision_enrutamiento.justificacion_enrutamiento


def test_el_caso_aprobado_desaparece_de_la_bandeja(auditoria):
    auditoria.aprobar(
        "DOC-AMB-1",
        Correcciones(medico_matricula="41883", medicamentos=["Metformina 850 mg"]),
    )

    assert auditoria.bandeja(PREFIJO_AUDITORIA) == []


def test_el_caso_aprobado_no_queda_contradiciendose_a_si_mismo(auditoria, almacen):
    # Si el almacen permite borrar, el objeto viejo se va. Si no (OCI por PAR),
    # se sobreescribe con la decision nueva. En los dos casos, lo que quede en
    # el prefijo anterior no puede decir lo contrario que el nuevo.
    auditoria.aprobar(
        "DOC-AMB-1",
        Correcciones(medico_matricula="41883", medicamentos=["Metformina 850 mg"]),
    )

    viejo = almacen.leer_texto(PREFIJO_AUDITORIA, "DOC-AMB-1.json")

    if viejo is not None:
        guardado = json.loads(viejo)
        assert (
            guardado["decision_enrutamiento"]["destino_principal"]
            == "Farmacia_Hospitalaria"
        )


def test_si_el_auditor_no_completa_lo_que_falta_el_caso_vuelve_a_revision(auditoria):
    # Aprobar sin corregir no fuerza el paso: el agente vuelve a decidir y
    # vuelve a encontrar que falta la matricula.
    nueva = auditoria.aprobar("DOC-AMB-1", Correcciones(auditor="Alguien"))

    assert nueva.decision_enrutamiento.destino_principal == "Cola_Revision_Humana"
    assert nueva.decision_enrutamiento.requiere_auditoria_humana is True


def test_una_correccion_no_pisa_lo_que_el_auditor_no_mando(auditoria):
    # Corregir es completar, no volver a cargar el documento entero.
    nueva = auditoria.aprobar(
        "DOC-AMB-1",
        Correcciones(medico_matricula="41883", medicamentos=["Metformina 850 mg"]),
    )

    assert nueva.datos_extraidos.paciente.nombre == "Rosa Mabel Aguero"
    assert nueva.datos_extraidos.paciente.edad == 58


def test_al_aprobar_la_urgencia_se_reevalua_sobre_el_documento_original(almacen):
    # El defecto que esto ataja: `aprobar` leia el original y lo descartaba,
    # asi que la urgencia se reevaluaba sobre los campos extraidos. Una orden
    # que grita "URGENTE. Paciente en shock" en el cuerpo, pero cuyos campos
    # no recogen ninguna de esas palabras, salia del panel como rutina.
    documento_id = "DOC-URG-1"
    original = (
        "HOSPITAL CENTRAL - GUARDIA DE EMERGENCIAS\n"
        "ORDEN DE ESTUDIO URGENTE\n"
        "Paciente: Oscar Daniel Riveros, 61 anos\n"
        "Caracter: URGENTE. Paciente en shock, hipotenso.\n"
        "Dra. Veronica Alcaraz - MP 61120"
    )

    respuesta = a_respuesta_triaje(
        resultado=AgentResult(
            document_id=documento_id,
            classification=ClassificationResult(
                document_type="orden_procedimiento", confidence=0.95
            ),
            # Ni un solo campo repite las palabras del cuerpo.
            extracted_data=ExtractedData(
                patient=Patient(name="Oscar Daniel Riveros", age=61),
                doctor=Doctor(name="Dra. Veronica Alcaraz", license_number="61120"),
                procedure="Angiotomografia de aorta con contraste",
            ),
        ),
        nivel_prioridad="Rutina",
        decision_enrutamiento=DecisionEnrutamientoContrato(
            destino_principal="Cola_Revision_Humana",
            requiere_auditoria_humana=True,
            justificacion_enrutamiento="motivo",
        ),
        almacenamiento_oci=AlmacenamientoOciContrato(
            bucket="b", ruta_objeto="x", status_backup="exito"
        ),
        status="derivado_revision_humana",
    )

    almacen.guardar_texto(
        PREFIJO_AUDITORIA, f"{documento_id}.json", respuesta.model_dump_json()
    )
    almacen.guardar_texto(PREFIJO_RECIBIDOS, f"{documento_id}.txt", original)

    nueva = ServicioAuditoria(almacen).aprobar(documento_id, Correcciones())

    assert nueva.clasificacion.nivel_prioridad == "Urgente"
    assert nueva.decision_enrutamiento.destino_principal == "Cola_Emergencia_Medica"


def test_el_auditor_corrige_el_contenido_pero_no_elige_el_destino(auditoria):
    # No hay forma de pedir un destino: Correcciones no tiene ese campo. El
    # grafo sigue siendo la unica autoridad sobre el enrutamiento.
    assert "destino" not in Correcciones.model_fields
    assert "destino_principal" not in Correcciones.model_fields
