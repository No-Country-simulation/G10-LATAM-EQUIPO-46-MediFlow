"""Extraccion guiada por el tipo de documento.

Recibe el tipo que ya determino el clasificador y usa el esquema y el prompt
que corresponden. Despues verifica el codigo CIE-10 contra el catalogo local y
lo descarta si no existe.

Ante un tipo desconocido no inventa un esquema: no extrae nada. Un documento
que no se pudo clasificar va a revision humana de todos modos, y correr una
extraccion sobre el solo agrega ruido con apariencia de dato.
"""

import logging
import os
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel

from mediflow_agent.extraction.esquemas_por_tipo import (
    ESQUEMA_POR_TIPO,
    a_datos_comunes,
)
from mediflow_agent.config import variable
from mediflow_agent.modelos import MODELO_POR_DEFECTO
from mediflow_agent.schemas.models import ExtractedData
from mediflow_agent.validacion.cie10 import depurar

_log = logging.getLogger(__name__)

# Reglas comunes a todos los prompts. Se repiten en cada llamada a proposito:
# son las que impiden que el modelo rellene huecos por su cuenta.
REGLAS = """Reglas que no se negocian:

1. Extrae SOLO lo que aparece explicitamente escrito en el documento.
2. Si un dato no esta, o esta ilegible, usa null. Nunca lo deduzcas ni lo
   completes con lo que seria razonable.
3. No conviertas una sospecha en un diagnostico. "Sospecha de X" no es "X".
4. Conserva los nombres, numeros y unidades tal como figuran.
5. Si el documento dice [ilegible] en un dato, ese campo va en null."""

INSTRUCCIONES = {
    "receta_medica": """Estas leyendo una RECETA MEDICA.

Lo que mas importa son los medicamentos con su dosis y su frecuencia. La dosis
es el dato mas peligroso de leer mal: si no esta clara, va en null. Mas vale
que un farmaceutico la consulte a que se dispense una dosis equivocada.

Marca es_receta_controlada solo si el documento lo dice, o si prescribe un
opioide o un psicotropico.""",

    "informe_estudio_diagnostico": """Estas leyendo un INFORME DE ESTUDIO DIAGNOSTICO.

Distingue tres cosas que suelen confundirse: la indicacion es por que se pidio
el estudio, los hallazgos son lo que se observo, y la conclusion es lo que el
profesional concluye. No las mezcles.

El diagnostico va solo si el informe afirma un diagnostico. Si dice "compatible
con" o "sospecha de", eso es la conclusion, no un diagnostico confirmado.

El codigo CIE-10 es distinto: es una SUGERENCIA para clasificar el caso, no un
diagnostico. Si la conclusion nombra una condicion, sugeri su codigo aunque
venga precedida de "compatible con". Lo que nunca se hace es inventarlo.""",

    "orden_procedimiento": """Estas leyendo una ORDEN DE SOLICITUD DE PROCEDIMIENTO.

Lo central es que procedimiento o estudio se solicita, y con que caracter:
urgente, programado o ambulatorio, tal como lo diga el documento.

La hipotesis diagnostica es la que motiva el pedido, y suele ser una sospecha.
Registrala como tal, sin convertirla en diagnostico.""",

    "epicrisis": """Estas leyendo una EPICRISIS o INFORME DE ALTA.

El diagnostico es el de EGRESO, que puede no ser el del ingreso. La medicacion
que interesa es la indicada AL ALTA, no la que recibio durante la internacion.""",

    "certificado_medico": """Estas leyendo un CERTIFICADO MEDICO.

Registra que se certifica (reposo, aptitud, una constancia) y el motivo clinico
si figura. Muchos certificados no consignan diagnostico: en ese caso va null.""",
}


@dataclass
class ResultadoExtraccion:
    """Lo extraido, mas lo que haya que contarle a un humano."""

    datos: ExtractedData
    especifico: BaseModel | None = None
    avisos: tuple[str, ...] = field(default_factory=tuple)


class ExtractorPorTipo:

    def __init__(self, llm: Any = None):
        """`llm` permite inyectar un doble en las pruebas."""
        if llm is not None:
            self._llm = llm
            return

        from langchain_google_genai import ChatGoogleGenerativeAI

        api_key = variable("GEMINI_API_KEY")

        if not api_key:
            raise ValueError("No se encontro GEMINI_API_KEY en el archivo .env")

        self._llm = ChatGoogleGenerativeAI(
            model=variable("GEMINI_MODEL", MODELO_POR_DEFECTO),
            google_api_key=api_key,
            temperature=0,
        )

    def extract(self, texto: str, tipo_documento: str) -> ResultadoExtraccion:
        esquema = ESQUEMA_POR_TIPO.get(tipo_documento)

        if esquema is None:
            # Tipo desconocido: no se extrae. Correr una extraccion sobre un
            # documento sin clasificar produce ruido con apariencia de dato.
            return ResultadoExtraccion(
                datos=ExtractedData(),
                avisos=(
                    f"No hay esquema de extraccion para '{tipo_documento}'. "
                    "No se extrajeron datos; el caso requiere revision humana.",
                ),
            )

        prompt = (
            f"{INSTRUCCIONES[tipo_documento]}\n\n{REGLAS}\n\n"
            f"Documento:\n\n{texto}"
        )

        especifico = self._llm.with_structured_output(esquema).invoke(prompt)
        datos = a_datos_comunes(especifico)

        datos, avisos = self._depurar_cie10(datos)

        return ResultadoExtraccion(
            datos=datos, especifico=especifico, avisos=tuple(avisos)
        )

    @staticmethod
    def _depurar_cie10(datos: ExtractedData) -> tuple[ExtractedData, list[str]]:
        """Descarta el codigo CIE-10 si no existe en el catalogo."""
        codigo, motivo = depurar(datos.suggested_icd10)

        if motivo:
            _log.warning("CIE-10 descartado: %s", motivo)
            return datos.model_copy(update={"suggested_icd10": None}), [motivo]

        if codigo != datos.suggested_icd10:
            # Se normalizo la forma (por ejemplo "i269" a "I26.9").
            return datos.model_copy(update={"suggested_icd10": codigo}), []

        return datos, []
