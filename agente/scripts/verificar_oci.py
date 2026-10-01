"""Verifica la conexion con OCI Object Storage.

Es la prueba de subida y descarga que pide la tarea 1.2 del cronograma.
Correrlo desde `agente/`:

    python scripts/verificar_oci.py

Sube un objeto de prueba a cada uno de los cuatro prefijos, lo vuelve a leer,
compara el contenido y lo informa. No toca ningun documento real.

Si algo falla, dice QUE fallo y QUE revisar, en lugar de escupir una traza.
"""

import os
import sys
import uuid
from pathlib import Path

# Permite correr el script sin instalar el paquete ni exportar PYTHONPATH.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from dotenv import load_dotenv  # noqa: E402

from mediflow_agent.storage.base import (  # noqa: E402
    PREFIJO_AUDITORIA,
    PREFIJO_RECIBIDOS,
    PREFIJO_RUTINA,
    PREFIJO_URGENTES,
)

load_dotenv()

PREFIJOS = [PREFIJO_RECIBIDOS, PREFIJO_RUTINA, PREFIJO_URGENTES, PREFIJO_AUDITORIA]

# Contenido con acentos y una ene a proposito: si el objeto vuelve distinto,
# hay un problema de codificacion que conviene descubrir aca y no en la demo.
CONTENIDO = '{"prueba": "conexion OCI", "paciente": "José Muñoz Ramírez"}'


def main() -> int:
    from mediflow_agent.storage.oci_storage import (
        AlmacenamientoOci,
        ErrorDeConfiguracionOci,
    )

    print("Verificando la conexion con OCI Object Storage\n")

    try:
        almacen = AlmacenamientoOci()
    except ErrorDeConfiguracionOci as err:
        print("FALLO: no se pudo configurar el cliente.\n")
        print(f"  {err}\n")
        print("Que revisar:")
        print("  - Que el archivo .env tenga las variables OCI_* completas,")
        print("    o que exista ~/.oci/config.")
        print("  - Que la clave privada corresponda al fingerprint cargado.")
        return 1

    print(f"  bucket    : {almacen.bucket}")
    print(f"  namespace : {almacen.namespace}")
    print(f"  region    : {os.getenv('OCI_REGION', '(desde ~/.oci/config)')}\n")

    nombre = f"prueba-conexion-{uuid.uuid4().hex[:8]}.json"
    fallos = 0

    for prefijo in PREFIJOS:
        resultado = almacen.guardar_texto(prefijo, nombre, CONTENIDO)

        if not resultado.exito:
            print(f"  FALLO subida   {prefijo}/  -> {resultado.detalle_error}")
            fallos += 1
            continue

        leido = almacen.leer_texto(prefijo, nombre)

        if leido is None:
            print(f"  FALLO descarga {prefijo}/  -> se subio pero no se pudo leer")
            fallos += 1
        elif leido != CONTENIDO:
            print(f"  FALLO contenido {prefijo}/ -> volvio distinto de lo subido")
            fallos += 1
        else:
            print(f"  ok  {resultado.ruta_objeto}")

    print()

    if fallos:
        print(f"{fallos} de {len(PREFIJOS)} prefijos fallaron.\n")
        print("Que revisar:")
        print("  - Que el bucket exista y se llame como dice MEDIFLOW_BUCKET.")
        print("  - Que el usuario tenga permiso de escritura sobre el bucket")
        print("    (una politica con manage object-family en su compartment).")
        print("  - Que la region del .env sea la del bucket.")
        return 1

    print("Todo bien: subida y descarga funcionan en los cuatro prefijos.")
    print(f"\nQuedaron cuatro objetos de prueba llamados {nombre}.")
    print("Se pueden borrar desde la consola de OCI.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
