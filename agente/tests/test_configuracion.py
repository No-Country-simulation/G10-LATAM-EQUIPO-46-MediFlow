"""Reglas de triaje editables desde la pantalla (diferencial del enunciado).

Lo que estas pruebas protegen, por encima de todo: que **nadie sin la clave
pueda cambiar las reglas**. La pagina esta abierta a internet sin contraseña,
y una escritura libre dejaria a cualquiera con el enlace poner el umbral en
cero y desactivar la revision humana de todo el sistema.
"""

import textwrap

import pytest
from fastapi.testclient import TestClient

from mediflow_agent.api import configuracion as cfg
from mediflow_agent.api.app import app
from mediflow_agent.config import olvidar_archivo

CLAVE = "clave-de-prueba-123"


@pytest.fixture
def archivo(tmp_path, monkeypatch):
    """Un triaje.toml propio, para no tocar el del repositorio."""
    ruta = tmp_path / "triaje.toml"
    ruta.write_text(
        textwrap.dedent(
            """
            [confianza]
            umbral = 0.70

            [urgencia]
            usar_lista = true
            usar_modelo = true
            canales_prioritarios = ["guardia_emergencias"]

            [destinos]
            receta_medica = "Farmacia_Hospitalaria"
            orden_procedimiento = "Auditoria_Autorizaciones"
            informe_estudio_diagnostico = "Historia_Clinica_Electronica"
            epicrisis = "Historia_Clinica_Electronica"
            certificado_medico = "Historia_Clinica_Electronica"
            """
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(cfg, "ARCHIVO_TRIAJE", ruta)
    monkeypatch.setattr("mediflow_agent.config.ARCHIVO_TRIAJE", ruta)

    # El .env del desarrollador puede traer un umbral forzado, que tiene
    # precedencia sobre el archivo. Sin esto, las pruebas medirian su maquina
    # en lugar del comportamiento.
    monkeypatch.delenv("MEDIFLOW_UMBRAL_CONFIANZA", raising=False)

    olvidar_archivo()
    yield ruta
    olvidar_archivo()


@pytest.fixture
def cliente(archivo):
    return TestClient(app)


@pytest.fixture
def con_clave(monkeypatch):
    monkeypatch.setenv("MEDIFLOW_ADMIN_CLAVE", CLAVE)


@pytest.fixture
def sin_clave(monkeypatch):
    monkeypatch.delenv("MEDIFLOW_ADMIN_CLAVE", raising=False)


def _reglas(**cambios):
    base = {
        "umbral_confianza": 0.70,
        "canales_prioritarios": ["guardia_emergencias"],
        "destinos": dict(cfg.DESTINOS_POR_DEFECTO),
    }
    base.update(cambios)
    return base


# --- lectura --------------------------------------------------------------

def test_cualquiera_puede_ver_las_reglas_vigentes(cliente, sin_clave):
    # Leer no expone nada sensible: son umbrales y nombres de departamento.
    respuesta = cliente.get("/configuracion")

    assert respuesta.status_code == 200

    cuerpo = respuesta.json()
    assert cuerpo["reglas"]["umbral_confianza"] == 0.70
    assert "Farmacia_Hospitalaria" in cuerpo["destinos_validos"]


def test_sin_clave_la_pantalla_se_declara_de_solo_lectura(cliente, sin_clave):
    assert cliente.get("/configuracion").json()["editable"] is False


def test_con_clave_la_pantalla_se_declara_editable(cliente, con_clave):
    assert cliente.get("/configuracion").json()["editable"] is True


def test_la_respuesta_no_filtra_la_clave(cliente, con_clave):
    # El panel dice SI se puede editar, nunca CON QUE.
    assert CLAVE not in cliente.get("/configuracion").text


# --- escritura: lo que no puede pasar -------------------------------------

def test_sin_clave_en_el_servidor_nadie_puede_escribir(cliente, sin_clave):
    respuesta = cliente.put("/configuracion", json=_reglas(umbral_confianza=0.0))

    assert respuesta.status_code == 403
    assert "solo lectura" in respuesta.json()["detail"]


def test_sin_enviar_la_clave_se_rechaza(cliente, con_clave):
    respuesta = cliente.put("/configuracion", json=_reglas(umbral_confianza=0.0))

    assert respuesta.status_code == 401


def test_con_la_clave_equivocada_se_rechaza(cliente, con_clave):
    respuesta = cliente.put(
        "/configuracion",
        json=_reglas(umbral_confianza=0.0),
        headers={"X-Admin-Clave": "otra-cosa"},
    )

    assert respuesta.status_code == 401


def test_un_rechazo_no_toca_el_archivo(cliente, con_clave, archivo):
    antes = archivo.read_text(encoding="utf-8")

    cliente.put("/configuracion", json=_reglas(umbral_confianza=0.0))

    assert archivo.read_text(encoding="utf-8") == antes


# --- escritura: lo que si debe pasar --------------------------------------

def test_con_la_clave_correcta_se_guarda(cliente, con_clave, archivo):
    respuesta = cliente.put(
        "/configuracion",
        json=_reglas(umbral_confianza=0.85),
        headers={"X-Admin-Clave": CLAVE},
    )

    assert respuesta.status_code == 200
    assert respuesta.json()["reglas"]["umbral_confianza"] == 0.85
    assert "umbral = 0.85" in archivo.read_text(encoding="utf-8")


def test_el_cambio_rige_sin_reiniciar(cliente, con_clave):
    # El punto de todo el ejercicio. Si esto falla, la pantalla muestra una
    # cosa y el agente usa otra hasta el proximo reinicio.
    from mediflow_agent.routing.baseline import destinos_configurados

    assert destinos_configurados()["receta_medica"] == "Farmacia_Hospitalaria"

    nuevos = dict(cfg.DESTINOS_POR_DEFECTO)
    nuevos["receta_medica"] = "Auditoria_Autorizaciones"

    cliente.put(
        "/configuracion",
        json=_reglas(destinos=nuevos),
        headers={"X-Admin-Clave": CLAVE},
    )

    assert destinos_configurados()["receta_medica"] == "Auditoria_Autorizaciones"


def test_quitar_un_tipo_lo_deja_sin_ruta_automatica(cliente, con_clave):
    from mediflow_agent.routing.baseline import destinos_configurados

    parcial = {
        t: d for t, d in cfg.DESTINOS_POR_DEFECTO.items() if t != "receta_medica"
    }

    cliente.put(
        "/configuracion",
        json=_reglas(destinos=parcial),
        headers={"X-Admin-Clave": CLAVE},
    )

    assert "receta_medica" not in destinos_configurados()


def test_los_canales_se_guardan_normalizados(cliente, con_clave):
    # El grafo compara en minuscula y sin espacios. Guardar
    # "Guardia Emergencias" tal cual dejaria la regla escrita pero sin efecto.
    respuesta = cliente.put(
        "/configuracion",
        json=_reglas(canales_prioritarios=["Guardia Emergencias", "  URGENCIAS "]),
        headers={"X-Admin-Clave": CLAVE},
    )

    assert respuesta.json()["reglas"]["canales_prioritarios"] == [
        "guardia_emergencias",
        "urgencias",
    ]


def test_lo_que_la_pantalla_no_toca_sobrevive_al_guardado(cliente, con_clave, archivo):
    cliente.put(
        "/configuracion",
        json=_reglas(umbral_confianza=0.9),
        headers={"X-Admin-Clave": CLAVE},
    )

    texto = archivo.read_text(encoding="utf-8")
    assert "usar_lista = true" in texto
    assert "usar_modelo = true" in texto


# --- validacion -----------------------------------------------------------

@pytest.mark.parametrize("umbral", [-0.1, 1.5])
def test_un_umbral_fuera_de_rango_se_rechaza(cliente, con_clave, umbral):
    respuesta = cliente.put(
        "/configuracion",
        json=_reglas(umbral_confianza=umbral),
        headers={"X-Admin-Clave": CLAVE},
    )

    assert respuesta.status_code == 422


def test_un_destino_inexistente_se_rechaza(cliente, con_clave, archivo):
    antes = archivo.read_text(encoding="utf-8")

    respuesta = cliente.put(
        "/configuracion",
        json=_reglas(destinos={"receta_medica": "Deposito_Central"}),
        headers={"X-Admin-Clave": CLAVE},
    )

    assert respuesta.status_code == 422
    # Y el archivo quedo intacto: se valida ANTES de escribir.
    assert archivo.read_text(encoding="utf-8") == antes


def test_un_tipo_de_documento_inexistente_se_rechaza(cliente, con_clave):
    respuesta = cliente.put(
        "/configuracion",
        json=_reglas(destinos={"radiografia": "Historia_Clinica_Electronica"}),
        headers={"X-Admin-Clave": CLAVE},
    )

    assert respuesta.status_code == 422


# --- precedencia del entorno ----------------------------------------------

def test_un_umbral_forzado_por_entorno_se_declara_bloqueado(
    cliente, con_clave, monkeypatch
):
    # Sin este aviso la pantalla mentiria: guardaria el valor nuevo en el
    # archivo y el agente seguiria usando el del entorno.
    monkeypatch.setenv("MEDIFLOW_UMBRAL_CONFIANZA", "0.55")

    cuerpo = cliente.get("/configuracion").json()

    assert cuerpo["bloqueados_por_entorno"] == ["umbral_confianza"]
    assert cuerpo["reglas"]["umbral_confianza"] == 0.55


def test_sin_variable_de_entorno_no_hay_campos_bloqueados(cliente, con_clave):
    assert cliente.get("/configuracion").json()["bloqueados_por_entorno"] == []
