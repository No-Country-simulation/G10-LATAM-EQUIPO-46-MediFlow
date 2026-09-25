import sys
from pathlib import Path

from mediflow_agent.classification.classifier import DocumentClassifier
from mediflow_agent.extraction.extractor import DocumentExtractor
from mediflow_agent.schemas.models import AgentResult


def read_document(file_path: str) -> str:
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(
            f"No existe el archivo: {file_path}"
        )

    return path.read_text(encoding="utf-8")


def process_document(
    document_id: str,
    document_text: str
) -> AgentResult:
    classifier = DocumentClassifier()
    extractor = DocumentExtractor()

    print("\n[1/2] Clasificando documento...")

    classification = classifier.classify(document_text)

    print(
        f"Tipo detectado: {classification.document_type}"
    )

    print("\n[2/2] Extrayendo información...")

    extracted_data = extractor.extract(document_text)

    # Se arma el AgentResult en lugar de un dict suelto: asi la salida final
    # pasa por la validacion de Pydantic igual que sus partes. Si el modelo
    # devolviera algo que no respeta el esquema, falla aca y no rio abajo.
    result = AgentResult(
        document_id=document_id,
        classification=classification,
        extracted_data=extracted_data,
    )

    return result


def main():

    if len(sys.argv) < 2:
        print(
            "Uso:\n"
            "python -m mediflow_agent.main "
            "examples/informe.txt"
        )
        return

    file_path = sys.argv[1]

    document_text = read_document(file_path)

    document_id = Path(file_path).stem

    result = process_document(
        document_id=document_id,
        document_text=document_text,
    )

    print("\n========== RESULTADO ==========\n")

    print(
        result.model_dump_json(indent=2)
    )


if __name__ == "__main__":
    main()