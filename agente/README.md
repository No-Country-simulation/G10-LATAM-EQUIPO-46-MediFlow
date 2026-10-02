# MediFlow Agent

Módulo de inteligencia artificial encargado del procesamiento y análisis de documentos clínicos para el proyecto MediFlow.

## Sprint 1

El primer sprint implementa el núcleo inicial del agente mediante el siguiente flujo secuencial:

```mermaid
flowchart TD
    A["Documento de texto"] --> B["Clasificacion"]
    B --> C["Extraccion"]
    C --> D["Validacion Pydantic"]
    D --> E["JSON estructurado"]
```

El grafo de decisión completo, con el enrutamiento a los cinco destinos, está en
el [README de la raíz](../README.md#grafo-de-decisión-del-agente). Este diagrama
muestra solo lo que el Sprint 1 implementa hoy.

## Tecnologías

* **Python** (Núcleo del desarrollo)
* **Gemini** (Modelo de Lenguaje / LLM)
* **LangChain / LangGraph** (Orquestación del Agente)
* **Pydantic** (Validación de estructuras de datos)
* **Pytest** (Pruebas unitarias y automatizadas)

## Categorías de Clasificación

Actualmente el clasificador reconoce estrictamente las siguientes categorías de documentos:

* receta_medica
* informe_estudio_diagnostico
* orden_procedimiento
* epicrisis
* certificado_medico
* desconocido

## Guía de Ejecución

Sigue estos pasos en la terminal para configurar y correr el agente localmente:

### 1. Crear y activar el entorno virtual
```bash
python -m venv .venv

# En PowerShell:
.\.venv\Scripts\Activate.ps1

# En CMD clásico de Windows:
.\.venv\Scripts\activate.bat
```

### 2. Instalar dependencias
```bash
pip install -r requirements.txt
```

### 3. Configurar variables de entorno
Crea un archivo llamado `.env` en la raíz de este módulo y define tus credenciales:
```env
GEMINI_API_KEY=TU_API_KEY
GEMINI_MODEL=
```

### 4. Ejecutar el agente
Para correr el script principal, debes indicarle a Python dónde encontrar el código fuente. Elige el comando según tu terminal:

* **En CMD (Símbolo del sistema):**
  ```cmd
  set PYTHONPATH=src&& python -m mediflow_agent.main examples/informe.txt
  ```
* **En PowerShell:**
  ```powershell
  $env:PYTHONPATH="src"
  python -m mediflow_agent.main examples/informe.txt
  ```

### 5. Levantar la API de triaje

```bash
uvicorn mediflow_agent.api.app:app --reload --app-dir src
```

Queda en `http://127.0.0.1:8000`. La documentación interactiva está en
`http://127.0.0.1:8000/docs`: desde ahí se puede pegar el JSON del enunciado y
ver la respuesta completa sin escribir una sola línea de código.

Dos endpoints:

| Método | Ruta | Para qué |
|--------|------|----------|
| `GET`  | `/salud` | Comprobar que el servicio está arriba. No llama al modelo ni gasta cuota. |
| `POST` | `/triaje` | Documento en **texto**. Cuerpo JSON. |
| `POST` | `/triaje/archivo` | Documento en **PDF o imagen**. Subida multipart. |

Los dos devuelven exactamente la misma respuesta: el formato de entrada no
cambia nada de lo que recibe el consumidor.

#### Qué formatos lee

| Entra | Cómo se lee |
|-------|-------------|
| Texto plano | Directo. |
| PDF nativo | Capa de texto del PDF. No gasta cuota del modelo. |
| PDF escaneado | Se rasterizan las páginas y las transcribe el modelo multimodal. |
| Imagen (foto, captura) | Se normaliza y la transcribe el modelo multimodal. |

Se usa Gemini multimodal en vez de un OCR tradicional, como sugiere el
enunciado. Eso evita depender de Tesseract, que en Windows es una instalación
externa aparte.

El caso peligroso está contemplado: un PDF con una **capa de texto pobre** —un
escaneo al que alguien le pasó un OCR malo— parece éxito y no lo es. Se detecta
por densidad de caracteres por página y se transcribe igual.

Prueba rápida con el caso del enunciado:

```bash
curl -X POST http://127.0.0.1:8000/triaje ^
  -H "Content-Type: application/json" ^
  -d "{\"documento_id\":\"DOC-CLIN-2026-8942\",\"tipo_archivo\":\"TEXTO\",\"documento_texto\":\"CONCLUSION: Cuadro compatible con Tromboembolismo Pulmonar Agudo.\",\"canal_origen\":\"Guardia_Emergencias\"}"
```

El formato exacto de entrada y salida está en
[`docs/CONTRATO.md`](../docs/CONTRATO.md).

#### Dónde se guardan los documentos

Mientras no exista el bucket de OCI (tarea 1.2), la persistencia va a disco con
**exactamente la misma estructura de prefijos** que tendrá el bucket:

```
.almacen/
  recibidos/              el documento tal como llego
  procesados/rutina/      confianza alta, ruta automatica
  procesados/urgentes/    hallazgo critico o prioridad urgente
  auditoria_humana/       confianza baja o documento ambiguo
```

Para usar OCI Object Storage, que es lo que exige el enunciado, se cambia una
variable. Hay dos formas:

**Con un Pre-Authenticated Request (PAR).** Es lo más rápido: no hace falta
usuario, ni clave de API, ni acceso a la consola. Solo el enlace.

```env
MEDIFLOW_ALMACEN=par
MEDIFLOW_OCI_PAR=https://objectstorage.<region>.oraclecloud.com/p/.../o/
```

> **Ese enlace es la credencial.** Quien lo tenga puede leer y escribir en el
> bucket. No va al repositorio ni a un canal público, y **caduca** en la fecha
> que se eligió al crearlo.

**Con credenciales IAM propias.** Es la vía normal y no caduca.

```env
MEDIFLOW_ALMACEN=oci
MEDIFLOW_BUCKET=nombre-del-bucket
```

más las variables `OCI_*` del `.env.example`.

Ni el endpoint ni el servicio se enteran de cuál de los tres almacenes está en
uso.

#### Verificar la conexión con OCI

```bash
python scripts/verificar_oci.py
```

Sube un objeto de prueba a los cuatro prefijos, lo vuelve a leer y compara el
contenido. Es la prueba de subida y descarga que pide la tarea 1.2. Si algo
falla, dice qué revisar en lugar de mostrar una traza.

#### Obtener las credenciales

En la consola de OCI: **perfil → My profile → API keys → Add API key**. Al
generarla, OCI muestra un bloque de configuración con el OCID del usuario, el
de la tenancy y el fingerprint, y descarga un archivo `.pem` con la clave
privada.

> **El `.pem` nunca va al repositorio.** El `.gitignore` lo bloquea, pero la
> red de seguridad no reemplaza mirar tu propio `git diff`.

Dos variables opcionales:

```env
MEDIFLOW_ALMACEN_LOCAL=.almacen
MEDIFLOW_BUCKET=mediflow-documentos-clinicos
MEDIFLOW_UMBRAL_CONFIANZA=0.70
```

### Ejecución de las Pruebas Unitarias

```bash
python -m pytest
```

`pytest.ini` ya pone `src/` en la ruta de importación, así que no hace falta
exportar `PYTHONPATH` a mano.

Las pruebas **no llaman a Gemini**: el modelo se sustituye por dobles. Corren
en menos de un segundo y no consumen cuota, que es la contramedida al riesgo
de quedarse sin llamadas gratuitas a mitad de la semana.

## Tiempo de respuesta

El requisito es resolver un documento en **10 segundos o menos**. No es una
meta de rendimiento: un informe de guardia que tarda un minuto en enrutarse no
sirve para nada.

Medido sobre un informe real, clasificando y extrayendo con la misma clave:

| Modelo | Clasificación | Extracción | Total |
|--------|---------------|------------|-------|
| `gemini-3.5-flash-lite` | 0,9 s | 1,2 s | **2,1 s** |
| `gemini-flash-lite-latest` | 1,0 s | 1,1 s | 2,1 s |
| `gemini-3.7-flash` | 79,0 s | 44,8 s | **123,8 s** |
| `gemini-3.8-flash` | — | — | cuota libre: **20 pedidos por día** |

Los modelos que razonan antes de responder tardan dos minutos. Por eso el
proyecto usa un modelo *lite* por defecto.

Además, **el clasificador y el extractor corren en paralelo**: el extractor
genérico no necesita saber el tipo de documento, así que las dos llamadas
salen a la vez. Eso baja el total a poco más de un segundo.

Medido de punta a punta sobre los tres escenarios del enunciado: **1,0 a
1,3 segundos** por documento.

> La velocidad está medida; **la exactitud todavía no**. Un modelo más chico
> puede acertar menos. Se mide con `scripts/evaluar_corpus.py` sobre los 30
> documentos etiquetados. Si no alcanza, hay que subir de modelo sin pasarse
> del presupuesto de tiempo, no resignar el tiempo.

## Verificacion de codigos CIE-10

Un modelo de lenguaje puede devolver un codigo con forma perfecta que no
existe: `I29.4` se ve tan creible como `I26.9`, y nadie lo nota leyendo la
respuesta. Por eso todo codigo sugerido se contrasta contra el catalogo local
de `src/mediflow_agent/datos/cie10_categorias.txt`, y si no existe se descarta.

**Que verifica y que no**, porque una verificacion que promete de mas es peor
que ninguna:

| | |
|---|---|
| Verifica la forma del codigo | si |
| Verifica que la categoria de tres caracteres exista | si |
| Verifica que el codigo sea el correcto para el diagnostico | **no** — eso lo decide una persona |
| Verifica el cuarto caracter contra la CIE-10 de la OMS | **no** — el catalogo no llega a esa granularidad |

**Procedencia del catalogo.** Son 1.907 categorias derivadas de ICD-10-CM,
publicado por CMS (Estados Unidos), que es de dominio publico. No se usa la
CIE-10 de la OMS porque esta bajo licencia Creative Commons
Attribution-NoDerivatives, que prohibe producir adaptaciones, y reformatearla a
este archivo seria una. Las categorias de tres caracteres son comunes a las dos
clasificaciones.

**Hueco conocido:** la version de la fuente es anterior a 2020 y no traia el
capitulo U. Las cuatro categorias U (COVID-19) se agregaron a mano y estan
marcadas como tales en el archivo. Conviene refrescar el catalogo desde una
version vigente de CMS antes de la entrega final.

## Reglas Importantes del Agente

Para garantizar la seguridad y fiabilidad clínica, el comportamiento del Agente está blindado bajo las siguientes reglas:

1. **Evidencia estricta:** Extraer solamente información explícitamente disponible en el documento.
2. **Uso de nulos:** Utilizar `null` (`None`) cuando un dato no esté disponible en el texto.
3. **Cero alucinaciones:** No inventar ni inferir información clínica que no esté firmada por el médico.
4. **Validación estricta:** Validar los tipos y límites de todas las estructuras mediante Pydantic (ej. confianza entre 0 y 1).
5. **Alcance de Codificación:** Tratar `suggested_icd10` únicamente como una sugerencia automatizada y jamás como un diagnóstico definitivo.

