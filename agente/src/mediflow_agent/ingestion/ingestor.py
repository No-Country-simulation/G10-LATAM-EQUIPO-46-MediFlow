"""Punto de entrada unico de la ingesta.

Decide, segun el formato y el contenido real del archivo, como obtener el texto
y devuelve siempre un `DocumentoNormalizado`. Es el unico modulo que sabe que
existen los PDF y las imagenes; de aca para adentro del sistema, todo es texto.

La decision que importa esta en `_ingerir_pdf`: un PDF puede traer una capa de
texto perfecta, no traer ninguna, o traer una capa pobre de un OCR malo. El
tercer caso es el peligroso, porque parece exito y no lo es. Se detecta por
densidad de caracteres por pagina y se cae a transcripcion.
"""

import logging

from mediflow_agent.ingestion.base import (
    MINIMO_CARACTERES_POR_PAGINA,
    DocumentoNormalizado,
    ErrorDeIngesta,
)
from mediflow_agent.ingestion.imagen import normalizar as normalizar_imagen
from mediflow_agent.ingestion.pdf import extraer_texto, rasterizar
from mediflow_agent.ingestion.transcriptor import Transcriptor

_log = logging.getLogger(__name__)

FORMATOS_SOPORTADOS = frozenset({"TEXTO", "JSON", "PDF", "IMAGEN"})


class Ingestor:

    def __init__(self, transcriptor: Transcriptor | None = None):
        # El transcriptor es opcional: sin el, la ingesta sigue leyendo texto
        # plano y PDF nativo. Solo el escaneado y la imagen lo necesitan.
        self._transcriptor = transcriptor

    # -- entrada publica -------------------------------------------------

    def ingerir(
        self,
        tipo_archivo: str,
        contenido: bytes | None = None,
        texto: str | None = None,
    ) -> DocumentoNormalizado:
        if tipo_archivo not in FORMATOS_SOPORTADOS:
            raise ErrorDeIngesta(
                f"Formato no soportado: {tipo_archivo!r}. "
                f"Admitidos: {', '.join(sorted(FORMATOS_SOPORTADOS))}."
            )

        if tipo_archivo in ("TEXTO", "JSON"):
            return self._ingerir_texto(texto)

        if contenido is None:
            raise ErrorDeIngesta(
                f"Un documento de tipo {tipo_archivo} necesita el archivo, "
                "no solo texto."
            )

        if tipo_archivo == "PDF":
            return self._ingerir_pdf(contenido)

        return self._ingerir_imagen(contenido)

    # -- por formato -----------------------------------------------------

    def _ingerir_texto(self, texto: str | None) -> DocumentoNormalizado:
        if not texto or not texto.strip():
            raise ErrorDeIngesta("El documento de texto llego vacio.")

        return DocumentoNormalizado(texto=texto.strip(), origen="texto_plano")

    def _ingerir_pdf(self, contenido: bytes) -> DocumentoNormalizado:
        texto, paginas = extraer_texto(contenido)

        if self._capa_de_texto_es_suficiente(texto, paginas):
            return DocumentoNormalizado(
                texto=texto,
                origen="pdf_nativo",
                paginas=paginas,
            )

        # Capa de texto ausente o sospechosamente pobre: es un escaneo.
        avisos: list[str] = []

        if texto.strip():
            avisos.append(
                "El PDF traia una capa de texto muy pobre para su cantidad de "
                "paginas; se transcribio la imagen en su lugar."
            )

        imagenes, avisos_raster = rasterizar(contenido)
        avisos.extend(avisos_raster)

        transcrito = self._transcribir(imagenes)

        return DocumentoNormalizado(
            texto=transcrito,
            origen="pdf_escaneado",
            paginas=paginas,
            avisos=tuple(avisos),
        )

    def _ingerir_imagen(self, contenido: bytes) -> DocumentoNormalizado:
        imagen, avisos = normalizar_imagen(contenido)
        transcrito = self._transcribir([imagen])

        return DocumentoNormalizado(
            texto=transcrito,
            origen="imagen",
            paginas=1,
            avisos=tuple(avisos),
        )

    # -- apoyo -----------------------------------------------------------

    @staticmethod
    def _capa_de_texto_es_suficiente(texto: str, paginas: int) -> bool:
        """Decide si la capa de texto del PDF alcanza o hay que transcribir.

        Se mide por promedio de caracteres por pagina y no por total: un PDF de
        veinte paginas con doscientos caracteres tiene texto, pero claramente no
        el del documento. Ese es el caso que, sin esta comprobacion, pasaria
        como exito y llegaria al clasificador practicamente vacio.
        """
        limpio = texto.strip()

        if not limpio:
            return False

        return len(limpio) / max(paginas, 1) >= MINIMO_CARACTERES_POR_PAGINA

    def _transcribir(self, imagenes: list[bytes]) -> str:
        if self._transcriptor is None:
            raise ErrorDeIngesta(
                "Este documento necesita transcripcion multimodal y no hay un "
                "transcriptor configurado."
            )

        texto = self._transcriptor.transcribir(imagenes)

        if not texto or not texto.strip():
            # El modelo respondio pero no saco nada. No se inventa contenido:
            # se falla, y el endpoint deriva el caso a revision humana.
            raise ErrorDeIngesta(
                "No se pudo extraer texto legible del documento."
            )

        return texto.strip()
