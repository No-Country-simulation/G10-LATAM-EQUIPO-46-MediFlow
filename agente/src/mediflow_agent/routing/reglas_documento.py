"""Reglas por tipo de documento: que hace falta para avanzar sin un humano.

Vienen de la revision de Danilo Loaiza sobre los 30 documentos del corpus
(12/10/2026). Encontro que el sistema enrutaba automaticamente documentos a
los que les faltaba informacion que un humano habria pedido antes de actuar.

**La regla de fondo.** Un documento solo sigue su ruta automatica si trae lo
minimo para que el destino pueda actuar sobre el. Una receta sin matricula no
puede ir sola a farmacia: nadie puede verificar que la firmo un profesional
habilitado. El dato ausente queda en `null` y el caso va a revision humana;
nunca se completa ni se asume.

**Que NO hace esto.** No decide si el documento es urgente: eso ya se evaluo
antes y gana sobre todo lo demas. Un informe con un hallazgo critico va a
emergencia aunque le falte la matricula del solicitante.
"""

from dataclasses import dataclass

from mediflow_agent.schemas.models import ClassificationResult, ExtractedData

# Que necesita cada tipo para avanzar solo, y por que.
#
# La lista es corta a proposito: cada campo que se agrega es un documento mas
# que va a revision humana. Pedir de mas satura la bandeja del auditor y
# termina haciendo que no mire ninguno con atencion.
CAMPOS_MINIMOS: dict[str, tuple[tuple[str, str], ...]] = {
    "receta_medica": (
        ("paciente.nombre", "sin saber a quien se dispensa"),
        ("medico.nombre", "sin saber quien prescribe"),
        ("medico.matricula", "sin matricula no se puede verificar la habilitacion"),
        ("medicamentos", "sin farmacos no hay nada que dispensar"),
    ),
    "orden_procedimiento": (
        ("paciente.nombre", "sin saber a quien se autoriza"),
        ("medico.nombre", "sin saber quien solicita"),
        ("procedimiento", "sin saber que se solicita no se puede autorizar"),
    ),
    "informe_estudio_diagnostico": (
        ("paciente.nombre", "sin saber de quien es el informe"),
    ),
    "epicrisis": (
        ("paciente.nombre", "sin saber de quien es el alta"),
    ),
    "certificado_medico": (
        ("paciente.nombre", "sin saber a quien certifica"),
        ("medico.nombre", "un certificado sin profesional no certifica nada"),
    ),
}

# Un certificado para junta evaluadora tiene consecuencias administrativas y
# previsionales. El proyecto todavia no acordo un destino para esos: hasta
# entonces van a una persona en lugar de archivarse solos.
MARCAS_JUNTA_MEDICA = (
    "junta medica",
    "junta evaluadora",
    "junta de evaluacion",
    "comision medica",
    "discapacidad",
)


@dataclass(frozen=True)
class Faltante:
    campo: str
    motivo: str


def _valor(datos: ExtractedData, campo: str):
    rutas = {
        "paciente.nombre": lambda d: d.patient.name,
        "paciente.edad": lambda d: d.patient.age,
        "medico.nombre": lambda d: d.doctor.name,
        "medico.matricula": lambda d: d.doctor.license_number,
        "medicamentos": lambda d: d.medications,
        "procedimiento": lambda d: d.procedure,
        "estudio": lambda d: d.study,
        "diagnostico": lambda d: d.diagnosis,
        "conclusion": lambda d: d.conclusion,
    }
    return rutas[campo](datos)


def _tiene_valor(valor) -> bool:
    if valor is None:
        return False
    if isinstance(valor, str):
        return bool(valor.strip())
    if isinstance(valor, (list, tuple)):
        return bool(valor)
    return True


def campos_faltantes(
    tipo_documento: str, datos: ExtractedData
) -> tuple[Faltante, ...]:
    """Campos minimos que el documento no trae, con el porque de cada uno."""
    return tuple(
        Faltante(campo, motivo)
        for campo, motivo in CAMPOS_MINIMOS.get(tipo_documento, ())
        if not _tiene_valor(_valor(datos, campo))
    )


def es_receta_controlada(especifico) -> bool:
    """True si el extractor marco la receta como controlada.

    El dato se extraia desde la tarea 2.2 y no se usaba en ninguna parte. Una
    receta controlada exige verificar la firma antes de dispensar, asi que va
    a una persona. **No es una emergencia**: que sea controlada no la vuelve
    urgente, solo no automatizable.
    """
    return bool(getattr(especifico, "es_receta_controlada", False))


def es_certificado_de_junta(texto: str) -> bool:
    """True si el certificado esta destinado a una junta evaluadora."""
    minuscula = texto.lower()
    return any(marca in minuscula for marca in MARCAS_JUNTA_MEDICA)
