"""Pruebas de la deteccion de urgencia por doble via (tarea 3.2).

El modelo se sustituye por dobles: no consumen cuota.

Estas pruebas fijan lo que se midio contra el banco de 95 frases clinicas de
`corpus/urgencias.json`. La medicion completa se corre con
`scripts/evaluar_urgencia.py`.
"""

import json
from pathlib import Path

import pytest

from mediflow_agent.routing.terminos_criticos import GRUPOS, TERMINOS_CRITICOS
from mediflow_agent.routing.urgencia import (
    detectar,
    detectar_por_lista,
)

BANCO = Path(__file__).resolve().parent.parent / "corpus" / "urgencias.json"


class ModeloDoble:
    """Doble del modelo. Dice lo que se le indique, sin llamar a nadie."""

    def __init__(self, es_urgente: bool, motivo: str = "motivo de prueba", error=None):
        self._es_urgente = es_urgente
        self._motivo = motivo
        self._error = error
        self.llamadas = 0

    def with_structured_output(self, _esquema):
        return self

    def invoke(self, _prompt):
        self.llamadas += 1

        if self._error:
            raise self._error

        class _R:
            es_urgente = self._es_urgente
            motivo = self._motivo

        return _R()


@pytest.fixture(scope="module")
def banco() -> list[dict]:
    return json.loads(BANCO.read_text(encoding="utf-8"))


# --- La lista ------------------------------------------------------------

def test_la_lista_crecio_y_cubre_todos_los_sistemas():
    # Empezo con 17 terminos y se midio que no alcanzaba. El tamano no es la
    # solucion, pero menos de cien terminos deja afuera sistemas enteros.
    assert len(TERMINOS_CRITICOS) > 150
    assert len(GRUPOS) >= 10


def test_detecta_los_cuadros_con_nombre_propio(banco):
    # Es el piso que la lista si garantiza, y tiene que ser perfecto: estos
    # son los que no pueden escaparse ni aunque el modelo este caido.
    con_termino = [c for c in banco if c["grupo"] == "con_termino"]
    fallos = [c["texto"] for c in con_termino if not detectar_por_lista(c["texto"])]

    assert not fallos, f"la lista no vio: {fallos}"


def test_la_rutina_no_dispara(banco):
    rutina = [c for c in banco if c["grupo"] == "rutina"]
    fallos = [c["texto"] for c in rutina if detectar_por_lista(c["texto"])]

    assert not fallos, f"falsos positivos en rutina: {fallos}"


@pytest.mark.parametrize(
    "frase",
    [
        "El estudio descarta infarto agudo de miocardio.",
        "Sin signos de hemorragia intracraneal.",
        "No se observa tromboembolismo pulmonar.",
        "Antecedente de infarto hace quince anos, asintomatico.",
        "Paciente niega perdida de conciencia.",
        "Ausencia de neumotorax en la placa de control.",
        "Estudio solicitado para descartar diseccion aortica.",
    ],
)
def test_una_negacion_no_dispara(frase):
    # Sin este filtro las 20 negaciones del banco disparaban. "El estudio
    # descarta infarto" mandaba el caso a la cola de emergencia.
    assert not detectar_por_lista(frase), f"disparo con: {frase}"


def test_una_negacion_de_otra_oracion_no_apaga_la_urgencia():
    # El filtro mira hacia atras hasta la puntuacion anterior. Si mirara mas
    # lejos, un "sin" de la oracion previa apagaria una urgencia real.
    frase = "Sin signos de fractura. CONCLUSION: infarto agudo de miocardio."

    assert detectar_por_lista(frase)


def test_no_se_reporta_el_termino_contenido_en_otro():
    # "shock septico" y no "shock" suelto: la justificacion tiene que ser
    # precisa para que un auditor entienda que vio el sistema.
    terminos = detectar_por_lista("Paciente en shock septico.")

    assert "shock septico" in terminos
    assert "shock" not in terminos


# --- La doble via --------------------------------------------------------

def test_sin_modelo_funciona_solo_la_lista():
    # Es el piso que queda en pie si se agota la cuota del modelo.
    urgencia = detectar("Infarto agudo de miocardio.", llm=None)

    assert urgencia.es_urgente
    assert urgencia.via == "lista"


def test_el_modelo_detecta_lo_que_la_lista_no_ve():
    # El caso que justifica la segunda via: cuadro critico descrito sin
    # nombrar la patologia. Medido: 28 de 30 se escapaban con una sola via.
    frase = "Obstruccion completa de la arteria descendente anterior."

    assert not detectar_por_lista(frase)

    urgencia = detectar(frase, llm=ModeloDoble(True, "obstruccion coronaria"))

    assert urgencia.es_urgente
    assert urgencia.via == "modelo"


def test_basta_con_que_una_via_diga_urgente():
    # La regla es OR, no AND. Si fuera AND, un fallo de cualquiera de las dos
    # dejaria pasar una urgencia.
    frase = "Infarto agudo de miocardio."

    urgencia = detectar(frase, llm=ModeloDoble(False, "no me parece"))

    assert urgencia.es_urgente, "la lista sola tiene que alcanzar"
    assert urgencia.via == "lista"


def test_cuando_las_dos_coinciden_se_informa():
    urgencia = detectar("Sepsis grave.", llm=ModeloDoble(True, "sepsis"))

    assert urgencia.via == "ambas"


def test_un_fallo_del_modelo_no_apaga_la_via_por_lista():
    # Si el modelo revienta, la lista sigue valiendo. Lo contrario seria que
    # una urgencia nombrada se escape por un problema de red.
    urgencia = detectar(
        "Hemorragia subaracnoidea aguda.",
        llm=ModeloDoble(True, error=RuntimeError("cuota agotada")),
    )

    assert urgencia.es_urgente
    assert urgencia.via == "lista"


def test_un_fallo_del_modelo_no_lanza_excepcion():
    urgencia = detectar(
        "Control de rutina.", llm=ModeloDoble(True, error=RuntimeError("timeout"))
    )

    assert urgencia.es_urgente is False


# --- La explicacion ------------------------------------------------------

def test_la_explicacion_dice_que_se_encontro():
    # Es lo que lee el auditor. Tiene que nombrar el hallazgo concreto, no
    # decir "se detecto una urgencia".
    urgencia = detectar("Infarto agudo de miocardio.", llm=None)

    explicacion = urgencia.explicacion()

    assert "infarto" in explicacion.lower()
    assert "cardiovascular" in explicacion


def test_la_explicacion_de_un_caso_no_urgente_es_clara():
    assert "Sin hallazgos criticos" in detectar("Control de rutina.").explicacion()


# --- Configuracion desde archivo -----------------------------------------

def test_los_umbrales_salen_del_archivo_de_configuracion():
    from mediflow_agent.config import ARCHIVO_TRIAJE, cargar_archivo

    assert ARCHIVO_TRIAJE.is_file(), "falta config/triaje.toml"

    configuracion = cargar_archivo()

    assert configuracion["confianza"]["umbral"] == 0.70
    assert configuracion["rendimiento"]["pedidos_por_minuto"] == 15


def test_un_archivo_roto_no_tumba_el_sistema(tmp_path):
    # Un error de tipeo en un TOML no puede dejar sin atender una guardia.
    from mediflow_agent.config import cargar_archivo

    roto = tmp_path / "triaje.toml"
    roto.write_text("esto [ no es = toml valido", encoding="utf-8")

    assert cargar_archivo(roto) == {}


def test_el_entorno_le_gana_al_archivo(monkeypatch):
    from mediflow_agent.config import ajuste

    monkeypatch.setenv("MEDIFLOW_UMBRAL_CONFIANZA", "0.95")

    assert ajuste("confianza", "umbral", 0.70, "MEDIFLOW_UMBRAL_CONFIANZA") == 0.95
