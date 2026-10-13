# Guía de pruebas del equipo

Qué probar antes de la entrega, en qué orden y qué tiene que pasar en cada
caso. Está pensada para que cualquiera del equipo la corra en su máquina sin
saber cómo está hecho el sistema por dentro.

**Si algo no da lo esperado, anotalo en Discord con el comando que corriste y
lo que salió.** Un "no me anda" sin la salida no se puede diagnosticar.

---

## Paso 0 · Preparar el entorno (una vez)

```powershell
cd C:\GitHub\G10-LATAM-EQUIPO-46-MediFlow\agente
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
notepad .env
```

En el `.env`, completá como mínimo:

```env
GEMINI_API_KEY=tu-clave
GEMINI_MODEL=gemini-3.5-flash-lite
```

La clave se saca gratis en [aistudio.google.com](https://aistudio.google.com) →
*Get API key*.

> **No actives el entorno** con `Activate.ps1`: en muchas máquinas la política
> de ejecución de Windows lo bloquea. Llamá siempre a
> `.venv\Scripts\python.exe` por ruta y te ahorrás el problema.

> **Si la primera ejecución falla con "una directiva de Control de
> aplicaciones bloqueó este archivo"**, no es el proyecto: es Smart App
> Control de Windows evaluando una librería recién instalada. Esperá un minuto
> y reintentá.

---

## Prueba 1 · Las pruebas automáticas

**Qué valida:** que el entorno quedó bien y que nada se rompió.
**Cuesta:** nada. No llama a Gemini.
**Tarda:** 3 segundos.

```powershell
.venv\Scripts\python.exe -m pytest -q
```

**Esperado:** `318 passed`.

Si falla algo acá, parar. El resto de las pruebas no tiene sentido.

---

## Prueba 2 · La detección de urgencia, sin gastar cuota

**Qué valida:** el peor fallo posible del sistema — que un hallazgo urgente se
clasifique como rutina.
**Cuesta:** nada. La vía por lista es comparación de texto.

```powershell
.venv\Scripts\python.exe scripts\evaluar_urgencia.py
```

**Esperado:** 25/25 en los urgentes nombrados, 20/20 en rutina, y 18/20 en
negaciones. Los urgentes "sin término" dan 0/30 **y está bien**: son los que
solo ve el modelo.

Para medir las dos vías, que sí consume cuota y tarda unos 7 minutos:

```powershell
.venv\Scripts\python.exe scripts\evaluar_urgencia.py --modelo
```

**Esperado:** `URGENTES QUE SE ESCAPAN: ninguno`.

### Cómo ampliar el banco

Es el aporte más útil que puede hacer alguien del equipo. Abrí
`agente\corpus\urgencias.json` y agregá frases:

```json
{ "texto": "Trazado con QRS ancho y frecuencia de 210 por minuto.",
  "urgente": true, "grupo": "sin_termino" }
```

Los grupos son `con_termino`, `sin_termino`, `rutina` y `trampa`. **El valioso
es `sin_termino`**: cuadros críticos descritos sin nombrar la patología. Cada
frase que se escape de las dos vías es un hallazgo real.

---

## Prueba 3 · El agente por consola

**Qué valida:** que la clave de Gemini funciona.
**Cuesta:** 2 llamadas.

```powershell
$env:PYTHONPATH="src"
.venv\Scripts\python.exe -m mediflow_agent.main examples\informe.txt
```

**Esperado:** `Tipo detectado: informe_estudio_diagnostico` y un JSON con
`"suggested_icd10": "I26.9"`.

| Si sale | Es porque |
|---------|-----------|
| `No se encontró GEMINI_API_KEY` | El `.env` no quedó bien |
| `404 ... no longer available` | El modelo del `.env` no existe para tu clave. Corré `scripts\listar_modelos.py` |
| `429 RESOURCE_EXHAUSTED` | Cuota agotada. Esperá un minuto |

---

## Prueba 4 · La página web

**Qué valida:** lo que se va a mostrar en la demo.

```powershell
.venv\Scripts\python.exe -m uvicorn mediflow_agent.api.app:app --app-dir src
```

Abrí **http://127.0.0.1:8000** en el navegador.

### 4.1 — Los tres escenarios del enunciado

En la pantalla de bienvenida hay tres ejemplos cargables de un clic:

| Ejemplo | Tiene que dar |
|---------|---------------|
| **Urgencia** (tromboembolismo) | `Urgente` → Cola de Emergencia Médica, con alerta de guardia y CIE-10 `I26.9` |
| **Rutina** (orden de laboratorio) | `Rutina` → Auditoría de Autorizaciones |
| **Ambigüedad** (receta ilegible) | → Cola de Revisión Humana, con la dosis **no inventada** |

Mirá la **justificación** de cada uno: es lo que demuestra que el agente
razona y no solo extrae.

### 4.2 — El panel de auditoría

Después del tercer ejemplo, el caso aparece en la bandeja **Revisión** de la
derecha. Hacé clic.

1. Se abre el documento original junto a los datos extraídos.
2. Los campos vacíos están resaltados: son los que faltan.
3. Completá **Matrícula** con `41883` y **Medicamentos** con
   `Metformina 850 mg cada 12 horas; Glibenclamida 5 mg`.
4. Poné tu nombre en **Auditor** y apretá **Aprobar y re-enrutar**.

**Esperado:** el documento pasa a **Farmacia Hospitalaria**, la bandeja de
revisión queda vacía y la justificación registra quién aprobó.

**Probá también lo contrario:** aprobar sin completar nada. El agente tiene
que devolverlo a revisión, porque sigue faltando la matrícula. El auditor
corrige el contenido; **el destino lo decide el agente**.

### 4.3 — PDF e imagen

Subí cualquier PDF o una foto de un papel con **Subir PDF o imagen**.

- Un PDF con texto se lee directo, **sin gastar cuota del modelo multimodal**.
- Un escaneo o una foto se transcriben con Gemini.
- Si algo queda ilegible, el caso va a revisión humana.

---

## Prueba 5 · La evaluación del corpus

**Qué valida:** cuánto acierta el agente sobre 30 documentos etiquetados.
**Cuesta:** 60 llamadas. **Tarda:** unos 5 minutos por el límite de ritmo.

```powershell
.venv\Scripts\python.exe scripts\evaluar_corpus.py
```

Primero, sin gastar nada, para ver que la cañería corre:

```powershell
.venv\Scripts\python.exe scripts\evaluar_corpus.py --simulado
```

**Qué mirar, en orden:**

1. **Falsos negativos de urgencia.** Si no dice "Ninguno", eso es lo primero.
2. **Campos inventados.** El proyecto prohíbe inventar: cualquier valor acá es
   un defecto, no una imprecisión.
3. Exactitud de clasificación y cobertura de campos.

---

## Prueba 6 · OCI Object Storage

**Qué valida:** el requisito obligatorio del enunciado.

En el `.env`:

```env
MEDIFLOW_ALMACEN=par
MEDIFLOW_OCI_PAR=<el enlace que circuló por el canal privado>
MEDIFLOW_BUCKET=bucket-hackaton-01
```

```powershell
.venv\Scripts\python.exe scripts\verificar_oci.py
```

**Esperado:** cuatro líneas `ok`, una por prefijo.

> **El PAR es una credencial.** Quien tenga ese enlace puede leer y escribir en
> el bucket. No va al repositorio ni a un canal público.

> Deja cuatro objetos de prueba. OCI **no permite borrar a través de un PAR**,
> así que hay que eliminarlos desde la consola.

---

## Prueba 7 · El despliegue público

La página está en **http://159.112.180.217** (OCI Compute Always Free).
Probá ahí los mismos puntos de la Prueba 4: no hace falta instalar nada.

Instrucciones completas de cómo se montó en
[`infrastructure/README.md`](../infrastructure/README.md).

```powershell
curl http://159.112.180.217/salud
```

**Esperado:** `{"status":"ok","servicio":"mediflow-triaje"}`.

---

## Lo que conviene saber antes de la demo

**La cuota gratuita de Gemini es 15 pedidos por minuto.** Cada documento usa
2 o 3 llamadas. Si procesás varios seguidos en vivo, vas a ver esperas de
40 segundos. Durante la demo, **procesá uno, mostralo, y recién después el
siguiente**.

**Grabá el video con la cuota fresca**, no después de una tarde de pruebas.

**Probá el flujo completo en la máquina con la que vayas a presentar**, con un
día de anticipación. Es donde aparecen los problemas de instalación.

---

## Prueba 8 · Las reglas configurables desde la pantalla

**Qué valida:** el diferencial del enunciado — que un gestor hospitalario
cambie el triaje sin tocar el código fuente. **Es la prueba que conviene
mostrar en vivo**, porque se ve entera en la pantalla.

Antes de levantar la aplicación, en el `.env`:

```env
MEDIFLOW_ADMIN_CLAVE=lo-que-quieras-mientras-sea-largo
```

> Si además tenés `MEDIFLOW_UMBRAL_CONFIANZA` en el `.env`, **quitala**. Gana
> sobre el archivo y dejaría el umbral bloqueado. El panel te lo avisa, pero
> es una pregunta menos del jurado.

Arrancá y apretá **Reglas de triaje**, arriba a la derecha.

### 8.1 — Sin la clave no se guarda

Dejá el campo *Clave de administración* vacío y apretá **Guardar reglas**.

**Esperado:** `Clave incorrecta.` y nada cambia.

### 8.2 — Cambiar un destino

Poné la clave. En **Receta médica** elegí *Auditoría de Autorizaciones* y
guardá. Cerrá el panel y triá una receta.

**Esperado:** va a Auditoría de Autorizaciones en vez de Farmacia, **sin
reiniciar nada**.

### 8.3 — Quitar una ruta

Volvé a abrir el panel y en **Receta médica** elegí
*— sin ruta: va a revisión humana —*. Guardá y triá otra receta.

**Esperado:** va a **Cola de Revisión Humana**, con la justificación diciendo
que ese tipo no tiene ruta asignada. Es la forma que tiene el gestor de
desactivar una ruta automática hacia un destino que todavía no está listo
para recibir documentos sin supervisión.

Después dejá todo como estaba.

### 8.4 — Sin clave en el servidor, solo lectura

Sacá `MEDIFLOW_ADMIN_CLAVE` del `.env`, reiniciá y abrí el panel.

**Esperado:** los campos aparecen apagados, no hay botón de guardar, y arriba
dice *"Solo lectura: no hay clave de administración en el servidor"*.

### 8.5 — Lo que el panel no deja hacer

Con la clave puesta, probá un umbral de `1.5`.

**Esperado:** lo rechaza. Se valida **antes** de escribir, así que el archivo
nunca queda en un estado que el agente no pueda leer.
---

## Prueba 9 · La alerta de guardia

**Qué valida:** que la notificación se entrega de verdad, no solo se escribe
en el JSON.

Hace falta un webhook. El más rápido es uno de Discord: en cualquier canal,
*Editar canal → Integraciones → Webhooks → Nuevo webhook → Copiar URL*.

En el `.env`:

```env
MEDIFLOW_ALERTA_WEBHOOK=<la URL copiada>/slack
```

> El `/slack` del final es necesario para que Discord entienda el formato.
> **Esa URL es una credencial**: quien la tenga puede publicar en el canal. No
> la subas al repositorio ni la pegues en un canal público.

Reiniciá y cargá el ejemplo de **Urgencia**.

**Esperado:** el mensaje aparece en el canal en menos de dos segundos.

**Probá también que un canal caído no rompe nada:** poné una URL inventada
(`https://no-existe.invalido/hook`) y volvé a triar. El triaje tiene que
completarse igual, con el documento guardado en el bucket, y el fallo queda
solo en los logs:

```powershell
docker compose -f infrastructure/docker-compose.yml logs --tail 20
```
