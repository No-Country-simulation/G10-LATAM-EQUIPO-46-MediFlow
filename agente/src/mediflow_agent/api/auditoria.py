"""Panel de auditoria humana: ver la bandeja, corregir y aprobar.

Cierra el circulo del escenario 3 del enunciado. Un documento derivado a
revision humana no se queda ahi: un auditor completa lo que faltaba, aprueba,
y **el agente vuelve a decidir** con los datos corregidos.

Que el agente re-decida en vez de que el auditor elija el destino a mano no es
un capricho: si el auditor pudiera mandar un documento a cualquier cola, el
grafo de decision dejaria de ser la unica autoridad sobre el enrutamiento y
nadie podria auditar por que un documento termino donde termino.

Lo que el auditor SI decide es el contenido: que dice el documento. Lo que
decide el agente es a donde va.
"""

import json
import logging
from dataclasses import dataclass
from typing import Any, Optional

from pydantic import BaseModel, Field

from mediflow_agent.routing.baseline import decidir_enrutamiento
from mediflow_agent.schemas.models import (
    AgentResult,
    ClassificationResult,
    Doctor,
    ExtractedData,
    Patient,
)
from mediflow_agent.serialization.contract import (
    AlmacenamientoOciContrato,
    RespuestaTriaje,
    a_respuesta_triaje,
)
from mediflow_agent.storage.base import (
    PREFIJO_AUDITORIA,
    PREFIJO_RECIBIDOS,
    PREFIJO_RUTINA,
    PREFIJO_URGENTES,
    AlmacenamientoDocumentos,
)

_log = logging.getLogger(__name__)

# Donde buscar un documento, en el orden en que conviene mirarlo.
PREFIJOS = (PREFIJO_AUDITORIA, PREFIJO_URGENTES, PREFIJO_RUTINA)

# De la etiqueta publica del contrato de vuelta al slug interno. Es la inversa
# de TIPO_DOCUMENTO_PUBLICO: hace falta para re-decidir sobre un documento ya
# guardado, porque lo persistido esta en la forma publica.
TIPO_INTERNO = {
    "Receta Medica": "receta_medica",
    "Informe de Estudio Diagnostico": "informe_estudio_diagnostico",
    "Informe de Laboratorio": "informe_estudio_diagnostico",
    "Orden de Solicitud de Procedimiento": "orden_procedimiento",
    "Epicrisis": "epicrisis",
    "Certificado Medico": "certificado_medico",
    "Desconocido": "desconocido",
}


class Correcciones(BaseModel):
    """Lo que el auditor completa o corrige antes de aprobar."""

    paciente_nombre: Optional[str] = None
    paciente_edad: Optional[int] = None
    medico_nombre: Optional[str] = None
    medico_matricula: Optional[str] = None
    estudio_realizado: Optional[str] = None
    diagnostico_principal: Optional[str] = None
    cie10_sugerido: Optional[str] = None
    medicamentos: Optional[list[str]] = None

    auditor: str = Field(
        default="",
        description="Quien aprueba. Queda registrado en la justificacion.",
    )


@dataclass(frozen=True)
class CasoEnBandeja:
    documento_id: str
    prefijo: str
    tipo_documento: str
    nivel_prioridad: str
    destino: str
    justificacion: str
    paciente: Optional[str]


def _a_modelos_internos(
    respuesta: RespuestaTriaje,
) -> tuple[ClassificationResult, ExtractedData]:
    """Vuelve del contrato publico a los modelos internos.

    Es la inversa de `a_respuesta_triaje`. Hace falta porque lo que esta
    guardado en el bucket es la forma publica, y el grafo de decision trabaja
    con la interna.
    """
    clasificacion = respuesta.clasificacion
    datos = respuesta.datos_extraidos

    return (
        ClassificationResult(
            document_type=TIPO_INTERNO.get(
                clasificacion.tipo_documento, "desconocido"
            ),
            specialty=clasificacion.especialidad,
            confidence=clasificacion.score_confianza_clasificacion,
        ),
        ExtractedData(
            patient=Patient(name=datos.paciente.nombre, age=datos.paciente.edad),
            doctor=Doctor(
                name=datos.medico_solicitante.nombre,
                license_number=datos.medico_solicitante.matricula,
            ),
            study=datos.estudio_realizado,
            diagnosis=datos.diagnostico_principal,
            suggested_icd10=datos.cie10_sugerido,
            medications=datos.medicamentos,
        ),
    )


def _aplicar(datos: ExtractedData, correcciones: Correcciones) -> ExtractedData:
    """Devuelve los datos con lo que el auditor corrigio.

    Solo pisa lo que el auditor envio. Un campo que no mando queda como
    estaba: corregir no es volver a cargar el documento entero.
    """
    paciente = datos.patient.model_copy(
        update={
            k: v
            for k, v in {
                "name": correcciones.paciente_nombre,
                "age": correcciones.paciente_edad,
            }.items()
            if v is not None
        }
    )

    medico = datos.doctor.model_copy(
        update={
            k: v
            for k, v in {
                "name": correcciones.medico_nombre,
                "license_number": correcciones.medico_matricula,
            }.items()
            if v is not None
        }
    )

    cambios: dict[str, Any] = {"patient": paciente, "doctor": medico}

    for campo, valor in (
        ("study", correcciones.estudio_realizado),
        ("diagnosis", correcciones.diagnostico_principal),
        ("suggested_icd10", correcciones.cie10_sugerido),
        ("medications", correcciones.medicamentos),
    ):
        if valor is not None:
            cambios[campo] = valor

    return datos.model_copy(update=cambios)


class ServicioAuditoria:

    def __init__(self, almacenamiento: AlmacenamientoDocumentos, llm=None):
        self._almacenamiento = almacenamiento
        self._llm = llm

    # -- lectura ---------------------------------------------------------

    def bandeja(self, prefijo: str = PREFIJO_AUDITORIA) -> list[CasoEnBandeja]:
        """Los casos que esperan en un prefijo, con lo necesario para decidir."""
        casos = []

        for nombre in self._almacenamiento.listar(prefijo):
            if not nombre.endswith(".json"):
                continue

            respuesta = self._leer(prefijo, nombre)

            if respuesta is None:
                continue

            # Un caso ya aprobado puede seguir fisicamente en el prefijo de
            # auditoria si el almacen no permite borrar. La bandeja muestra lo
            # que sigue PENDIENTE, no lo que quedo archivado ahi.
            if (
                prefijo == PREFIJO_AUDITORIA
                and not respuesta.decision_enrutamiento.requiere_auditoria_humana
            ):
                continue

            casos.append(
                CasoEnBandeja(
                    documento_id=respuesta.documento_id,
                    prefijo=prefijo,
                    tipo_documento=respuesta.clasificacion.tipo_documento,
                    nivel_prioridad=respuesta.clasificacion.nivel_prioridad,
                    destino=respuesta.decision_enrutamiento.destino_principal,
                    justificacion=(
                        respuesta.decision_enrutamiento.justificacion_enrutamiento
                    ),
                    paciente=respuesta.datos_extraidos.paciente.nombre,
                )
            )

        # Urgente primero, despues Prioritario, despues Rutina: es lo que
        # "Prioritario" significa en el flujo, y el unico lugar donde cambia
        # algo observable.
        orden = {"Urgente": 0, "Prioritario": 1, "Rutina": 2}
        casos.sort(key=lambda c: (orden.get(c.nivel_prioridad, 3), c.documento_id))

        return casos

    def _leer(self, prefijo: str, nombre: str) -> RespuestaTriaje | None:
        crudo = self._almacenamiento.leer_texto(prefijo, nombre)

        if not crudo:
            return None

        try:
            return RespuestaTriaje(**json.loads(crudo))
        except Exception as err:  # noqa: BLE001
            _log.warning("No se pudo leer %s/%s: %s", prefijo, nombre, err)
            return None

    def documento(self, documento_id: str) -> tuple[RespuestaTriaje, str] | None:
        """Busca la decision guardada y devuelve (respuesta, prefijo)."""
        for prefijo in PREFIJOS:
            respuesta = self._leer(prefijo, f"{documento_id}.json")

            if respuesta is not None:
                return respuesta, prefijo

        return None

    def original(self, documento_id: str) -> str | None:
        """El documento tal como llego, para mostrarlo junto a lo extraido."""
        for extension in ("txt", "json"):
            crudo = self._almacenamiento.leer_texto(
                PREFIJO_RECIBIDOS, f"{documento_id}.{extension}"
            )
            if crudo:
                return crudo

        return None

    # -- aprobacion ------------------------------------------------------

    def aprobar(
        self, documento_id: str, correcciones: Correcciones
    ) -> RespuestaTriaje | None:
        """Aplica las correcciones y vuelve a decidir la ruta.

        El agente re-decide: el auditor corrige el CONTENIDO, no elige el
        destino. Asi el grafo sigue siendo la unica autoridad sobre el
        enrutamiento y la decision sigue siendo auditable.
        """
        encontrado = self.documento(documento_id)

        if encontrado is None:
            return None

        respuesta, prefijo_anterior = encontrado
        clasificacion, datos = _a_modelos_internos(respuesta)
        datos = _aplicar(datos, correcciones)

        texto = self.original(documento_id) or ""

        nivel, decision, status = decidir_enrutamiento(
            documento_id=documento_id,
            clasificacion=clasificacion,
            datos=datos,
            canal_origen="Panel_Auditoria",
            llm=self._llm,
        )

        quien = correcciones.auditor.strip() or "un auditor"

        decision = decision.model_copy(
            update={
                "justificacion_enrutamiento": (
                    f"Revisado y aprobado por {quien}. "
                    + decision.justificacion_enrutamiento
                )
            }
        )

        prefijo = (
            PREFIJO_URGENTES
            if nivel == "Urgente"
            else PREFIJO_AUDITORIA
            if decision.requiere_auditoria_humana
            else PREFIJO_RUTINA
        )

        nueva = a_respuesta_triaje(
            resultado=AgentResult(
                document_id=documento_id,
                classification=clasificacion,
                extracted_data=datos,
            ),
            nivel_prioridad=nivel,
            decision_enrutamiento=decision,
            almacenamiento_oci=AlmacenamientoOciContrato(
                bucket=self._almacenamiento.bucket,
                ruta_objeto=f"{prefijo}/{documento_id}.json",
                status_backup="exito",
            ),
            status=status,
        )

        guardado = self._almacenamiento.guardar_texto(
            prefijo, f"{documento_id}.json", nueva.model_dump_json(indent=2)
        )

        # El caso resuelto no puede quedar contradiciendo al nuevo desde su
        # prefijo anterior. Se intenta borrarlo; si el almacen no lo permite
        # —OCI no concede DELETE por PAR— se sobreescribe con la decision
        # nueva, para que las dos copias digan lo mismo.
        if prefijo_anterior != prefijo:
            nombre = f"{documento_id}.json"

            if not self._almacenamiento.borrar(prefijo_anterior, nombre):
                _log.info(
                    "El almacen no permite borrar; se sincroniza %s/%s con la "
                    "decision nueva.",
                    prefijo_anterior,
                    nombre,
                )
                self._almacenamiento.guardar_texto(
                    prefijo_anterior, nombre, nueva.model_dump_json(indent=2)
                )

        if not guardado.exito:
            nueva = nueva.model_copy(
                update={
                    "almacenamiento_oci": nueva.almacenamiento_oci.model_copy(
                        update={"status_backup": "fallo"}
                    )
                }
            )

        return nueva
