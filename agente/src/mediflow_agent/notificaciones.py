"""Envio real de las alertas de guardia.

Hasta ahora el agente *generaba* la notificacion —canal y mensaje, dentro del
JSON de respuesta, como pide el contrato del enunciado— pero no la mandaba a
ningun lado. Este modulo la entrega: es el diferencial "Alertas en Tiempo Real"
del enunciado, por webhook (Slack, Discord, Teams o n8n) o por correo.

Tres decisiones que gobiernan todo lo de abajo:

1. **Sin configurar, no hace nada y no molesta.** Un despliegue sin webhook ni
   SMTP funciona igual que antes. La demo no depende de que alguien tenga un
   Slack a mano.

2. **Un fallo al notificar NUNCA tumba un triaje.** El documento ya se
   clasifico, se enruto y se guardo. Que el webhook este caido no puede
   convertir eso en un error 500 para el hospital. Todo sale por el log.

3. **El envio tiene tiempo limite.** Un webhook que no responde bloquearia el
   unico worker del contenedor y dejaria la pagina colgada para todos. Cinco
   segundos y se abandona.
"""

import json
import logging
import smtplib
import urllib.error
import urllib.request
from email.message import EmailMessage

from mediflow_agent.config import numero, variable

_log = logging.getLogger(__name__)

# Un webhook lento bloquea el unico worker del contenedor. Ver decision 3.
ESPERA_MAXIMA = numero("MEDIFLOW_ALERTA_TIMEOUT", 5.0)


def _enviar_webhook(url: str, mensaje: str, documento_id: str) -> bool:
    """Publica el mensaje en un webhook entrante.

    El cuerpo usa la clave `text`, que es la que entienden Slack, Discord
    (con `/slack` al final de la URL), Teams y los nodos de n8n. Para otro
    destino, un nodo de n8n en el medio traduce el formato sin tocar esto.
    """
    cuerpo = json.dumps(
        {"text": mensaje, "documento_id": documento_id}
    ).encode("utf-8")

    pedido = urllib.request.Request(
        url,
        data=cuerpo,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urllib.request.urlopen(pedido, timeout=ESPERA_MAXIMA) as respuesta:
        return 200 <= respuesta.status < 300


def _enviar_correo(mensaje: str, documento_id: str) -> bool:
    """Manda la alerta por SMTP. Devuelve False si falta configuracion."""
    servidor = variable("MEDIFLOW_SMTP_HOST")
    destino = variable("MEDIFLOW_ALERTA_EMAIL")

    if not servidor or not destino:
        return False

    correo = EmailMessage()
    correo["Subject"] = f"[MediFlow] Alerta de guardia - {documento_id}"
    correo["From"] = variable("MEDIFLOW_SMTP_USUARIO") or "mediflow@localhost"
    correo["To"] = destino
    correo.set_content(mensaje)

    puerto = int(numero("MEDIFLOW_SMTP_PUERTO", 587))
    usuario = variable("MEDIFLOW_SMTP_USUARIO")
    clave = variable("MEDIFLOW_SMTP_CLAVE")

    with smtplib.SMTP(servidor, puerto, timeout=ESPERA_MAXIMA) as sesion:
        sesion.starttls()

        if usuario and clave:
            sesion.login(usuario, clave)

        sesion.send_message(correo)

    return True


def enviar_alerta(mensaje: str, documento_id: str) -> tuple[bool, str]:
    """Entrega la alerta por los canales configurados.

    Devuelve `(se_entrego, detalle)`. El detalle viaja al log, no a la
    respuesta: el contrato del enunciado fija la forma de
    `notificacion_generada` y no se le agregan campos.

    NUNCA levanta una excepcion. Ver decision 2 del encabezado del modulo.
    """
    url = variable("MEDIFLOW_ALERTA_WEBHOOK")
    entregado: list[str] = []
    fallado: list[str] = []

    if url:
        try:
            if _enviar_webhook(url, mensaje, documento_id):
                entregado.append("webhook")
            else:
                fallado.append("webhook (respuesta no exitosa)")
        except (urllib.error.URLError, OSError, ValueError) as error:
            # El mensaje de error puede traer la URL completa del webhook, que
            # es una credencial: quien la tenga puede publicar en ese canal.
            # Por eso se registra el TIPO del fallo, no su texto.
            fallado.append(f"webhook ({type(error).__name__})")

    try:
        if _enviar_correo(mensaje, documento_id):
            entregado.append("correo")
    except (smtplib.SMTPException, OSError) as error:
        fallado.append(f"correo ({type(error).__name__})")

    if fallado:
        _log.warning(
            "Alerta de %s: fallo el envio por %s. El triaje se completo igual.",
            documento_id,
            ", ".join(fallado),
        )

    if entregado:
        _log.info("Alerta de %s entregada por %s.", documento_id, ", ".join(entregado))
        return True, ", ".join(entregado)

    if not url and not variable("MEDIFLOW_SMTP_HOST"):
        # Caso normal en desarrollo y en la demo. No es un problema.
        return False, "sin canales configurados"

    return False, "ningun canal entrego la alerta"
