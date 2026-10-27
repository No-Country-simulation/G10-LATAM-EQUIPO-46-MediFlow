# Documentos clinicos de la demo

Los tres escenarios que exige el enunciado, en PDF, listos para subir a la
pagina o mostrar en el video.

| Archivo | Escenario | Resultado esperado |
|---|---|---|
| `1_rutina_orden_laboratorio.pdf` | Rutina | Auditoria de Autorizaciones, sin intervencion humana |
| `2_urgencia_informe_tomografia.pdf` | Urgencia | Cola de Emergencia Medica, alerta a la guardia, CIE-10 I26.9 |
| `3_ambiguedad_receta_manuscrita.pdf` | Ambiguedad | Cola de Revision Humana, con la dosis en `null` |

**El tercero no dice "ilegible" en ninguna parte.** Esta escrito con una
tipografia manuscrita y la dosis de la Metformina es un garabato dibujado.
Es la diferencia entre demostrar el comportamiento y declararlo: si el PDF
trajera la palabra escrita, el agente no estaria leyendo un documento
dificil, estaria obedeciendo una etiqueta.

La Glibenclamida del mismo documento **si** se lee. Esa asimetria es lo que
importa: el agente extrae lo que puede y deja en `null` lo que no, en lugar
de completar la receta entera o rechazarla entera.

Lo que el auditor completa en la demo: la dosis de la Metformina y la
matricula del profesional.

**Los datos de pacientes y profesionales son ficticios.** No corresponden a
ninguna persona real.

Para regenerarlos (hace falta `pip install reportlab`, que no esta en
`requirements.txt` porque el agente no lo usa):

    python scripts/generar_pdfs_demo.py
