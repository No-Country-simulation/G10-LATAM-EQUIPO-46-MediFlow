"""Almacenamiento en OCI mediante un Pre-Authenticated Request (PAR).

Un PAR es una URL que lleva el permiso adentro. Quien la tiene puede leer y
escribir en el bucket sin usuario, sin clave de API y sin acceso a la consola.
Para un equipo de ocho personas en una hackathon eso resuelve el reparto de
credenciales de un plumazo.

A cambio, tiene tres limitaciones que conviene tener presentes:

  1. **La URL ES la credencial.** Quien la consiga tiene el mismo acceso. Va en
     el .env, nunca en el repositorio ni en un canal publico.
  2. **Caduca.** Al crearlo se elige un vencimiento; pasado ese momento, todo
     deja de funcionar de golpe. Conviene que venza despues de la entrega.
  3. **No permite borrar.** OCI no concede DELETE por PAR. No nos afecta: el
     sistema solo escribe y lee.

Cuando haya credenciales IAM propias conviene usar `AlmacenamientoOci`, que es
la via normal. Este modulo existe para no quedar bloqueados mientras tanto.
"""

import logging
import os
import re
from typing import Any
from urllib.parse import quote

from mediflow_agent.storage.base import AlmacenamientoDocumentos, ObjetoGuardado

_log = logging.getLogger(__name__)

TIEMPO_LIMITE = 30

# Un PAR de bucket tiene esta forma:
#   https://objectstorage.<region>.oraclecloud.com/p/<token>/n/<ns>/b/<bucket>/o/
_FORMA_PAR = re.compile(
    r"^https://objectstorage\.(?P<region>[a-z0-9-]+)\.oraclecloud\.com"
    r"/p/(?P<token>[^/]+)/n/(?P<namespace>[^/]+)/b/(?P<bucket>[^/]+)/o/?$"
)


class ErrorDeConfiguracionPar(Exception):
    """El PAR falta o no tiene la forma esperada."""


class AlmacenamientoOciPar(AlmacenamientoDocumentos):

    def __init__(self, url_par: str | None = None, sesion: Any = None):
        url_par = (url_par or os.getenv("MEDIFLOW_OCI_PAR", "")).strip()

        if not url_par:
            raise ErrorDeConfiguracionPar(
                "Falta MEDIFLOW_OCI_PAR. Es la URL del Pre-Authenticated "
                "Request del bucket, que termina en /o/."
            )

        coincidencia = _FORMA_PAR.match(url_par)

        if not coincidencia:
            # El mensaje no repite la URL: lleva el token adentro.
            raise ErrorDeConfiguracionPar(
                "MEDIFLOW_OCI_PAR no tiene la forma de un PAR de bucket de "
                "OCI. Se espera https://objectstorage.<region>.oraclecloud.com"
                "/p/<token>/n/<namespace>/b/<bucket>/o/"
            )

        self._base = url_par if url_par.endswith("/") else url_par + "/"
        self._token = coincidencia.group("token")
        self._bucket = coincidencia.group("bucket")
        self._namespace = coincidencia.group("namespace")
        self._region = coincidencia.group("region")

        if sesion is not None:
            self._sesion = sesion
        else:
            import requests

            self._sesion = requests.Session()

    @property
    def bucket(self) -> str:
        return self._bucket

    @property
    def namespace(self) -> str:
        return self._namespace

    @property
    def region(self) -> str:
        return self._region

    # -- seguridad -------------------------------------------------------

    def _ocultar(self, texto: str) -> str:
        """Quita el token de cualquier texto antes de registrarlo.

        Sin esto el PAR se filtra a los logs: las excepciones de la libreria
        HTTP incluyen la URL completa en su mensaje, y la URL completa ES la
        credencial.
        """
        return texto.replace(self._token, "<PAR-OCULTO>")

    def _url(self, prefijo: str, nombre_objeto: str) -> str:
        # El nombre va codificado: el prefijo con sus barras es parte de la
        # ruta logica del objeto, pero el nombre no puede aportar barras
        # propias (eso lo valida _nombre_valido).
        return self._base + quote(f"{prefijo}/{nombre_objeto}", safe="/")

    # -- escritura -------------------------------------------------------

    def _guardar(
        self,
        prefijo: str,
        nombre_objeto: str,
        cuerpo: bytes,
        tipo_contenido: str,
    ) -> ObjetoGuardado:
        ruta = f"{prefijo}/{nombre_objeto}"

        if not _nombre_valido(nombre_objeto):
            motivo = f"El nombre de objeto {nombre_objeto!r} no es un segmento simple."
            _log.warning(motivo)
            return ObjetoGuardado(self._bucket, ruta, False, motivo)

        try:
            respuesta = self._sesion.put(
                self._url(prefijo, nombre_objeto),
                data=cuerpo,
                headers={"Content-Type": tipo_contenido},
                timeout=TIEMPO_LIMITE,
            )

            if respuesta.status_code not in (200, 201):
                motivo = f"OCI respondio {respuesta.status_code} al guardar."
                _log.warning("%s Objeto: %s", motivo, ruta)
                return ObjetoGuardado(self._bucket, ruta, False, motivo)

            return ObjetoGuardado(self._bucket, ruta, True)

        except Exception as err:  # noqa: BLE001 - el almacen no tumba el triaje
            motivo = self._ocultar(str(err))
            _log.warning("No se pudo guardar %s: %s", ruta, motivo)
            return ObjetoGuardado(self._bucket, ruta, False, motivo)

    def guardar_texto(
        self,
        prefijo: str,
        nombre_objeto: str,
        contenido: str,
        tipo_contenido: str = "application/json",
    ) -> ObjetoGuardado:
        return self._guardar(
            prefijo, nombre_objeto, contenido.encode("utf-8"), tipo_contenido
        )

    def guardar_binario(
        self,
        prefijo: str,
        nombre_objeto: str,
        contenido: bytes,
        tipo_contenido: str = "application/octet-stream",
    ) -> ObjetoGuardado:
        return self._guardar(prefijo, nombre_objeto, contenido, tipo_contenido)

    # -- lectura ---------------------------------------------------------

    def _leer(self, prefijo: str, nombre_objeto: str) -> bytes | None:
        if not _nombre_valido(nombre_objeto):
            return None

        try:
            respuesta = self._sesion.get(
                self._url(prefijo, nombre_objeto), timeout=TIEMPO_LIMITE
            )

            if respuesta.status_code == 404:
                # Que el objeto no exista es una respuesta valida, no un fallo.
                return None

            if respuesta.status_code != 200:
                _log.warning(
                    "OCI respondio %s al leer %s/%s",
                    respuesta.status_code,
                    prefijo,
                    nombre_objeto,
                )
                return None

            return respuesta.content

        except Exception as err:  # noqa: BLE001
            _log.warning(
                "Error al leer %s/%s: %s",
                prefijo,
                nombre_objeto,
                self._ocultar(str(err)),
            )
            return None

    def leer_texto(self, prefijo: str, nombre_objeto: str) -> str | None:
        datos = self._leer(prefijo, nombre_objeto)
        return datos.decode("utf-8") if datos is not None else None

    def leer_binario(self, prefijo: str, nombre_objeto: str) -> bytes | None:
        return self._leer(prefijo, nombre_objeto)

    # -- diagnostico -----------------------------------------------------

    def listar(self) -> list[str] | None:
        """Nombres de los objetos del bucket, o None si el PAR no lo permite.

        Solo para el script de verificacion: el sistema no lo usa.
        """
        try:
            respuesta = self._sesion.get(self._base, timeout=TIEMPO_LIMITE)

            if respuesta.status_code != 200:
                return None

            return [o["name"] for o in respuesta.json().get("objects", [])]

        except Exception as err:  # noqa: BLE001
            _log.warning("No se pudo listar el bucket: %s", self._ocultar(str(err)))
            return None


def _nombre_valido(nombre_objeto: str) -> bool:
    return bool(
        nombre_objeto
        and nombre_objeto not in {".", ".."}
        and "/" not in nombre_objeto
        and "\\" not in nombre_objeto
    )
