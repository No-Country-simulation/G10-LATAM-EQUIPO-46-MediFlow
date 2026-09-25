# Contrato de la API de triaje

Fuente: enunciado oficial del Hackathon ONE G10, Proyecto 2 — MediFlow,
sección *Funcionalidades obligatorias (MVP)*.

**Este documento manda sobre cualquier otra definición del repositorio.** Si el
código y este archivo no coinciden, el que está mal es el código. Se acordó así
para que los dos equipos escriban contra la misma forma y las piezas encajen en
la integración de la semana 3.

## Entrada

`POST /triaje`

```json
{
  "documento_id": "DOC-CLIN-2026-8942",
  "tipo_archivo": "PDF",
  "documento_texto": "HOSPITAL SANTA LUCIA - INFORME DE ESTUDIO RADIOLOGICO. ...",
  "canal_origen": "Guardia_Emergencias"
}
```

| Campo              | Tipo   | Obligatorio | Notas |
|--------------------|--------|-------------|-------|
| `documento_id`     | string | sí          | Identificador que asigna el sistema emisor. |
| `tipo_archivo`     | string | sí          | `PDF`, `IMAGEN`, `TEXTO` o `JSON`. |
| `documento_texto`  | string | condicional | Contenido cuando el tipo es texto. Para PDF o imagen, el binario llega por otra vía y este campo puede venir vacío. |
| `canal_origen`     | string | sí          | De dónde llegó. Alimenta la detección de urgencia: `Guardia_Emergencias` es una señal de prioridad, no una prueba. |

## Salida

```json
{
  "status": "procesado",
  "documento_id": "DOC-CLIN-2026-8942",
  "clasificacion": {
    "tipo_documento": "Informe de Estudio por Imagenes",
    "especialidad": "Radiologia / Neumonologia",
    "nivel_prioridad": "Urgente",
    "score_confianza_clasificacion": 0.99
  },
  "datos_extraidos": {
    "paciente": { "nombre": "Carlos Eduardo Mendes", "edad": 52 },
    "medico_solicitante": { "nombre": "Dra. Renata Silveira", "matricula": "145892" },
    "estudio_realizado": "Tomografia de Torax con contraste",
    "diagnostico_principal": "Tromboembolismo Pulmonar Agudo (TEP)",
    "cie10_sugerido": "I26.9"
  },
  "decision_enrutamiento": {
    "destino_principal": "Cola_Emergencia_Medica",
    "requiere_auditoria_humana": false,
    "justificacion_enrutamiento": "Hallazgo critico de alta gravedad (TEP agudo) detectado en paciente sintomatico.",
    "notificacion_generada": {
      "canal": "Alerta_Guardia_Medica",
      "mensaje": "ALERTA URGENTE: Informe critico de TEP Agudo para el paciente Carlos Eduardo Mendes en Guardia de Emergencias."
    }
  },
  "almacenamiento_oci": {
    "bucket": "mediflow-documentos-clinicos",
    "ruta_objeto": "procesados/urgentes/DOC-CLIN-2026-8942.json",
    "status_backup": "exito"
  }
}
```

### Valores admitidos

- **`status`** — `procesado`, `derivado_revision_humana`, `error`.
- **`nivel_prioridad`** — `Rutina`, `Prioritario`, `Urgente`.
- **`destino_principal`** — `Cola_Emergencia_Medica`, `Auditoria_Autorizaciones`,
  `Farmacia_Hospitalaria`, `Historia_Clinica_Electronica`, `Cola_Revision_Humana`.
- **`tipo_documento`** — Receta Medica, Informe de Estudio por Imagenes,
  Informe de Laboratorio, Orden de Solicitud de Procedimiento, Epicrisis,
  Certificado Medico, Desconocido.
- **`status_backup`** — `exito`, `fallo`. Un `fallo` aquí **no** invalida el
  triaje: la decisión ya se tomó. Se reporta y se reintenta.

### Reglas de forma

1. **Todo campo ausente va en `null`, nunca se omite ni se inventa.** El
   consumidor tiene que poder distinguir "no estaba en el documento" de "no lo
   supimos leer". Un `cie10_sugerido` inventado es peor que un `null`.
2. **`justificacion_enrutamiento` nunca viene vacío.** Es lo que demuestra que
   el agente razona y no solo extrae, y es lo que se muestra en la demo.
3. **`notificacion_generada` va en `null`** cuando la ruta no genera alerta.
4. `score_confianza_clasificacion` es un número entre 0 y 1.

## Dos notas sobre el enunciado

- El ejemplo oficial escribe `"nome"` dentro de `paciente`. Es un resto en
  portugués del documento original; el resto del contrato está en español.
  **Acá usamos `nombre`.** Si el jurado evalúa contra la letra literal del PDF,
  es un cambio de una línea en la capa de serialización.
- El enunciado pide extraer `medicamentos` y `dosis` (página 2), pero el
  ejemplo de respuesta no los muestra porque es un informe radiológico. Para
  recetas, `datos_extraidos` incluye además `medicamentos`, como lista de
  objetos `{ "nombre", "dosis", "frecuencia" }`.

## Cómo se implementa sin romper el módulo del agente

Los modelos Pydantic de `agente/src/mediflow_agent/schemas/models.py` están en
inglés y **está bien que sigan así**: son el modelo interno de dominio.

Lo que falta es una **capa de serialización** en el borde de la API que traduzca
del modelo interno a este contrato. Traducir en el borde, y no renombrar los
modelos, tiene tres ventajas: el módulo del agente sigue evolucionando sin
tocar la API, el contrato público queda en un solo archivo fácil de auditar
contra el enunciado, y nadie tiene que reescribir el trabajo ya hecho.

Responsable: Equipo B, junto con la tarea 3.3 del cronograma. El contrato se
congela ahora; la implementación llega en la semana 3.
