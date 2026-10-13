"""El diferencial del enunciado: cambiar el enrutamiento sin tocar codigo.

    "Flujo Clinico Personalizable por el Usuario: Modulo o interfaz que
     permita al gestor hospitalario configurar reglas de triaje
     personalizadas, NUEVOS DESTINOS DE ENRUTAMIENTO y umbrales de urgencia
     sin modificar el codigo fuente."

El defecto que estas pruebas atajan: `config/triaje.toml` traia una seccion
`[destinos]` documentada como si funcionara, y ningun punto del codigo la
leia. Editar el archivo no cambiaba nada. Un evaluador que probara el
diferencial no habria visto ningun efecto.
"""

import textwrap

import pytest

from mediflow_agent.routing.baseline import (
    DESTINOS_POR_DEFECTO,
    destinos_configurados,
)


def _archivo(tmp_path, contenido):
    ruta = tmp_path / "triaje.toml"
    ruta.write_text(textwrap.dedent(contenido), encoding="utf-8")
    return ruta


def test_el_archivo_manda_sobre_los_valores_por_defecto(tmp_path):
    ruta = _archivo(
        tmp_path,
        """
        [destinos]
        receta_medica = "Auditoria_Autorizaciones"
        """,
    )

    mapa = destinos_configurados(ruta)

    # Cambiado por el gestor, sin tocar una linea de Python.
    assert mapa["receta_medica"] == "Auditoria_Autorizaciones"
    assert DESTINOS_POR_DEFECTO["receta_medica"] == "Farmacia_Hospitalaria"


def test_un_tipo_que_no_figura_en_el_archivo_se_queda_sin_ruta(tmp_path):
    # Y por lo tanto escala a revision humana en el grafo. Es la forma que
    # tiene el gestor de desactivar una ruta automatica hacia un destino que
    # todavia no esta listo para recibir documentos sin supervision.
    ruta = _archivo(
        tmp_path,
        """
        [destinos]
        receta_medica = "Farmacia_Hospitalaria"
        """,
    )

    mapa = destinos_configurados(ruta)

    assert "orden_procedimiento" not in mapa


def test_sin_seccion_de_destinos_se_usan_los_valores_por_defecto(tmp_path):
    ruta = _archivo(
        tmp_path,
        """
        [confianza]
        umbral = 0.70
        """,
    )

    assert destinos_configurados(ruta) == DESTINOS_POR_DEFECTO


def test_un_archivo_inexistente_no_deja_al_sistema_sin_rutas(tmp_path):
    assert destinos_configurados(tmp_path / "no-existe.toml") == DESTINOS_POR_DEFECTO


def test_un_destino_mal_escrito_se_descarta_sin_tumbar_el_arranque(tmp_path, caplog):
    # Un error de tipeo en un TOML no puede dejar sin triaje a una guardia.
    ruta = _archivo(
        tmp_path,
        """
        [destinos]
        receta_medica = "Farmacia_Hospitalaria"
        orden_procedimiento = "Farmacia_Hospitalria"
        """,
    )

    mapa = destinos_configurados(ruta)

    assert mapa == {"receta_medica": "Farmacia_Hospitalaria"}
    assert "Farmacia_Hospitalria" in caplog.text


def test_el_archivo_entregado_cubre_todos_los_tipos_clasificables():
    # Si alguien agrega un tipo al Literal y se olvida del TOML, los
    # documentos de ese tipo empiezan a escalar en silencio.
    from typing import get_args

    from mediflow_agent.schemas.models import DocumentType

    tipos = set(get_args(DocumentType)) - {"desconocido"}

    assert set(destinos_configurados()) == tipos


@pytest.mark.parametrize(
    "tipo,destino",
    sorted(DESTINOS_POR_DEFECTO.items()),
)
def test_el_archivo_entregado_coincide_con_los_valores_por_defecto(tipo, destino):
    # No es redundante: si el archivo entregado se desviara de los valores del
    # codigo, el comportamiento real dejaria de ser el que documenta el README.
    assert destinos_configurados()[tipo] == destino
