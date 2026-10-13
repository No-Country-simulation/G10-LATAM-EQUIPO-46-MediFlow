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
import secrets
from functools import lru_cache
from pathlib import Path

from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    Header,
    HTTPException,
    UploadFile,
    status as http_status,
)

from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from mediflow_agent.api import configuracion as cfg
from mediflow_agent.api.auditoria import Correcciones, ServicioAuditoria
from mediflow_agent.api.servicio import ServicioTriaje
from mediflow_agent.config import variable
from mediflow_agent.modelos import MODELO_POR_DEFECTO
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
    nombre_bucket = variable("MEDIFLOW_BUCKET", "mediflow-documentos-clinicos")
    destino = variable("MEDIFLOW_ALMACEN", "local").lower()

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

    raiz = variable("MEDIFLOW_ALMACEN_LOCAL", ".almacen")

    return AlmacenamientoLocal(Path(raiz), nombre_bucket=nombre_bucket)


@lru_cache(maxsize=1)
def obtener_servicio() -> ServicioTriaje:
    """Arma el servicio con las dependencias reales.

    Los clientes del modelo se importan aca adentro y no arriba: construirlos
    exige GEMINI_API_KEY, y si se importaran al cargar el modulo, la API no
    podria ni arrancar sin credenciales. Las pruebas sustituyen esta funcion
    entera con `app.dependency_overrides`.
    """
    from langchain_google_genai import ChatGoogleGenerativeAI

    from mediflow_agent.classification.classifier import DocumentClassifier
    from mediflow_agent.extraction.extractor_por_tipo import ExtractorPorTipo
    from mediflow_agent.ingestion.transcriptor import TranscriptorGemini

    return ServicioTriaje(
        clasificador=DocumentClassifier(),
        extractor=ExtractorPorTipo(),
        almacenamiento=obtener_almacenamiento(),
        ingestor=Ingestor(transcriptor=TranscriptorGemini()),
        llm_urgencia=ChatGoogleGenerativeAI(
            model=variable("GEMINI_MODEL", MODELO_POR_DEFECTO),
            google_api_key=variable("GEMINI_API_KEY"),
            temperature=0,
        ),
    )


ESTATICOS = Path(__file__).resolve().parent / "estaticos"


@lru_cache(maxsize=1)
def obtener_auditoria() -> ServicioAuditoria:
    """Panel de auditoria. Lee del mismo almacen que escribe el triaje.

    Que lea del almacen y no de una lista en memoria es lo que hace que la
    bandeja muestre el estado real: incluye los documentos que proceso otra
    persona, en otra maquina, contra el mismo bucket.
    """
    from langchain_google_genai import ChatGoogleGenerativeAI

    api_key = variable("GEMINI_API_KEY")

    llm = (
        ChatGoogleGenerativeAI(
            model=variable("GEMINI_MODEL", MODELO_POR_DEFECTO),
            google_api_key=api_key,
            temperature=0,
        )
        if api_key
        else None
    )

    return ServicioAuditoria(obtener_almacenamiento(), llm=llm)


@app.get("/", include_in_schema=False)
def inicio() -> FileResponse:
    """La interfaz de triaje."""
    return FileResponse(ESTATICOS / "index.html")


@app.get("/bandeja", tags=["panel"])
def bandeja(
    prefijo: str = "auditoria_humana",
    auditoria: ServicioAuditoria = Depends(obtener_auditoria),
) -> list[dict]:
    """Casos que esperan en un prefijo, ordenados por prioridad.

    Urgente primero, despues Prioritario, despues Rutina. Es el unico lugar
    donde "Prioritario" cambia algo observable: el orden de atencion.
    """
    return [
        {
            "documento_id": c.documento_id,
            "tipo_documento": c.tipo_documento,
            "nivel_prioridad": c.nivel_prioridad,
            "destino": c.destino,
            "justificacion": c.justificacion,
            "paciente": c.paciente,
        }
        for c in auditoria.bandeja(prefijo)
    ]


@app.get("/documentos/{documento_id}", tags=["panel"])
def documento(
    documento_id: str,
    auditoria: ServicioAuditoria = Depends(obtener_auditoria),
) -> dict:
    """La decision guardada junto al documento original.

    Los dos juntos: es lo que necesita un auditor para decidir sin tener que
    abrir el bucket por su cuenta.
    """
    encontrado = auditoria.documento(documento_id)

    if encontrado is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"No hay ningun documento {documento_id} en el almacen.",
        )

    respuesta, prefijo = encontrado

    return {
        "prefijo": prefijo,
        "original": auditoria.original(documento_id),
        "decision": respuesta.model_dump(),
    }


@app.post("/documentos/{documento_id}/aprobar", tags=["panel"])
def aprobar(
    documento_id: str,
    correcciones: Correcciones,
    auditoria: ServicioAuditoria = Depends(obtener_auditoria),
) -> RespuestaTriaje:
    """El auditor corrige el contenido y el agente vuelve a decidir la ruta.

    El auditor no elige el destino: corrige lo que el documento dice. Si
    pudiera elegir la cola, el grafo de decision dejaria de ser la unica
    autoridad sobre el enrutamiento y nadie podria auditar por que un
    documento termino donde termino.
    """
    nueva = auditoria.aprobar(documento_id, correcciones)

    if nueva is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"No hay ningun documento {documento_id} en el almacen.",
        )

    return nueva


@app.get("/salud", tags=["operacion"])
def salud() -> dict[str, str]:
    """Comprueba que el servicio esta arriba. No llama al modelo."""
    return {"status": "ok", "servicio": "mediflow-triaje"}


# --- reglas de triaje configurables ---------------------------------------
#
# El diferencial del enunciado. Leer es libre; escribir exige la clave de
# MEDIFLOW_ADMIN_CLAVE, porque la pagina esta abierta a internet y sin eso
# cualquiera podria desactivar la revision humana de todo el sistema.


@app.get("/configuracion", tags=["configuracion"])
def ver_configuracion() -> dict:
    """Las reglas de triaje vigentes, tal como las usa el agente ahora."""
    return {
        "reglas": cfg.leer().model_dump(),
        "editable": bool(variable("MEDIFLOW_ADMIN_CLAVE")),
        "bloqueados_por_entorno": cfg.bloqueados_por_entorno(),
        "destinos_validos": list(cfg.DESTINOS_VALIDOS),
        "tipos_validos": list(cfg.TIPOS_VALIDOS),
    }


@app.put("/configuracion", tags=["configuracion"])
def guardar_configuracion(
    reglas: cfg.ReglasTriaje,
    x_admin_clave: str | None = Header(default=None),
) -> dict:
    """Reemplaza las reglas de triaje. Rige desde el documento siguiente."""
    esperada = variable("MEDIFLOW_ADMIN_CLAVE")

    if not esperada:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail=(
                "La edicion esta deshabilitada: no hay MEDIFLOW_ADMIN_CLAVE "
                "configurada en el servidor. El panel queda en solo lectura."
            ),
        )

    # `compare_digest` en lugar de `==`: comparar cadenas con != corta en la
    # primera diferencia, y ese tiempo distinto deja adivinar la clave
    # caracter por caracter.
    if not x_admin_clave or not secrets.compare_digest(x_admin_clave, esperada):
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail="Clave de administracion incorrecta o ausente.",
        )

    try:
        vigentes = cfg.guardar(reglas)
    except OSError as error:
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"No se pudo escribir el archivo de reglas: {error}",
        ) from error

    return {
        "reglas": vigentes.model_dump(),
        "editable": True,
        "bloqueados_por_entorno": cfg.bloqueados_por_entorno(),
    }


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


# Se monta al final para que no tape las rutas de la API.
app.mount("/estaticos", StaticFiles(directory=ESTATICOS), name="estaticos")
