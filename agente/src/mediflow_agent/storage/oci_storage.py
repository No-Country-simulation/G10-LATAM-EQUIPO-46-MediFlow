"""Implementacion de `AlmacenamientoDocumentos` sobre OCI Object Storage.

Es el requisito obligatorio del enunciado: "Integracion activa con OCI Object
Storage (capa Always Free) para la segregacion y almacenamiento de los
documentos".

Respeta el mismo contrato que `AlmacenamientoLocal`, incluida la regla que mas
importa: **un fallo del almacen no lanza excepcion**. Cuando se intenta
guardar, el triaje ya se resolvio y la decision clinica ya esta tomada. Que el
bucket no responda se informa como `status_backup: "fallo"` y se reintenta
aparte; nunca tumba una respuesta que el consumidor necesita.

El modulo se llama `oci_storage` y no `oci` a proposito: un modulo llamado
`oci` dentro del paquete confundiria a cualquiera que lea un `import oci` en
este archivo.

Configuracion, en orden de preferencia:

  1. Variables de entorno (OCI_USER_OCID, OCI_TENANCY_OCID, OCI_FINGERPRINT,
     OCI_PRIVATE_KEY, OCI_REGION). Es lo que conviene para desplegar.
  2. El archivo ~/.oci/config que genera la consola de OCI. Es lo mas comodo
     para trabajar en la maquina de cada uno.
"""

import logging
import os
from typing import Any

from mediflow_agent.config import variable
from mediflow_agent.storage.base import AlmacenamientoDocumentos, ObjetoGuardado

_log = logging.getLogger(__name__)

# Reintentos ante fallo de red. El SDK de OCI trae su propia estrategia; se usa
# la por defecto en lugar de escribir una propia.
NOMBRE_BUCKET_POR_DEFECTO = "mediflow-documentos-clinicos"


class ErrorDeConfiguracionOci(Exception):
    """Falta configuracion para hablar con OCI.

    Se lanza al construir el cliente, no al guardar: si las credenciales estan
    mal, conviene enterarse cuando arranca la aplicacion y no la primera vez
    que alguien manda un documento urgente.
    """


def _configuracion_desde_entorno() -> dict[str, Any] | None:
    """Arma la configuracion del SDK desde variables de entorno.

    Devuelve None si no estan todas: en ese caso se cae al archivo de config.
    Se exige que esten TODAS y no algunas, porque una configuracion a medias
    falla mas tarde y con un mensaje peor.
    """
    requeridas = {
        "user": variable("OCI_USER_OCID"),
        "tenancy": variable("OCI_TENANCY_OCID"),
        "fingerprint": variable("OCI_FINGERPRINT"),
        "region": variable("OCI_REGION"),
    }
    clave = variable("OCI_PRIVATE_KEY")

    if not all(requeridas.values()) or not clave:
        return None

    configuracion: dict[str, Any] = dict(requeridas)

    # La clave privada puede venir como contenido (una variable de entorno con
    # el PEM completo, con los saltos de linea escapados) o como ruta a un
    # archivo .pem. El PEM en la variable es lo que sirve para desplegar.
    if clave.strip().startswith("-----BEGIN"):
        configuracion["key_content"] = clave.replace("\\n", "\n")
    else:
        configuracion["key_file"] = clave

    if passphrase := variable("OCI_PASSPHRASE"):
        configuracion["pass_phrase"] = passphrase

    return configuracion


class AlmacenamientoOci(AlmacenamientoDocumentos):

    def __init__(
        self,
        nombre_bucket: str | None = None,
        namespace: str | None = None,
        cliente: Any = None,
        configuracion: dict[str, Any] | None = None,
    ):
        """Construye el cliente.

        `cliente` permite inyectar un doble en las pruebas, para que la suite
        no necesite credenciales ni toque un bucket real.
        """
        import oci  # import local: el SDK solo hace falta si se usa OCI

        self._bucket = nombre_bucket or variable(
            "MEDIFLOW_BUCKET", NOMBRE_BUCKET_POR_DEFECTO
        )

        if cliente is not None:
            self._cliente = cliente
        else:
            configuracion = configuracion or _configuracion_desde_entorno()

            if configuracion is None:
                try:
                    configuracion = oci.config.from_file(
                        file_location=variable("OCI_CONFIG_FILE", "~/.oci/config"),
                        profile_name=variable("OCI_CONFIG_PROFILE", "DEFAULT"),
                    )
                except (
                    oci.exceptions.ConfigFileNotFound,
                    oci.exceptions.InvalidConfig,
                ) as err:
                    raise ErrorDeConfiguracionOci(
                        "No hay configuracion de OCI. Defini las variables de "
                        "entorno OCI_USER_OCID, OCI_TENANCY_OCID, "
                        "OCI_FINGERPRINT, OCI_REGION y OCI_PRIVATE_KEY, o "
                        f"crea el archivo ~/.oci/config. Detalle: {err}"
                    ) from err

            try:
                oci.config.validate_config(configuracion)
            except oci.exceptions.InvalidConfig as err:
                raise ErrorDeConfiguracionOci(
                    f"La configuracion de OCI es invalida: {err}"
                ) from err

            self._cliente = oci.object_storage.ObjectStorageClient(configuracion)

        # El namespace identifica la tenancy y no cambia nunca. Se consulta una
        # sola vez al arrancar en lugar de en cada operacion.
        self._namespace = namespace or variable("OCI_NAMESPACE") or self._obtener_namespace()

    def _obtener_namespace(self) -> str:
        try:
            return self._cliente.get_namespace().data
        except Exception as err:  # noqa: BLE001
            raise ErrorDeConfiguracionOci(
                f"No se pudo obtener el namespace de OCI: {err}"
            ) from err

    @property
    def bucket(self) -> str:
        return self._bucket

    @property
    def namespace(self) -> str:
        return self._namespace

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
            # Misma regla que el almacen local: el nombre sale del
            # documento_id, que es entrada externa. Un nombre con barras
            # dejaria el objeto fuera del prefijo que le corresponde y rompe la
            # segregacion por estado que exige el enunciado.
            motivo = f"El nombre de objeto {nombre_objeto!r} no es un segmento simple."
            _log.warning(motivo)
            return ObjetoGuardado(self._bucket, ruta, False, motivo)

        try:
            self._cliente.put_object(
                namespace_name=self._namespace,
                bucket_name=self._bucket,
                object_name=ruta,
                put_object_body=cuerpo,
                content_type=tipo_contenido,
            )
            return ObjetoGuardado(self._bucket, ruta, True)

        except Exception as err:  # noqa: BLE001 - el almacen no tumba el triaje
            _log.warning("No se pudo guardar %s en OCI: %s", ruta, err)
            return ObjetoGuardado(self._bucket, ruta, False, str(err))

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
        import oci

        if not _nombre_valido(nombre_objeto):
            return None

        try:
            respuesta = self._cliente.get_object(
                namespace_name=self._namespace,
                bucket_name=self._bucket,
                object_name=f"{prefijo}/{nombre_objeto}",
            )
            return respuesta.data.content

        except oci.exceptions.ServiceError as err:
            if err.status == 404:
                # Que el objeto no exista es una respuesta valida, no un fallo.
                return None
            _log.warning("Error al leer %s/%s: %s", prefijo, nombre_objeto, err)
            return None

        except Exception as err:  # noqa: BLE001
            _log.warning("Error al leer %s/%s: %s", prefijo, nombre_objeto, err)
            return None

    def leer_texto(self, prefijo: str, nombre_objeto: str) -> str | None:
        datos = self._leer(prefijo, nombre_objeto)
        return datos.decode("utf-8") if datos is not None else None

    def leer_binario(self, prefijo: str, nombre_objeto: str) -> bytes | None:
        return self._leer(prefijo, nombre_objeto)


def _nombre_valido(nombre_objeto: str) -> bool:
    return bool(
        nombre_objeto
        and nombre_objeto not in {".", ".."}
        and "/" not in nombre_objeto
        and "\\" not in nombre_objeto
    )
