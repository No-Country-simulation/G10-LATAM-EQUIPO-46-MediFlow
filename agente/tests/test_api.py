"""Pruebas del endpoint de triaje, de punta a punta.

El modelo se sustituye por dobles: estas pruebas no llaman a Gemini, no
consumen cuota y corren en milisegundos. Es la contramedida al riesgo
"se agota la cuota gratuita del modelo" que el plan marca para la semana 1.
"""

import json

import pytest
from fastapi.testclient import TestClient

from mediflow_agent.api.app import app, obtener_servicio
from mediflow_agent.api.servicio import ServicioTriaje
from mediflow_agent.ingestion.ingestor import Ingestor
from mediflow_agent.schemas.models import (
    ClassificationResult,
    Doctor,
    ExtractedData,
    Patient,
)
from mediflow_agent.serialization.contract import SolicitudTriaje
from mediflow_agent.storage.local import AlmacenamientoLocal

from conftest import TranscriptorDoble, construir_imagen, construir_pdf

TEXTO_TEP = (
    "HOSPITAL SANTA LUCIA - INFORME DE ESTUDIO RADIOLOGICO. Paciente: Carlos "
    "Eduardo Mendes, 52 anos. Medico Solicitante: Dra. Renata Silveira MP "
    "145892. Estudio: Tomografia de Torax con contraste. CONCLUSION: Cuadro "
    "compatible con Tromboembolismo Pulmonar Agudo."
)


class ClasificadorDoble:
    def __init__(self, resultado=None, error=None):
        self._resultado = resultado or ClassificationResult(
            document_type="informe_estudio_diagnostico",
            specialty="Radiologia / Neumonologia",
            confidence=0.99,
        )
        self._error = error

    def classify(self, texto):
        if self._error:
            raise self._error
        return self._resultado


class ExtractorDoble:
    def __init__(self, resultado=None, error=None):
        self._resultado = resultado or ExtractedData(
            patient=Patient(name="Carlos Eduardo Mendes", age=52),
            doctor=Doctor(name="Dra. Renata Silveira", license_number="145892"),
            study="Tomografia de Torax con contraste",
            diagnosis="Tromboembolismo Pulmonar Agudo (TEP)",
            suggested_icd10="I26.9",
        )
        self._error = error

    def extract(self, texto):
        if self._error:
            raise self._error
        return self._resultado


@pytest.fixture
def almacen(tmp_path):
    return AlmacenamientoLocal(tmp_path, nombre_bucket="mediflow-documentos-clinicos")


@pytest.fixture
def cliente(almacen):
    """Cliente con el servicio real pero el modelo sustituido."""

    def _construir(clasificador=None, extractor=None, transcripcion=None):
        servicio = ServicioTriaje(
            clasificador=clasificador or ClasificadorDoble(),
            extractor=extractor or ExtractorDoble(),
            almacenamiento=almacen,
            ingestor=Ingestor(transcriptor=TranscriptorDoble(transcripcion))
            if transcripcion is not None
            else Ingestor(transcriptor=TranscriptorDoble()),
        )
        app.dependency_overrides[obtener_servicio] = lambda: servicio
        return TestClient(app)

    yield _construir
    app.dependency_overrides.clear()


def _solicitud(**campos):
    base = {
        "documento_id": "DOC-CLIN-2026-8942",
        "tipo_archivo": "TEXTO",
        "documento_texto": TEXTO_TEP,
        "canal_origen": "Guardia_Emergencias",
    }
    base.update(campos)
    return base


# --- Operacion ------------------------------------------------------------

def test_salud_responde_sin_tocar_el_modelo(cliente):
    r = cliente().get("/salud")

    assert r.status_code == 200
    assert r.json()["status"] == "ok"


# --- Escenario 2 del enunciado: urgencia ----------------------------------

def test_el_caso_del_enunciado_devuelve_el_contrato_completo(cliente):
    r = cliente().post("/triaje", json=_solicitud())

    assert r.status_code == 200
    cuerpo = r.json()

    assert set(cuerpo) == {
        "status",
        "documento_id",
        "clasificacion",
        "datos_extraidos",
        "decision_enrutamiento",
        "almacenamiento_oci",
    }
    assert cuerpo["documento_id"] == "DOC-CLIN-2026-8942"
    assert cuerpo["clasificacion"]["nivel_prioridad"] == "Urgente"
    assert cuerpo["datos_extraidos"]["paciente"]["nombre"] == "Carlos Eduardo Mendes"
    assert cuerpo["datos_extraidos"]["cie10_sugerido"] == "I26.9"
    assert (
        cuerpo["decision_enrutamiento"]["destino_principal"]
        == "Cola_Emergencia_Medica"
    )
    assert cuerpo["decision_enrutamiento"]["notificacion_generada"] is not None
    assert cuerpo["decision_enrutamiento"]["justificacion_enrutamiento"].strip()


def test_el_caso_urgente_se_persiste_en_el_prefijo_de_urgentes(cliente, almacen):
    r = cliente().post("/triaje", json=_solicitud())

    ruta = r.json()["almacenamiento_oci"]["ruta_objeto"]
    assert ruta == "procesados/urgentes/DOC-CLIN-2026-8942.json"
    assert r.json()["almacenamiento_oci"]["status_backup"] == "exito"

    guardado = almacen.leer_texto("procesados/urgentes", "DOC-CLIN-2026-8942.json")
    assert guardado is not None
    # Lo persistido es exactamente lo que vio el cliente.
    assert json.loads(guardado) == r.json()


def test_el_documento_original_queda_en_recibidos(cliente, almacen):
    cliente().post("/triaje", json=_solicitud())

    assert almacen.leer_texto("recibidos", "DOC-CLIN-2026-8942.txt") == TEXTO_TEP


# --- Escenario 1 del enunciado: rutina ------------------------------------

def test_un_caso_de_rutina_va_al_prefijo_de_rutina(cliente):
    r = cliente(
        clasificador=ClasificadorDoble(
            ClassificationResult(document_type="orden_procedimiento", confidence=0.96)
        ),
        extractor=ExtractorDoble(
            ExtractedData(
                patient=Patient(name="Ana Gomez", age=31),
                procedure="Hemograma completo ambulatorio",
            )
        ),
    ).post("/triaje", json=_solicitud(documento_id="DOC-RUT-1", canal_origen="Recepcion"))

    cuerpo = r.json()
    assert cuerpo["clasificacion"]["nivel_prioridad"] == "Rutina"
    assert (
        cuerpo["decision_enrutamiento"]["destino_principal"]
        == "Auditoria_Autorizaciones"
    )
    assert cuerpo["decision_enrutamiento"]["requiere_auditoria_humana"] is False
    assert cuerpo["almacenamiento_oci"]["ruta_objeto"].startswith("procesados/rutina/")


# --- Escenario 3 del enunciado: ambiguedad --------------------------------

def test_la_confianza_baja_va_a_auditoria_humana(cliente):
    r = cliente(
        clasificador=ClasificadorDoble(
            ClassificationResult(document_type="receta_medica", confidence=0.35)
        ),
        extractor=ExtractorDoble(ExtractedData(patient=Patient(name="Luis Paredes"))),
    ).post("/triaje", json=_solicitud(documento_id="DOC-AMB-1", canal_origen="Recepcion"))

    cuerpo = r.json()
    assert cuerpo["status"] == "derivado_revision_humana"
    assert cuerpo["decision_enrutamiento"]["destino_principal"] == "Cola_Revision_Humana"
    assert cuerpo["decision_enrutamiento"]["requiere_auditoria_humana"] is True
    assert cuerpo["almacenamiento_oci"]["ruta_objeto"].startswith("auditoria_humana/")
    # Los campos que no se pudieron leer viajan como null, no se omiten.
    assert cuerpo["datos_extraidos"]["cie10_sugerido"] is None


# --- Contingencias --------------------------------------------------------

def test_si_el_modelo_falla_el_caso_escala_y_no_se_aprueba_solo(cliente):
    r = cliente(
        clasificador=ClasificadorDoble(error=RuntimeError("cuota agotada"))
    ).post("/triaje", json=_solicitud(documento_id="DOC-ERR-1"))

    assert r.status_code == 200, "un fallo del modelo no puede tumbar la API"
    cuerpo = r.json()

    assert cuerpo["status"] == "error"
    assert cuerpo["decision_enrutamiento"]["requiere_auditoria_humana"] is True
    assert "modelo" in cuerpo["decision_enrutamiento"]["justificacion_enrutamiento"].lower()


def test_un_pdf_en_el_endpoint_de_texto_redirige_al_de_archivos(cliente):
    r = cliente().post(
        "/triaje",
        json=_solicitud(tipo_archivo="PDF", documento_texto=None),
    )

    assert r.status_code == 400
    assert "/triaje/archivo" in r.json()["detail"]


def test_un_texto_vacio_se_rechaza_antes_de_llamar_al_modelo(cliente):
    r = cliente().post("/triaje", json=_solicitud(documento_texto="   "))

    assert r.status_code == 422


def test_un_formato_inexistente_se_rechaza(cliente):
    r = cliente().post("/triaje", json=_solicitud(tipo_archivo="DOCX"))

    assert r.status_code == 422


def test_falta_un_campo_obligatorio(cliente):
    r = cliente().post("/triaje", json={"tipo_archivo": "TEXTO"})

    assert r.status_code == 422


# --- Endpoint de archivos (tarea 2.1) -------------------------------------

def _subir(cli, datos: bytes, tipo="PDF", nombre="doc.pdf", documento_id="DOC-PDF-1"):
    return cli.post(
        "/triaje/archivo",
        data={
            "documento_id": documento_id,
            "tipo_archivo": tipo,
            "canal_origen": "Recepcion",
        },
        files={"archivo": (nombre, datos, "application/octet-stream")},
    )


def test_un_pdf_nativo_se_procesa_y_devuelve_el_mismo_contrato(cliente):
    pdf = construir_pdf(
        [
            "HOSPITAL SANTA LUCIA",
            "Paciente: Carlos Eduardo Mendes, 52 anos",
            "CONCLUSION: Cuadro compatible con Tromboembolismo Pulmonar Agudo.",
        ]
    )

    r = _subir(cliente(), pdf)

    assert r.status_code == 200
    cuerpo = r.json()
    assert set(cuerpo) == {
        "status",
        "documento_id",
        "clasificacion",
        "datos_extraidos",
        "decision_enrutamiento",
        "almacenamiento_oci",
    }
    assert cuerpo["documento_id"] == "DOC-PDF-1"


def test_el_pdf_original_se_archiva_tal_como_llego(cliente, almacen):
    pdf = construir_pdf(["Informe de laboratorio ambulatorio de rutina completo"])

    _subir(cliente(), pdf)

    assert almacen.leer_binario("recibidos", "DOC-PDF-1.pdf") == pdf


def test_una_imagen_se_procesa_por_el_mismo_endpoint(cliente):
    r = _subir(cliente(), construir_imagen(), tipo="IMAGEN", nombre="receta.png")

    assert r.status_code == 200
    assert r.json()["documento_id"] == "DOC-PDF-1"


def test_una_transcripcion_ilegible_deriva_a_auditoria_humana(cliente):
    # Escenario 3 del enunciado, de punta a punta: foto de receta con la dosis
    # ilegible. Tiene que terminar en auditoria_humana/, no en farmacia.
    cli = cliente(
        clasificador=ClasificadorDoble(
            ClassificationResult(document_type="receta_medica", confidence=0.95)
        ),
        extractor=ExtractorDoble(ExtractedData(patient=Patient(name="Luis Paredes"))),
        transcripcion="Amoxicilina [ilegible] mg cada 8 horas",
    )

    r = _subir(cli, construir_imagen(), tipo="IMAGEN", nombre="receta.png")

    cuerpo = r.json()
    assert cuerpo["decision_enrutamiento"]["destino_principal"] == "Cola_Revision_Humana"
    assert cuerpo["decision_enrutamiento"]["requiere_auditoria_humana"] is True
    assert cuerpo["almacenamiento_oci"]["ruta_objeto"].startswith("auditoria_humana/")


def test_un_archivo_ilegible_escala_en_vez_de_devolver_un_triaje_vacio(cliente):
    r = _subir(cliente(), b"esto no es un pdf")

    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["status"] == "error"
    assert cuerpo["decision_enrutamiento"]["requiere_auditoria_humana"] is True
    assert "No se pudo leer" in cuerpo["decision_enrutamiento"]["justificacion_enrutamiento"]


def test_un_archivo_vacio_se_rechaza(cliente):
    assert _subir(cliente(), b"").status_code == 422


def test_un_tipo_invalido_en_el_endpoint_de_archivos_se_rechaza(cliente):
    assert _subir(cliente(), b"%PDF-1.4", tipo="TEXTO").status_code == 422


def test_un_archivo_demasiado_grande_se_rechaza(cliente):
    from mediflow_agent.api.app import MAXIMO_BYTES_SUBIDA

    r = _subir(cliente(), b"x" * (MAXIMO_BYTES_SUBIDA + 1))

    assert r.status_code == 413


# --- Rendimiento (tarea 1.3, requisito clinico) ---------------------------

def test_la_clasificacion_y_la_extraccion_corren_en_paralelo(almacen):
    """El requisito es resolver un documento en 10 segundos o menos.

    El extractor generico no necesita el tipo de documento, asi que las dos
    llamadas al modelo pueden salir a la vez. Con dobles que duermen medio
    segundo cada uno, en serie tardaria 1 segundo y en paralelo medio.

    Esta prueba falla si alguien vuelve a encadenarlas.
    """
    import time

    class Lento:
        def __init__(self, resultado):
            self._resultado = resultado

        def _dormir(self, _texto):
            time.sleep(0.5)
            return self._resultado

        classify = _dormir
        extract = _dormir

    servicio = ServicioTriaje(
        clasificador=Lento(
            ClassificationResult(document_type="receta_medica", confidence=0.9)
        ),
        extractor=Lento(ExtractedData()),
        almacenamiento=almacen,
    )

    inicio = time.perf_counter()
    servicio.procesar(
        SolicitudTriaje(
            documento_id="DOC-TIEMPO",
            tipo_archivo="TEXTO",
            documento_texto="texto de prueba",
            canal_origen="Recepcion",
        )
    )
    transcurrido = time.perf_counter() - inicio

    assert transcurrido < 0.9, (
        f"tardo {transcurrido:.2f}s: las llamadas al modelo volvieron a ser "
        "secuenciales"
    )


def test_el_presupuesto_de_tiempo_esta_declarado():
    # El numero vive en un solo lugar y es un requisito clinico, no un
    # detalle de implementacion.
    from mediflow_agent.modelos import PRESUPUESTO_SEGUNDOS

    assert PRESUPUESTO_SEGUNDOS == 10.0
