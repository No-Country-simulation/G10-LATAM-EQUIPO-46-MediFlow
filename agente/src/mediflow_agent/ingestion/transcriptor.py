"""Transcripcion de imagenes a texto mediante el modelo multimodal.

El enunciado es explicito sobre por que no usamos un OCR tradicional: los
agentes con LLMs multimodales "superan ampliamente a los OCRs tradicionales,
ya que son capaces de interpretar el contexto clinico". Ademas nos evita
depender de Tesseract, que en Windows es una instalacion externa pesada.

La transcripcion es deliberadamente tonta: pasa los pixeles a texto y nada mas.
No clasifica, no extrae y no interpreta, porque de eso ya se encargan el
clasificador y el extractor rio abajo. Mezclar las dos cosas haria imposible
saber si un error vino de leer mal o de entender mal.
"""

import base64
import logging
from abc import ABC, abstractmethod

from mediflow_agent.config import variable
from mediflow_agent.modelos import MODELO_POR_DEFECTO

_log = logging.getLogger(__name__)

INSTRUCCION = """Transcribi el texto de estas imagenes de un documento clinico.

Reglas:

1. Transcribi LITERALMENTE lo que ves. No corrijas, no completes y no
   interpretes lo que el documento dice.
2. Si una palabra, una cifra o una dosis es ilegible, escribi [ilegible] en su
   lugar. NUNCA adivines: en una receta, una dosis mal leida es peligrosa.
3. Conserva el orden y la separacion en lineas del original.
4. Si hay varias imagenes, son paginas consecutivas del mismo documento.
   Transcribilas en orden y separalas con una linea "--- pagina N ---".
5. No agregues comentarios, encabezados ni explicaciones. Solo el texto.
"""


class Transcriptor(ABC):
    """Convierte una o varias imagenes en texto plano."""

    @abstractmethod
    def transcribir(self, imagenes: list[bytes]) -> str:
        """Devuelve el texto de las imagenes, en orden.

        Recibe la lista completa y no una imagen por vez a proposito: las
        paginas de un mismo documento se entienden mejor juntas, y es una sola
        llamada al modelo en lugar de N.
        """


class TranscriptorGemini(Transcriptor):

    def __init__(self, modelo: str | None = None, api_key: str | None = None):
        from langchain_google_genai import ChatGoogleGenerativeAI

        api_key = api_key or variable("GEMINI_API_KEY")
        modelo = modelo or variable("GEMINI_MODEL", MODELO_POR_DEFECTO)

        if not api_key:
            raise ValueError(
                "No se encontro GEMINI_API_KEY en el archivo .env"
            )

        self._llm = ChatGoogleGenerativeAI(
            model=modelo,
            google_api_key=api_key,
            temperature=0,
        )

    def transcribir(self, imagenes: list[bytes]) -> str:
        from langchain_core.messages import HumanMessage

        if not imagenes:
            return ""

        contenido: list[dict] = [{"type": "text", "text": INSTRUCCION}]

        for imagen in imagenes:
            codificada = base64.b64encode(imagen).decode("ascii")
            contenido.append(
                {
                    "type": "image_url",
                    "image_url": f"data:image/png;base64,{codificada}",
                }
            )

        respuesta = self._llm.invoke([HumanMessage(content=contenido)])

        texto = respuesta.content

        if isinstance(texto, list):
            # Algunas versiones devuelven el contenido en bloques.
            texto = "".join(
                bloque.get("text", "") if isinstance(bloque, dict) else str(bloque)
                for bloque in texto
            )

        return (texto or "").strip()
