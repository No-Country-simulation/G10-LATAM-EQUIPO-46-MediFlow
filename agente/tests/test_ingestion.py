"""Pruebas de la ingesta (tarea 2.1).

Ninguna llama al modelo: el transcriptor multimodal se sustituye por un doble.
"""

import pytest

from mediflow_agent.ingestion.base import DocumentoNormalizado, ErrorDeIngesta
from mediflow_agent.ingestion.imagen import normalizar
from mediflow_agent.ingestion.ingestor import Ingestor
from mediflow_agent.ingestion.pdf import extraer_texto, rasterizar

from conftest import TranscriptorDoble, construir_imagen, construir_pdf


# --- PDF: capa de texto ---------------------------------------------------

def test_se_lee_la_capa_de_texto_de_un_pdf_nativo(pdf_con_texto):
    texto, paginas = extraer_texto(pdf_con_texto)

    assert paginas == 1
    assert "HOSPITAL SANTA LUCIA" in texto
    assert "Tromboembolismo Pulmonar Agudo" in texto
    assert "\r" not in texto, "los saltos tienen que venir normalizados"


def test_un_pdf_escaneado_no_tiene_capa_de_texto(pdf_escaneado):
    texto, paginas = extraer_texto(pdf_escaneado)

    assert paginas == 1
    assert texto.strip() == ""


def test_un_archivo_que_no_es_pdf_falla_con_mensaje_claro():
    with pytest.raises(ErrorDeIngesta, match="no es un PDF legible"):
        extraer_texto(b"esto no es un pdf")


def test_un_pdf_vacio_falla():
    with pytest.raises(ErrorDeIngesta, match="vacio"):
        extraer_texto(b"")


# --- PDF: rasterizado -----------------------------------------------------

def test_rasterizar_devuelve_un_png_por_pagina(pdf_escaneado):
    imagenes, avisos = rasterizar(pdf_escaneado)

    assert len(imagenes) == 1
    assert imagenes[0].startswith(b"\x89PNG")
    assert avisos == []


def test_un_pdf_largo_se_trunca_y_lo_avisa():
    # El aviso importa: sin el, un auditor podria creer que el agente vio el
    # documento entero cuando solo vio las primeras paginas.
    imagenes, avisos = rasterizar(construir_pdf(None, paginas=3), maximo_paginas=2)

    assert len(imagenes) == 2
    assert len(avisos) == 1
    assert "3 paginas" in avisos[0] and "primeras 2" in avisos[0]


def test_un_pdf_de_varias_paginas_se_lee_entero(pdf_con_texto):
    texto, paginas = extraer_texto(construir_pdf(["Linea de prueba"], paginas=3))

    assert paginas == 3
    assert texto.count("Linea de prueba") == 3


# --- Imagenes -------------------------------------------------------------

def test_una_imagen_se_normaliza_a_png(imagen_png):
    salida, avisos = normalizar(imagen_png)

    assert salida.startswith(b"\x89PNG")
    assert avisos == []


def test_un_jpeg_tambien_sale_como_png():
    jpeg = construir_imagen(formato="JPEG")
    salida, _ = normalizar(jpeg)

    assert salida.startswith(b"\x89PNG")


def test_una_imagen_enorme_se_reduce_y_lo_avisa():
    grande = construir_imagen(ancho=4000, alto=3000)
    salida, avisos = normalizar(grande, lado_maximo=1000)

    assert salida.startswith(b"\x89PNG")
    assert len(avisos) == 1
    assert "se redujo" in avisos[0]


def test_un_archivo_que_no_es_imagen_falla():
    with pytest.raises(ErrorDeIngesta, match="no es una imagen legible"):
        normalizar(b"no soy una imagen")


# --- Ingestor: decision de camino ----------------------------------------

def test_el_texto_plano_pasa_derecho():
    doc = Ingestor().ingerir("TEXTO", texto="  Informe de laboratorio  ")

    assert doc == DocumentoNormalizado(texto="Informe de laboratorio", origen="texto_plano")
    assert doc.fue_transcrito is False


def test_un_texto_vacio_falla():
    with pytest.raises(ErrorDeIngesta, match="vacio"):
        Ingestor().ingerir("TEXTO", texto="   ")


def test_un_pdf_nativo_no_llama_al_transcriptor(pdf_con_texto, transcriptor):
    doc = Ingestor(transcriptor).ingerir("PDF", contenido=pdf_con_texto)

    assert doc.origen == "pdf_nativo"
    assert doc.fue_transcrito is False
    assert "Tromboembolismo" in doc.texto
    assert transcriptor.llamadas == [], "no hacia falta gastar una llamada al modelo"


def test_un_pdf_escaneado_se_transcribe(pdf_escaneado, transcriptor):
    doc = Ingestor(transcriptor).ingerir("PDF", contenido=pdf_escaneado)

    assert doc.origen == "pdf_escaneado"
    assert doc.fue_transcrito is True
    assert doc.texto == transcriptor.texto
    assert len(transcriptor.llamadas) == 1
    assert len(transcriptor.llamadas[0]) == 1, "una imagen por pagina"


def test_una_capa_de_texto_pobre_se_trata_como_escaneo(transcriptor):
    # Este es el caso peligroso: el PDF TIENE texto, asi que parece exito, pero
    # son cuatro palabras de un OCR malo. Sin esta regla llegaria practicamente
    # vacio al clasificador y nadie se enteraria.
    pdf_pobre = construir_pdf(["Pag 1"])

    doc = Ingestor(transcriptor).ingerir("PDF", contenido=pdf_pobre)

    assert doc.origen == "pdf_escaneado"
    assert len(transcriptor.llamadas) == 1
    assert any("capa de texto muy pobre" in a for a in doc.avisos)


def test_una_imagen_se_transcribe(imagen_png, transcriptor):
    doc = Ingestor(transcriptor).ingerir("IMAGEN", contenido=imagen_png)

    assert doc.origen == "imagen"
    assert doc.fue_transcrito is True
    assert doc.texto == transcriptor.texto


def test_los_avisos_de_la_imagen_llegan_al_documento(transcriptor):
    grande = construir_imagen(ancho=4000, alto=3000)
    doc = Ingestor(transcriptor).ingerir("IMAGEN", contenido=grande)

    assert any("se redujo" in a for a in doc.avisos)


# --- Ingestor: errores ----------------------------------------------------

def test_un_formato_no_soportado_falla():
    with pytest.raises(ErrorDeIngesta, match="Formato no soportado"):
        Ingestor().ingerir("DOCX", contenido=b"x")


def test_un_pdf_sin_archivo_falla():
    with pytest.raises(ErrorDeIngesta, match="necesita el archivo"):
        Ingestor().ingerir("PDF", texto="solo texto")


def test_sin_transcriptor_un_escaneo_falla_en_vez_de_devolver_vacio(pdf_escaneado):
    with pytest.raises(ErrorDeIngesta, match="transcriptor"):
        Ingestor().ingerir("PDF", contenido=pdf_escaneado)


def test_si_el_modelo_transcribe_vacio_se_falla_y_no_se_inventa(pdf_escaneado):
    ingestor = Ingestor(TranscriptorDoble(texto="   "))

    with pytest.raises(ErrorDeIngesta, match="texto legible"):
        ingestor.ingerir("PDF", contenido=pdf_escaneado)
