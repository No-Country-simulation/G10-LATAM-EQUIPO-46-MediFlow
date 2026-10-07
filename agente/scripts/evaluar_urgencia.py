"""Mide la deteccion de urgencia contra el banco de frases (tarea 3.2).

Desde `agente/`:

    python scripts/evaluar_urgencia.py            # solo la via por lista, gratis
    python scripts/evaluar_urgencia.py --modelo   # las dos vias

**La via por lista no cuesta una sola llamada**: es comparacion de texto. Por
eso se puede correr tantas veces como se quiera y contra un banco tan grande
como se arme. La via por modelo si consume cuota, y por eso es opcional.

El numero que importa no es el promedio: es cuantos urgentes se escapan. Un
falso positivo cuesta que alguien mire un caso de mas; un falso negativo
cuesta que un infarto espere en una bandeja. No son comparables, y por eso el
informe los separa.
"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

from mediflow_agent.config import variable  # noqa: E402
from mediflow_agent.limites import PEDIDOS_POR_MINUTO, LimitadorDeRitmo  # noqa: E402
from mediflow_agent.modelos import MODELO_POR_DEFECTO  # noqa: E402
from mediflow_agent.routing.terminos_criticos import GRUPOS, TERMINOS_CRITICOS  # noqa: E402
from mediflow_agent.routing.urgencia import detectar  # noqa: E402

BANCO = RAIZ / "corpus" / "urgencias.json"

DESCRIPCION_GRUPO = {
    "con_termino": "urgentes nombrados con un termino de la lista",
    "sin_termino": "urgentes descritos SIN termino de la lista",
    "rutina": "documentacion de rutina",
    "trampa": "negaciones y antecedentes (no deben disparar)",
}


def construir_llm():
    from langchain_google_genai import ChatGoogleGenerativeAI

    api_key = variable("GEMINI_API_KEY")

    if not api_key:
        print("Falta GEMINI_API_KEY en el .env. Se mide solo la via por lista.\n")
        return None

    return ChatGoogleGenerativeAI(
        model=variable("GEMINI_MODEL", MODELO_POR_DEFECTO),
        google_api_key=api_key,
        temperature=0,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Mide la deteccion de urgencia.")
    parser.add_argument(
        "--modelo",
        action="store_true",
        help="Agrega la segunda via. Consume cuota del modelo.",
    )
    usar_modelo = parser.parse_args().modelo

    casos = json.loads(BANCO.read_text(encoding="utf-8"))

    llm = construir_llm() if usar_modelo else None
    limitador = LimitadorDeRitmo(PEDIDOS_POR_MINUTO) if llm else None

    print(f"Banco: {len(casos)} frases clinicas")
    print(f"Lista: {len(TERMINOS_CRITICOS)} terminos en {len(GRUPOS)} grupos")
    print(f"Vias : {'lista + modelo' if llm else 'solo lista'}")

    if limitador:
        print(
            f"Ritmo limitado a {PEDIDOS_POR_MINUTO} por minuto: "
            f"unos {len(casos) / PEDIDOS_POR_MINUTO:.0f} minutos."
        )

    print()

    resultados: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    escapes: list[str] = []
    falsos: list[tuple[str, tuple[str, ...]]] = []
    por_via: dict[str, int] = defaultdict(int)

    for caso in casos:
        if limitador:
            limitador.esperar_turno()

        urgencia = detectar(caso["texto"], llm=llm)
        grupo = caso["grupo"]
        resultados[grupo][1] += 1

        if urgencia.es_urgente == caso["urgente"]:
            resultados[grupo][0] += 1
        elif caso["urgente"]:
            escapes.append(caso["texto"])
        else:
            falsos.append((caso["texto"], urgencia.terminos))

        if caso["urgente"] and urgencia.es_urgente:
            por_via[urgencia.via] += 1

    # ---------------- informe ----------------
    print("=" * 68)
    print("ACIERTOS POR GRUPO")
    print("=" * 68)

    for grupo in ("con_termino", "sin_termino", "rutina", "trampa"):
        if grupo not in resultados:
            continue
        ok, total = resultados[grupo]
        barra = "#" * round(20 * ok / total)
        print(f"  {DESCRIPCION_GRUPO[grupo]:48} {ok:3}/{total:<3} {ok / total:5.0%}")
        print(f"  {'':48} {barra}")

    urgentes = sum(1 for c in casos if c["urgente"])

    print()
    print("=" * 68)
    print("LO QUE IMPORTA: URGENTES QUE SE ESCAPAN")
    print("=" * 68)

    if escapes:
        print(f"  {len(escapes)} de {urgentes} urgentes NO fueron detectados:\n")
        for texto in escapes:
            print(f"    {texto[:64]}")
    else:
        print(f"  NINGUNO. Los {urgentes} casos urgentes fueron detectados.")

    print()
    print("=" * 68)
    print("FALSOS POSITIVOS")
    print("=" * 68)
    print("  Cuestan que alguien mire un caso de mas. Molestan, no matan,")
    print("  pero en exceso saturan la cola de emergencia.\n")

    if falsos:
        print(f"  {len(falsos)}:\n")
        for texto, terminos in falsos:
            print(f"    {texto[:52]:52} <- {list(terminos)}")
    else:
        print("  Ninguno.")

    if por_via:
        print()
        print("=" * 68)
        print("QUE VIA DETECTO CADA URGENCIA")
        print("=" * 68)
        print("  Si una via sola bastara, la otra sobraria. Estos numeros")
        print("  dicen cuanto aporta cada una.\n")

        for via in ("ambas", "lista", "modelo"):
            if via in por_via:
                print(f"    {via:8} {por_via[via]:3}")

    print()

    return 1 if escapes else 0


if __name__ == "__main__":
    raise SystemExit(main())
