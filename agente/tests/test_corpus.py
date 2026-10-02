"""Integridad del corpus etiquetado (tarea 2.3).

No miden al agente: verifican que el corpus y sus etiquetas esten
sincronizados. Si alguien agrega un documento y olvida la etiqueta, o al
reves, estas pruebas lo dicen antes de que la evaluacion devuelva un numero
que no significa lo que parece.
"""

import json
from pathlib import Path
from typing import get_args

import pytest

from mediflow_agent.schemas.models import DocumentType

CORPUS = Path(__file__).resolve().parent.parent / "corpus"
DOCUMENTOS = CORPUS / "documentos"

CAMPOS_VALIDOS = {
    "paciente.nombre",
    "paciente.edad",
    "medico.nombre",
    "medico.matricula",
    "estudio",
    "diagnostico",
    "hallazgos",
    "conclusion",
    "medicamentos",
    "procedimiento",
}

PRIORIDADES_VALIDAS = {"Rutina", "Prioritario", "Urgente"}


@pytest.fixture(scope="module")
def etiquetas() -> list[dict]:
    return json.loads((CORPUS / "etiquetas.json").read_text(encoding="utf-8"))


def test_el_corpus_tiene_los_treinta_documentos_que_pide_la_tarea(etiquetas):
    assert len(etiquetas) == 30
    assert len(list(DOCUMENTOS.glob("*.txt"))) == 30


def test_cada_etiqueta_apunta_a_un_archivo_que_existe(etiquetas):
    for e in etiquetas:
        assert (DOCUMENTOS / e["archivo"]).is_file(), f"falta {e['archivo']}"


def test_cada_archivo_tiene_su_etiqueta(etiquetas):
    etiquetados = {e["archivo"] for e in etiquetas}
    en_disco = {p.name for p in DOCUMENTOS.glob("*.txt")}

    assert en_disco - etiquetados == set(), "hay documentos sin etiqueta"


def test_no_hay_archivos_repetidos(etiquetas):
    nombres = [e["archivo"] for e in etiquetas]
    assert len(nombres) == len(set(nombres))


def test_los_tipos_existen_en_el_esquema(etiquetas):
    validos = set(get_args(DocumentType))

    for e in etiquetas:
        assert e["tipo_documento"] in validos, (
            f"{e['archivo']}: tipo {e['tipo_documento']!r} no esta en DocumentType"
        )


def test_las_prioridades_son_validas(etiquetas):
    for e in etiquetas:
        assert e["nivel_prioridad"] in PRIORIDADES_VALIDAS


def test_los_campos_etiquetados_existen(etiquetas):
    for e in etiquetas:
        desconocidos = set(e["campos_presentes"]) - CAMPOS_VALIDOS
        assert not desconocidos, f"{e['archivo']}: campos {desconocidos}"


def test_estan_representadas_las_seis_categorias(etiquetas):
    presentes = {e["tipo_documento"] for e in etiquetas}

    assert presentes == set(get_args(DocumentType)), (
        "falta al menos una categoria en el corpus"
    )


def test_hay_casos_urgentes_en_mas_de_un_tipo_de_documento(etiquetas):
    # Si todos los urgentes fueran informes, la deteccion de urgencia podria
    # acertar mirando solo la categoria y no el contenido clinico. El corpus
    # tiene que impedir ese atajo.
    tipos = {e["tipo_documento"] for e in etiquetas if e["nivel_prioridad"] == "Urgente"}

    assert len(tipos) >= 3, f"los urgentes se concentran en {tipos}"


def test_hay_documentos_con_datos_faltantes(etiquetas):
    # El corpus tiene que ejercitar la regla de devolver null en vez de
    # inventar. Si todos los documentos estuvieran completos, no se mediria.
    incompletos = [e for e in etiquetas if len(e["campos_presentes"]) <= 3]

    assert len(incompletos) >= 4


def test_ningun_documento_esta_vacio(etiquetas):
    for e in etiquetas:
        contenido = (DOCUMENTOS / e["archivo"]).read_text(encoding="utf-8")
        assert contenido.strip(), f"{e['archivo']} esta vacio"


def test_los_desconocidos_no_declaran_campos_clinicos(etiquetas):
    # Un documento que no es clinico no tiene datos clinicos que extraer.
    for e in etiquetas:
        if e["tipo_documento"] == "desconocido":
            assert e["campos_presentes"] == [], f"{e['archivo']} declara campos"
