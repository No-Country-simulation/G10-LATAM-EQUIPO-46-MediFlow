# -*- coding: utf-8 -*-
"""Genera el banco de frases para medir la deteccion de urgencia.

Script de un solo uso. Lo que queda versionado es `corpus/urgencias.json`.

Cuatro grupos, y los dos del medio son los que importan:

  1. URGENTE CON TERMINO. Cuadros criticos nombrados con una palabra de la
     lista. La deteccion por lista TIENE que encontrarlos todos.

  2. URGENTE SIN TERMINO. Cuadros igual de criticos descritos sin usar
     ninguna palabra de la lista: por anatomia, por valores de laboratorio, o
     con el nombre que usa el medico que dicta. **Estos son los que miden de
     verdad**, porque son los que se escapan.

  3. NO URGENTE. Documentacion de rutina. No debe disparar.

  4. NO URGENTE TRAMPA. Mencionan una palabra critica pero NO describen una
     urgencia: negaciones, antecedentes, estudios que descartan. Una lista de
     185 terminos que compara subcadenas dispara con "se descarta infarto",
     y eso llena la cola de emergencia de casos que no lo son.

Todo el contenido es ficticio y describe cuadros clinicos de uso corriente.
No fue revisado por un profesional: es material de prueba para un prototipo.
"""

import io
import json
import pathlib

DESTINO = pathlib.Path(
    r"C:\GitHub\G10-LATAM-EQUIPO-46-MediFlow\agente\corpus\urgencias.json"
)

URGENTE_CON_TERMINO = [
    "CONCLUSION: Cuadro compatible con Tromboembolismo Pulmonar Agudo.",
    "Hallazgos compatibles con infarto agudo de miocardio de cara anterior.",
    "Imagen hiperdensa en cisternas compatible con hemorragia subaracnoidea.",
    "Paciente en shock septico, requiere soporte vasoactivo.",
    "Sospecha de diseccion aortica. Paciente hipotenso.",
    "Se constata neumotorax a tension en hemitorax derecho.",
    "Cetoacidosis diabetica con acidosis severa.",
    "Status epileptico de mas de treinta minutos de evolucion.",
    "Abdomen agudo con neumoperitoneo en la radiografia.",
    "Eclampsia: convulsiones en gestante de 34 semanas.",
    "Politraumatismo grave tras colision vehicular.",
    "Neutropenia febril en paciente oncologico.",
    "Anafilaxia tras administracion de contraste yodado.",
    "Isquemia mesenterica aguda confirmada por angiotomografia.",
    "Hemorragia digestiva alta con sangrado activo.",
    "Fascitis necrotizante en miembro inferior izquierdo.",
    "Meningitis bacteriana confirmada por puncion lumbar.",
    "Insuficiencia respiratoria aguda con hipoxemia severa.",
    "Taponamiento cardiaco secundario a derrame pericardico.",
    "Sindrome HELLP en puerperio inmediato.",
    "Rotura uterina durante trabajo de parto.",
    "Compresion medular por metastasis vertebral.",
    "Intoxicacion por monoxido de carbono.",
    "Edema agudo de pulmon con saturacion critica.",
    "Perforacion intestinal con peritonitis difusa.",
]

# Los que la lista NO puede ver. Cada uno describe un cuadro critico real
# sin usar ninguna palabra del listado.
URGENTE_SIN_TERMINO = [
    "Obstruccion completa de la arteria descendente anterior en su tercio proximal.",
    "Defecto de llenado en arteria pulmonar principal derecha.",
    "Coleccion hiperdensa extraaxial con efecto de masa sobre el ventriculo lateral.",
    "Pupila derecha de 6 mm que no responde a la luz.",
    "El paciente no responde a estimulos verbales ni dolorosos.",
    "Presion arterial 70/40 pese a reposicion con cristaloides.",
    "Lactato serico de 6.8 mmol/L en ascenso.",
    "Potasio serico 7.2 mEq/L con ondas T picudas en el trazado.",
    "Glucemia capilar de 28 mg/dL con sudoracion profusa.",
    "pH arterial 7.08 con bicarbonato de 8 mEq/L.",
    "Hemoglobina de 4.1 g/dL con palidez cutaneomucosa marcada.",
    "Plaquetas en 8.000 por mm3 con gingivorragia espontanea.",
    "Frecuencia cardiaca fetal sostenida en 85 latidos por minuto.",
    "Liquido libre en los cuatro cuadrantes en la ecografia abdominal.",
    "Aire libre subdiafragmatico en la placa de torax de pie.",
    "Asa intestinal dilatada con ausencia de realce de la pared.",
    "Dilatacion de 6.2 cm en aorta abdominal con signos de fisura.",
    "Trazado con QRS ancho y frecuencia de 210 por minuto.",
    "Saturacion de oxigeno en 78 por ciento con mascara de reservorio.",
    "Quemaduras en el 45 por ciento de la superficie corporal.",
    "Hollin en orofaringe y disfonia tras incendio en espacio cerrado.",
    "Ausencia de pulsos distales con extremidad fria y palida.",
    "Desviacion de estructuras de la linea media de 9 mm.",
    "Cuello uterino con procidencia de asa de cordon.",
    "Recien nacido con puntaje de 3 al primer minuto.",
    "Troponina ultrasensible de 4.500 ng/L con dolor precordial.",
    "Rigidez de nuca con fotofobia y fiebre de 39.5 grados.",
    "Paciente con tres episodios de vomito en borra de cafe.",
    "INR de 8.4 con hematoma espontaneo en muslo.",
    "Imposibilidad de hablar y hemiparesia derecha de inicio subito.",
]

NO_URGENTE = [
    "Control de rutina sin particularidades.",
    "Estudio dentro de parametros normales para la edad.",
    "Se solicita hemograma completo y perfil lipidico ambulatorio.",
    "Radiografia de torax sin alteraciones significativas.",
    "Litiasis vesicular unica. Control ambulatorio.",
    "Certifico reposo laboral por tres dias por lumbalgia aguda.",
    "Parto vaginal eutocico de termino sin complicaciones.",
    "Apta para la practica de actividad deportiva recreativa.",
    "Rp/ Amoxicilina 500 mg cada 8 horas por 7 dias.",
    "Espirometria con valores dentro de limites esperados.",
    "Ecografia abdominal: higado de ecoestructura conservada.",
    "Control post operatorio a los treinta dias, herida en buen estado.",
    "Se indica kinesiologia motora tres veces por semana.",
    "Solicita resonancia de rodilla por sospecha de lesion meniscal.",
    "Glucemia en ayunas de 92 mg/dL.",
    "Paciente refiere mejoria del dolor con el tratamiento indicado.",
    "Se programa colecistectomia laparoscopica electiva.",
    "Audiometria sin hipoacusia significativa.",
    "Control de embarazo de 22 semanas, evolucion normal.",
    "Se renueva receta de medicacion cronica sin cambios.",
]

# El caso que una lista grande vuelve peligroso: la palabra esta, la urgencia
# no. Si estas disparan, la cola de emergencia se llena de ruido y deja de
# mirarse con urgencia.
NO_URGENTE_TRAMPA = [
    "El estudio descarta infarto agudo de miocardio.",
    "Sin signos de hemorragia intracraneal.",
    "No se observa tromboembolismo pulmonar.",
    "Antecedente de infarto hace quince anos, asintomatico.",
    "Control anual en paciente con antecedente de sepsis en 2019.",
    "Se descarta perforacion intestinal.",
    "Ausencia de neumotorax en la placa de control.",
    "Paciente niega perdida de conciencia.",
    "Estudio solicitado para descartar diseccion aortica.",
    "Sin evidencia de metastasis a distancia.",
    "Evolucion favorable del shock septico tratado el mes pasado.",
    "Alta tras resolucion de cetoacidosis diabetica.",
    "Riesgo quirurgico bajo, sin compromiso vital.",
    "No presenta convulsiones desde hace dos anos.",
    "Se indica control para prevenir una crisis hipertensiva.",
    "Informe previo de hemorragia digestiva ya resuelta.",
    "Charla de prevencion sobre signos de alarma de infarto.",
    "Paciente en seguimiento por antecedente de embolia pulmonar.",
    "Sin criterios de insuficiencia respiratoria.",
    "Ecografia normal, se descarta embarazo ectopico.",
]


def main() -> None:
    casos = (
        [{"texto": t, "urgente": True, "grupo": "con_termino"} for t in URGENTE_CON_TERMINO]
        + [{"texto": t, "urgente": True, "grupo": "sin_termino"} for t in URGENTE_SIN_TERMINO]
        + [{"texto": t, "urgente": False, "grupo": "rutina"} for t in NO_URGENTE]
        + [{"texto": t, "urgente": False, "grupo": "trampa"} for t in NO_URGENTE_TRAMPA]
    )

    DESTINO.parent.mkdir(parents=True, exist_ok=True)
    io.open(DESTINO, "w", encoding="utf-8", newline="\n").write(
        json.dumps(casos, ensure_ascii=False, indent=2) + "\n"
    )

    from collections import Counter

    print(f"{len(casos)} casos escritos en {DESTINO.name}")
    for grupo, n in Counter(c["grupo"] for c in casos).items():
        print(f"  {grupo:14} {n}")


if __name__ == "__main__":
    main()
