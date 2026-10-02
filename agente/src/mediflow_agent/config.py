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

NO_DEFINIDO = object()


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
