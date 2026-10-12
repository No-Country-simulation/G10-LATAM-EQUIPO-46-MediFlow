# Imagen de MediFlow para desplegar en una maquina OCI Compute Always Free.
#
# Se parte de slim y no de alpine: el SDK de OCI y pypdfium2 traen binarios
# compilados contra glibc, y en alpine (musl) habria que compilarlos a mano.
# La imagen pesa mas, pero se construye en una Always Free sin pelear.

FROM python:3.12-slim

# No generar .pyc ni bufferear la salida: en un contenedor, los logs tienen
# que salir cuando pasan las cosas, no cuando se llena el buffer.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Las dependencias primero y el codigo despues: asi un cambio en el codigo no
# invalida la capa de dependencias, que es la que tarda.
COPY agente/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY agente/src ./src
COPY agente/config ./config
COPY agente/corpus ./corpus

# Usuario sin privilegios. Si alguien encuentra una forma de ejecutar codigo a
# traves de un documento subido, que no sea root quien lo ejecute.
RUN useradd --create-home --uid 10001 mediflow && chown -R mediflow:mediflow /app
USER mediflow

EXPOSE 8000

# Comprobacion de salud: /salud no llama al modelo, asi que no gasta cuota
# aunque el orquestador la consulte cada treinta segundos.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/salud', timeout=4).status == 200 else 1)"

# Un solo worker a proposito: la capa gratuita de Gemini limita a 15 pedidos
# por minuto para todo el proyecto, asi que mas procesos no darian mas
# capacidad, solo mas formas de chocar contra el limite a la vez.
CMD ["python", "-m", "uvicorn", "mediflow_agent.api.app:app", \
     "--app-dir", "src", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
