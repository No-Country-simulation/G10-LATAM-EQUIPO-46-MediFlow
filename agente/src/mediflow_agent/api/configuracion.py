"""Lectura y escritura de las reglas de triaje desde la pantalla.

Es el diferencial del enunciado:

    "Flujo Clinico Personalizable por el Usuario: Modulo o interfaz que
     permita al gestor hospitalario configurar reglas de triaje
     personalizadas, nuevos destinos de enrutamiento y umbrales de urgencia
     sin modificar el codigo fuente."

Hasta aca eso existia como archivo TOML en el servidor. Funcionaba, pero solo
para quien tuviera acceso por SSH: delante de alguien que mira la aplicacion,
no se podia personalizar nada. Este modulo lo pone en la pantalla.

Cuatro decisiones que gobiernan lo de abajo:

1. **Escribir requiere clave.** La pagina esta abierta a internet sin
   contraseña. Sin esto, cualquiera con el enlace podria poner el umbral en
   cero y desactivar la revision humana de todo el sistema, o mandar las
   recetas al departamento equivocado. Leer es libre; escribir no.

2. **Sin clave configurada, el panel es de solo lectura.** No se elige una
   clave por defecto: una clave por defecto es no tener clave, con la
   desventaja de parecer que si.

3. **Se valida ANTES de escribir.** Un umbral fuera de rango o un destino
   inexistente se rechazan con un motivo entendible. El archivo nunca queda
   en un estado que el agente no pueda leer.

4. **Se escribe el archivo entero, no un parche.** El TOML es la fuente de
   verdad y `cargar_archivo` lo relee cuando cambia su fecha. Asi lo que
   muestra la pantalla, lo que usa el agente y lo que sobrevive a un
   reinicio son siempre lo mismo.
"""

import logging
from pathlib import Path
from typing import Optional, get_args

from pydantic import BaseModel, Field, field_validator

from mediflow_agent.config import ARCHIVO_TRIAJE, cargar_archivo, olvidar_archivo
from mediflow_agent.routing.baseline import (
    CANALES_POR_DEFECTO,
    DESTINOS_POR_DEFECTO,
    UMBRAL_POR_DEFECTO,
    canales_prioritarios,
    destinos_configurados,
    umbral_configurado,
)
from mediflow_agent.schemas.models import DocumentType
from mediflow_agent.serialization.contract import DestinoEnrutamiento

_log = logging.getLogger(__name__)

DESTINOS_VALIDOS = tuple(get_args(DestinoEnrutamiento))
TIPOS_VALIDOS = tuple(t for t in get_args(DocumentType) if t != "desconocido")


class ReglasTriaje(BaseModel):
    """Lo que un gestor hospitalario puede cambiar sin tocar el codigo."""

    umbral_confianza: float = Field(
        ge=0.0,
        le=1.0,
        description="Por debajo de este valor el caso va a revision humana.",
    )

    canales_prioritarios: list[str] = Field(
        description="Canales de origen que elevan la prioridad a Prioritario."
    )

    destinos: dict[str, str] = Field(
        description="A que departamento va cada tipo de documento."
    )

    @field_validator("destinos")
    @classmethod
    def validar_destinos(cls, valor: dict[str, str]) -> dict[str, str]:
        for tipo, destino in valor.items():
            if tipo not in TIPOS_VALIDOS:
                raise ValueError(
                    f"'{tipo}' no es un tipo de documento. Los tipos son: "
                    + ", ".join(TIPOS_VALIDOS)
                )
            if destino not in DESTINOS_VALIDOS:
                raise ValueError(
                    f"'{destino}' no es un destino valido. Los destinos son: "
                    + ", ".join(DESTINOS_VALIDOS)
                )

        return valor

    @field_validator("canales_prioritarios")
    @classmethod
    def limpiar_canales(cls, valor: list[str]) -> list[str]:
        # Se guardan normalizados porque asi los compara el grafo. Si se
        # guardara "Guardia_Emergencias" tal cual, no coincidiria nunca y el
        # gestor veria su regla escrita pero sin efecto.
        limpios = [c.strip().lower().replace(" ", "_") for c in valor if c.strip()]

        return list(dict.fromkeys(limpios))


def bloqueados_por_entorno() -> list[str]:
    """Campos que una variable de entorno fija por encima del archivo.

    La precedencia entorno > archivo es deliberada: permite forzar un valor en
    un despliegue concreto. Pero entonces la pantalla guardaria el valor nuevo
    en el archivo y el agente seguiria usando el del entorno. En lugar de
    mentir, el panel marca esos campos y dice por que no se pueden mover.
    """
    from mediflow_agent.config import variable

    bloqueados = []

    if variable("MEDIFLOW_UMBRAL_CONFIANZA") is not None:
        bloqueados.append("umbral_confianza")

    return bloqueados


def leer(ruta: Optional[Path] = None) -> ReglasTriaje:
    """Las reglas vigentes, tal como las usa el agente en este momento."""
    if ruta is None:
        return ReglasTriaje(
            umbral_confianza=umbral_configurado(),
            canales_prioritarios=sorted(canales_prioritarios()),
            destinos=destinos_configurados(),
        )

    datos = cargar_archivo(ruta)

    return ReglasTriaje(
        umbral_confianza=datos.get("confianza", {}).get("umbral", UMBRAL_POR_DEFECTO),
        canales_prioritarios=sorted(
            datos.get("urgencia", {}).get(
                "canales_prioritarios", list(CANALES_POR_DEFECTO)
            )
        ),
        destinos=datos.get("destinos") or dict(DESTINOS_POR_DEFECTO),
    )


def _como_toml(reglas: ReglasTriaje, previo: dict) -> str:
    """Arma el archivo entero, conservando lo que la pantalla no toca."""
    usar_lista = previo.get("urgencia", {}).get("usar_lista", True)
    usar_modelo = previo.get("urgencia", {}).get("usar_modelo", True)
    rendimiento = previo.get("rendimiento", {})

    lineas = [
        "# Reglas de triaje de MediFlow.",
        "#",
        "# ESTE ARCHIVO LO ESCRIBE LA PANTALLA DE CONFIGURACION. Se puede",
        "# editar a mano, pero los comentarios que se agreguen se pierden en",
        "# el proximo guardado desde la interfaz.",
        "#",
        "# La evidencia detras del umbral, y sus limites, estan en el README:",
        "# tres corridas del corpus dieron 0.65, 0.70 y 0.75 para la unica",
        "# clasificacion errada, asi que 0.70 la atrapa en una de tres. Si se",
        "# prioriza atrapar errores por encima de ahorrar revisiones, 0.80 la",
        "# atrapa en las tres.",
        "",
        "[confianza]",
        f"umbral = {reglas.umbral_confianza}",
        "",
        "[urgencia]",
        f"usar_lista = {str(usar_lista).lower()}",
        f"usar_modelo = {str(usar_modelo).lower()}",
        "canales_prioritarios = ["
        + ", ".join(f'"{c}"' for c in reglas.canales_prioritarios)
        + "]",
        "",
    ]

    if rendimiento:
        lineas.append("[rendimiento]")
        for clave, valor in rendimiento.items():
            if isinstance(valor, bool):
                lineas.append(f"{clave} = {str(valor).lower()}")
            elif isinstance(valor, (int, float)):
                lineas.append(f"{clave} = {valor}")
            else:
                lineas.append(f'{clave} = "{valor}"')
        lineas.append("")

    lineas.append("[destinos]")
    lineas.append(
        "# Un tipo que no figure aca se queda sin ruta automatica y escala a"
    )
    lineas.append("# revision humana, en lugar de elegir un destino arbitrario.")

    for tipo in TIPOS_VALIDOS:
        if tipo in reglas.destinos:
            lineas.append(f'{tipo} = "{reglas.destinos[tipo]}"')

    return "\n".join(lineas) + "\n"


def guardar(reglas: ReglasTriaje, ruta: Optional[Path] = None) -> ReglasTriaje:
    """Escribe las reglas al archivo y devuelve las que quedaron vigentes.

    Escribe a un temporal y recien despues reemplaza el archivo real. Si el
    proceso muere a mitad de la escritura, el agente sigue leyendo la version
    anterior completa en lugar de un TOML truncado.
    """
    archivo = ruta or ARCHIVO_TRIAJE
    contenido = _como_toml(reglas, cargar_archivo(archivo))

    temporal = archivo.with_suffix(archivo.suffix + ".tmp")
    temporal.write_text(contenido, encoding="utf-8")
    temporal.replace(archivo)

    # `cargar_archivo` se guia por la fecha del archivo. En un sistema donde
    # esa fecha tiene poca resolucion, dos guardados seguidos podrian compartir
    # marca y el segundo no verse. Se olvida a mano para no depender de eso.
    olvidar_archivo(archivo)

    vigentes = leer(ruta)

    _log.info(
        "Reglas de triaje actualizadas: umbral %.2f, %d canales, %d destinos.",
        vigentes.umbral_confianza,
        len(vigentes.canales_prioritarios),
        len(vigentes.destinos),
    )

    return vigentes
