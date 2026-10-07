"""El modelo de lenguaje que usa el agente, en un solo lugar.

Estaba repetido en cuatro modulos. Cuando Google retiro `gemini-2.5-flash`
para cuentas nuevas, el sistema dejo de funcionar y habia que corregirlo en
cuatro archivos, con el riesgo de olvidar uno.

**Por que un modelo "lite".** Se midieron cuatro candidatos clasificando y
extrayendo el mismo informe, con la misma clave:

    modelo                      clasificacion  extraccion  total
    gemini-3.5-flash-lite             0.9 s       1.2 s     2.1 s
    gemini-flash-lite-latest          1.0 s       1.1 s     2.1 s
    gemini-3.7-flash                 79.0 s      44.8 s   123.8 s
    gemini-3.8-flash                     cuota gratuita agotada (429)

Los modelos que razonan antes de responder tardan dos minutos. En triaje de
urgencias eso es inaceptable: el objetivo del proyecto es resolver un
documento en 10 segundos o menos. Los "lite" entran con un margen enorme.

La contrapartida es que un modelo mas chico puede acertar menos. Esa parte
**todavia no esta medida**: se mide con `scripts/evaluar_corpus.py` sobre los
30 documentos etiquetados. Si la exactitud no alcanza, el camino es subir a un
modelo mayor sin pasarse del presupuesto de tiempo, no resignar el tiempo.

Se puede cambiar sin tocar codigo con la variable GEMINI_MODEL.
Para ver que modelos admite una clave: `python scripts/listar_modelos.py`.
"""

MODELO_POR_DEFECTO = "gemini-3.5-flash-lite"

# Presupuesto de tiempo para clasificar y extraer un documento, en segundos.
# No es un limite tecnico: es el requisito clinico. Un documento de guardia
# que tarda un minuto en enrutarse no sirve.
from mediflow_agent.config import ajuste  # noqa: E402

PRESUPUESTO_SEGUNDOS = ajuste(
    "rendimiento", "presupuesto_segundos", 10.0, "MEDIFLOW_PRESUPUESTO"
)
