"""Lectura de PDF: capa de texto y rasterizado de paginas.

Se usa pypdfium2 y no PyMuPDF ni pdf2image, por dos razones concretas:

  - PyMuPDF es AGPL, y este proyecto se publica en un repositorio abierto.
  - pdf2image necesita que Poppler este instalado aparte en el sistema, que es
    exactamente el tipo de paso que rompe la instalacion limpia desde cero que
    pide la tarea 5.1, sobre todo en Windows.

pypdfium2 es BSD/Apache y viene en una rueda autocontenida.
"""

import io
import logging

import pypdfium2 as pdfium

from mediflow_agent.ingestion.base import ErrorDeIngesta

_log = logging.getLogger(__name__)

# Factor de rasterizado. 2 equivale a unos 144 DPI, suficiente para que el
# modelo lea texto impreso sin generar imagenes enormes que tarden y cuesten.
ESCALA_RASTERIZADO = 2.0

# Tope de paginas a transcribir. Un informe clinico rara vez pasa de unas pocas
# paginas; un PDF de cien paginas es casi siempre un error de carga, y
# transcribirlo entero quemaria la cuota del modelo de una sola vez.
MAXIMO_PAGINAS_TRANSCRITAS = 10


def _abrir(datos: bytes) -> pdfium.PdfDocument:
    if not datos:
        raise ErrorDeIngesta("El archivo PDF llego vacio.")

    try:
        return pdfium.PdfDocument(datos)
    except Exception as err:  # noqa: BLE001 - pdfium lanza tipos variados
        raise ErrorDeIngesta(f"El archivo no es un PDF legible: {err}") from err


def extraer_texto(datos: bytes) -> tuple[str, int]:
    """Devuelve la capa de texto del PDF y su cantidad de paginas.

    Un PDF escaneado devuelve cadena vacia o casi: no es un error, es la senal
    de que hay que rasterizar y transcribir. Quien llama decide.
    """
    documento = _abrir(datos)

    try:
        paginas = len(documento)
        partes = []

        for indice in range(paginas):
            pagina_texto = documento[indice].get_textpage()
            partes.append(pagina_texto.get_text_bounded() or "")

        # Se normalizan los saltos: pdfium devuelve \r\n y el resto del sistema
        # trabaja con \n.
        texto = "\n".join(partes).replace("\r\n", "\n").replace("\r", "\n")

        return texto.strip(), paginas

    finally:
        documento.close()


def rasterizar(
    datos: bytes,
    escala: float = ESCALA_RASTERIZADO,
    maximo_paginas: int = MAXIMO_PAGINAS_TRANSCRITAS,
) -> tuple[list[bytes], list[str]]:
    """Convierte las paginas del PDF en imagenes PNG.

    Devuelve las imagenes y los avisos generados (por ejemplo, si se truncaron
    paginas). Los avisos no se registran y se olvidan: viajan hasta la
    respuesta para que un auditor humano sepa que no vio el documento entero.
    """
    documento = _abrir(datos)
    avisos: list[str] = []

    try:
        total = len(documento)
        a_procesar = min(total, maximo_paginas)

        if total > maximo_paginas:
            avisos.append(
                f"El PDF tiene {total} paginas y solo se transcribieron las "
                f"primeras {maximo_paginas}. Revisar el documento completo a mano."
            )

        imagenes: list[bytes] = []

        for indice in range(a_procesar):
            try:
                imagen = documento[indice].render(scale=escala).to_pil()
                buffer = io.BytesIO()
                imagen.save(buffer, format="PNG")
                imagenes.append(buffer.getvalue())

            except Exception as err:  # noqa: BLE001
                # Una pagina ilegible no invalida las demas, pero tiene que
                # quedar dicho: puede ser justo la que traia el hallazgo.
                _log.warning("No se pudo rasterizar la pagina %d: %s", indice + 1, err)
                avisos.append(
                    f"No se pudo leer la pagina {indice + 1} del PDF."
                )

        if not imagenes:
            raise ErrorDeIngesta(
                "No se pudo rasterizar ninguna pagina del PDF."
            )

        return imagenes, avisos

    finally:
        documento.close()
