"""Pruebas de `AlmacenamientoOciPar`.

Usan un doble de la sesion HTTP: no tocan la red ni el bucket real.

La prueba que mas importa es `test_el_token_nunca_aparece_en_un_error`. El PAR
va dentro de la URL, y las excepciones de la libreria HTTP incluyen la URL en
su mensaje. Sin ocultarlo, la credencial del bucket termina escrita en los
logs de la aplicacion.
"""

import pytest

from mediflow_agent.storage.base import (
    PREFIJO_AUDITORIA,
    PREFIJO_RECIBIDOS,
    PREFIJO_RUTINA,
    AlmacenamientoDocumentos,
)
from mediflow_agent.storage.oci_par import (
    AlmacenamientoOciPar,
    ErrorDeConfiguracionPar,
)

TOKEN = "TOKENsecretoDePrueba123"
PAR = (
    "https://objectstorage.sa-saopaulo-1.oraclecloud.com"
    f"/p/{TOKEN}/n/espacio-de-prueba/b/bucket-de-prueba/o/"
)


class RespuestaDoble:
    def __init__(self, status_code=200, content=b"", payload=None):
        self.status_code = status_code
        self.content = content
        self._payload = payload

    def json(self):
        return self._payload


class SesionDoble:
    """Doble de requests.Session que guarda los objetos en memoria."""

    def __init__(self, error=None, estado_put=200):
        self.objetos: dict[str, bytes] = {}
        self.tipos: dict[str, str] = {}
        self._error = error
        self._estado_put = estado_put

    def put(self, url, data=None, headers=None, timeout=None):
        if self._error:
            raise self._error

        if self._estado_put not in (200, 201):
            return RespuestaDoble(status_code=self._estado_put)

        self.objetos[url] = data
        self.tipos[url] = (headers or {}).get("Content-Type", "")
        return RespuestaDoble(status_code=self._estado_put)

    def get(self, url, timeout=None):
        if self._error:
            raise self._error

        if url.endswith("/o/"):
            nombres = [u.split("/o/", 1)[1] for u in self.objetos]
            return RespuestaDoble(payload={"objects": [{"name": n} for n in nombres]})

        if url not in self.objetos:
            return RespuestaDoble(status_code=404)

        return RespuestaDoble(content=self.objetos[url])


@pytest.fixture
def sesion() -> SesionDoble:
    return SesionDoble()


@pytest.fixture
def almacen(sesion) -> AlmacenamientoOciPar:
    return AlmacenamientoOciPar(url_par=PAR, sesion=sesion)


# --- Configuracion --------------------------------------------------------

def test_cumple_la_misma_interfaz(almacen):
    assert isinstance(almacen, AlmacenamientoDocumentos)


def test_los_datos_del_bucket_salen_del_propio_par(almacen):
    assert almacen.bucket == "bucket-de-prueba"
    assert almacen.namespace == "espacio-de-prueba"
    assert almacen.region == "sa-saopaulo-1"


def test_sin_par_falla_al_construir(monkeypatch):
    monkeypatch.delenv("MEDIFLOW_OCI_PAR", raising=False)

    with pytest.raises(ErrorDeConfiguracionPar, match="Falta MEDIFLOW_OCI_PAR"):
        AlmacenamientoOciPar()


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/p/x/n/a/b/c/o/",
        "https://objectstorage.sa-saopaulo-1.oraclecloud.com/p/tok/n/a/b/c",
        "no-es-una-url",
    ],
)
def test_una_url_que_no_es_un_par_falla(url):
    with pytest.raises(ErrorDeConfiguracionPar, match="forma de un PAR"):
        AlmacenamientoOciPar(url_par=url)


def test_el_error_de_formato_no_repite_la_url():
    # El mensaje de error no puede incluir la URL: lleva el token adentro.
    try:
        AlmacenamientoOciPar(url_par=f"https://example.com/p/{TOKEN}/x")
    except ErrorDeConfiguracionPar as err:
        assert TOKEN not in str(err)


# --- Subida y descarga ----------------------------------------------------

def test_lo_guardado_se_puede_leer(almacen):
    resultado = almacen.guardar_texto(PREFIJO_RUTINA, "DOC-1.json", '{"a": 1}')

    assert resultado.exito is True
    assert resultado.ruta_objeto == "procesados/rutina/DOC-1.json"
    assert resultado.bucket == "bucket-de-prueba"
    assert almacen.leer_texto(PREFIJO_RUTINA, "DOC-1.json") == '{"a": 1}'


def test_un_binario_sobrevive_intacto(almacen):
    datos = bytes(range(256))

    assert almacen.guardar_binario(PREFIJO_RECIBIDOS, "DOC-1.pdf", datos).exito
    assert almacen.leer_binario(PREFIJO_RECIBIDOS, "DOC-1.pdf") == datos


def test_se_conservan_los_acentos(almacen):
    almacen.guardar_texto(PREFIJO_RUTINA, "a.json", '{"nombre": "José Muñoz"}')

    assert "José Muñoz" in almacen.leer_texto(PREFIJO_RUTINA, "a.json")


def test_el_objeto_va_bajo_su_prefijo_de_estado(almacen, sesion):
    almacen.guardar_texto(PREFIJO_AUDITORIA, "DOC-9.json", "{}")

    assert any(u.endswith("/o/auditoria_humana/DOC-9.json") for u in sesion.objetos)


def test_se_declara_el_tipo_de_contenido(almacen, sesion):
    almacen.guardar_binario(PREFIJO_RECIBIDOS, "a.pdf", b"%PDF", "application/pdf")

    assert "application/pdf" in sesion.tipos.values()


def test_leer_algo_que_no_existe_devuelve_none(almacen):
    assert almacen.leer_texto(PREFIJO_RUTINA, "no-existe.json") is None


# --- Seguridad ------------------------------------------------------------

def test_el_token_nunca_aparece_en_un_error():
    # Las excepciones de requests incluyen la URL completa, y la URL ES la
    # credencial. Si no se oculta, el PAR del bucket queda en los logs.
    rota = SesionDoble(error=RuntimeError(f"fallo al conectar a {PAR}"))
    almacen = AlmacenamientoOciPar(url_par=PAR, sesion=rota)

    resultado = almacen.guardar_texto(PREFIJO_RUTINA, "DOC-1.json", "{}")

    assert resultado.exito is False
    assert TOKEN not in resultado.detalle_error
    assert "<PAR-OCULTO>" in resultado.detalle_error


@pytest.mark.parametrize("nombre", ["../fuga.json", "sub/DOC.json", "..", ""])
def test_un_nombre_que_no_es_un_segmento_simple_se_rechaza(almacen, sesion, nombre):
    assert almacen.guardar_texto(PREFIJO_RUTINA, nombre, "{}").exito is False
    assert sesion.objetos == {}


# --- Contingencias --------------------------------------------------------

def test_un_fallo_de_red_no_lanza_excepcion():
    # El triaje ya se resolvio cuando se intenta guardar.
    rota = SesionDoble(error=RuntimeError("timeout"))
    almacen = AlmacenamientoOciPar(url_par=PAR, sesion=rota)

    assert almacen.guardar_texto(PREFIJO_RUTINA, "DOC-1.json", "{}").exito is False


def test_un_par_vencido_se_reporta_como_fallo_de_respaldo():
    # Un PAR caducado responde 404 en la escritura. No puede tumbar el triaje.
    vencida = SesionDoble(estado_put=404)
    almacen = AlmacenamientoOciPar(url_par=PAR, sesion=vencida)

    resultado = almacen.guardar_texto(PREFIJO_RUTINA, "DOC-1.json", "{}")

    assert resultado.exito is False
    assert "404" in resultado.detalle_error


def test_listar_devuelve_los_objetos(almacen):
    almacen.guardar_texto(PREFIJO_RUTINA, "DOC-1.json", "{}")

    assert almacen.listar() == ["procesados/rutina/DOC-1.json"]
