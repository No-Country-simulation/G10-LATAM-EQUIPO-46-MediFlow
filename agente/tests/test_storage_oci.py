"""Pruebas de `AlmacenamientoOci`.

Usan un doble del cliente del SDK: no necesitan credenciales, no tocan el
bucket real y no gastan cuota de la capa Always Free.

La prueba que de verdad importa es `test_un_fallo_de_oci_no_lanza_excepcion`.
Cuando se intenta guardar, el triaje ya se resolvio: si el bucket no responde,
la respuesta clinica tiene que llegar igual al consumidor, con el fallo del
respaldo informado.
"""

import pytest

from mediflow_agent.storage.base import (
    PREFIJO_RECIBIDOS,
    PREFIJO_RUTINA,
    AlmacenamientoDocumentos,
)
from mediflow_agent.storage.oci_storage import AlmacenamientoOci


class RespuestaDoble:
    def __init__(self, contenido: bytes):
        self.data = type("Datos", (), {"content": contenido})()


class ClienteOciDoble:
    """Doble en memoria del ObjectStorageClient."""

    def __init__(self, error_al_guardar=None, error_al_leer=None):
        self.objetos: dict[str, bytes] = {}
        self.tipos: dict[str, str] = {}
        self.llamadas: list[tuple] = []
        self._error_al_guardar = error_al_guardar
        self._error_al_leer = error_al_leer

    def get_namespace(self):
        return type("R", (), {"data": "namespace-de-prueba"})()

    def put_object(
        self, namespace_name, bucket_name, object_name, put_object_body, **kwargs
    ):
        self.llamadas.append(("put", namespace_name, bucket_name, object_name))

        if self._error_al_guardar:
            raise self._error_al_guardar

        self.objetos[object_name] = put_object_body
        self.tipos[object_name] = kwargs.get("content_type", "")

    def get_object(self, namespace_name, bucket_name, object_name, **kwargs):
        import oci

        if self._error_al_leer:
            raise self._error_al_leer

        if object_name not in self.objetos:
            raise oci.exceptions.ServiceError(
                status=404, code="ObjectNotFound", headers={}, message="no existe"
            )

        return RespuestaDoble(self.objetos[object_name])


@pytest.fixture
def cliente() -> ClienteOciDoble:
    return ClienteOciDoble()


@pytest.fixture
def almacen(cliente) -> AlmacenamientoOci:
    return AlmacenamientoOci(
        nombre_bucket="bucket-de-prueba",
        namespace="namespace-de-prueba",
        cliente=cliente,
    )


# --- Contrato de la interfaz ---------------------------------------------

def test_cumple_la_misma_interfaz_que_el_almacen_local(almacen):
    assert isinstance(almacen, AlmacenamientoDocumentos)
    assert almacen.bucket == "bucket-de-prueba"


def test_el_namespace_se_consulta_una_sola_vez(cliente):
    almacen = AlmacenamientoOci(nombre_bucket="b", cliente=cliente)

    assert almacen.namespace == "namespace-de-prueba"


# --- Subida y descarga (lo que pide la tarea 1.2) -------------------------

def test_lo_guardado_se_puede_leer(almacen):
    resultado = almacen.guardar_texto(
        PREFIJO_RUTINA, "DOC-1.json", '{"status": "procesado"}'
    )

    assert resultado.exito is True
    assert resultado.ruta_objeto == "procesados/rutina/DOC-1.json"
    assert resultado.bucket == "bucket-de-prueba"

    assert almacen.leer_texto(PREFIJO_RUTINA, "DOC-1.json") == '{"status": "procesado"}'


def test_un_binario_se_guarda_y_se_lee_igual(almacen):
    datos = bytes(range(256))

    assert almacen.guardar_binario(PREFIJO_RECIBIDOS, "DOC-1.pdf", datos).exito is True
    assert almacen.leer_binario(PREFIJO_RECIBIDOS, "DOC-1.pdf") == datos


def test_se_conservan_los_acentos(almacen):
    almacen.guardar_texto(PREFIJO_RUTINA, "a.json", '{"nombre": "José Ramírez"}')

    assert "José Ramírez" in almacen.leer_texto(PREFIJO_RUTINA, "a.json")


def test_el_objeto_lleva_el_prefijo_de_estado_en_su_nombre(almacen, cliente):
    almacen.guardar_texto("procesados/urgentes", "DOC-9.json", "{}")

    assert "procesados/urgentes/DOC-9.json" in cliente.objetos


def test_se_declara_el_tipo_de_contenido(almacen, cliente):
    almacen.guardar_texto(PREFIJO_RUTINA, "a.json", "{}")
    almacen.guardar_binario(PREFIJO_RECIBIDOS, "a.pdf", b"%PDF", "application/pdf")

    assert cliente.tipos["procesados/rutina/a.json"] == "application/json"
    assert cliente.tipos["recibidos/a.pdf"] == "application/pdf"


def test_leer_algo_que_no_existe_devuelve_none(almacen):
    assert almacen.leer_texto(PREFIJO_RUTINA, "no-existe.json") is None
    assert almacen.leer_binario(PREFIJO_RUTINA, "no-existe.pdf") is None


# --- Contingencias --------------------------------------------------------

def test_un_fallo_de_oci_no_lanza_excepcion(cliente):
    # Cuando se intenta guardar, el triaje YA se resolvio. Un bucket caido se
    # informa; no puede tumbar una decision clinica ya tomada.
    roto = ClienteOciDoble(error_al_guardar=RuntimeError("503 Service Unavailable"))
    almacen = AlmacenamientoOci(
        nombre_bucket="b", namespace="n", cliente=roto
    )

    resultado = almacen.guardar_texto(PREFIJO_RUTINA, "DOC-1.json", "{}")

    assert resultado.exito is False
    assert "503" in resultado.detalle_error


def test_un_fallo_al_leer_devuelve_none_y_no_explota(cliente):
    roto = ClienteOciDoble(error_al_leer=RuntimeError("timeout"))
    almacen = AlmacenamientoOci(nombre_bucket="b", namespace="n", cliente=roto)

    assert almacen.leer_texto(PREFIJO_RUTINA, "DOC-1.json") is None


@pytest.mark.parametrize("nombre", ["../fuga.json", "sub/DOC.json", "..", ""])
def test_un_nombre_que_no_es_un_segmento_simple_se_rechaza(almacen, cliente, nombre):
    # Misma regla que el almacen local: un nombre con barras dejaria el objeto
    # fuera de su prefijo de estado y rompe la segregacion del enunciado.
    resultado = almacen.guardar_texto(PREFIJO_RUTINA, nombre, "{}")

    assert resultado.exito is False
    assert cliente.objetos == {}
