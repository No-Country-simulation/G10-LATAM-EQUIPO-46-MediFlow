# Guion del video demo

Para grabar en una sola tarde, sin improvisar y sin quedarse sin cuota.

**Duración objetivo: 5 a 6 minutos.** El enunciado no fija un largo; exige
cubrir **tres escenarios** (rutina, urgencia y ambigüedad derivada a revisión
humana). Todo lo demás suma, pero eso es lo obligatorio.

---

## Antes de grabar

### 1. Dos arreglos en la máquina (cinco minutos)

**El umbral aparece bloqueado.** El `.env` del servidor todavía tiene
`MEDIFLOW_UMBRAL_CONFIANZA`, que gana sobre el archivo, así que en el panel de
reglas ese campo sale apagado con un cartel de "fijado por variable de
entorno". No está roto, pero en cámara se lee como una limitación.

```bash
ssh -i C:\GitHub\claves\ssh-key-2026-10-12.key ubuntu@159.112.180.217
cd ~/G10-LATAM-EQUIPO-46-MediFlow
nano agente/.env
```

Poné un `#` delante de `MEDIFLOW_UMBRAL_CONFIANZA=0.70`. Guardás con `Ctrl+O`,
Enter, `Ctrl+X`. Después:

```bash
docker compose -f infrastructure/docker-compose.yml restart
curl -s localhost/configuracion | grep -o '"bloqueados_por_entorno":\[[^]]*\]'
```

Tiene que decir `"bloqueados_por_entorno":[]`.

### 2. Reservá cuota

**La cuota gratuita de Gemini es 15 pedidos por minuto y cada documento usa 2
o 3.** Esta es la causa número uno de que una grabación salga mal: se procesan
cuatro documentos seguidos, el quinto espera cuarenta segundos y queda en el
video.

- **No proceses nada en la hora previa** a grabar.
- **Grabá por tramos, no de una sola toma.** Si un tramo sale mal, se repite
  solo ese. Una toma única de seis minutos obliga a rehacer todo y a gastar
  cuota de nuevo.
- Entre escenario y escenario, **esperá a que la tarjeta termine** antes de
  cargar el siguiente.

### 3. Lo que NUNCA debe entrar en cámara

El video va a los examinadores y puede quedar publicado.

- **El archivo `.env`**, en cualquier editor o terminal. Tiene la clave de
  Gemini, la URL del PAR y la clave de administración.
- **La consola de OCI con el PAR a la vista** (Bucket → Pre-Authenticated
  Requests). La URL completa es una credencial.
- **El campo de clave del panel de reglas mientras tipeás.** Es de tipo
  contraseña y se ve con puntos, pero no la dictes en voz alta.
- Pestañas del navegador con otras cosas, y la barra de marcadores.

### 4. Preparar la pantalla

- Ventana del navegador **nueva y limpia**, sin marcadores (`Ctrl+Shift+B`).
- Zoom al **110 % o 125 %** (`Ctrl` y `+`). El texto por defecto no se lee en
  un video comprimido.
- Pantalla a **1920x1080**. Si tu monitor es más grande, achicá la resolución:
  grabar en 4K y que lo vean en una ventana chica hace ilegible todo.
- Cerrá Discord, correo y cualquier cosa que tire notificaciones.

### 5. Con qué grabar

**Recomendado: OBS Studio** (gratis, obsproject.com). Cinco minutos de
instalación. En *Sources* agregás **Display Capture** y listo. Importa porque
captura **los diálogos de archivo**, y vos vas a abrir uno para subir un PDF.

**Alternativa sin instalar nada: Xbox Game Bar** (`Win+G`, grabás con
`Win+Alt+R`). Funciona, pero **no captura el diálogo de subir archivo** ni el
Explorador de Windows: si vas a mostrar esa parte, usá OBS.

Grabá con micrófono. Un video narrado explica el razonamiento del agente; uno
mudo obliga al jurado a adivinarlo.

---

## El guion, tramo por tramo

Los textos en *cursiva* son lo que decís. No hace falta leerlos literal.

### Tramo 1 — Qué es y dónde está (0:00 – 0:30)

En pantalla: la página abierta en **http://159.112.180.217**, con la URL
visible en la barra de direcciones.

> *MediFlow es un agente autónomo de triaje de documentos clínicos. Está
> desplegado en una máquina Always Free de Oracle Cloud y lo que ven es la
> aplicación corriendo, no una maqueta: la dirección es pública y cualquiera
> puede abrirla.*
>
> *El problema que resuelve: un hospital recibe miles de documentos en papel,
> PDF y fotos, y alguien los lee a mano para cargarlos en el sistema. Eso es
> lento, caro, y retrasa la atención de un paciente urgente.*

Mostrá el indicador **servicio activo** arriba a la derecha.

### Tramo 2 — Escenario 1, flujo estándar (0:30 – 1:20)

Clic en el ejemplo **Rutina** y después en **Triar**.

> *Primer escenario: una orden de estudios de laboratorio, ambulatoria y
> completa. El agente la clasifica, extrae los datos y la enruta sola.*

Cuando aparezca la tarjeta, señalá con el mouse:

- **Tipo**: Orden de procedimiento
- **Confianza**: el porcentaje
- **Destino**: Auditoría de Autorizaciones
- La línea `guardado bucket-hackaton-01/procesados/rutina/...`

> *Sin intervención humana. Y abajo está la ruta del objeto en OCI Object
> Storage: el documento y la decisión quedan guardados, segregados por estado.*

### Tramo 3 — Escenario 2, urgencia (1:20 – 2:20)

Clic en **Urgencia**, después en **Triar**.

> *Segundo escenario: un informe de tomografía con un hallazgo crítico. Este
> es el caso donde el sistema no se puede equivocar.*

Señalá, en este orden:

1. La etiqueta **URGENTE** en rojo
2. **Destino: Cola de Emergencia Médica**
3. **CIE-10: I26.9**
4. El recuadro rojo de **ALERTA_GUARDIA_MEDICA**
5. La **justificación**

> *Lo importante es la justificación: el agente dice por qué decidió lo que
> decidió, y nombra los términos que lo llevaron a eso. No es una caja negra.*
>
> *La detección de urgencia corre antes que cualquier otra regla y gana sobre
> todas. Un hallazgo crítico va a emergencia aunque el tipo de documento
> indique otra ruta. Y funciona por dos vías en paralelo —una lista de 185
> términos clínicos y el modelo— combinadas con un O lógico: alcanza con que
> una diga urgente.*

Si tenés el webhook configurado, mostrá el mensaje llegando al canal.

### Tramo 4 — Escenario 3, ambigüedad y auditoría humana (2:20 – 3:50)

**Es el tramo más fuerte. No lo apures.**

Clic en **Ambigüedad**, después en **Triar**.

> *Tercer escenario: una receta manuscrita donde la transcripción no pudo leer
> la dosis.*

Señalá:

- **Destino: Cola de Revisión Humana**
- El campo de **medicamentos**, donde Metformina aparece **sin dosis**

> *Acá está la decisión de diseño más importante del proyecto. El agente
> podría haber completado la dosis: Metformina se receta casi siempre en 850
> u 1000 miligramos, y el modelo lo sabe. No lo hizo. Un dato inventado en una
> receta es peor que un dato faltante, porque el faltante se ve y el inventado
> no.*

Ahora el panel. Clic en el caso en la bandeja **Revisión**.

> *El documento original a la izquierda, los datos extraídos a la derecha, y
> los campos vacíos resaltados: son los que el auditor vino a completar.*

Completá:

- **Matrícula**: `41883`
- **Medicamentos**: `Metformina 850 mg cada 12 horas; Glibenclamida 5 mg`
- **Auditor**: tu nombre

Clic en **Aprobar y re-enrutar**.

> *Y acá está lo que hace que esto sea un agente y no un formulario: al
> aprobar, el agente vuelve a decidir con los datos corregidos. El auditor
> corrige el contenido; el destino lo sigue eligiendo el grafo. Ahora que la
> receta tiene matrícula y dosis, sigue sola a Farmacia Hospitalaria.*

### Tramo 5 — El diferencial configurable (3:50 – 4:40)

Clic en **Reglas de triaje**, arriba a la derecha.

> *El enunciado pide, como diferencial, que un gestor hospitalario pueda
> cambiar las reglas sin tocar el código. Esto es eso.*

Mostrá el umbral y los canales. Después, en **Receta médica**, elegí
**— sin ruta: va a revisión humana —**, poné la clave y **Guardar reglas**.

Cerrá el panel y triá de nuevo el ejemplo **Ambigüedad**.

> *Sin reiniciar nada, las recetas ya no tienen ruta automática y escalan a
> revisión humana. Así es como un hospital desactiva una ruta hacia un
> departamento que todavía no está listo para recibir documentos sin
> supervisión.*

**Volvé a dejarlo en Farmacia Hospitalaria antes de seguir.**

### Tramo 6 — OCI y cierre (4:40 – 5:30)

Cambiá a la pestaña de la consola de OCI, en el bucket.

> *Todo lo que vieron quedó acá: el requisito obligatorio del enunciado.*

Mostrá los prefijos `recibidos/`, `procesados/rutina/`,
`procesados/urgentes/`, `auditoria_humana/`, y abrí el JSON del caso urgente.

> *Cada objeto es la respuesta completa del contrato, con la clasificación,
> los datos extraídos, la decisión y su justificación. La decisión queda
> auditable.*

Volvé a la página.

> *El grafo tiene nueve pasos y está documentado en el README. El proyecto
> tiene 318 pruebas automáticas, ninguna de las cuales llama al modelo, y una
> evaluación sobre un corpus de 30 documentos etiquetados: 29 de 30 en
> clasificación y cero falsos negativos de urgencia en tres corridas
> independientes.*
>
> *El enlace es público y el repositorio está en GitHub. Gracias.*

---

## Si algo sale mal mientras grabás

| Síntoma | Qué pasó | Qué hacer |
|---|---|---|
| La respuesta tarda 40 segundos | Cuota: 15 pedidos por minuto | Cortá, esperá dos minutos, regrabá ese tramo |
| `429 RESOURCE_EXHAUSTED` | Cuota agotada | Esperá. No hay atajo |
| La página no carga | Contenedor caído | `docker compose -f infrastructure/docker-compose.yml ps` |
| Un campo sale distinto a este guion | El modelo no es determinista | Es esperable. Narrá lo que se ve, no lo que dice el papel |

Ese último punto importa: **el mismo documento puede dar resultados algo
distintos entre corridas**. No es un defecto. Si un campo sale diferente,
seguí con lo que hay; no vale la pena quemar cuota buscando la toma perfecta.

---

## Checklist final antes de subir

- [ ] Se ve la URL pública en la barra de direcciones
- [ ] Están los tres escenarios obligatorios
- [ ] En ningún cuadro aparece el `.env`, el PAR ni la clave de Gemini
- [ ] Se escucha la narración
- [ ] El texto se lee a tamaño normal
- [ ] Las reglas quedaron como estaban (receta a Farmacia)
