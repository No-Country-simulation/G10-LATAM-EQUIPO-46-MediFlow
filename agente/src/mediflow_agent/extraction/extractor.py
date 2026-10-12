from dotenv import load_dotenv

from mediflow_agent.config import variable
from mediflow_agent.modelos import MODELO_POR_DEFECTO
from langchain_google_genai import ChatGoogleGenerativeAI
from mediflow_agent.schemas.models import ExtractedData


load_dotenv()


# El prompt vive aparte porque lo usan dos caminos: esta clase, que extrae sin
# conocer el tipo, y la red de seguridad de ExtractorPorTipo, que recurre a el
# cuando el esquema del tipo no encajo con el documento.
def prompt_generico(texto: str) -> str:
    """Pide los campos comunes sin suponer de que clase de documento se trata."""
    return f"""
                    Eres un extractor de información para el sistema MediFlow.

                    Extrae únicamente información que aparezca explícitamente
                    en el documento.

                    Reglas importantes:

                        1. NO inventes datos.
                        2. Si un dato no aparece, utiliza null.
                        3. No conviertas una inferencia médica en un hecho.
                        4. El diagnóstico debe ser extraído únicamente si aparece
                        explícitamente en el documento.
                        5. suggested_icd10 es solamente una sugerencia y debe ser null
                        si no existe evidencia suficiente.
                        6. Conserva los nombres y datos tal como aparecen cuando sea posible.
                        7. Extrae medicamentos, estudios y procedimientos únicamente
                        si aparecen en el documento.

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