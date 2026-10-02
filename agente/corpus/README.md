# Corpus sintético etiquetado

Treinta documentos clínicos **inventados** con su etiqueta, para medir qué tan
bien los lee el agente. Es la tarea 2.3 del cronograma.

**Todos los datos son ficticios.** Nombres, matrículas, fechas, instituciones y
números de documento fueron inventados para este corpus. Ninguno corresponde a
una persona real, y no debe agregarse acá ningún documento clínico real, ni
siquiera anonimizado.

## Qué hay

| Tipo de documento | Cantidad |
|-------------------|----------|
| `informe_estudio_diagnostico` | 7 |
| `receta_medica` | 6 |
| `orden_procedimiento` | 5 |
| `epicrisis` | 4 |
| `certificado_medico` | 4 |
| `desconocido` | 4 |

Por prioridad esperada: 18 de rutina, 7 prioritarios y **5 urgentes**.

El corpus incluye a propósito los casos que rompen las cosas:

- Documentos **completos y legibles**, que son el caso fácil.
- Documentos **incompletos**: sin matrícula, sin firma, sin identificación del
  paciente. Ahí el agente debe devolver `null`, no inventar.
- Una receta con la **dosis ilegible**, que nunca puede ir sola a farmacia.
- Cinco **hallazgos críticos** (TEP, infarto, hemorragia subaracnoidea, sepsis,
  disección aórtica) repartidos en tipos de documento distintos, para que la
  urgencia no se pueda detectar solo por la categoría.
- Cuatro documentos que **no son clínicos** (un comprobante de pago, un correo
  interno, una página en blanco y una transcripción ilegible), que no deben
  forzarse a ninguna categoría.

## Las etiquetas

`etiquetas.json` tiene una entrada por documento:

```json
{
  "archivo": "007-informe-tep.txt",
  "tipo_documento": "informe_estudio_diagnostico",
  "nivel_prioridad": "Urgente",
  "campos_presentes": ["paciente.nombre", "paciente.edad", "..."],
  "nota": "El caso del enunciado. Hallazgo critico, debe ir a emergencia."
}
```

`campos_presentes` es la clave de la medición: son los datos que **un humano sí
puede leer** en ese documento. Un `null` donde había un dato es un fallo de
cobertura; un valor donde no había nada es una invención, que el proyecto
prohíbe.

## Cómo se mide

```bash
python scripts/evaluar_corpus.py --simulado    # sin gastar cuota
python scripts/evaluar_corpus.py               # con Gemini
```

## Cómo se amplía

Agregá el `.txt` en `documentos/` con el siguiente número correlativo y su
entrada en `etiquetas.json`. La prueba `tests/test_corpus.py` verifica que los
dos lados estén sincronizados y falla si alguien agrega uno y olvida el otro.
