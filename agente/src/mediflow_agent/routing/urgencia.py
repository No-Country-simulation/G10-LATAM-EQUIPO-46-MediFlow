"""Deteccion de urgencia por doble via (tarea 3.2).

**Por que dos vias.** Se midio una sola via, la lista de terminos, contra 95
frases clinicas. El resultado dejo poco lugar a la duda:

    urgentes nombrados con un termino de la lista     25/25   100%
    urgentes descritos SIN termino de la lista         2/30     7%
    frases de rutina                                  20/20   100%
    negaciones ("se descarta infarto")                 0/20     0%

La lista se habia agrandado de 17 a 185 terminos antes de medir. Diez veces
mas palabras, y los cuadros descritos por anatomia o por valores de
laboratorio se siguen escapando en un 93 por ciento. El problema no es el
tamano de la lista: es que una lista compara texto y no entiende lo que lee.

Y una lista grande trae su propio dano: las 20 negaciones disparaban. "El
estudio descarta infarto" mandaba el caso a la cola de emergencia.

**Como se combinan.** La regla es OR, no AND: **basta con que una de las dos
vias diga urgente**. No es un detalle de implementacion, es la regla clinica
del proyecto. Un falso positivo cuesta que alguien mire un caso de mas; un
falso negativo cuesta que un infarto espere en una bandeja.

**Que aporta cada una.** La lista es instantanea, gratis y no falla nunca de
la misma forma dos veces: es el piso que queda en pie aunque el modelo este
caido o sin cuota. El modelo entiende lo que la lista no puede nombrar.
"""

import logging
import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from mediflow_agent.routing.terminos_criticos import TERMINOS_CRITICOS, grupo_de

_log = logging.getLogger(__name__)

Via = Literal["lista", "modelo", "ambas", "ninguna"]

# Palabras que, delante de un termino critico, dicen que el cuadro NO esta
# presente: lo niegan, lo descartan o lo ubican en el pasado.
NEGADORES = (
    "sin signos de",
    "sin evidencia de",
    "sin criterios de",
    "sin hallazgos de",
    "sin",
    "no se observa",
    "no se evidencia",
    "no se constata",
    "no presenta",
    "no hay",
    "no",
    "descarta",
    "descartar",
    "se descarta",
    "ausencia de",
    "niega",
    "antecedente de",
    "antecedentes de",
    "previo",
    "previa",
    "resuelto",
    "resuelta",
    "prevenir",
    "prevencion",
    "riesgo de",
    "seguimiento por",
    "control por",
)

# Cuantos caracteres antes del termino se miran buscando una negacion. Una
# ventana corta pierde "no se observa, en el estudio de hoy, tromboembolismo";
# una larga empieza a negar cosas que no corresponden. 60 cubre las formas
# habituales de redactar un informe.
VENTANA_NEGACION = 60


@dataclass(frozen=True)
class Urgencia:
    """Resultado de evaluar si un documento es urgente."""

    es_urgente: bool
    via: Via
    terminos: tuple[str, ...] = ()
    motivo_modelo: Optional[str] = None

    def explicacion(self) -> str:
        """Frase lista para la justificacion del enrutamiento."""
        if not self.es_urgente:
            return "Sin hallazgos criticos en el texto."

        partes = []

        if self.terminos:
            grupos = {grupo_de(t) for t in self.terminos}
            partes.append(
                f"La deteccion por terminos encontro {', '.join(self.terminos)} "
                f"({', '.join(sorted(grupos))})"
            )

        if self.motivo_modelo:
            partes.append(f"El modelo lo marco como urgente: {self.motivo_modelo}")

        return ". ".join(partes) + "."


def _normalizar(texto: str) -> str:
    sin_tilde = unicodedata.normalize("NFKD", texto)
    sin_tilde = "".join(c for c in sin_tilde if not unicodedata.combining(c))
    return sin_tilde.lower()


def _esta_negado(texto: str, posicion: int) -> bool:
    """Decide si el termino que empieza en `posicion` viene negado.

    Mira hacia atras hasta el signo de puntuacion anterior o hasta
    VENTANA_NEGACION caracteres, lo que ocurra primero. Cortar en la
    puntuacion evita que un "sin" de la oracion anterior niegue esta.
    """
    inicio = max(0, posicion - VENTANA_NEGACION)
    antes = texto[inicio:posicion]

    corte = max(antes.rfind("."), antes.rfind(";"), antes.rfind(":"))
    if corte != -1:
        antes = antes[corte + 1 :]

    palabras = re.findall(r"[a-z]+", antes)

    if not palabras:
        return False

    # Se arma la frase previa y se busca cualquier negador como palabra
    # completa, para que "sinusitis" no cuente como "sin".
    frase = " " + " ".join(palabras) + " "

    return any(f" {n} " in frase for n in NEGADORES)


def detectar_por_lista(texto: str) -> tuple[str, ...]:
    """Terminos criticos presentes y NO negados.

    Sin el filtro de negacion, "el estudio descarta infarto" se enruta a la
    cola de emergencia. Medido: las 20 frases de negacion del banco disparaban
    todas.
    """
    normalizado = _normalizar(texto)
    encontrados = []

    for termino in TERMINOS_CRITICOS:
        posicion = normalizado.find(termino)

        while posicion != -1:
            if not _esta_negado(normalizado, posicion):
                encontrados.append(termino)
                break
            posicion = normalizado.find(termino, posicion + 1)

    # Se descartan los terminos contenidos en otro ya encontrado, para no
    # reportar "shock" junto a "shock septico".
    return tuple(
        t for t in encontrados if not any(t != o and t in o for o in encontrados)
    )


class _EvaluacionUrgencia(BaseModel):
    """Lo que se le pide al modelo. Deliberadamente corto: una pregunta sola."""

    es_urgente: bool = Field(
        description=(
            "True si el documento describe una condicion que requiere atencion "
            "medica inmediata. Ante la duda, True: un caso de mas revisado por "
            "una persona es barato; una urgencia que espera, no."
        )
    )

    motivo: str = Field(
        description=(
            "Una frase breve que cite el hallazgo concreto del documento que "
            "justifica la decision. Si no es urgente, por que no."
        )
    )


INSTRUCCION_MODELO = """Sos un medico de guardia clasificando documentos por prioridad.

Decidi si este documento describe una condicion que requiere ATENCION MEDICA
INMEDIATA.

Es urgente cuando:
- Describe un hallazgo que pone en riesgo la vida o un organo a corto plazo.
- Reporta valores de laboratorio o signos vitales incompatibles con la vida
  sin intervencion.
- El profesional pide atencion inmediata.

NO es urgente cuando:
- El hallazgo esta NEGADO o descartado ("sin signos de", "se descarta").
- Es un ANTECEDENTE o un cuadro ya resuelto.
- Es documentacion de rutina, control o prevencion.

Ante la duda, marcalo como urgente: que una persona revise un caso de mas es
barato; que una urgencia espere en una bandeja, no.

Documento:

{texto}"""


def detectar_por_modelo(texto: str, llm: Any) -> tuple[bool, Optional[str]]:
    """Segunda via. Devuelve (es_urgente, motivo).

    Si el modelo falla, devuelve (False, None) en lugar de propagar: la via
    por lista sigue valiendo y el fallo del modelo ya tiene su propia ruta de
    escalado en el servicio.
    """
    if not texto or not texto.strip():
        # Preguntarle al modelo sobre un texto vacio es pedirle que adivine, y
        # como el prompt lo sesga a escalar, responde "urgente". Se midio: una
        # receta de rutina terminaba en la cola de emergencia con la
        # justificacion "el documento no contiene texto". Un documento sin
        # contenido legible ya tiene su propia ruta de escalado.
        return False, None

    try:
        evaluacion = llm.with_structured_output(_EvaluacionUrgencia).invoke(
            INSTRUCCION_MODELO.format(texto=texto)
        )
        return bool(evaluacion.es_urgente), evaluacion.motivo

    except Exception as err:  # noqa: BLE001
        _log.warning("La deteccion de urgencia por modelo fallo: %s", err)
        return False, None


def detectar(texto: str, llm: Any = None) -> Urgencia:
    """Evalua por las dos vias y combina con OR.

    `llm` opcional: sin el, funciona solo la via por lista. Es lo que permite
    que el sistema siga triando si se agota la cuota del modelo.
    """
    terminos = detectar_por_lista(texto)
    por_lista = bool(terminos)

    por_modelo, motivo = (False, None)

    # Si la lista ya dijo urgente, no se le pregunta al modelo: la regla es OR,
    # asi que su respuesta no puede cambiar el resultado. Ahorra una llamada
    # justo en los casos criticos, que son los que no pueden esperar, y una
    # llamada menos es tambien un riesgo menos de chocar contra el limite de
    # 15 pedidos por minuto de la capa gratuita.
    if llm is not None and not por_lista:
        por_modelo, motivo = detectar_por_modelo(texto, llm)

    if por_lista and por_modelo:
        via: Via = "ambas"
    elif por_lista:
        via = "lista"
    elif por_modelo:
        via = "modelo"
    else:
        via = "ninguna"

    return Urgencia(
        es_urgente=por_lista or por_modelo,
        via=via,
        terminos=terminos,
        motivo_modelo=motivo if por_modelo else None,
    )
