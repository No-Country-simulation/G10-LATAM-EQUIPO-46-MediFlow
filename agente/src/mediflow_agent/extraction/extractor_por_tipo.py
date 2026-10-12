"""Extraccion guiada por el tipo de documento.

Recibe el tipo que ya determino el clasificador y usa el esquema y el prompt
que corresponden. Despues verifica el codigo CIE-10 contra el catalogo local y
lo descarta si no existe.

Tiene una red de seguridad. La extraccion por tipo solo sirve si la etiqueta
es la correcta: el prompt de epicrisis pide el diagnostico "de egreso", y ante
una hoja de triaje mal etiquetada como epicrisis el modelo responde null a
todo, porque no hay egreso. Sin red, un error de clasificacion no empeora la
extraccion, la anula. Por eso, cuando el esquema del tipo no cosecha ningun
dato clinico, se reintenta con el esquema generico, que no supone nada sobre
la clase de documento.
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
from mediflow_agent.extraction.extractor import REGLAS, prompt_generico
from mediflow_agent.modelos import MODELO_POR_DEFECTO
from mediflow_agent.schemas.models import ExtractedData
from mediflow_agent.validacion.cie10 import depurar

_log = logging.getLogger(__name__)


def _sin_contenido_clinico(datos: ExtractedData) -> bool:
    """True si no se cosecho ningun dato clinico, solo quiza paciente y medico.

    El nombre del paciente no cuenta: aparece en el encabezado de cualquier
    formulario y se extrae aunque el esquema no encaje con el documento.
    """
    return not any(
        (
            datos.study,
            datos.diagnosis,
            datos.findings,
            datos.conclusion,
            datos.procedure,
            datos.medications,
            datos.suggested_icd10,
        )
    )

# Las reglas son las mismas para los dos caminos de extraccion y viven en
# `extractor`. Se repiten en cada llamada a proposito: son las que impiden que
# el modelo rellene huecos por su cuenta.

INSTRUCCIONES = {
    "receta_medica": """Estas leyendo una RECETA MEDICA.

Lo que mas importa son los medicamentos con su dosis y su frecuencia. La dosis
es el dato mas peligroso de leer mal: si no esta clara, va en null. Mas vale
que un farmaceutico la consulte a que se dispense una dosis equivocada.

Un medicamento necesita un NOMBRE. Si en el documento solo queda una dosis
suelta ("40 mg") sin saber de que farmaco es, NO lo registres: una dosis sin
nombre no se puede dispensar, y nombrarla como medicamento es peor que dejar
la lista vacia.

Marca es_receta_controlada solo si el documento lo dice, o si prescribe un
opioide o un psicotropico.""",

    "informe_estudio_diagnostico": """Estas leyendo un INFORME DE ESTUDIO DIAGNOSTICO.

Distingue tres cosas que suelen confundirse: la indicacion es por que se pidio
el estudio, los hallazgos son lo que se observo, y la conclusion es lo que el
profesional concluye. No las mezcles.

El diagnostico va solo si el informe lo AFIRMA. Si dice "compatible con" o
"sospecha de", eso queda unicamente en conclusion, con la expresion completa,
y diagnostico va en null. Si la conclusion afirma la condicion, va en los dos
campos: el diagnostico afirmado y la conclusion textual.

Los valores de laboratorio van en hallazgos, con sus unidades, aunque el
documento no tenga un apartado llamado "Hallazgos".

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

Registra que se certifica (reposo, aptitud, una constancia) en conclusion, y el
motivo clinico en diagnostico si figura. Muchos certificados no consignan
diagnostico: en ese caso va null.

El titulo del documento NO es un procedimiento ni un estudio. Un certificado
no tiene procedimiento: ese campo queda vacio.""",
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
            # Sin esquema no hay prompt especifico, pero eso no es razon para
            # devolver el documento vacio: se va directo a la via generica.
            return self._por_la_via_generica(
                texto,
                f"No hay esquema de extraccion para '{tipo_documento}'. "
                "Se extrajo con el esquema generico.",
            )

        prompt = (
            f"{INSTRUCCIONES[tipo_documento]}\n\n{REGLAS}\n\n"
            f"Documento:\n\n{texto}"
        )

        especifico = self._llm.with_structured_output(esquema).invoke(prompt)
        datos = a_datos_comunes(especifico)

        # Una cosecha vacia casi siempre significa que la etiqueta no era la
        # correcta: al prompt de epicrisis se le pide el diagnostico "de
        # egreso", y una hoja de triaje no tiene egreso, asi que el modelo
        # responde null a todo y responde bien. Sin esta red, un error de
        # clasificacion no degrada la extraccion: la anula.
        if _sin_contenido_clinico(datos):
            return self._por_la_via_generica(
                texto,
                f"El esquema de '{tipo_documento}' no encontro ningun dato "
                "clinico; probablemente el tipo detectado no corresponda. Se "
                "reintento con el esquema generico.",
                especifico=especifico,
            )

        datos, avisos = self._depurar_cie10(datos)

        return ResultadoExtraccion(
            datos=datos, especifico=especifico, avisos=tuple(avisos)
        )

    def _por_la_via_generica(
        self, texto: str, motivo: str, especifico: Any = None
    ) -> ResultadoExtraccion:
        """Extrae los campos comunes sin suponer de que tipo es el documento."""
        datos = self._llm.with_structured_output(ExtractedData).invoke(
            prompt_generico(texto)
        )

        datos, avisos = self._depurar_cie10(datos)

        return ResultadoExtraccion(
            datos=datos, especifico=especifico, avisos=(motivo, *avisos)
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
