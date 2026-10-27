"""Genera los tres documentos clinicos de la demo en PDF.

Los tres escenarios que exige el enunciado:

    1_rutina_orden_laboratorio.pdf      flujo estandar, sin intervencion
    2_urgencia_informe_tomografia.pdf   hallazgo critico -> emergencia
    3_ambiguedad_receta_manuscrita.pdf  receta con la dosis ILEGIBLE

El tercero no dice "[ilegible]" en ninguna parte: esta escrito con una
tipografia manuscrita y la dosis es un garabato dibujado, no texto. Esa es
la diferencia entre demostrar el comportamiento y declararlo. Si el PDF
trajera la palabra "ilegible" escrita, el agente no estaria leyendo un
documento dificil: estaria obedeciendo una etiqueta.

Los datos de pacientes y profesionales son FICTICIOS.

reportlab no esta en requirements.txt a proposito: hace falta para regenerar
estos PDF, no para correr el agente.

    pip install reportlab
    python scripts/generar_pdfs_demo.py
"""

import random
from pathlib import Path

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

SALIDA = Path(__file__).resolve().parent.parent / "examples" / "pdf"

ANCHO, ALTO = A4
MARGEN = 22 * mm

TINTA = HexColor("#1a1a1a")
GRIS = HexColor("#555555")
LINEA = HexColor("#bbbbbb")
LAPICERA = HexColor("#1b2f6b")  # azul de boligrafo

# Windows trae estas dos. Si falta la manuscrita el tercer PDF pierde el
# sentido, asi que se avisa en lugar de caer a una serif cualquiera.
FUENTES = {
    "Manuscrita": r"C:\Windows\Fonts\segoepr.ttf",
    "ManuscritaFuerte": r"C:\Windows\Fonts\segoeprb.ttf",
}

FICTICIO = (
    "Documento ficticio generado para la demostracion de MediFlow. "
    "No corresponde a ninguna persona real."
)


def registrar_manuscrita() -> bool:
    try:
        for nombre, ruta in FUENTES.items():
            pdfmetrics.registerFont(TTFont(nombre, ruta))
        return True
    except Exception as error:
        print(f"  AVISO: no se pudo cargar la tipografia manuscrita ({error}).")
        return False


def membrete(c, institucion: str, subtitulo: str) -> float:
    """Dibuja el encabezado y devuelve la altura donde sigue el cuerpo."""
    y = ALTO - MARGEN

    c.setFillColor(TINTA)
    c.setFont("Helvetica-Bold", 15)
    c.drawString(MARGEN, y, institucion)

    y -= 6 * mm
    c.setFillColor(GRIS)
    c.setFont("Helvetica", 9.5)
    c.drawString(MARGEN, y, subtitulo)

    y -= 4 * mm
    c.setStrokeColor(LINEA)
    c.setLineWidth(0.8)
    c.line(MARGEN, y, ANCHO - MARGEN, y)

    return y - 10 * mm


def campo(c, y: float, etiqueta: str, valor: str, ancho_etiqueta=38 * mm) -> float:
    c.setFillColor(GRIS)
    c.setFont("Helvetica", 9)
    c.drawString(MARGEN, y, etiqueta.upper())

    c.setFillColor(TINTA)
    c.setFont("Helvetica", 10.5)
    c.drawString(MARGEN + ancho_etiqueta, y, valor)

    return y - 6.5 * mm


def parrafo(c, y: float, texto: str, fuente="Helvetica", tam=10.5) -> float:
    """Corta el texto al ancho util. Suficiente para documentos cortos."""
    c.setFillColor(TINTA)
    c.setFont(fuente, tam)

    util = ANCHO - 2 * MARGEN
    linea = ""

    for palabra in texto.split():
        prueba = f"{linea} {palabra}".strip()
        if pdfmetrics.stringWidth(prueba, fuente, tam) > util and linea:
            c.drawString(MARGEN, y, linea)
            y -= tam * 1.45
            linea = palabra
        else:
            linea = prueba

    if linea:
        c.drawString(MARGEN, y, linea)
        y -= tam * 1.45

    return y


def titulo_seccion(c, y: float, texto: str) -> float:
    c.setFillColor(TINTA)
    c.setFont("Helvetica-Bold", 10.5)
    c.drawString(MARGEN, y, texto.upper())
    return y - 6 * mm


def pie(c) -> None:
    c.setFillColor(GRIS)
    c.setFont("Helvetica-Oblique", 7.5)
    c.drawString(MARGEN, MARGEN - 6 * mm, FICTICIO)


def firma(c, y: float, nombre: str, cargo: str) -> None:
    c.setStrokeColor(LINEA)
    c.setLineWidth(0.8)
    c.line(MARGEN, y, MARGEN + 70 * mm, y)

    y -= 5 * mm
    c.setFillColor(TINTA)
    c.setFont("Helvetica", 10)
    c.drawString(MARGEN, y, nombre)

    y -= 5 * mm
    c.setFillColor(GRIS)
    c.setFont("Helvetica", 9.5)
    c.drawString(MARGEN, y, cargo)


# --- 1. Rutina ------------------------------------------------------------

def rutina(ruta: Path) -> None:
    c = canvas.Canvas(str(ruta), pagesize=A4)
    c.setTitle("Orden de estudios complementarios")

    y = membrete(
        c,
        "OBRA SOCIAL UNIFICADA",
        "Orden de Estudios Complementarios - Atencion Ambulatoria",
    )

    y = campo(c, y, "Orden N.", "OSU-2026-114728")
    y = campo(c, y, "Fecha de emision", "26 de octubre de 2026")
    y -= 3 * mm

    y = titulo_seccion(c, y, "Datos del paciente")
    y = campo(c, y, "Nombre y apellido", "Adriana Carolina Paredes")
    y = campo(c, y, "Edad", "45 anos")
    y = campo(c, y, "Documento", "4.128.905")
    y = campo(c, y, "Afiliado N.", "OSU-88-4471-02")
    y -= 3 * mm

    y = titulo_seccion(c, y, "Practicas solicitadas")
    for practica in (
        "Hemograma completo con formula leucocitaria",
        "Glucemia en ayunas",
        "Perfil tiroideo (TSH, T4 libre)",
        "Perfil lipidico completo",
    ):
        c.setFillColor(TINTA)
        c.setFont("Helvetica", 10.5)
        c.drawString(MARGEN + 4 * mm, y, f"-  {practica}")
        y -= 6 * mm

    y -= 3 * mm
    y = titulo_seccion(c, y, "Indicaciones")
    y = parrafo(
        c,
        y,
        "Control anual de rutina. Paciente asintomatica. Concurrir en ayunas "
        "de 8 horas. Caracter ambulatorio, NO urgente. Sin requerimiento de "
        "internacion ni de autorizacion previa especial.",
    )

    firma(
        c,
        y - 12 * mm,
        "Dr. Guillermo Segovia",
        "Clinica Medica  -  Matricula Profesional 30958",
    )
    pie(c)
    c.save()


# --- 2. Urgencia ----------------------------------------------------------

def urgencia(ruta: Path) -> None:
    c = canvas.Canvas(str(ruta), pagesize=A4)
    c.setTitle("Informe de estudio radiologico")

    y = membrete(
        c,
        "HOSPITAL SANTA LUCIA",
        "Servicio de Diagnostico por Imagenes - Informe de Estudio Radiologico",
    )

    y = campo(c, y, "Informe N.", "HSL-IMG-2026-8942")
    y = campo(c, y, "Fecha y hora", "26 de octubre de 2026, 03:42 h")
    y = campo(c, y, "Origen", "Guardia de Emergencias")
    y -= 3 * mm

    y = titulo_seccion(c, y, "Datos del paciente")
    y = campo(c, y, "Nombre y apellido", "Carlos Eduardo Mendes")
    y = campo(c, y, "Edad", "52 anos")
    y = campo(c, y, "Documento", "2.904.336")
    y -= 3 * mm

    y = titulo_seccion(c, y, "Estudio realizado")
    y = campo(c, y, "Practica", "Angiotomografia de torax con contraste")
    y = campo(c, y, "Medico solicitante", "Dra. Renata Silveira  -  MP 145892")
    y -= 3 * mm

    y = titulo_seccion(c, y, "Indicacion clinica")
    y = parrafo(
        c,
        y,
        "Paciente que ingresa por guardia con disnea subita de tres horas de "
        "evolucion, dolor toracico pleuritico y taquicardia. Antecedente de "
        "inmovilizacion prolongada por cirugia de rodilla hace once dias. "
        "Dimero D elevado. Se solicita estudio por sospecha de embolia "
        "pulmonar aguda.",
    )

    y -= 4 * mm
    y = titulo_seccion(c, y, "Hallazgos")
    y = parrafo(
        c,
        y,
        "Defecto de llenado endoluminal en la arteria pulmonar principal "
        "derecha, que se extiende hacia las ramas lobares superior e inferior "
        "homolaterales. Se observa dilatacion del ventriculo derecho con "
        "relacion VD/VI mayor a 1,0, signo indirecto de sobrecarga de "
        "cavidades derechas. Pequeno derrame pleural derecho. Parenquima "
        "pulmonar sin consolidaciones.",
    )

    y -= 4 * mm
    y = titulo_seccion(c, y, "Conclusion")
    y = parrafo(
        c,
        y,
        "Cuadro compatible con TROMBOEMBOLISMO PULMONAR AGUDO, con signos "
        "tomograficos de sobrecarga ventricular derecha. Se sugiere "
        "evaluacion clinica inmediata e inicio de anticoagulacion segun "
        "criterio del equipo tratante.",
        fuente="Helvetica-Bold",
    )

    firma(
        c,
        y - 12 * mm,
        "Dr. Hernan Villalba",
        "Medico Radiologo  -  Matricula Profesional 71204",
    )
    pie(c)
    c.save()


# --- 3. Ambiguedad --------------------------------------------------------

def garabato(c, x: float, y: float, ancho: float, semilla: int) -> None:
    """Un trazo que parece escritura y no se puede leer.

    Es el corazon del tercer escenario: la dosis tiene que ser genuinamente
    ilegible, no una palabra que diga que lo es. La semilla esta fijada para
    que el documento salga identico en cada corrida; si cambiara entre
    generaciones, el video y el PDF entregado no coincidirian.
    """
    azar = random.Random(semilla)
    camino = c.beginPath()

    x_actual = x
    camino.moveTo(x_actual, y)

    while x_actual < x + ancho:
        paso = azar.uniform(2.2, 4.5)
        alto = azar.uniform(-3.2, 4.8)
        control = azar.uniform(-5.0, 6.0)
        camino.curveTo(
            x_actual + paso * 0.4, y + control,
            x_actual + paso * 0.7, y + alto,
            x_actual + paso, y + azar.uniform(-1.2, 1.2),
        )
        x_actual += paso

    c.setStrokeColor(LAPICERA)
    c.setLineWidth(1.15)
    c.setLineCap(1)
    c.drawPath(camino)


def ambiguedad(ruta: Path, hay_manuscrita: bool) -> None:
    c = canvas.Canvas(str(ruta), pagesize=A4)
    c.setTitle("Receta medica manuscrita")

    mano = "Manuscrita" if hay_manuscrita else "Helvetica"
    mano_fuerte = "ManuscritaFuerte" if hay_manuscrita else "Helvetica-Bold"

    y = membrete(c, "CONSULTORIO EXTERNO - CLINICA DEL SOL", "Recetario Medico")

    # El encabezado del formulario esta impreso; lo que lo completa esta
    # escrito a mano, en azul. Esa mezcla es lo que hace al documento real.
    c.setFillColor(GRIS)
    c.setFont("Helvetica", 9)
    c.drawString(MARGEN, y, "FECHA")
    c.setFillColor(LAPICERA)
    c.setFont(mano, 13)
    c.drawString(MARGEN + 25 * mm, y, "26 / 10 / 2026")
    y -= 10 * mm

    c.setFillColor(GRIS)
    c.setFont("Helvetica", 9)
    c.drawString(MARGEN, y, "PACIENTE")
    c.setFillColor(LAPICERA)
    c.setFont(mano, 14)
    c.drawString(MARGEN + 25 * mm, y, "Rosa Mabel Aguero")
    c.setStrokeColor(LINEA)
    c.line(MARGEN + 23 * mm, y - 2 * mm, ANCHO - MARGEN, y - 2 * mm)
    y -= 10 * mm

    c.setFillColor(GRIS)
    c.setFont("Helvetica", 9)
    c.drawString(MARGEN, y, "EDAD")
    c.setFillColor(LAPICERA)
    c.setFont(mano, 14)
    c.drawString(MARGEN + 25 * mm, y, "58 anos")
    c.setStrokeColor(LINEA)
    c.line(MARGEN + 23 * mm, y - 2 * mm, MARGEN + 80 * mm, y - 2 * mm)
    y -= 16 * mm

    # El "Rp/" del recetario.
    c.setFillColor(TINTA)
    c.setFont("Helvetica-Bold", 20)
    c.drawString(MARGEN, y, "Rp/")
    y -= 12 * mm

    sangria = MARGEN + 12 * mm

    # Primer renglon: el medicamento SE LEE, la dosis NO. Esa asimetria es
    # todo el escenario. Si no se leyera nada, el caso seria "documento
    # ilegible"; lo interesante es que el agente tenga la mitad del dato y
    # aun asi no complete la otra mitad.
    c.setFillColor(LAPICERA)
    c.setFont(mano_fuerte, 15)
    c.drawString(sangria, y, "Metformina")
    ancho_med = pdfmetrics.stringWidth("Metformina", mano_fuerte, 15)
    garabato(c, sangria + ancho_med + 8, y + 2, 52, semilla=11)
    c.setFont(mano, 15)
    c.drawString(sangria + ancho_med + 68, y, "mg")
    y -= 9 * mm

    c.setFont(mano, 13)
    inicio = sangria + 6 * mm
    c.drawString(inicio, y, "tomar")
    # El ancho se mide, no se estima: con un valor fijo el garabato se monta
    # encima de "tomar" y el renglon deja de parecer escritura.
    tras_tomar = inicio + pdfmetrics.stringWidth("tomar", mano, 13) + 8
    garabato(c, tras_tomar, y + 2, 34, semilla=23)
    c.drawString(tras_tomar + 42, y, "veces al dia")
    y -= 14 * mm

    # Segundo renglon: perfectamente legible. Prueba que el documento no es
    # malo en general y que el agente si extrae lo que puede leer.
    c.setFont(mano_fuerte, 15)
    c.drawString(sangria, y, "Glibenclamida 5 mg")
    y -= 9 * mm
    c.setFont(mano, 13)
    c.drawString(sangria + 6 * mm, y, "1 comprimido antes del desayuno")
    y -= 16 * mm

    c.setFont(mano, 13)
    c.drawString(sangria, y, "Control en 30 dias con laboratorio")
    y -= 24 * mm

    # Firma y matricula: la matricula tambien es ilegible. Es el segundo
    # campo que el auditor completa en la demo.
    c.setStrokeColor(LINEA)
    c.setLineWidth(0.8)
    c.line(MARGEN, y, MARGEN + 70 * mm, y)

    c.setFillColor(LAPICERA)
    c.setFont(mano, 16)
    c.drawString(MARGEN + 4 * mm, y + 4 * mm, "E. Caballero")

    y -= 6 * mm
    c.setFillColor(TINTA)
    c.setFont("Helvetica", 10)
    c.drawString(MARGEN, y, "Dr. Ernesto Caballero")
    y -= 5.5 * mm

    c.setFillColor(GRIS)
    c.setFont("Helvetica", 9.5)
    c.drawString(MARGEN, y, "Medico Clinico  -  M.P.")
    garabato(c, MARGEN + 36 * mm, y + 1 * mm, 40, semilla=37)

    pie(c)
    c.save()


def main() -> int:
    SALIDA.mkdir(parents=True, exist_ok=True)
    hay_manuscrita = registrar_manuscrita()

    trabajos = [
        ("1_rutina_orden_laboratorio.pdf", rutina, False),
        ("2_urgencia_informe_tomografia.pdf", urgencia, False),
        ("3_ambiguedad_receta_manuscrita.pdf", ambiguedad, True),
    ]

    for nombre, funcion, necesita_mano in trabajos:
        destino = SALIDA / nombre
        if necesita_mano:
            funcion(destino, hay_manuscrita)
        else:
            funcion(destino)
        print(f"  ok  {nombre}  ({destino.stat().st_size // 1024} KB)")

    print(f"\nTres documentos en {SALIDA}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
