"""Lista los modelos de Gemini que admite tu clave.

Desde `agente/`:

    python scripts/listar_modelos.py

Existe porque Google retira modelos: `gemini-2.5-flash` dejo de estar
disponible para cuentas nuevas y el sistema fallaba con un 404 que no decia
cual usar en su lugar. En vez de adivinar el nombre, se pregunta.

Marca con una flecha el que el proyecto usa por defecto.
"""

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

from dotenv import load_dotenv  # noqa: E402

from mediflow_agent.config import variable  # noqa: E402
from mediflow_agent.modelos import MODELO_POR_DEFECTO  # noqa: E402

load_dotenv()


def main() -> int:
    api_key = variable("GEMINI_API_KEY")

    if not api_key:
        print("Falta GEMINI_API_KEY en el archivo .env.")
        print("Se obtiene gratis en https://aistudio.google.com -> Get API key")
        return 1

    try:
        from google import genai
    except ImportError:
        print("Falta el paquete google-genai. Corre: pip install -r requirements.txt")
        return 1

    cliente = genai.Client(api_key=api_key)

    print(f"El proyecto usa por defecto: {MODELO_POR_DEFECTO}\n")
    print("Modelos que admite tu clave para generar contenido:\n")

    encontrados = []

    try:
        for modelo in cliente.models.list():
            acciones = getattr(modelo, "supported_actions", None) or []

            if acciones and "generateContent" not in acciones:
                continue

            nombre = (modelo.name or "").removeprefix("models/")
            encontrados.append(nombre)

            marca = "  <-- el que usa el proyecto" if nombre == MODELO_POR_DEFECTO else ""
            print(f"  {nombre}{marca}")

    except Exception as err:  # noqa: BLE001
        print(f"No se pudo consultar la lista de modelos: {err}")
        return 1

    print()

    if MODELO_POR_DEFECTO in encontrados:
        print("El modelo por defecto esta disponible. No hay que cambiar nada.")
        return 0

    print(f"ATENCION: {MODELO_POR_DEFECTO} NO figura entre los disponibles.")
    print("Elegi uno de la lista y ponelo en el .env:\n")
    print("    GEMINI_MODEL=<el que elijas>\n")
    print("Si varios sirven, conviene un 'flash': son los mas baratos y rapidos.")

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
