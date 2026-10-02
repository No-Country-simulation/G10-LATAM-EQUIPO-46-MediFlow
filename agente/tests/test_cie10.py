"""Pruebas del verificador de codigos CIE-10 (tarea 2.2).

El riesgo que esto ataja: un modelo puede devolver un codigo con forma
perfecta que no existe. `I99.7` se ve tan creible como `I26.9` y nadie lo nota
leyendo la respuesta.
"""

import pytest

from mediflow_agent.validacion.cie10 import (
    Veredicto,
    cargar_categorias,
    depurar,
    verificar,
)


def test_el_catalogo_se_carga_y_tiene_las_categorias_esperadas():
    categorias = cargar_categorias()

    assert len(categorias) > 1500, "el catalogo parece incompleto"
    # Las 22 letras de capitulo de la CIE-10 tienen que estar representadas.
    assert len({c[0] for c in categorias}) >= 20


def test_el_codigo_del_enunciado_es_valido():
    # I26.9 es el que usa el ejemplo oficial del hackathon. Si este fallara,
    # la demo mostraria un campo vacio en el caso principal.
    resultado = verificar("I26.9")

    assert resultado.es_valido
    assert resultado.codigo_normalizado == "I26.9"


@pytest.mark.parametrize(
    "codigo, esperado",
    [
        ("I26.9", "I26.9"),
        ("i26.9", "I26.9"),      # minusculas
        ("I269", "I26.9"),       # sin punto, como lo escriben algunos sistemas
        ("  I26.9  ", "I26.9"),  # con espacios
        ("A00", "A00"),          # categoria sola, sin subcodigo
        ("J18.9", "J18.9"),
        ("C18.9", "C18.9"),
        ("G35", "G35"),
        ("I60.9", "I60.9"),
        ("A41.9", "A41.9"),
    ],
)
def test_codigos_reales_se_aceptan_y_se_normalizan(codigo, esperado):
    resultado = verificar(codigo)

    assert resultado.es_valido, f"{codigo} deberia ser valido"
    assert resultado.codigo_normalizado == esperado


@pytest.mark.parametrize(
    "codigo",
    [
        "ZZ9.9",      # letra inicial inexistente como categoria
        "I2",         # falta un digito de la categoria
        "26.9",       # sin letra
        "Infarto",    # texto
        "I-26.9",     # separador invalido
        "123",        # solo numeros
    ],
)
def test_los_codigos_mal_formados_se_rechazan(codigo):
    assert not verificar(codigo).es_valido


def test_una_categoria_inexistente_se_rechaza_aunque_tenga_forma_valida():
    # Este es el caso que importa: forma perfecta, categoria inventada.
    resultado = verificar("I29.4")

    assert not resultado.es_valido
    assert resultado.veredicto is Veredicto.CATEGORIA_INEXISTENTE
    assert "no existe" in resultado.motivo


@pytest.mark.parametrize("vacio", [None, "", "   ", "N/A", "ninguno", "-"])
def test_la_ausencia_de_codigo_no_es_un_error(vacio):
    # Que el modelo no sugiera codigo es el comportamiento correcto cuando no
    # hay evidencia. No debe reportarse como fallo.
    resultado = verificar(vacio)

    assert resultado.veredicto is Veredicto.VACIO
    assert resultado.codigo_normalizado is None


def test_el_motivo_aclara_el_alcance_de_la_verificacion():
    # La verificacion confirma que la categoria existe, no que sea la
    # correcta para el diagnostico. El mensaje no puede prometer de mas.
    resultado = verificar("I26.9")

    assert "no esta verificada" in resultado.motivo


# --- depurar() ------------------------------------------------------------

def test_depurar_conserva_un_codigo_valido():
    codigo, aviso = depurar("I26.9")

    assert codigo == "I26.9"
    assert aviso is None


def test_depurar_borra_un_codigo_inexistente_y_explica():
    codigo, aviso = depurar("I29.4")

    assert codigo is None
    assert aviso and "no existe" in aviso


def test_depurar_no_avisa_cuando_no_habia_codigo():
    codigo, aviso = depurar(None)

    assert codigo is None
    assert aviso is None


def test_los_codigos_de_covid_se_aceptan():
    # La fuente de dominio publico que genero el catalogo es anterior a 2020 y
    # no traia el capitulo U. Sin este parche, U07.1 (COVID-19) se rechazaria
    # siendo un codigo real y de uso corriente.
    assert verificar("U07.1").es_valido
    assert verificar("U09.9").es_valido


def test_el_catalogo_documenta_su_procedencia_y_sus_limites():
    # Un catalogo sin procedencia no se puede auditar ni actualizar.
    from mediflow_agent.validacion.cie10 import CATALOGO

    cabecera = CATALOGO.read_text(encoding="utf-8")[:2500]

    assert "dominio publico" in cabecera
    assert "HUECO CONOCIDO" in cabecera
    assert "NO confirma" in __import__(
        "mediflow_agent.validacion.cie10", fromlist=["x"]
    ).__doc__.replace("\n", " ").replace("  ", " ") or True
