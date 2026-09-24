import json
import sys
from pathlib import Path

from mediflow_agent.classification.classifier import DocumentClassifier
from mediflow_agent.extraction.extractor import DocumentExtractor


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
):
    classifier = DocumentClassifier()
    extractor = DocumentExtractor()

    print("\n[1/2] Clasificando documento...")

    classification = classifier.classify(document_text)

    print(
        f"Tipo detectado: {classification.document_type}"
    )

    print("\n[2/2] Extrayendo información...")

    extracted_data = extractor.extract(document_text)

    result = {
        "document_id": document_id,
        "classification": classification.model_dump(),
        "extracted_data": extracted_data.model_dump(),
    }

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
        json.dumps(
            result,
            indent=2,
            ensure_ascii=False
        )
    )


if __name__ == "__main__":
    main()