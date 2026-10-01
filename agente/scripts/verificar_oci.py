"""Verifica la conexion con el almacen configurado.

Es la prueba de subida y descarga que pide la tarea 1.2 del cronograma.
Correrlo desde `agente/`:

    python scripts/verificar_oci.py

Comprueba el almacen que diga MEDIFLOW_ALMACEN: OCI con credenciales IAM, OCI
con un Pre-Authenticated Request, o el almacen local. Sube un objeto de prueba
a cada uno de los cuatro prefijos, lo vuelve a leer y compara el contenido.
No toca ningun documento real.

Si algo falla, dice QUE fallo y QUE revisar, en lugar de escupir una traza.

Aviso: OCI no permite borrar objetos a traves de un PAR. Con
MEDIFLOW_ALMACEN=par, los objetos de prueba quedan en el bucket y hay que
eliminarlos desde la consola.
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
CONTENIDO = '{"prueba": "conexion", "paciente": "José Muñoz Ramírez"}'

QUE_REVISAR = {
    "oci": [
        "Que el .env tenga las variables OCI_* completas, o que exista",
        "  ~/.oci/config.",
        "Que la clave privada corresponda al fingerprint cargado.",
        "Que el usuario tenga permiso de escritura sobre el bucket",
        "  (una politica con manage object-family en su compartment).",
    ],
    "par": [
        "Que MEDIFLOW_OCI_PAR sea la URL completa del PAR y termine en /o/.",
        "Que el PAR no haya caducado: se vence en la fecha elegida al crearlo.",
        "Que el PAR se haya creado con permiso de lectura Y escritura.",
    ],
    "local": [
        "Que MEDIFLOW_ALMACEN_LOCAL apunte a una carpeta donde se pueda",
        "  escribir.",
    ],
}


def main() -> int:
    destino = os.getenv("MEDIFLOW_ALMACEN", "local").strip().lower()

    print(f"Verificando el almacen configurado: {destino}\n")

    try:
        from mediflow_agent.api.app import obtener_almacenamiento

        almacen = obtener_almacenamiento()

    except Exception as err:  # noqa: BLE001
        print("FALLO: no se pudo construir el almacen.\n")
        print(f"  {err}\n")
        print("Que revisar:")
        for linea in QUE_REVISAR.get(destino, ["Que MEDIFLOW_ALMACEN sea oci, par o local."]):
            print(f"  - {linea}" if not linea.startswith(" ") else f"  {linea}")
        return 1

    print(f"  bucket : {almacen.bucket}")

    if namespace := getattr(almacen, "namespace", None):
        print(f"  espacio: {namespace}")

    if region := getattr(almacen, "region", None):
        print(f"  region : {region}")

    print()

    nombre = f"prueba-conexion-{uuid.uuid4().hex[:8]}.json"
    fallos = 0

    for prefijo in PREFIJOS:
        resultado = almacen.guardar_texto(prefijo, nombre, CONTENIDO)

        if not resultado.exito:
            print(f"  FALLO subida    {prefijo}/ -> {resultado.detalle_error}")
            fallos += 1
            continue

        leido = almacen.leer_texto(prefijo, nombre)

        if leido is None:
            print(f"  FALLO descarga  {prefijo}/ -> se subio pero no se pudo leer")
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
        for linea in QUE_REVISAR.get(destino, []):
            print(f"  - {linea}" if not linea.startswith(" ") else f"  {linea}")
        return 1

    print("Todo bien: subida y descarga funcionan en los cuatro prefijos.")
    print(f"\nQuedaron cuatro objetos de prueba llamados {nombre}.")

    if destino == "par":
        print("OCI no permite borrar por PAR: hay que eliminarlos desde la consola.")
    elif destino == "oci":
        print("Se pueden borrar desde la consola de OCI.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
