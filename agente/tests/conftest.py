"""Utilidades compartidas por las pruebas.

Los PDF se construyen a mano en lugar de usar una libreria generadora, para no
sumar una dependencia que solo serviria para los tests. Son PDF validos
minimos: fuente estandar y xref calculado.
"""

import io

import pytest
from PIL import Image


def construir_pdf(lineas: list[str] | None = None, paginas: int = 1) -> bytes:
    """PDF valido de N paginas.

    Sin `lineas`, el PDF queda sin capa de texto: es lo que produce un escaner.
    """

    def flujo_de(numero_pagina: int) -> bytes:
        contenido = "BT /F1 14 Tf 72 720 Td 18 TL\n"

        for linea in lineas or []:
            texto = f"{linea} pag {numero_pagina}" if paginas > 1 else linea
            escapada = (
                texto.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            )
            contenido += f"({escapada}) Tj T*\n"

        return (contenido + "ET").encode("latin-1")

    # Numeracion de objetos: 1 catalogo, 2 arbol de paginas, luego por cada
    # pagina su objeto y su flujo de contenido, y al final la fuente.
    ids_paginas = [3 + i * 2 for i in range(paginas)]
    id_fuente = 3 + paginas * 2

    objetos: list[bytes] = [
        b"<</Type/Catalog/Pages 2 0 R>>",
        b"<</Type/Pages/Kids["
        + b" ".join(b"%d 0 R" % i for i in ids_paginas)
        + b"]/Count %d>>" % paginas,
    ]

    for indice, id_pagina in enumerate(ids_paginas):
        flujo = flujo_de(indice + 1)
        objetos.append(
            b"<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]/Contents %d 0 R"
            b"/Resources<</Font<</F1 %d 0 R>>>>>>" % (id_pagina + 1, id_fuente)
        )
        objetos.append(
            b"<</Length %d>>stream\n" % len(flujo) + flujo + b"\nendstream"
        )

    objetos.append(b"<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>")

    buf = io.BytesIO()
    buf.write(b"%PDF-1.4\n")
    posiciones = []

    for numero, cuerpo in enumerate(objetos, start=1):
        posiciones.append(buf.tell())
        buf.write(b"%d 0 obj" % numero + cuerpo + b"endobj\n")

    inicio_xref = buf.tell()
    buf.write(b"xref\n0 %d\n" % (len(objetos) + 1))
    buf.write(b"0000000000 65535 f \n")

    for posicion in posiciones:
        buf.write(b"%010d 00000 n \n" % posicion)

    buf.write(b"trailer<</Size %d/Root 1 0 R>>\n" % (len(objetos) + 1))
    buf.write(b"startxref\n%d\n%%EOF\n" % inicio_xref)

    return buf.getvalue()


def construir_imagen(
    ancho: int = 400,
    alto: int = 300,
    formato: str = "PNG",
    modo: str = "RGB",
) -> bytes:
    color = 240 if modo == "L" else (240, 240, 240)
    imagen = Image.new(modo, (ancho, alto), color=color)
    buf = io.BytesIO()
    imagen.save(buf, format=formato)
    return buf.getvalue()


class TranscriptorDoble:
    """Doble del transcriptor multimodal. No llama al modelo."""

    def __init__(self, texto: str = "TEXTO TRANSCRITO DE LA IMAGEN"):
        self.texto = texto
        self.llamadas: list[list[bytes]] = []

    def transcribir(self, imagenes: list[bytes]) -> str:
        self.llamadas.append(imagenes)
        return self.texto


@pytest.fixture
def pdf_con_texto() -> bytes:
    return construir_pdf(
        [
            "HOSPITAL SANTA LUCIA - INFORME DE ESTUDIO RADIOLOGICO",
            "Paciente: Carlos Eduardo Mendes, 52 anos",
            "Medico Solicitante: Dra. Renata Silveira MP 145892",
            "Estudio: Tomografia de Torax con contraste",
            "CONCLUSION: Cuadro compatible con Tromboembolismo Pulmonar Agudo.",
        ]
    )


@pytest.fixture
def pdf_escaneado() -> bytes:
    """PDF sin capa de texto: lo que produce un escaner."""
    return construir_pdf(None)


@pytest.fixture
def imagen_png() -> bytes:
    return construir_imagen()


@pytest.fixture
def transcriptor() -> TranscriptorDoble:
    return TranscriptorDoble()
