"""Lectura de configuracion desde el entorno.

Existe por un defecto concreto que se encontro probando: `os.getenv(nombre,
defecto)` devuelve el valor por defecto solo cuando la variable **no existe**.
Si existe pero esta vacia, devuelve la cadena vacia.

Eso importa porque el `.env.example` del proyecto trae varias variables
declaradas y vacias, para que se vean y se completen. Al copiarlo a `.env`,
todas quedan definidas como cadena vacia, y el valor por defecto deja de
aplicarse en silencio. El sintoma que lo delato: la respuesta del endpoint
salio con `"bucket": ""` en lugar del nombre por defecto.

`variable()` trata una variable vacia igual que una ausente, que es lo que
cualquiera espera al leer un archivo de configuracion.
"""

import os

from dotenv import load_dotenv

# Se carga el .env aca y no en cada modulo. Antes lo hacia classification y
# extraction por separado, asi que ExtractorPorTipo funcionaba dentro de la
# API (de rebote, porque el clasificador se importaba antes) y fallaba al
# usarlo solo. Cualquier modulo que lea configuracion pasa por aca.
load_dotenv()


def variable(nombre: str, defecto: str | None = None) -> str | None:
    """Valor de la variable de entorno, o `defecto` si falta o esta vacia."""
    valor = os.getenv(nombre)

    if valor is None:
        return defecto

    valor = valor.strip()

    return valor if valor else defecto


def numero(nombre: str, defecto: float) -> float:
    """Igual que `variable`, pero convertido a numero.

    Un valor que no se puede convertir se trata como ausente en lugar de
    tumbar la aplicacion al arrancar: un umbral mal escrito en un .env no
    deberia impedir que el sistema triee documentos.
    """
    crudo = variable(nombre)

    if crudo is None:
        return defecto

    try:
        return float(crudo)
    except ValueError:
        return defecto


# --------------------------------------------------------------------------
# Configuracion desde archivo
# --------------------------------------------------------------------------

import tomllib  # noqa: E402
from pathlib import Path  # noqa: E402

ARCHIVO_TRIAJE = Path(__file__).resolve().parent.parent.parent / "config" / "triaje.toml"


def cargar_archivo(ruta: Path | None = None) -> dict:
    """Lee `config/triaje.toml`. Devuelve {} si no existe o esta roto.

    Un archivo de configuracion ausente o mal escrito NO puede impedir que el
    sistema triee documentos: se cae a los valores por defecto y se sigue.
    Lo contrario significaria que un error de tipeo en un TOML deja sin
    atender una guardia.
    """
    archivo = ruta or ARCHIVO_TRIAJE

    if not archivo.is_file():
        return {}

    try:
        with open(archivo, "rb") as fh:
            return tomllib.load(fh)
    except (tomllib.TOMLDecodeError, OSError):
        import logging

        logging.getLogger(__name__).warning(
            "No se pudo leer %s; se usan los valores por defecto.", archivo
        )
        return {}


def ajuste(seccion: str, clave: str, defecto, variable_entorno: str | None = None):
    """Valor de configuracion, con precedencia entorno > archivo > defecto."""
    if variable_entorno:
        crudo = variable(variable_entorno)

        if crudo is not None:
            if isinstance(defecto, bool):
                return crudo.strip().lower() in ("1", "true", "si", "yes")
            if isinstance(defecto, (int, float)):
                try:
                    return type(defecto)(crudo)
                except ValueError:
                    pass
            else:
                return crudo

    valor = cargar_archivo().get(seccion, {}).get(clave)

    return defecto if valor is None else valor
