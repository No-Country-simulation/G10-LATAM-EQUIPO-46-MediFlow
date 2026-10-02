"""API de triaje clinico.

Expone los endpoints que pide el enunciado: reciben un documento, lo procesan
con el agente y devuelven el diagnostico de triaje con los datos extraidos y la
decision de enrutamiento.

Para levantarla, desde `agente/`:

    uvicorn mediflow_agent.api.app:app --reload --app-dir src

La documentacion interactiva queda en http://127.0.0.1:8000/docs y sirve para
la demo: se pega el JSON del enunciado, o se sube un PDF, y se ve la respuesta
completa.
"""

import os
from functools import lru_cache
from pathlib import Path

from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    UploadFile,
    status as http_status,
)

from mediflow_agent.api.servicio import ServicioTriaje
from mediflow_agent.ingestion.ingestor import Ingestor
from mediflow_agent.serialization.contract import RespuestaTriaje, SolicitudTriaje
from mediflow_agent.storage.base import AlmacenamientoDocumentos
from mediflow_agent.storage.local import AlmacenamientoLocal

# Tope de tamano de subida. Un informe clinico escaneado no llega a esto ni de
# cerca; por encima es casi siempre un error de carga, y aceptarlo significaria
# rasterizarlo y mandarlo al modelo.
MAXIMO_BYTES_SUBIDA = 20 * 1024 * 1024

app = FastAPI(
    title="MediFlow - API de triaje clinico",
    version="0.2.0",
    description=(
        "Agente autonomo para triaje, extraccion y enrutamiento de documentos "
        "clinicos. Hackathon ONE G10, Equipo 46."
    ),
)


def obtener_almacenamiento() -> AlmacenamientoDocumentos:
    """Construye el almacen segun MEDIFLOW_ALMACEN.

    Este es el unico lugar del sistema que sabe que existen dos almacenes. Ni
    el servicio ni los endpoints se enteran de cual esta en uso.

      MEDIFLOW_ALMACEN=oci     -> OCI con credenciales IAM (la via normal)
      MEDIFLOW_ALMACEN=par     -> OCI con un Pre-Authenticated Request
      MEDIFLOW_ALMACEN=local   -> disco, para desarrollo y demo sin red

    El valor por defecto es "local" a proposito: sin credenciales de OCI la
    aplicacion arranca igual y el equipo puede trabajar. Elegir "oci" o "par"
    sin configuracion valida falla al arrancar, no a mitad de un triaje.
    """
    nombre_bucket = os.getenv("MEDIFLOW_BUCKET", "mediflow-documentos-clinicos")
    destino = os.getenv("MEDIFLOW_ALMACEN", "local").strip().lower()

    if destino == "oci":
        from mediflow_agent.storage.oci_storage import AlmacenamientoOci

        return AlmacenamientoOci(nombre_bucket=nombre_bucket)

    if destino == "par":
        from mediflow_agent.storage.oci_par import AlmacenamientoOciPar

        # El nombre del bucket sale del propio PAR, asi que no se pasa.
        return AlmacenamientoOciPar()

    if destino != "local":
        raise ValueError(
            f"MEDIFLOW_ALMACEN={destino!r} no es valido. "
            "Use 'oci', 'par' o 'local'."
        )

    raiz = os.getenv("MEDIFLOW_ALMACEN_LOCAL", ".almacen")

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
    from mediflow_agent.ingestion.transcriptor import TranscriptorGemini

    return ServicioTriaje(
        clasificador=DocumentClassifier(),
        extractor=DocumentExtractor(),
        almacenamiento=obtener_almacenamiento(),
        ingestor=Ingestor(transcriptor=TranscriptorGemini()),
    )


@app.get("/salud", tags=["operacion"])
def salud() -> dict[str, str]:
    """Comprueba que el servicio esta arriba. No llama al modelo."""
    return {"status": "ok", "servicio": "mediflow-triaje"}


@app.post(
    "/triaje",
    response_model=RespuestaTriaje,
    tags=["triaje"],
    summary="Procesa un documento de texto y devuelve la decision de triaje",
)
def triaje(
    solicitud: SolicitudTriaje,
    servicio: ServicioTriaje = Depends(obtener_servicio),
) -> RespuestaTriaje:
    """Recibe un documento clinico en texto y devuelve el triaje completo.

    El cuerpo se valida contra `SolicitudTriaje` antes de llegar aca, asi que
    un formato invalido o un documento de texto vacio ya fueron rechazados con
    un 422 y no consumieron cuota del modelo.

    Para PDF e imagenes, usar `POST /triaje/archivo`.
    """
    if solicitud.tipo_archivo not in ("TEXTO", "JSON"):
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Un documento de tipo {solicitud.tipo_archivo} tiene que "
                "subirse por POST /triaje/archivo."
            ),
        )

    return servicio.procesar(solicitud)


@app.post(
    "/triaje/archivo",
    response_model=RespuestaTriaje,
    tags=["triaje"],
    summary="Procesa un PDF o una imagen y devuelve la decision de triaje",
)
async def triaje_archivo(
    documento_id: str = Form(..., description="Identificador del sistema emisor."),
    tipo_archivo: str = Form(..., description="PDF o IMAGEN."),
    canal_origen: str = Form(..., description="De donde llego el documento."),
    archivo: UploadFile = File(..., description="El PDF o la imagen."),
    servicio: ServicioTriaje = Depends(obtener_servicio),
) -> RespuestaTriaje:
    """Recibe el documento como archivo y devuelve el mismo contrato.

    La respuesta es identica a la de `POST /triaje`: el formato de entrada no
    cambia nada de lo que el consumidor recibe. De eso se encarga la ingesta.
    """
    if tipo_archivo not in ("PDF", "IMAGEN"):
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="tipo_archivo tiene que ser PDF o IMAGEN en este endpoint.",
        )

    contenido = await archivo.read()

    if not contenido:
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="El archivo llego vacio.",
        )

    if len(contenido) > MAXIMO_BYTES_SUBIDA:
        raise HTTPException(
            status_code=http_status.HTTP_413_CONTENT_TOO_LARGE,
            detail=(
                f"El archivo pesa {len(contenido) // (1024 * 1024)} MB y el "
                f"maximo es {MAXIMO_BYTES_SUBIDA // (1024 * 1024)} MB."
            ),
        )

    solicitud = SolicitudTriaje(
        documento_id=documento_id,
        tipo_archivo=tipo_archivo,
        documento_texto=None,
        canal_origen=canal_origen,
    )

    return servicio.procesar(solicitud, contenido=contenido)
