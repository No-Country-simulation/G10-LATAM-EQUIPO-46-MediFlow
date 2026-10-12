"""Re-etiqueta el corpus segun las reglas acordadas (revision de Danilo).

Script de un solo uso. Lo que queda versionado es `corpus/etiquetas.json`.

**Por que hacia falta.** La evaluacion reportaba 17 "campos inventados" que no
lo eran: datos reales del documento puestos en un campo que la etiqueta no
preveia. El defecto no estaba en el agente ni en las etiquetas sueltas, sino
en que la medicion tenia **dos categorias donde hacen falta tres**.

    campos_presentes   El dato esta escrito y el agente DEBE extraerlo.
                       Un null aca es un fallo de cobertura.

    campos_aceptables  El dato esta en el documento pero el campo donde cae es
                       discutible. Extraerlo no es un fallo ni un acierto.

    el resto           No esta en el documento. Cualquier valor es una
                       invencion, y el proyecto las prohibe.

**Los dos solapamientos reales**, que son los que obligaban a elegir mal:

  - `estudio` y `procedimiento`. "Tomografia de Torax" es el estudio de un
    informe y el procedimiento de una orden. El mismo texto cae en cualquiera
    de los dos segun quien lo lea.

  - `conclusion` y `diagnostico`. Por la regla 4, si la conclusion AFIRMA la
    condicion va en los dos campos. Si solo la sugiere ("compatible con"),
    va unicamente en conclusion.
"""

import io
import json
import pathlib

CORPUS = pathlib.Path(r"C:\GitHub\G10-LATAM-EQUIPO-46-MediFlow\agente\corpus")

# Documentos cuya conclusion AFIRMA la condicion: por la regla 4 de Danilo,
# el diagnostico tambien esta presente y el agente DEBE extraerlo.
CONCLUSION_AFIRMA = {
    "009-informe-infarto.txt",       # "compatible con infarto" -> afirmado en hallazgos
    "012-informe-hemorragia.txt",    # "Hemorragia subaracnoidea aguda."
    "011-informe-ecografia.txt",     # "Litiasis vesicular unica."
}

# Documentos con valores de laboratorio o descripcion de evolucion: por la
# regla 5, eso son hallazgos aunque no haya un apartado con ese nombre.
HALLAZGOS_IMPLICITOS = {
    "008-informe-laboratorio-normal.txt",
    "018-orden-urgente-guardia.txt",   # "Paciente en shock, hipotenso"
    "019-epicrisis-neumonia.txt",      # evolucion de la internacion
    "020-epicrisis-parto.txt",
    "021-epicrisis-sepsis.txt",
}


def aceptables(presentes: list[str], archivo: str) -> list[str]:
    """Campos que el agente PUEDE llenar sin que sea invencion ni cobertura."""
    opcionales: set[str] = set()

    # Solapamiento estudio / procedimiento: si uno esta, el otro es aceptable.
    if "estudio" in presentes:
        opcionales.add("procedimiento")
    if "procedimiento" in presentes:
        opcionales.add("estudio")

    # Solapamiento conclusion / diagnostico.
    if "conclusion" in presentes and "diagnostico" not in presentes:
        opcionales.add("diagnostico")
    if "diagnostico" in presentes and "conclusion" not in presentes:
        opcionales.add("conclusion")

    # Un informe con hallazgos suele permitir resumirlos como conclusion.
    if "hallazgos" in presentes and "conclusion" not in presentes:
        opcionales.add("conclusion")

    return sorted(opcionales - set(presentes))


def main() -> None:
    ruta = CORPUS / "etiquetas.json"
    etiquetas = json.loads(ruta.read_text(encoding="utf-8"))

    cambios = 0

    for etiqueta in etiquetas:
        archivo = etiqueta["archivo"]
        presentes = list(etiqueta["campos_presentes"])
        original = list(presentes)

        if archivo in CONCLUSION_AFIRMA and "diagnostico" not in presentes:
            presentes.append("diagnostico")

        if archivo in HALLAZGOS_IMPLICITOS and "hallazgos" not in presentes:
            presentes.append("hallazgos")

        presentes.sort()
        etiqueta["campos_presentes"] = presentes
        etiqueta["campos_aceptables"] = aceptables(presentes, archivo)

        if presentes != sorted(original) or etiqueta["campos_aceptables"]:
            cambios += 1

    io.open(ruta, "w", encoding="utf-8", newline="\n").write(
        json.dumps(etiquetas, ensure_ascii=False, indent=2) + "\n"
    )

    print(f"{len(etiquetas)} documentos revisados, {cambios} con etiquetas nuevas")
    print()

    for etiqueta in etiquetas:
        if etiqueta["campos_aceptables"]:
            print(
                "  %-34s aceptables: %s"
                % (etiqueta["archivo"], ", ".join(etiqueta["campos_aceptables"]))
            )


if __name__ == "__main__":
    main()
