"""Entrega real de la alerta de guardia (diferencial del enunciado).

    "Alertas en Tiempo Real: Workflow en n8n disparando alertas en
     Slack/Email para los equipos de guardia."

Lo que estas pruebas protegen, por encima de todo: que un canal caido NO
convierta un triaje resuelto en un error. El documento ya se clasifico, se
enruto y se guardo antes de que se intente notificar.
"""

import smtplib
import urllib.error

import pytest

from mediflow_agent import notificaciones
from mediflow_agent.notificaciones import enviar_alerta


@pytest.fixture(autouse=True)
def sin_configuracion(monkeypatch):
    """Parte de un entorno limpio: la maquina real puede tener estas puestas."""
    for nombre in (
        "MEDIFLOW_ALERTA_WEBHOOK",
        "MEDIFLOW_SMTP_HOST",
        "MEDIFLOW_ALERTA_EMAIL",
        "MEDIFLOW_SMTP_USUARIO",
        "MEDIFLOW_SMTP_CLAVE",
    ):
        monkeypatch.delenv(nombre, raising=False)


# --- sin configurar -------------------------------------------------------

def test_sin_canales_configurados_no_falla_ni_intenta_nada():
    # Es el caso de la demo y del desarrollo local. No es un error.
    entregado, detalle = enviar_alerta("ALERTA URGENTE", "DOC-1")

    assert entregado is False
    assert detalle == "sin canales configurados"


# --- webhook --------------------------------------------------------------

def test_con_webhook_configurado_se_publica_el_mensaje(monkeypatch):
    enviados = []

    def doble(url, mensaje, documento_id):
        enviados.append((url, mensaje, documento_id))
        return True

    monkeypatch.setenv("MEDIFLOW_ALERTA_WEBHOOK", "https://ejemplo.invalido/hook")
    monkeypatch.setattr(notificaciones, "_enviar_webhook", doble)

    entregado, detalle = enviar_alerta("ALERTA URGENTE: TEP agudo", "DOC-1")

    assert entregado is True
    assert detalle == "webhook"
    assert enviados == [
        ("https://ejemplo.invalido/hook", "ALERTA URGENTE: TEP agudo", "DOC-1")
    ]


def test_un_webhook_caido_no_levanta_una_excepcion(monkeypatch):
    # LA prueba del modulo. Si esto falla, un Slack caido tumba el triaje.
    def doble(url, mensaje, documento_id):
        raise urllib.error.URLError("conexion rechazada")

    monkeypatch.setenv("MEDIFLOW_ALERTA_WEBHOOK", "https://ejemplo.invalido/hook")
    monkeypatch.setattr(notificaciones, "_enviar_webhook", doble)

    entregado, detalle = enviar_alerta("ALERTA", "DOC-1")

    assert entregado is False
    assert "ningun canal" in detalle


def test_el_fallo_del_webhook_no_escribe_la_url_en_el_log(monkeypatch, caplog):
    # La URL de un webhook entrante es una credencial: quien la tenga puede
    # publicar en ese canal. No puede terminar en un log.
    secreto = "https://hooks.ejemplo.invalido/servicios/T000/B000/xxxxSECRETOxxxx"

    def doble(url, mensaje, documento_id):
        raise urllib.error.URLError(f"fallo al conectar con {url}")

    monkeypatch.setenv("MEDIFLOW_ALERTA_WEBHOOK", secreto)
    monkeypatch.setattr(notificaciones, "_enviar_webhook", doble)

    with caplog.at_level("WARNING"):
        enviar_alerta("ALERTA", "DOC-1")

    assert "xxxxSECRETOxxxx" not in caplog.text
    assert "URLError" in caplog.text


def test_una_respuesta_no_exitosa_se_reporta_como_no_entregada(monkeypatch):
    monkeypatch.setenv("MEDIFLOW_ALERTA_WEBHOOK", "https://ejemplo.invalido/hook")
    monkeypatch.setattr(
        notificaciones, "_enviar_webhook", lambda url, mensaje, documento_id: False
    )

    entregado, _ = enviar_alerta("ALERTA", "DOC-1")

    assert entregado is False


# --- correo ---------------------------------------------------------------

def test_sin_destinatario_el_correo_no_se_intenta(monkeypatch):
    monkeypatch.setenv("MEDIFLOW_SMTP_HOST", "smtp.ejemplo.invalido")
    # Falta MEDIFLOW_ALERTA_EMAIL.

    entregado, _ = enviar_alerta("ALERTA", "DOC-1")

    assert entregado is False


def test_un_smtp_caido_no_levanta_una_excepcion(monkeypatch):
    def doble(mensaje, documento_id):
        raise smtplib.SMTPException("servidor no disponible")

    monkeypatch.setenv("MEDIFLOW_SMTP_HOST", "smtp.ejemplo.invalido")
    monkeypatch.setenv("MEDIFLOW_ALERTA_EMAIL", "guardia@ejemplo.invalido")
    monkeypatch.setattr(notificaciones, "_enviar_correo", doble)

    entregado, detalle = enviar_alerta("ALERTA", "DOC-1")

    assert entregado is False
    assert "ningun canal" in detalle


def test_los_dos_canales_juntos_se_reportan_los_dos(monkeypatch):
    monkeypatch.setenv("MEDIFLOW_ALERTA_WEBHOOK", "https://ejemplo.invalido/hook")
    monkeypatch.setenv("MEDIFLOW_SMTP_HOST", "smtp.ejemplo.invalido")
    monkeypatch.setenv("MEDIFLOW_ALERTA_EMAIL", "guardia@ejemplo.invalido")
    monkeypatch.setattr(
        notificaciones, "_enviar_webhook", lambda url, mensaje, documento_id: True
    )
    monkeypatch.setattr(
        notificaciones, "_enviar_correo", lambda mensaje, documento_id: True
    )

    entregado, detalle = enviar_alerta("ALERTA", "DOC-1")

    assert entregado is True
    assert detalle == "webhook, correo"


def test_si_un_canal_falla_el_otro_entrega_igual(monkeypatch):
    monkeypatch.setenv("MEDIFLOW_ALERTA_WEBHOOK", "https://ejemplo.invalido/hook")
    monkeypatch.setenv("MEDIFLOW_SMTP_HOST", "smtp.ejemplo.invalido")
    monkeypatch.setenv("MEDIFLOW_ALERTA_EMAIL", "guardia@ejemplo.invalido")

    def webhook_roto(url, mensaje, documento_id):
        raise urllib.error.URLError("caido")

    monkeypatch.setattr(notificaciones, "_enviar_webhook", webhook_roto)
    monkeypatch.setattr(
        notificaciones, "_enviar_correo", lambda mensaje, documento_id: True
    )

    entregado, detalle = enviar_alerta("ALERTA", "DOC-1")

    assert entregado is True
    assert detalle == "correo"
