"""Pruebas del almacenamiento.

Son el criterio de aceptacion de la tarea 1.2: cuando exista `AlmacenamientoOci`,
estas mismas pruebas tienen que pasar contra esa implementacion cambiando solo
como se construye el objeto. La prueba de subida y descarga que pide el
enunciado es `test_lo_guardado_se_puede_leer`.
"""

import pytest

from mediflow_agent.storage.base import PREFIJO_RUTINA, AlmacenamientoDocumentos
from mediflow_agent.storage.local import AlmacenamientoLocal


@pytest.fixture
def almacen(tmp_path) -> AlmacenamientoLocal:
    return AlmacenamientoLocal(tmp_path, nombre_bucket="bucket-de-prueba")


def test_cumple_la_interfaz(almacen):
    assert isinstance(almacen, AlmacenamientoDocumentos)
    assert almacen.bucket == "bucket-de-prueba"


def test_lo_guardado_se_puede_leer(almacen):
    resultado = almacen.guardar_texto(
        prefijo=PREFIJO_RUTINA,
        nombre_objeto="DOC-1.json",
        contenido='{"status": "procesado"}',
    )

    assert resultado.exito is True
    assert resultado.ruta_objeto == "procesados/rutina/DOC-1.json"
    assert resultado.bucket == "bucket-de-prueba"

    assert almacen.leer_texto(PREFIJO_RUTINA, "DOC-1.json") == '{"status": "procesado"}'


def test_leer_algo_que_no_existe_devuelve_none(almacen):
    assert almacen.leer_texto(PREFIJO_RUTINA, "no-existe.json") is None


def test_se_conservan_los_acentos(almacen):
    almacen.guardar_texto(PREFIJO_RUTINA, "a.json", '{"nombre": "José Ramírez"}')

    assert "José Ramírez" in almacen.leer_texto(PREFIJO_RUTINA, "a.json")


def test_los_prefijos_se_crean_solos(almacen, tmp_path):
    almacen.guardar_texto("procesados/urgentes", "x.json", "{}")

    assert (tmp_path / "procesados" / "urgentes" / "x.json").is_file()


@pytest.mark.parametrize(
    "nombre",
    [
        "../../../escape.json",   # sale del almacen entero
        "../../escape.json",      # queda en el almacen pero fuera del prefijo
        "sub/DOC-1.json",         # inventa un nivel que no existe
        "..",
        "",
    ],
)
def test_un_nombre_de_objeto_que_no_es_un_segmento_simple_se_rechaza(
    almacen, tmp_path, nombre
):
    # El nombre del objeto sale del documento_id, que es entrada externa.
    # Un nombre con separadores puede dejar el documento fuera del prefijo de
    # estado que le corresponde, y eso rompe la segregacion que exige el
    # enunciado aunque el archivo siga dentro del bucket.
    resultado = almacen.guardar_texto(PREFIJO_RUTINA, nombre, "{}")

    assert resultado.exito is False
    assert not (tmp_path / "escape.json").exists()
    assert not (tmp_path.parent / "escape.json").exists()


def test_solo_se_escribe_dentro_del_prefijo_pedido(almacen, tmp_path):
    almacen.guardar_texto(PREFIJO_RUTINA, "DOC-1.json", "{}")

    escritos = [p for p in tmp_path.rglob("*") if p.is_file()]
    assert escritos == [tmp_path / "procesados" / "rutina" / "DOC-1.json"]


def test_un_fallo_al_guardar_no_lanza_excepcion(tmp_path):
    # El triaje ya se resolvio cuando se intenta guardar. Un almacen caido se
    # reporta, no tumba la respuesta.
    archivo = tmp_path / "ocupado"
    archivo.write_text("no soy un directorio", encoding="utf-8")

    almacen = AlmacenamientoLocal(archivo)
    resultado = almacen.guardar_texto(PREFIJO_RUTINA, "DOC-1.json", "{}")

    assert resultado.exito is False
    assert resultado.detalle_error


# --- Binarios (documento original en PDF o imagen) ------------------------

def test_un_binario_se_guarda_y_se_lee_igual(almacen):
    datos = bytes(range(256))

    resultado = almacen.guardar_binario("recibidos", "DOC-1.pdf", datos)

    assert resultado.exito is True
    assert almacen.leer_binario("recibidos", "DOC-1.pdf") == datos


def test_leer_un_binario_inexistente_devuelve_none(almacen):
    assert almacen.leer_binario("recibidos", "no-existe.pdf") is None


def test_el_binario_respeta_la_misma_validacion_de_nombre(almacen):
    assert almacen.guardar_binario("recibidos", "../fuga.pdf", b"x").exito is False
