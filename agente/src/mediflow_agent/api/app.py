"""API de triaje clinico.

Expone el endpoint que pide el enunciado: recibe un documento, lo procesa con
el agente y devuelve el diagnostico de triaje con los datos extraidos y la
decision de enrutamiento.

Para levantarla, desde `agente/`:

    set MEDIFLOW_ALMACEN_LOCAL=.almacen
    uvicorn mediflow_agent.api.app:app --reload --app-dir src

La documentacion interactiva queda en http://127.0.0.1:8000/docs y sirve para
la demo: se pega el JSON del enunciado y se ve la respuesta completa.
"""

import os
from functools import lru_cache
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, status as http_status

from mediflow_agent.api.servicio import FormatoNoSoportado, ServicioTriaje
from mediflow_agent.serialization.contract import RespuestaTriaje, SolicitudTriaje
from mediflow_agent.storage.base import AlmacenamientoDocumentos
from mediflow_agent.storage.local import AlmacenamientoLocal

app = FastAPI(
    title="MediFlow - API de triaje clinico",
    version="0.1.0",
    description=(
        "Agente autonomo para triaje, extraccion y enrutamiento de documentos "
        "clinicos. Hackathon ONE G10, Equipo 46.\n\n"
        "**Prototipo con datos ficticios. No debe usarse como sustituto de una "
        "evaluacion, diagnostico o decision medica profesional.**"
    ),
)


def obtener_almacenamiento() -> AlmacenamientoDocumentos:
    """Construye el almacen configurado.

    Hoy siempre devuelve el almacen en disco. Cuando exista el bucket de OCI
    (tarea 1.2), este es el unico lugar que hay que tocar: se elige una
    implementacion u otra segun la configuracion, y ni el servicio ni el
    endpoint se enteran.
    """
    raiz = os.getenv("MEDIFLOW_ALMACEN_LOCAL", ".almacen")
    nombre_bucket = os.getenv("MEDIFLOW_BUCKET", "mediflow-documentos-clinicos")

    return AlmacenamientoLocal(Path(raiz), nombre_bucket=nombre_bucket)


@lru_cache(maxsize=1)
def obtener_servicio() -> ServicioTriaje:
    """Arma el servicio con las dependencias reales.

    Los clientes del modelo se importan aca adentro y no arriba: construirlos
    exige GEMINI_API_KEY, y si se importaran al cargar el modulo, la API no
    podria ni arrancar sin credenciales. Las pruebas sustituyen esta funcion
    entera con `app.dependency_overrides`.
    """
    from mediflow_agent.classification.classifier import DocumentClassifier
    from mediflow_agent.extraction.extractor import DocumentExtractor

    return ServicioTriaje(
        clasificador=DocumentClassifier(),
        extractor=DocumentExtractor(),
        almacenamiento=obtener_almacenamiento(),
    )


@app.get("/salud", tags=["operacion"])
def salud() -> dict[str, str]:
    """Comprueba que el servicio esta arriba. No llama al modelo."""
    return {"status": "ok", "servicio": "mediflow-triaje"}


@app.post(
    "/triaje",
    response_model=RespuestaTriaje,
    tags=["triaje"],
    summary="Procesa un documento clinico y devuelve la decision de triaje",
)
def triaje(
    solicitud: SolicitudTriaje,
    servicio: ServicioTriaje = Depends(obtener_servicio),
) -> RespuestaTriaje:
    """Recibe un documento clinico y devuelve el triaje completo.

    El cuerpo se valida contra `SolicitudTriaje` antes de llegar aca, asi que
    un formato invalido o un documento de texto vacio ya fueron rechazados con
    un 422 y no consumieron cuota del modelo.
    """
    try:
        return servicio.procesar(solicitud)

    except FormatoNoSoportado as err:
        raise HTTPException(
            status_code=http_status.HTTP_501_NOT_IMPLEMENTED,
            detail=str(err),
        ) from err
