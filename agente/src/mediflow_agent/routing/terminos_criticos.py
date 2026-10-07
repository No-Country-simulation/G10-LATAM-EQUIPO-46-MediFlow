"""Terminos que marcan un hallazgo clinico critico.

Es la **primera via** de la deteccion de urgencia: rapida, determinista, sin
costo y sin depender de que el modelo este disponible. La segunda via es el
propio modelo, en `urgencia.py`, y basta con que CUALQUIERA de las dos dispare
para que el caso vaya a emergencia.

**Por que una lista no alcanza, y por eso hay una segunda via.** Una lista
compara cadenas de texto, no significados. "Obstruccion completa de la arteria
descendente anterior" describe un infarto sin decir "infarto". Por grande que
sea la lista, siempre existe la frase que nadie previo, y en urgencias esa es
justo la que importa.

**Lo que esta lista si garantiza** es un piso: los cuadros con nombre propio
que no pueden escaparse nunca, aunque el modelo falle, este caido o se quede
sin cuota.

**Alcance y limites de este contenido.** Son terminos de uso corriente en
medicina de urgencias, agrupados por sistema. No es una clasificacion clinica
oficial ni fue revisada por un profesional: es una heuristica de software para
un prototipo con datos ficticios. **Antes de cualquier uso real, un medico
tiene que revisarla.** Agregar un termino es barato; quitarlo requiere pensar
dos veces, porque cada termino que sale es un caso que puede pasar como
rutina.

**El sesgo es a sobre-detectar.** Un falso positivo cuesta que una persona
mire un caso que no lo necesitaba. Un falso negativo cuesta que un infarto
espere en una bandeja. No son comparables.
"""

# --- Cardiovascular -------------------------------------------------------
CARDIOVASCULAR = (
    "infarto",
    "iam",
    "sindrome coronario agudo",
    "angina inestable",
    "supradesnivel del st",
    "elevacion del st",
    "supradesnivel st",
    "paro cardiaco",
    "paro cardiorrespiratorio",
    "parada cardiorrespiratoria",
    "fibrilacion ventricular",
    "taquicardia ventricular",
    "bloqueo auriculoventricular completo",
    "bloqueo av completo",
    "asistolia",
    "bradicardia severa",
    "diseccion aortica",
    "aneurisma roto",
    "aneurisma disecante",
    "rotura de aneurisma",
    "taponamiento cardiaco",
    "edema agudo de pulmon",
    "insuficiencia cardiaca descompensada",
    "shock cardiogenico",
    "isquemia aguda",
    "isquemia critica",
    "trombosis arterial aguda",
    "crisis hipertensiva",
    "emergencia hipertensiva",
)

# --- Respiratorio ---------------------------------------------------------
RESPIRATORIO = (
    "tromboembolismo",
    "tromboembolismo pulmonar",
    "tep agudo",
    "embolia pulmonar",
    "embolismo pulmonar",
    "insuficiencia respiratoria",
    "insuficiencia respiratoria aguda",
    "neumotorax",
    "neumotorax a tension",
    "hemotorax",
    "obstruccion de la via aerea",
    "obstruccion via aerea",
    "estridor",
    "broncoespasmo severo",
    "crisis asmatica severa",
    "estado asmatico",
    "distres respiratorio",
    "saturacion critica",
    "hipoxemia severa",
    "apnea",
)

# --- Neurologico ----------------------------------------------------------
NEUROLOGICO = (
    "hemorragia",
    "hemorragia subaracnoidea",
    "hemorragia intracraneal",
    "hemorragia intraparenquimatosa",
    "hematoma subdural",
    "hematoma epidural",
    "accidente cerebrovascular",
    "acv isquemico",
    "acv hemorragico",
    "ictus",
    "infarto cerebral",
    "trombosis venosa cerebral",
    "hipertension endocraneana",
    "herniacion cerebral",
    "desviacion de la linea media",
    "edema cerebral",
    "status epileptico",
    "estado epileptico",
    "convulsiones",
    "coma",
    "glasgow",
    "midriasis arreactiva",
    "pupila arreactiva",
    "anisocoria",
    "deterioro del sensorio",
    "perdida de conciencia",
    "meningitis",
    "encefalitis",
    "compresion medular",
    "sindrome de cola de caballo",
)

# --- Infeccioso y sistemico -----------------------------------------------
INFECCIOSO = (
    "sepsis",
    "shock septico",
    "sepsis grave",
    "bacteriemia",
    "fascitis necrotizante",
    "gangrena",
    "absceso cerebral",
    "endocarditis",
    "peritonitis",
    "mediastinitis",
    "shock",
    "falla multiorganica",
    "fallo multiorganico",
    "disfuncion multiorganica",
)

# --- Abdominal y quirurgico -----------------------------------------------
ABDOMINAL = (
    "abdomen agudo",
    "perforacion",
    "perforacion intestinal",
    "viscera perforada",
    "neumoperitoneo",
    "isquemia mesenterica",
    "obstruccion intestinal",
    "volvulo",
    "invaginacion intestinal",
    "apendicitis complicada",
    "colecistitis aguda",
    "pancreatitis grave",
    "pancreatitis necrotizante",
    "hemorragia digestiva",
    "sangrado activo",
    "hemoperitoneo",
    "rotura esplenica",
    "rotura hepatica",
    "embarazo ectopico",
)

# --- Metabolico y toxicologico -------------------------------------------
METABOLICO = (
    "cetoacidosis",
    "cetoacidosis diabetica",
    "estado hiperosmolar",
    "hipoglucemia severa",
    "hiperkalemia",
    "hiperpotasemia",
    "hipokalemia severa",
    "hiponatremia severa",
    "acidosis metabolica",
    "acidosis severa",
    "crisis tirotoxica",
    "tormenta tiroidea",
    "crisis addisoniana",
    "insuficiencia suprarrenal aguda",
    "insuficiencia renal aguda",
    "insuficiencia hepatica aguda",
    "falla hepatica fulminante",
    "intoxicacion",
    "sobredosis",
    "intoxicacion por monoxido",
    "anafilaxia",
    "shock anafilactico",
    "angioedema",
)

# --- Obstetrico -----------------------------------------------------------
OBSTETRICO = (
    "preeclampsia severa",
    "eclampsia",
    "sindrome hellp",
    "desprendimiento de placenta",
    "placenta previa sangrante",
    "rotura uterina",
    "sufrimiento fetal",
    "sufrimiento fetal agudo",
    "bradicardia fetal",
    "hemorragia posparto",
    "prolapso de cordon",
)

# --- Trauma ---------------------------------------------------------------
TRAUMA = (
    "politraumatismo",
    "traumatismo craneoencefalico grave",
    "tce grave",
    "fractura expuesta",
    "fractura de pelvis inestable",
    "lesion medular",
    "quemadura extensa",
    "quemadura de via aerea",
    "amputacion traumatica",
    "herida penetrante",
    "herida de arma de fuego",
)

# --- Oncologico y hematologico --------------------------------------------
ONCOHEMATOLOGICO = (
    "neoplasia maligna",
    "metastasis",
    "carcinomatosis",
    "sindrome de lisis tumoral",
    "neutropenia febril",
    "sindrome de vena cava superior",
    "coagulacion intravascular diseminada",
    "cid",
    "trombocitopenia severa",
    "anemia severa",
    "hemoglobina critica",
)

# --- Pediatrico y neonatal ------------------------------------------------
PEDIATRICO = (
    "apgar bajo",
    "distres respiratorio del recien nacido",
    "deshidratacion severa",
    "fiebre sin foco en lactante",
    "sospecha de maltrato",
)

# --- Senales explicitas del propio documento ------------------------------
# No describen un cuadro: son el emisor diciendo que corre.
SENALES_EXPLICITAS = (
    "urgente",
    "emergencia",
    "inmediata",
    "de inmediato",
    "critico",
    "grave",
    "riesgo vital",
    "compromiso vital",
    "estado critico",
    "codigo rojo",
    "requiere atencion inmediata",
    "correlacion clinica urgente",
)

GRUPOS = {
    "cardiovascular": CARDIOVASCULAR,
    "respiratorio": RESPIRATORIO,
    "neurologico": NEUROLOGICO,
    "infeccioso": INFECCIOSO,
    "abdominal": ABDOMINAL,
    "metabolico": METABOLICO,
    "obstetrico": OBSTETRICO,
    "trauma": TRAUMA,
    "oncohematologico": ONCOHEMATOLOGICO,
    "pediatrico": PEDIATRICO,
    "senales_explicitas": SENALES_EXPLICITAS,
}

# Se ordenan de mas largo a mas corto para que, al informar que disparo, se
# reporte "shock septico" y no "shock".
TERMINOS_CRITICOS: tuple[str, ...] = tuple(
    sorted({t for grupo in GRUPOS.values() for t in grupo}, key=len, reverse=True)
)


def grupo_de(termino: str) -> str:
    """A que sistema pertenece un termino. Sirve para explicar la decision."""
    for nombre, terminos in GRUPOS.items():
        if termino in terminos:
            return nombre
    return "desconocido"
