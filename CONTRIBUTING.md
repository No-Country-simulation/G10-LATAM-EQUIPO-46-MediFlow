# Cómo trabajamos — Equipo 46

Ocho personas sobre un mismo repositorio en cinco semanas. Estas reglas existen
para que nadie pise el trabajo de otro y para que el jueves haya algo que mostrar.

## Regla base

**Nadie commitea directo a `main`.** Toda tarea entra por una rama y un pull
request. `main` siempre tiene que estar en un estado que se pueda mostrar en la
Sprint Demo.

## Nombre de las ramas

```
<tipo>/<id-tarea>-<descripcion-corta>
```

- **`<tipo>`** — qué clase de cambio es:

  | Tipo    | Para qué                                                      |
  |---------|---------------------------------------------------------------|
  | `feat`  | funcionalidad nueva                                            |
  | `fix`   | corrección de un defecto                                       |
  | `docs`  | documentación, README, la página del plan                      |
  | `test`  | pruebas y corpus de evaluación                                 |
  | `infra` | OCI, buckets, despliegue, CI                                   |
  | `chore` | dependencias, configuración, limpieza                          |

- **`<id-tarea>`** — el identificador de la tarea en el
  [plan de ejecución](https://no-country-simulation.github.io/G10-LATAM-EQUIPO-46-MediFlow/):
  `1.3` es la tercera tarea de la semana 1. Así cualquiera sabe, con solo leer el
  nombre de la rama, a qué compromiso del cronograma corresponde.

- **`<descripcion-corta>`** — dos a cuatro palabras en minúscula separadas por
  guiones, sin acentos ni ñ (evita problemas entre Windows, macOS y Linux).

Ejemplos reales del cronograma:

```
docs/1.1-readme-inicial
infra/1.2-bucket-oci
feat/1.3-endpoint-triaje
feat/2.1-ingesta-pdf-imagen
feat/2.2-extraccion-por-tipo
test/2.3-corpus-sintetico
feat/3.1-grafo-decision
feat/3.2-score-confianza
feat/4.1-panel-auditoria
```

Para trabajo que no sale del cronograma (un bug encontrado sobre la marcha), se
omite el id: `fix/clasificador-devuelve-none`.

## Una rama, una tarea, un pull request

Una rama resuelve **una** tarea del cronograma. Si tu rama toca el agente, el
backend y el frontend a la vez, es señal de que son tres tareas y no una.

Regla práctica de aislamiento por módulo, para que dos ramas no choquen:

| Módulo              | Dueño habitual | Tareas del plan        |
|---------------------|----------------|------------------------|
| `agente/`           | Equipo A       | 1.3, 2.1, 2.2, 3.1, 3.2, 4.2, 4.3 |
| `backend/`          | Equipo B       | 3.3                    |
| `frontend/`         | Equipo B       | 4.1                    |
| `infrastructure/`   | Equipo B       | 1.2                    |
| `docs/`, `README.md`| Equipo B       | 1.1, 5.2, 5.3          |

Esto no es propiedad exclusiva: es el orden por defecto. Si necesitás tocar el
módulo de otro equipo, avisá en Discord antes, no después del pull request.

## Mensajes de commit

```
<tipo>: <qué hace el cambio, en presente>
```

Ejemplos: `feat: endpoint de triaje que clasifica y persiste en OCI`,
`fix: el clasificador ya no falla si falta la especialidad`,
`docs: pagina del plan de ejecucion en GitHub Pages`.

## Antes de abrir el pull request

1. Traé lo último de `main`: `git fetch origin && git rebase origin/main`.
2. Corré las pruebas del módulo que tocaste. Si no pasan, no abras el PR.
3. Revisá con `git diff --staged` que no se te cuele un `.env`, una credencial
   ni un dato real de paciente. **Nunca** subas el archivo `.env`.
4. En la descripción del PR, poné el id de la tarea y qué probaste.

## Revisión

Cada PR necesita la aprobación de **una** persona que no sea quien lo escribió.
El referente de cada equipo revisa lo de su módulo. No dejes un PR abierto más
de 24 horas sin revisar: en una hackathon de cinco semanas, un PR trabado es una
semana perdida.

## Lo que no se negocia

Las dos reglas del agente, copiadas del plan porque aplican a todo el código:

1. Ante cualquier duda, fallo del modelo o documento ilegible, el caso **escala
   a una persona**; nunca a aprobación automática.
2. Si un dato no está en el documento, el campo va en `null` y baja la
   confianza. Un código CIE-10 inventado es peor que un campo vacío.
