"""Pruebas del enrutamiento de linea base.

El fallo mas caro de este sistema es que un hallazgo urgente termine en la cola
de rutina. La mayoria de estas pruebas apuntan a eso.
"""

import pytest

from mediflow_agent.routing.baseline import decidir_enrutamiento
from mediflow_agent.schemas.models import (
    ClassificationResult,
    Doctor,
    ExtractedData,
    Patient,
)


def _clasificacion(tipo="informe_estudio_diagnostico", confianza=0.95):
    return ClassificationResult(document_type=tipo, confidence=confianza)


def _datos(**campos):
    base = dict(patient=Patient(name="Carlos Mendes", age=52), doctor=Doctor())
    base.update(campos)
    return ExtractedData(**base)


def _decidir(clasificacion=None, datos=None, canal="Recepcion", umbral=0.70):
    return decidir_enrutamiento(
        documento_id="DOC-1",
        clasificacion=clasificacion or _clasificacion(),
        datos=datos or _datos(),
        canal_origen=canal,
        umbral_confianza=umbral,
    )


# --- Urgencia -------------------------------------------------------------

def test_un_hallazgo_critico_va_a_emergencia_con_notificacion():
    prioridad, decision, status = _decidir(
        datos=_datos(diagnosis="Tromboembolismo Pulmonar Agudo (TEP)")
    )

    assert prioridad == "Urgente"
    assert decision.destino_principal == "Cola_Emergencia_Medica"
    assert decision.notificacion_generada is not None
    assert "tromboembolismo" in decision.justificacion_enrutamiento.lower()
    assert status == "procesado"


def test_la_urgencia_gana_sobre_la_ruta_del_tipo_de_documento():
    # Una receta con un hallazgo critico NO va a farmacia: va a emergencia.
    prioridad, decision, _ = _decidir(
        clasificacion=_clasificacion(tipo="receta_medica", confianza=0.99),
        datos=_datos(findings="Sospecha de sepsis en curso"),
    )

    assert prioridad == "Urgente"
    assert decision.destino_principal == "Cola_Emergencia_Medica"


def test_la_urgencia_gana_sobre_la_confianza_baja():
    # Confianza mala Y hallazgo critico: prima el hallazgo. Mandarlo a la cola
    # de revision comun seria enterrar un caso urgente en una bandeja lenta.
    prioridad, decision, _ = _decidir(
        clasificacion=_clasificacion(confianza=0.10),
        datos=_datos(conclusion="Imagen compatible con infarto agudo"),
    )

    assert prioridad == "Urgente"
    assert decision.destino_principal == "Cola_Emergencia_Medica"


def test_la_urgencia_se_detecta_sin_acentos_y_sin_mayusculas():
    prioridad, _, _ = _decidir(datos=_datos(findings="HEMORRAGIA DIGESTIVA ALTA"))
    assert prioridad == "Urgente"


@pytest.mark.parametrize(
    "texto",
    [
        "Control de rutina sin particularidades",
        "Estudio dentro de parametros normales",
        "Solicita hemograma completo ambulatorio",
    ],
)
def test_un_texto_de_rutina_no_dispara_urgencia(texto):
    prioridad, decision, status = _decidir(datos=_datos(conclusion=texto))

    assert prioridad == "Rutina"
    assert decision.destino_principal != "Cola_Emergencia_Medica"
    assert status == "procesado"


# --- Documento desconocido ------------------------------------------------

def test_un_documento_desconocido_escala_y_no_se_aprueba_solo():
    prioridad, decision, status = _decidir(
        clasificacion=_clasificacion(tipo="desconocido", confianza=0.99)
    )

    assert decision.requiere_auditoria_humana is True
    assert decision.destino_principal == "Cola_Emergencia_Medica"
    assert status == "derivado_revision_humana"
    assert prioridad == "Prioritario"


# --- Confianza ------------------------------------------------------------

def test_la_confianza_baja_deriva_a_revision_humana():
    _, decision, status = _decidir(clasificacion=_clasificacion(confianza=0.42))

    assert decision.destino_principal == "Cola_Revision_Humana"
    assert decision.requiere_auditoria_humana is True
    assert status == "derivado_revision_humana"
    assert "0.42" in decision.justificacion_enrutamiento


def test_el_umbral_es_configurable():
    # Con 0.70 deriva; subiendo el umbral a 0.90, el mismo caso tambien.
    _, decision_permisiva, _ = _decidir(
        clasificacion=_clasificacion(confianza=0.80), umbral=0.70
    )
    _, decision_estricta, _ = _decidir(
        clasificacion=_clasificacion(confianza=0.80), umbral=0.90
    )

    assert decision_permisiva.destino_principal != "Cola_Revision_Humana"
    assert decision_estricta.destino_principal == "Cola_Revision_Humana"


def test_el_limite_del_umbral_no_deriva():
    # Exactamente en el umbral se considera suficiente: la regla es "menor que".
    _, decision, _ = _decidir(
        clasificacion=_clasificacion(confianza=0.70), umbral=0.70
    )
    assert decision.destino_principal != "Cola_Revision_Humana"


# --- Rutas por tipo -------------------------------------------------------

@pytest.mark.parametrize(
    "tipo, destino",
    [
        ("receta_medica", "Farmacia_Hospitalaria"),
        ("orden_procedimiento", "Auditoria_Autorizaciones"),
        ("informe_estudio_diagnostico", "Historia_Clinica_Electronica"),
        ("epicrisis", "Historia_Clinica_Electronica"),
        ("certificado_medico", "Historia_Clinica_Electronica"),
    ],
)
def test_cada_tipo_tiene_su_destino(tipo, destino):
    _, decision, status = _decidir(clasificacion=_clasificacion(tipo=tipo))

    assert decision.destino_principal == destino
    assert decision.requiere_auditoria_humana is False
    assert status == "procesado"


def test_todo_tipo_del_esquema_tiene_ruta_o_escala():
    # Si alguien agrega una categoria al Literal y olvida mapearla, el caso
    # tiene que escalar, nunca elegir un destino arbitrario.
    from typing import get_args

    from mediflow_agent.schemas.models import DocumentType

    for tipo in get_args(DocumentType):
        _, decision, _ = _decidir(clasificacion=_clasificacion(tipo=tipo))
        assert decision.justificacion_enrutamiento


# --- Canal de origen ------------------------------------------------------

def test_el_canal_de_guardia_eleva_la_prioridad_sin_declarar_urgencia():
    # Venir de guardia es una senal, no una prueba: sube a Prioritario, no a
    # Urgente, y no cambia el destino.
    prioridad, decision, _ = _decidir(canal="Guardia_Emergencias")

    assert prioridad == "Prioritario"
    assert decision.destino_principal == "Historia_Clinica_Electronica"


def test_la_justificacion_nunca_viene_vacia():
    for caso in (
        dict(clasificacion=_clasificacion(tipo="desconocido")),
        dict(clasificacion=_clasificacion(confianza=0.1)),
        dict(datos=_datos(diagnosis="sepsis")),
        dict(),
    ):
        _, decision, _ = _decidir(**caso)
        assert decision.justificacion_enrutamiento.strip()
