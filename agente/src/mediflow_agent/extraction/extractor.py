import os
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from mediflow_agent.schemas.models import ExtractedData


load_dotenv()


class DocumentExtractor:

    def __init__(self):
        api_key = os.getenv("GEMINI_API_KEY")
        model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

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

        prompt = f"""
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

                    {document_text}
                """

        result = self.structured_llm.invoke(prompt)

        return result