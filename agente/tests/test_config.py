"""Pruebas de la lectura de configuracion.

Fijan el defecto que se encontro probando el endpoint contra Gemini: el
`.env.example` declara variables vacias para que se vean y se completen, y al
copiarlo quedaban definidas como cadena vacia. `os.getenv(nombre, defecto)`
solo usa el defecto cuando la variable NO existe, asi que el valor por defecto
dejaba de aplicarse en silencio.

El sintoma fue una respuesta del endpoint con `"bucket": ""`.
"""

import pytest

from mediflow_agent.config import numero, variable


# --- variable() -----------------------------------------------------------

def test_una_variable_definida_se_devuelve(monkeypatch):
    monkeypatch.setenv("MEDIFLOW_PRUEBA", "valor")

    assert variable("MEDIFLOW_PRUEBA", "defecto") == "valor"


def test_una_variable_ausente_cae_al_defecto(monkeypatch):
    monkeypatch.delenv("MEDIFLOW_PRUEBA", raising=False)

    assert variable("MEDIFLOW_PRUEBA", "defecto") == "defecto"


@pytest.mark.parametrize("vacia", ["", "   ", "\t", "\n"])
def test_una_variable_VACIA_tambien_cae_al_defecto(monkeypatch, vacia):
    # Este es el caso que os.getenv no cubre y que rompio el bucket.
    monkeypatch.setenv("MEDIFLOW_PRUEBA", vacia)

    assert variable("MEDIFLOW_PRUEBA", "defecto") == "defecto"


def test_se_recortan_los_espacios(monkeypatch):
    monkeypatch.setenv("MEDIFLOW_PRUEBA", "  valor  ")

    assert variable("MEDIFLOW_PRUEBA") == "valor"


def test_sin_defecto_devuelve_none(monkeypatch):
    monkeypatch.setenv("MEDIFLOW_PRUEBA", "")

    assert variable("MEDIFLOW_PRUEBA") is None


# --- numero() -------------------------------------------------------------

def test_un_numero_valido_se_convierte(monkeypatch):
    monkeypatch.setenv("MEDIFLOW_UMBRAL", "0.85")

    assert numero("MEDIFLOW_UMBRAL", 0.70) == 0.85


@pytest.mark.parametrize("malo", ["", "   ", "alto", "0,85"])
def test_un_numero_invalido_cae_al_defecto_en_vez_de_explotar(monkeypatch, malo):
    # Un umbral mal escrito en un .env no puede impedir que el sistema triee.
    monkeypatch.setenv("MEDIFLOW_UMBRAL", malo)

    assert numero("MEDIFLOW_UMBRAL", 0.70) == 0.70


# --- El caso real que lo destapo -----------------------------------------

def test_el_bucket_no_queda_vacio_con_un_env_recien_copiado(monkeypatch):
    # Reproduce el sintoma exacto: .env copiado del ejemplo, con la variable
    # declarada y vacia. La respuesta salia con "bucket": "".
    monkeypatch.setenv("MEDIFLOW_BUCKET", "")
    monkeypatch.setenv("MEDIFLOW_ALMACEN", "local")
    monkeypatch.setenv("MEDIFLOW_ALMACEN_LOCAL", "")

    from mediflow_agent.api.app import obtener_almacenamiento

    almacen = obtener_almacenamiento()

    assert almacen.bucket == "mediflow-documentos-clinicos"
    assert almacen.bucket != ""


def test_el_modelo_por_defecto_esta_en_un_solo_lugar():
    # Estaba repetido en cuatro modulos. Cuando Google retiro gemini-2.5-flash
    # habia que corregirlo en los cuatro, con el riesgo de olvidar uno.
    from pathlib import Path

    from mediflow_agent.modelos import MODELO_POR_DEFECTO

    assert MODELO_POR_DEFECTO

    fuente = Path(__file__).resolve().parent.parent / "src" / "mediflow_agent"
    codificados = [
        p.name
        for p in fuente.rglob("*.py")
        if p.name != "modelos.py" and "gemini-" in p.read_text(encoding="utf-8")
    ]

    assert not codificados, f"el modelo quedo escrito a mano en: {codificados}"
