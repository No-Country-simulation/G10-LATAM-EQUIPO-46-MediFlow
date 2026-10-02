"""Interfaz de persistencia de documentos y decisiones.

El enunciado exige OCI Object Storage en capa Always Free, con los objetos
segregados por estado. Esa integracion es la tarea 1.2 y depende de que exista
la cuenta de OCI, que es un tramite externo al codigo.

Para que nada quede bloqueado esperando ese tramite, el resto del sistema no
habla con OCI: habla con esta interfaz. Hoy la implementa `AlmacenamientoLocal`
guardando en disco; manana la implementara un `AlmacenamientoOci` y lo unico
que cambia es que objeto se construye al arrancar la aplicacion.

Quien escriba la implementacion de OCI tiene que respetar exactamente este
contrato: mismos prefijos, mismo objeto de retorno, mismo comportamiento ante
fallo. Las pruebas de `tests/test_storage.py` valen para cualquier
implementacion y sirven de criterio de aceptacion.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass


# Prefijos por estado del documento. El enunciado los nombra como ejemplo
# (/recibidos, /procesados, /auditoria_humana) y el README los fija como
# organizacion del bucket. Viven aca, en un solo lugar, para que nadie los
# escriba a mano en otro modulo y se desincronicen.
PREFIJO_RECIBIDOS = "recibidos"
PREFIJO_RUTINA = "procesados/rutina"
PREFIJO_URGENTES = "procesados/urgentes"
PREFIJO_AUDITORIA = "auditoria_humana"


@dataclass(frozen=True)
class ObjetoGuardado:
    """Resultado de persistir un objeto.

    `exito` en False no es una excepcion: significa que el triaje se resolvio
    pero el respaldo fallo. La decision clinica ya se tomo y no se pierde por
    un problema de almacenamiento; se reporta en la respuesta como
    `status_backup: "fallo"` y se reintenta aparte.
    """

    bucket: str
    ruta_objeto: str
    exito: bool
    detalle_error: str | None = None


class AlmacenamientoDocumentos(ABC):
    """Lo minimo que el sistema necesita de un almacen de objetos."""

    @property
    @abstractmethod
    def bucket(self) -> str:
        """Nombre del bucket o contenedor, tal como se reporta en la respuesta."""

    @abstractmethod
    def guardar_texto(
        self,
        prefijo: str,
        nombre_objeto: str,
        contenido: str,
        tipo_contenido: str = "application/json",
    ) -> ObjetoGuardado:
        """Guarda contenido de texto bajo `<prefijo>/<nombre_objeto>`.

        No debe lanzar excepcion ante un fallo del almacen: devuelve
        `ObjetoGuardado` con `exito=False` y el motivo en `detalle_error`.
        Un almacen caido no puede tumbar un triaje ya resuelto.
        """

    @abstractmethod
    def leer_texto(self, prefijo: str, nombre_objeto: str) -> str | None:
        """Devuelve el contenido guardado, o None si el objeto no existe.

        Existe para que la prueba de subida y descarga que pide la tarea 1.2
        se pueda escribir contra la interfaz y no contra una implementacion.
        """

    @abstractmethod
    def guardar_binario(
        self,
        prefijo: str,
        nombre_objeto: str,
        contenido: bytes,
        tipo_contenido: str = "application/octet-stream",
    ) -> ObjetoGuardado:
        """Guarda contenido binario. Mismas reglas que `guardar_texto`.

        Hace falta porque el documento original puede ser un PDF o una foto, y
        `recibidos/` tiene que conservarlo tal como llego: es lo unico que
        permite auditar despues si el agente leyo mal o si el documento ya
        venia ilegible.
        """

    @abstractmethod
    def leer_binario(self, prefijo: str, nombre_objeto: str) -> bytes | None:
        """Devuelve el contenido binario guardado, o None si no existe."""
