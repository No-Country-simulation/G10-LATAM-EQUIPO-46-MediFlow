"""Implementacion de `AlmacenamientoDocumentos` sobre el sistema de archivos.

Es el sustituto temporal de OCI Object Storage mientras no exista la cuenta
Always Free (tarea 1.2). Reproduce la misma estructura de prefijos, asi que lo
que se guarde hoy en disco tiene exactamente las mismas rutas que tendra el
bucket, y migrar es copiar el arbol.

No es la entrega: el enunciado exige OCI y esto no lo reemplaza. Es lo que
permite que el endpoint funcione de punta a punta desde ya.
"""

import logging
from pathlib import Path

from mediflow_agent.storage.base import AlmacenamientoDocumentos, ObjetoGuardado

_log = logging.getLogger(__name__)


class AlmacenamientoLocal(AlmacenamientoDocumentos):

    def __init__(self, raiz: Path | str, nombre_bucket: str = "mediflow-local"):
        self._raiz = Path(raiz)
        self._bucket = nombre_bucket

    @property
    def bucket(self) -> str:
        return self._bucket

    def _ruta_absoluta(self, prefijo: str, nombre_objeto: str) -> Path:
        # `nombre_objeto` se deriva del `documento_id` de la solicitud, que es
        # entrada externa y no controlamos. Se exige que sea un unico segmento.
        #
        # No alcanza con comprobar que el resultado caiga dentro de la raiz:
        # un nombre como "../../x.json" bajo "procesados/rutina" resuelve a
        # "<raiz>/x.json", que esta dentro del almacen pero FUERA del prefijo
        # que le corresponde. Eso rompe la segregacion por estado que el
        # enunciado exige, aunque no escape del bucket.
        if (
            not nombre_objeto
            or nombre_objeto in {".", ".."}
            or "/" in nombre_objeto
            or "\\" in nombre_objeto
        ):
            raise ValueError(
                f"El nombre de objeto {nombre_objeto!r} no es un segmento simple."
            )

        destino = (self._raiz / prefijo / nombre_objeto).resolve()
        esperado = (self._raiz / prefijo).resolve()

        # Defensa en profundidad: aunque el nombre ya se valido, el prefijo
        # tambien tiene que quedar donde corresponde.
        if destino.parent != esperado:
            raise ValueError(
                f"El objeto {nombre_objeto!r} no cae dentro del prefijo {prefijo!r}."
            )

        return destino

    def guardar_texto(
        self,
        prefijo: str,
        nombre_objeto: str,
        contenido: str,
        tipo_contenido: str = "application/json",
    ) -> ObjetoGuardado:
        ruta_logica = f"{prefijo}/{nombre_objeto}"

        try:
            destino = self._ruta_absoluta(prefijo, nombre_objeto)
            destino.parent.mkdir(parents=True, exist_ok=True)
            destino.write_text(contenido, encoding="utf-8")

            return ObjetoGuardado(
                bucket=self._bucket,
                ruta_objeto=ruta_logica,
                exito=True,
            )

        except (OSError, ValueError) as err:
            # Se registra pero no se propaga: el triaje ya se resolvio y la
            # respuesta debe llegar al cliente con status_backup en "fallo".
            _log.warning("No se pudo guardar %s: %s", ruta_logica, err)

            return ObjetoGuardado(
                bucket=self._bucket,
                ruta_objeto=ruta_logica,
                exito=False,
                detalle_error=str(err),
            )

    def leer_texto(self, prefijo: str, nombre_objeto: str) -> str | None:
        try:
            destino = self._ruta_absoluta(prefijo, nombre_objeto)
        except ValueError:
            return None

        if not destino.is_file():
            return None

        return destino.read_text(encoding="utf-8")
