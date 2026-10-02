"""Representacion interna unica de un documento ingerido.

El objetivo de la tarea 2.1 es que el resto del sistema deje de saber en que
formato llego el documento. Entre un PDF nativo, un PDF escaneado, una foto o
un texto pegado a mano, todos salen de aca como el mismo objeto y el
clasificador y el extractor no cambian una linea.

Lo que SI se conserva es COMO se obtuvo el texto, en `origen`. No es un dato
decorativo: un texto transcrito por el modelo desde una foto borrosa merece
menos confianza que uno leido directamente de la capa de texto de un PDF, y la
deteccion de urgencia de la semana 3 va a querer esa distincion.
"""

from dataclasses import dataclass, field
from typing import Literal

# De donde salio el texto, en orden decreciente de fiabilidad.
OrigenTexto = Literal[
    "texto_plano",      # llego ya como texto, sin intermediarios
    "pdf_nativo",       # capa de texto del PDF, sin interpretacion
    "pdf_escaneado",    # paginas rasterizadas y transcritas por el modelo
    "imagen",           # foto o captura transcrita por el modelo
]

# Origenes en los que un modelo interpreto pixeles. Todo lo que venga de aca
# arrastra incertidumbre de transcripcion ademas de la de extraccion.
ORIGENES_TRANSCRITOS = frozenset({"pdf_escaneado", "imagen"})

# Un PDF con capa de texto pero casi vacia suele ser un escaneo al que alguien
# le paso un OCR pobre, o un PDF de solo imagenes. Por debajo de este promedio
# de caracteres utiles por pagina se prefiere rasterizar y transcribir.
MINIMO_CARACTERES_POR_PAGINA = 80


class ErrorDeIngesta(Exception):
    """El documento no se pudo leer en absoluto.

    Es distinto de "se leyo y salio poco texto": eso es un documento pobre, y
    el enrutamiento lo va a derivar a revision humana por baja confianza. Esto
    es un archivo corrupto, vacio o de un tipo que no es el declarado.
    """


@dataclass(frozen=True)
class DocumentoNormalizado:
    """Lo que el resto del sistema recibe, venga de donde venga."""

    texto: str
    origen: OrigenTexto
    paginas: int = 1

    # Avisos no fatales acumulados durante la ingesta: paginas que no se
    # pudieron transcribir, imagenes redimensionadas, capa de texto sospechosa.
    # Viajan hasta la respuesta para que el auditor humano sepa que mirar.
    avisos: tuple[str, ...] = field(default_factory=tuple)

    @property
    def fue_transcrito(self) -> bool:
        """True si un modelo tuvo que interpretar pixeles para obtener el texto."""
        return self.origen in ORIGENES_TRANSCRITOS

    @property
    def tiene_contenido_util(self) -> bool:
        return bool(self.texto and self.texto.strip())
