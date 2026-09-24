import os
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from mediflow_agent.schemas.models import ClassificationResult


load_dotenv()


class DocumentClassifier:

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
            ClassificationResult
        )

    def classify(self, document_text: str) -> ClassificationResult:

        prompt = f"""
                    Eres un clasificador de documentos para un prototipo llamado MediFlow.

                    Debes clasificar el documento únicamente en una de estas categorías:

                    - receta_medica
                    - informe_estudio_diagnostico
                    - orden_procedimiento
                    - epicrisis
                    - certificado_medico
                    - desconocido

                    Reglas:

                    1. Clasifica según el contenido real del documento.
                    2. No inventes información.
                    3. Si el texto no corresponde claramente a una de las categorías,
                    utiliza "desconocido".
                    4. La confianza debe estar entre 0 y 1.
                    5. Si puedes identificar una especialidad médica, indícala.
                    6. Si no puedes identificarla, utiliza null.

                    Documento:

                    {document_text}
                    """

        result = self.structured_llm.invoke(prompt)

        return result