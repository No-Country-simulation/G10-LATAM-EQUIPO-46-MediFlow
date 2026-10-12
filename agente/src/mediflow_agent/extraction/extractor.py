from dotenv import load_dotenv

from mediflow_agent.config import variable
from mediflow_agent.modelos import MODELO_POR_DEFECTO
from langchain_google_genai import ChatGoogleGenerativeAI
from mediflow_agent.schemas.models import ExtractedData


load_dotenv()


# Las reglas viven aca, y no junto a los prompts por tipo, porque las usan los
# dos caminos de extraccion. Tenerlas en un solo lugar no es prolijidad: la
# primera version las tenia solo en el camino por tipo, y cuando la extraccion
# generica paso a usarse de red de seguridad empezo a inventar justo lo que
# estas reglas prohiben: una dosis suelta en un documento ilegible, un estudio
# sacado de un correo administrativo.
REGLAS = """Reglas que no se negocian:

1. Extrae SOLO lo que aparece explicitamente escrito en el documento.
2. Si un dato no esta, o esta ilegible, usa null. Nunca lo deduzcas ni lo
   completes con lo que seria razonable.
3. No conviertas una sospecha en un diagnostico. "Sospecha de X" no es "X".
4. Conserva los nombres, numeros y unidades tal como figuran.
5. Si el documento dice [ilegible] en un dato, ese campo va en null.
6. Un dato suelto no alcanza: una dosis sin el nombre del farmaco al lado no
   es un medicamento, y va en null.
7. Si el documento no trata la atencion de un paciente concreto (un correo
   administrativo, un aviso de mantenimiento, una circular), todos los campos
   clinicos van en null, aunque el texto nombre estudios o procedimientos.
8. El codigo CIE-10 es una sugerencia: null si no hay un diagnostico
   codificable. Nunca inventes un codigo."""


# El prompt vive aparte porque lo usan dos caminos: esta clase, que extrae sin
# conocer el tipo, y la red de seguridad de ExtractorPorTipo, que recurre a el
# cuando el esquema del tipo no encajo con el documento.
def prompt_generico(texto: str) -> str:
    """Pide los campos comunes sin suponer de que clase de documento se trata."""
    return f"""Eres un extractor de informacion para el sistema MediFlow.

Extrae unicamente informacion que aparezca explicitamente en el documento. No
sabes de que clase de documento se trata, asi que no supongas que campos
deberia tener: deja en null todo lo que no este escrito.

{REGLAS}

Documento:

{texto}
"""


class DocumentExtractor:

    def __init__(self):
        api_key = variable("GEMINI_API_KEY")
        model = variable("GEMINI_MODEL", MODELO_POR_DEFECTO)

        if not api_key:
            raise ValueError(
                "No se encontró GEMINI_API_KEY en el archivo .env"
            )

        self.llm = ChatGoogleGenerativeAI(
            model=model,
            google_api_key=api_key,
            temperature=0,
        )

        self.structured_llm = self.llm.with_structured_output(
            ExtractedData
        )

    def extract(self, document_text: str) -> ExtractedData:
        return self.structured_llm.invoke(prompt_generico(document_text))