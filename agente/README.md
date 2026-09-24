# MediFlow Agent

Módulo de inteligencia artificial encargado del procesamiento y análisis de documentos clínicos para el proyecto MediFlow.

## Sprint 1

El primer sprint implementa el núcleo inicial del agente mediante el siguiente flujo secuencial:

```mermaid
graph TD
    Documento de texto
          ↓
      Clasificación
          ↓
      Extracción
          ↓
    Validación Pydantic
          ↓
    JSON estructurado
```

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
* picrisis
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
GEMINI_MODEL=gemini-2.5-flash
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

### Ejecución de las Pruebas Unitarias
Para correr la suite de pruebas automatizadas con `pytest`:

* **En CMD:**
  ```cmd
  set PYTHONPATH=src&& pytest
  ```
* **En PowerShell o usando el atajo nativo de Python:**
  ```bash
  python -m pytest
  ```

## Reglas Importantes del Agente

Para garantizar la seguridad y fiabilidad clínica, el comportamiento del Agente está blindado bajo las siguientes reglas:

1. **Evidencia estricta:** Extraer solamente información explícitamente disponible en el documento.
2. **Uso de nulos:** Utilizar `null` (`None`) cuando un dato no esté disponible en el texto.
3. **Cero alucinaciones:** No inventar ni inferir información clínica que no esté firmada por el médico.
4. **Validación estricta:** Validar los tipos y límites de todas las estructuras mediante Pydantic (ej. confianza entre 0 y 1).
5. **Alcance de Codificación:** Tratar `suggested_icd10` únicamente como una sugerencia automatizada y jamás como un diagnóstico definitivo.

## 🔬 Datos de Prueba

Los documentos incluidos en la carpeta `examples/` contienen exclusivamente **datos ficticios** destinados al desarrollo y pruebas del prototipo. No contienen información real de pacientes ni deben usarse con fines comerciales.