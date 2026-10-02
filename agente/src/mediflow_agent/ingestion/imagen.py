"""Normalizacion de imagenes antes de mandarlas al modelo.

Una foto de receta sacada con un telefono moderno pesa varios megabytes y tiene
mas resolucion de la que el modelo aprovecha. Mandarla tal cual es lento, caro
y no mejora la lectura. Aca se reduce a un tamano razonable y se convierte todo
a PNG, para que el transcriptor reciba siempre lo mismo.
"""

import io
import logging

from PIL import Image, ImageOps, UnidentifiedImageError

from mediflow_agent.ingestion.base import ErrorDeIngesta

_log = logging.getLogger(__name__)

# Lado maximo en pixeles. Por encima de esto el modelo no gana precision y la
# llamada tarda mas. Una receta manuscrita se lee bien a esta resolucion.
LADO_MAXIMO = 2048


def normalizar(datos: bytes, lado_maximo: int = LADO_MAXIMO) -> tuple[bytes, list[str]]:
    """Devuelve la imagen como PNG, reorientada y acotada en tamano."""
    if not datos:
        raise ErrorDeIngesta("El archivo de imagen llego vacio.")

    avisos: list[str] = []

    try:
        imagen = Image.open(io.BytesIO(datos))
        imagen.load()

    except (UnidentifiedImageError, OSError) as err:
        raise ErrorDeIngesta(
            f"El archivo no es una imagen legible: {err}"
        ) from err

    # Las fotos de telefono guardan la rotacion en los metadatos EXIF en lugar
    # de rotar los pixeles. Sin esto, una receta fotografiada en vertical llega
    # acostada al modelo y se transcribe mucho peor.
    imagen = ImageOps.exif_transpose(imagen)

    if imagen.mode not in ("RGB", "L"):
        # PNG con transparencia, CMYK de un escaner, paleta indexada. Se
        # unifica a RGB para que el modelo reciba siempre lo mismo.
        imagen = imagen.convert("RGB")

    ancho, alto = imagen.size

    if max(ancho, alto) > lado_maximo:
        imagen.thumbnail((lado_maximo, lado_maximo), Image.LANCZOS)
        avisos.append(
            f"La imagen se redujo de {ancho}x{alto} a "
            f"{imagen.size[0]}x{imagen.size[1]} antes de transcribirla."
        )

    buffer = io.BytesIO()
    imagen.save(buffer, format="PNG")

    return buffer.getvalue(), avisos
