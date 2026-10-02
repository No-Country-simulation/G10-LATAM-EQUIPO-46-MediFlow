"""El modelo de lenguaje que usa el agente, en un solo lugar.

Estaba repetido en cuatro modulos. Cuando Google retiro `gemini-2.5-flash`
para cuentas nuevas, el sistema dejo de funcionar y habia que corregirlo en
cuatro archivos, con el riesgo de olvidar uno.

El valor se puede cambiar sin tocar codigo con la variable GEMINI_MODEL.
Para ver que modelos admite una clave: `python scripts/listar_modelos.py`.
"""

# Lo indica la propia API de Google al rechazar gemini-2.5-flash:
# "Please update your code to use models/gemini-3.8-flash".
MODELO_POR_DEFECTO = "gemini-3.8-flash"
