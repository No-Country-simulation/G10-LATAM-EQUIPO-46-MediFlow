"""Verificacion de codigos CIE-10 contra un catalogo local.

El riesgo que esto ataja es concreto: un modelo de lenguaje puede devolver un
codigo con forma perfecta —`I26.9` se ve igual de creible que `I99.7`— sin que
exista. Nadie lo nota leyendo la respuesta. Lo unico que lo detecta es
contrastarlo contra una lista real.

**Que verifica y que no.** Hay que ser preciso con esto, porque una
verificacion que promete mas de lo que hace es peor que ninguna:

  - SI verifica que la **forma** del codigo sea valida (letra, dos digitos y un
    subcodigo opcional).
  - SI verifica que la **categoria de tres caracteres exista** en el catalogo.
  - NO verifica que el codigo sea el **correcto para ese diagnostico**. Eso lo
    decide una persona.
  - NO verifica el **cuarto caracter** contra la CIE-10 de la OMS, porque el
    catalogo de dominio publico que usamos no lo cubre con esa granularidad.

Cuando un codigo no pasa, el sistema lo pone en `null`. La regla del proyecto
es clara: un CIE-10 inventado es peor que un campo vacio.
"""

import re
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
from pathlib import Path

CATALOGO = Path(__file__).resolve().parent.parent / "datos" / "cie10_categorias.txt"

# Letra, dos digitos y hasta cuatro caracteres mas tras un punto opcional.
# Acepta tanto "I26.9" como "I269", que es como lo escriben algunos sistemas.
_FORMA = re.compile(r"^([A-Z])(\d{2})\.?([A-Z0-9]{0,4})$", re.IGNORECASE)

# La CIE-10 no usa la U para diagnosticos ordinarios (es un capitulo reservado)
# ni las letras que no aparecen como inicial de categoria.
_SIN_CODIGO = {"no aplica", "n/a", "na", "ninguno", "desconocido", "-", "none"}


class Veredicto(str, Enum):
    VALIDO = "valido"
    FORMA_INVALIDA = "forma_invalida"
    CATEGORIA_INEXISTENTE = "categoria_inexistente"
    VACIO = "vacio"


@dataclass(frozen=True)
class ResultadoCie10:
    veredicto: Veredicto
    codigo_normalizado: str | None
    motivo: str

    @property
    def es_valido(self) -> bool:
        return self.veredicto is Veredicto.VALIDO


@lru_cache(maxsize=1)
def cargar_categorias(ruta: Path | None = None) -> frozenset[str]:
    """Lee el catalogo una sola vez y lo deja en memoria.

    El archivo son unos 8 KB: cargarlo entero es mas simple y mas rapido que
    cualquier consulta, y evita una dependencia externa en caliente.
    """
    archivo = ruta or CATALOGO

    if not archivo.is_file():
        raise FileNotFoundError(
            f"No se encontro el catalogo CIE-10 en {archivo}. "
            "Sin el no se pueden verificar los codigos sugeridos."
        )

    categorias = set()

    for linea in archivo.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()

        if linea and not linea.startswith("#"):
            categorias.add(linea.upper())

    return frozenset(categorias)


def verificar(codigo: str | None, ruta_catalogo: Path | None = None) -> ResultadoCie10:
    """Comprueba que el codigo exista. Nunca lanza excepcion."""
    if codigo is None or not str(codigo).strip():
        return ResultadoCie10(Veredicto.VACIO, None, "No se sugirio ningun codigo.")

    crudo = str(codigo).strip()

    if crudo.lower() in _SIN_CODIGO:
        return ResultadoCie10(Veredicto.VACIO, None, "No se sugirio ningun codigo.")

    coincidencia = _FORMA.match(crudo)

    if not coincidencia:
        return ResultadoCie10(
            Veredicto.FORMA_INVALIDA,
            None,
            f"El codigo {crudo!r} no tiene forma de CIE-10 (letra, dos digitos "
            "y subcodigo opcional).",
        )

    letra, digitos, subcodigo = coincidencia.groups()
    categoria = f"{letra.upper()}{digitos}"

    if categoria not in cargar_categorias(ruta_catalogo):
        return ResultadoCie10(
            Veredicto.CATEGORIA_INEXISTENTE,
            None,
            f"La categoria {categoria} no existe en el catalogo CIE-10. "
            "El codigo se descarta en lugar de arrastrar un dato inventado.",
        )

    normalizado = categoria + (f".{subcodigo.upper()}" if subcodigo else "")

    return ResultadoCie10(
        Veredicto.VALIDO,
        normalizado,
        f"Categoria {categoria} verificada contra el catalogo local. "
        "La correspondencia con el diagnostico no esta verificada.",
    )


def depurar(codigo: str | None) -> tuple[str | None, str | None]:
    """Devuelve (codigo_valido_o_None, aviso_o_None).

    Es la forma comoda de usar esto desde el extractor: deja el codigo si
    existe y lo borra si no, informando por que.
    """
    resultado = verificar(codigo)

    if resultado.veredicto is Veredicto.VACIO:
        return None, None

    if resultado.es_valido:
        return resultado.codigo_normalizado, None

    return None, resultado.motivo
