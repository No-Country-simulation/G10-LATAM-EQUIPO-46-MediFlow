"""Mide que tan bien lee el agente el corpus etiquetado (tarea 2.3).

Desde `agente/`:

    python scripts/evaluar_corpus.py --simulado    # sin gastar cuota
    python scripts/evaluar_corpus.py               # con Gemini

Reporta cuatro cosas, y la cuarta es la que mas importa:

  1. **Exactitud de clasificacion.** Que porcentaje de documentos recibio la
     categoria correcta, con el detalle de en que se equivoco.
  2. **Cobertura de campos.** De los datos que un humano SI puede leer en el
     documento, cuantos extrajo el agente. Un null donde habia un dato es un
     fallo de cobertura.
  3. **Campos inventados.** Datos que el agente devolvio y que NO estaban en el
     documento. El proyecto prohibe inventar: cualquier valor aca es un
     defecto grave, no una imprecision.
  4. **Falsos negativos de urgencia.** Documentos etiquetados como urgentes que
     el enrutamiento NO mando a la cola de emergencia. Es el peor fallo posible
     del sistema y por eso tiene su propia metrica.

El modo `--simulado` usa un clasificador por palabras clave en lugar del
modelo. No sirve para medir calidad: sirve para comprobar que la canaleta de
evaluacion funciona sin consumir cuota.
"""

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

from dotenv import load_dotenv  # noqa: E402

from mediflow_agent.schemas.models import (  # noqa: E402
    ClassificationResult,
    Doctor,
    ExtractedData,
    Patient,
)

load_dotenv()

CORPUS = RAIZ / "corpus"

# Como se llama cada campo etiquetado dentro de ExtractedData.
CAMPOS = {
    "paciente.nombre": lambda d: d.patient.name,
    "paciente.edad": lambda d: d.patient.age,
    "medico.nombre": lambda d: d.doctor.name,
    "medico.matricula": lambda d: d.doctor.license_number,
    "estudio": lambda d: d.study,
    "diagnostico": lambda d: d.diagnosis,
    "hallazgos": lambda d: d.findings,
    "conclusion": lambda d: d.conclusion,
    "medicamentos": lambda d: d.medications,
    "procedimiento": lambda d: d.procedure,
}


# --------------------------------------------------------------------------
# Modo simulado
# --------------------------------------------------------------------------

PISTAS = [
    ("receta_medica", ("recetario", "rp/", "receta")),
    ("epicrisis", ("epicrisis", "informe de alta", "egreso:")),
    ("certificado_medico", ("certificado", "certifico que")),
    ("orden_procedimiento", ("se solicita", "orden de", "solicitud de")),
    ("informe_estudio_diagnostico", ("informe de", "hallazgos:", "conclusion:")),
]


class ClasificadorSimulado:
    """Clasificador por palabras clave. No reemplaza al modelo."""

    def classify(self, texto: str) -> ClassificationResult:
        minuscula = texto.lower()

        for tipo, pistas in PISTAS:
            if any(p in minuscula for p in pistas):
                return ClassificationResult(document_type=tipo, confidence=0.75)

        return ClassificationResult(document_type="desconocido", confidence=0.30)


class ExtractorSimulado:
    """Extractor por expresiones regulares. No reemplaza al modelo."""

    def extract(self, texto: str) -> ExtractedData:
        def buscar(patron):
            hallado = re.search(patron, texto, re.IGNORECASE)
            if not hallado:
                return None
            valor = hallado.group(1).strip()
            return None if "[ilegible]" in valor.lower() or not valor else valor

        edad = buscar(r"Edad:\s*(\d+)")

        return ExtractedData(
            patient=Patient(
                name=buscar(r"Paciente:\s*(.+)"),
                age=int(edad) if edad else None,
            ),
            doctor=Doctor(
                name=buscar(r"\n(Dr\.?a?\.?\s+[A-Z][^\n]+)"),
                license_number=buscar(r"MP\s*([0-9]+)"),
            ),
            study=buscar(r"Estudio:\s*(.+)"),
            diagnosis=buscar(r"Diagn[oó]stico[^:]*:\s*(.+)"),
            findings=buscar(r"Hallazgos:\s*(.+)"),
            conclusion=buscar(r"CONCLUSION:\s*(.+)"),
            procedure=buscar(r"(?:Procedimiento solicitado|Se solicita):\s*(.+)"),
        )


# --------------------------------------------------------------------------
# Evaluacion
# --------------------------------------------------------------------------

def _tiene_valor(valor) -> bool:
    if valor is None:
        return False
    if isinstance(valor, str):
        return bool(valor.strip())
    if isinstance(valor, list):
        return bool(valor)
    return True


def _cargar_enrutamiento():
    """Devuelve la funcion de enrutamiento, o None si todavia no esta en main.

    `routing/baseline.py` llega con el PR de la tarea 1.3. Mientras ese PR no
    se mergee, la metrica de urgencia no se puede calcular y se dice.
    """
    try:
        from mediflow_agent.routing.baseline import decidir_enrutamiento

        return decidir_enrutamiento
    except ImportError:
        return None


def evaluar(simulado: bool) -> int:
    etiquetas = json.loads((CORPUS / "etiquetas.json").read_text(encoding="utf-8"))

    if simulado:
        clasificador, extractor = ClasificadorSimulado(), ExtractorSimulado()
        print("Modo SIMULADO: clasificador por palabras clave, sin llamar a Gemini.")
        print("Los numeros no miden la calidad del agente, solo que todo corre.\n")
    else:
        from mediflow_agent.classification.classifier import DocumentClassifier
        from mediflow_agent.extraction.extractor import DocumentExtractor

        clasificador, extractor = DocumentClassifier(), DocumentExtractor()
        print(f"Evaluando {len(etiquetas)} documentos con el modelo real.\n")

    enrutar = _cargar_enrutamiento()

    aciertos = 0
    confusiones: Counter = Counter()
    cobertura_ok: Counter = defaultdict(int)
    cobertura_total: Counter = defaultdict(int)
    inventados: list[tuple[str, str, object]] = []
    urgencias_perdidas: list[str] = []
    urgentes = 0

    for etiqueta in etiquetas:
        texto = (CORPUS / "documentos" / etiqueta["archivo"]).read_text(encoding="utf-8")

        clasificacion = clasificador.classify(texto)
        datos = extractor.extract(texto)

        # --- clasificacion ---
        esperado = etiqueta["tipo_documento"]
        obtenido = clasificacion.document_type

        if obtenido == esperado:
            aciertos += 1
        else:
            confusiones[(esperado, obtenido)] += 1

        # --- cobertura e invenciones ---
        esperados = set(etiqueta["campos_presentes"])

        for campo, extraer in CAMPOS.items():
            valor = extraer(datos)

            if campo in esperados:
                cobertura_total[campo] += 1
                if _tiene_valor(valor):
                    cobertura_ok[campo] += 1
            elif _tiene_valor(valor):
                inventados.append((etiqueta["archivo"], campo, valor))

        # --- urgencia ---
        if etiqueta["nivel_prioridad"] == "Urgente":
            urgentes += 1

            if enrutar is not None:
                prioridad, decision, _ = enrutar(
                    documento_id=etiqueta["archivo"],
                    clasificacion=clasificacion,
                    datos=datos,
                    canal_origen="Recepcion",
                )
                if decision.destino_principal != "Cola_Emergencia_Medica":
                    urgencias_perdidas.append(etiqueta["archivo"])

    # ---------------- informe ----------------
    total = len(etiquetas)

    print("=" * 62)
    print("1. EXACTITUD DE CLASIFICACION")
    print("=" * 62)
    print(f"  {aciertos}/{total} correctos  ({aciertos / total:.1%})\n")

    if confusiones:
        print("  Se equivoco en:")
        for (esperado, obtenido), n in confusiones.most_common():
            print(f"    {esperado:30} -> {obtenido:30} x{n}")
    else:
        print("  Sin errores de clasificacion.")

    if simulado:
        print()
        print("  OJO: en modo simulado este numero NO significa nada. Las")
        print("  palabras clave se escribieron contra este mismo corpus, asi")
        print("  que acertar todo era el resultado esperado.")

    print()
    print("=" * 62)
    print("2. COBERTURA DE CAMPOS")
    print("=" * 62)
    print("  De los datos que SI estaban escritos, cuantos extrajo.\n")

    suma_ok = sum(cobertura_ok.values())
    suma_total = sum(cobertura_total.values())

    for campo in CAMPOS:
        if not cobertura_total[campo]:
            continue
        ok, tot = cobertura_ok[campo], cobertura_total[campo]
        barra = "#" * round(12 * ok / tot)
        print(f"    {campo:22} {ok:3}/{tot:<3} {ok / tot:6.1%}  {barra}")

    print(f"\n  TOTAL                  {suma_ok}/{suma_total}  {suma_ok / suma_total:.1%}")

    print()
    print("=" * 62)
    print("3. CAMPOS INVENTADOS")
    print("=" * 62)
    print("  Datos devueltos que NO estaban en el documento.")
    print("  El proyecto prohibe inventar: cualquier valor aca es un defecto.\n")

    if inventados:
        print(f"  {len(inventados)} invenciones:\n")
        for archivo, campo, valor in inventados[:12]:
            recorte = str(valor)[:46]
            print(f"    {archivo:32} {campo:20} {recorte}")
        if len(inventados) > 12:
            print(f"    ... y {len(inventados) - 12} mas")
    else:
        print("  Ninguno. El agente no invento datos.")

    print()
    print("=" * 62)
    print("4. FALSOS NEGATIVOS DE URGENCIA")
    print("=" * 62)

    if enrutar is None:
        print("  NO SE PUDO MEDIR: falta routing/baseline.py, que llega con el")
        print("  PR de la tarea 1.3. Mergealo y volve a correr esto.")
    elif urgencias_perdidas:
        print("  ESTE ES EL PEOR FALLO POSIBLE DEL SISTEMA.\n")
        print(f"  {len(urgencias_perdidas)} de {urgentes} documentos urgentes NO")
        print("  fueron a la cola de emergencia:\n")
        for archivo in urgencias_perdidas:
            print(f"    {archivo}")
    else:
        print(f"  Ninguno. Los {urgentes} documentos urgentes fueron a la cola")
        print("  de emergencia.")

    print()
    return 1 if urgencias_perdidas else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Evalua el agente sobre el corpus.")
    parser.add_argument(
        "--simulado",
        action="store_true",
        help="Usa un clasificador por palabras clave en vez de Gemini.",
    )
    return evaluar(parser.parse_args().simulado)


if __name__ == "__main__":
    raise SystemExit(main())
