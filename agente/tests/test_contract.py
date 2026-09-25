"""Pruebas del contrato publico de la API de triaje.

El caso de referencia es el ejemplo del enunciado: el informe de
tromboembolismo pulmonar. Si estas pruebas pasan, la respuesta tiene la forma
que el jurado va a comparar contra el PDF.
"""

import json

import pytest
from pydantic import ValidationError

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
    NotificacionContrato,
    RespuestaTriaje,
    SolicitudTriaje,
    a_respuesta_triaje,
    tipo_documento_publico,
)


@pytest.fixture
def resultado_tep() -> AgentResult:
    """El caso del enunciado, ya procesado por el agente."""
    return AgentResult(
        document_id="DOC-CLIN-2026-8942",
        classification=ClassificationResult(
            document_type="informe_estudio_diagnostico",
            specialty="Radiologia / Neumonologia",
            confidence=0.99,
        ),
        extracted_data=ExtractedData(
            patient=Patient(name="Carlos Eduardo Mendes", age=52),
            doctor=Doctor(
                name="Dra. Renata Silveira",
                license_number="145892",
            ),
            study="Tomografia de Torax con contraste",
            diagnosis="Tromboembolismo Pulmonar Agudo (TEP)",
            suggested_icd10="I26.9",
        ),
    )


@pytest.fixture
def enrutamiento_urgente() -> DecisionEnrutamientoContrato:
    return DecisionEnrutamientoContrato(
        destino_principal="Cola_Emergencia_Medica",
        requiere_auditoria_humana=False,
        justificacion_enrutamiento=(
            "Hallazgo critico de alta gravedad (TEP agudo) detectado en "
            "paciente sintomatico."
        ),
        notificacion_generada=NotificacionContrato(
            canal="Alerta_Guardia_Medica",
            mensaje=(
                "ALERTA URGENTE: Informe critico de TEP Agudo para el "
                "paciente Carlos Eduardo Mendes en Guardia de Emergencias."
            ),
        ),
    )


@pytest.fixture
def almacenamiento_urgente() -> AlmacenamientoOciContrato:
    return AlmacenamientoOciContrato(
        bucket="mediflow-documentos-clinicos",
        ruta_objeto="procesados/urgentes/DOC-CLIN-2026-8942.json",
        status_backup="exito",
    )


# ---------------------------------------------------------------------------
# Entrada
# ---------------------------------------------------------------------------

def test_la_solicitud_del_enunciado_es_valida():
    solicitud = SolicitudTriaje(
        documento_id="DOC-CLIN-2026-8942",
        tipo_archivo="PDF",
        documento_texto="HOSPITAL SANTA LUCIA - INFORME DE ESTUDIO ...",
        canal_origen="Guardia_Emergencias",
    )

    assert solicitud.documento_id == "DOC-CLIN-2026-8942"
    assert solicitud.tipo_archivo == "PDF"


def test_la_solicitud_rechaza_un_formato_no_soportado():
    with pytest.raises(ValidationError):
        SolicitudTriaje(
            documento_id="DOC-1",
            tipo_archivo="DOCX",
            canal_origen="Recepcion",
        )


def test_un_pdf_puede_llegar_sin_documento_texto():
    # El binario viaja por otra via; el campo queda en None y eso es valido.
    solicitud = SolicitudTriaje(
        documento_id="DOC-1",
        tipo_archivo="PDF",
        canal_origen="Recepcion",
    )

    assert solicitud.documento_texto is None


# ---------------------------------------------------------------------------
# Traduccion al contrato
# ---------------------------------------------------------------------------

def test_la_respuesta_tiene_las_claves_del_enunciado(
    resultado_tep, enrutamiento_urgente, almacenamiento_urgente
):
    respuesta = a_respuesta_triaje(
        resultado=resultado_tep,
        nivel_prioridad="Urgente",
        decision_enrutamiento=enrutamiento_urgente,
        almacenamiento_oci=almacenamiento_urgente,
    )

    payload = json.loads(respuesta.model_dump_json())

    assert set(payload) == {
        "status",
        "documento_id",
        "clasificacion",
        "datos_extraidos",
        "decision_enrutamiento",
        "almacenamiento_oci",
    }
    assert set(payload["clasificacion"]) == {
        "tipo_documento",
        "especialidad",
        "nivel_prioridad",
        "score_confianza_clasificacion",
    }
    assert set(payload["decision_enrutamiento"]) == {
        "destino_principal",
        "requiere_auditoria_humana",
        "justificacion_enrutamiento",
        "notificacion_generada",
    }
    assert set(payload["almacenamiento_oci"]) == {
        "bucket",
        "ruta_objeto",
        "status_backup",
    }


def test_los_valores_del_caso_del_enunciado_se_trasladan_sin_perdida(
    resultado_tep, enrutamiento_urgente, almacenamiento_urgente
):
    respuesta = a_respuesta_triaje(
        resultado=resultado_tep,
        nivel_prioridad="Urgente",
        decision_enrutamiento=enrutamiento_urgente,
        almacenamiento_oci=almacenamiento_urgente,
    )

    assert respuesta.documento_id == "DOC-CLIN-2026-8942"
    assert respuesta.clasificacion.nivel_prioridad == "Urgente"
    assert respuesta.clasificacion.score_confianza_clasificacion == 0.99
    assert respuesta.datos_extraidos.paciente.nombre == "Carlos Eduardo Mendes"
    assert respuesta.datos_extraidos.paciente.edad == 52
    assert respuesta.datos_extraidos.medico_solicitante.matricula == "145892"
    assert respuesta.datos_extraidos.cie10_sugerido == "I26.9"
    assert (
        respuesta.decision_enrutamiento.destino_principal
        == "Cola_Emergencia_Medica"
    )
    assert (
        respuesta.almacenamiento_oci.ruta_objeto
        == "procesados/urgentes/DOC-CLIN-2026-8942.json"
    )


def test_los_campos_ausentes_viajan_como_null_y_no_se_omiten(
    enrutamiento_urgente, almacenamiento_urgente
):
    # Un documento del que casi no se pudo extraer nada sigue produciendo una
    # respuesta con todas las claves. El consumidor tiene que poder distinguir
    # "no estaba en el documento" de "el campo no existe en esta version".
    vacio = AgentResult(
        document_id="DOC-VACIO",
        classification=ClassificationResult(
            document_type="desconocido",
            confidence=0.1,
        ),
        extracted_data=ExtractedData(),
    )

    respuesta = a_respuesta_triaje(
        resultado=vacio,
        nivel_prioridad="Rutina",
        decision_enrutamiento=enrutamiento_urgente,
        almacenamiento_oci=almacenamiento_urgente,
    )

    datos = json.loads(respuesta.model_dump_json())["datos_extraidos"]

    for campo in (
        "estudio_realizado",
        "diagnostico_principal",
        "cie10_sugerido",
        "medicamentos",
    ):
        assert campo in datos, f"falta la clave {campo}"
        assert datos[campo] is None

    assert datos["paciente"]["nombre"] is None
    assert datos["medico_solicitante"]["matricula"] is None


# ---------------------------------------------------------------------------
# Vocabularios cerrados
# ---------------------------------------------------------------------------

def test_cada_categoria_interna_tiene_etiqueta_publica():
    # Si alguien agrega una categoria al Literal interno y se olvida de la
    # etiqueta, esta prueba lo dice antes de que salga en la demo.
    from typing import get_args

    from mediflow_agent.schemas.models import DocumentType

    for categoria in get_args(DocumentType):
        etiqueta = tipo_documento_publico(categoria)
        assert etiqueta, f"sin etiqueta publica: {categoria}"
        assert etiqueta != "Desconocido" or categoria == "desconocido"


def test_un_destino_inventado_se_rechaza():
    with pytest.raises(ValidationError):
        DecisionEnrutamientoContrato(
            destino_principal="Cola_Cualquiera",
            requiere_auditoria_humana=False,
            justificacion_enrutamiento="motivo",
        )


def test_la_justificacion_no_puede_venir_vacia():
    # Regla del proyecto: la justificacion es lo que demuestra que el agente
    # razona. Una respuesta sin ella no sirve para la demo ni para el auditor.
    with pytest.raises(ValidationError):
        DecisionEnrutamientoContrato(
            destino_principal="Cola_Revision_Humana",
            requiere_auditoria_humana=True,
            justificacion_enrutamiento="",
        )


def test_la_notificacion_es_opcional():
    decision = DecisionEnrutamientoContrato(
        destino_principal="Historia_Clinica_Electronica",
        requiere_auditoria_humana=False,
        justificacion_enrutamiento="Epicrisis completa y legible.",
    )

    assert decision.notificacion_generada is None


def test_un_score_fuera_de_rango_se_rechaza(
    enrutamiento_urgente, almacenamiento_urgente
):
    with pytest.raises(ValidationError):
        RespuestaTriaje(
            status="procesado",
            documento_id="DOC-1",
            clasificacion={
                "tipo_documento": "Receta Medica",
                "especialidad": None,
                "nivel_prioridad": "Rutina",
                "score_confianza_clasificacion": 1.7,
            },
            datos_extraidos={
                "paciente": {},
                "medico_solicitante": {},
            },
            decision_enrutamiento=enrutamiento_urgente,
            almacenamiento_oci=almacenamiento_urgente,
        )
