# Organización de ramas

Quién sube qué, y a dónde.

Este documento es la referencia completa. Si tenés dudas sobre dónde va tu
trabajo, la respuesta está acá. Si no está, preguntá en Discord **antes** de
empujar, no después.

---

## Por qué trabajamos con ramas

Somos ocho personas sobre un repositorio en cinco semanas. Si todos empujamos a
`main`, pasan tres cosas, y las tres ya le pasaron a equipos de hackathon antes:

1. **`main` se rompe y nadie sabe quién.** El jueves, en la Sprint Demo, no hay
   nada que mostrar porque el último commit dejó el proyecto sin arrancar.
2. **Dos personas editan el mismo archivo y una pierde su trabajo.** Con ramas el
   conflicto aparece en el pull request, donde se resuelve con calma. Sin ramas
   aparece en la máquina de alguien, a las once de la noche.
3. **Nadie revisa nada.** En un proyecto donde una decisión mal enrutada significa
   que un informe de urgencia no se ve a tiempo, que un segundo par de ojos mire
   el código no es burocracia.

**Regla base: nadie commitea directo a `main`.** `main` siempre tiene que estar
en un estado que se pueda mostrar.

---

## Anatomía del nombre de una rama

```
tipo/id-tarea-descripcion-corta
 │      │         │
 │      │         └── dos a cuatro palabras, minúscula, con guiones,
 │      │             sin acentos ni ñ (evita problemas entre Windows,
 │      │             macOS y Linux)
 │      │
 │      └── el identificador de la tarea en el plan de ejecución.
 │          "1.3" es la tercera tarea de la semana 1. Así cualquiera
 │          sabe, leyendo el nombre, a qué compromiso responde.
 │
 └── qué clase de cambio es
```

Ejemplo: `feat/1.3-endpoint-triaje`

### Los seis tipos

| Tipo    | Para qué                                                   | Ejemplo |
|---------|------------------------------------------------------------|---------|
| `feat`  | funcionalidad nueva                                        | `feat/2.1-ingesta-pdf-imagen` |
| `fix`   | corrección de un defecto                                   | `fix/clasificador-sin-especialidad` |
| `docs`  | documentación, README, la página del plan                  | `docs/1.1-readme-inicial` |
| `test`  | pruebas y corpus de evaluación                             | `test/2.3-corpus-sintetico` |
| `infra` | OCI, buckets, despliegue, integración continua             | `infra/1.2-bucket-oci` |
| `chore` | dependencias, configuración, limpieza                      | `chore/fija-versiones-requirements` |

Para trabajo que no sale del cronograma (un defecto encontrado sobre la marcha),
se omite el id de tarea: `fix/clasificador-devuelve-none`.

---

## Qué va en cada rama: el mapa completo

Una rama resuelve **una** tarea del cronograma. Si tu rama toca el agente, el
backend y el frontend a la vez, es señal de que son tres tareas, no una.

### Semana 1 — Esqueleto vivo

| Tarea | Rama | Módulo que toca | Equipo |
|-------|------|-----------------|--------|
| 1.1 Documentación inicial | `docs/1.1-readme-y-contrato` | `README.md`, `docs/` | B |
| 1.2 Bucket de OCI | `infra/1.2-bucket-oci` | `infrastructure/` | B |
| 1.3 Endpoint de triaje | `feat/1.3-endpoint-triaje` | `backend/`, `agente/` | A |

### Semana 2 — Lee cualquier formato

| Tarea | Rama | Módulo que toca | Equipo |
|-------|------|-----------------|--------|
| 2.1 Ingesta PDF e imagen | `feat/2.1-ingesta-pdf-imagen` | `agente/src/.../ingestion/` | A |
| 2.2 Extracción por tipo | `feat/2.2-extraccion-por-tipo` | `agente/src/.../extraction/` | A |
| 2.3 Corpus sintético | `test/2.3-corpus-sintetico` | `agente/tests/`, `agente/examples/` | B |

### Semana 3 — El agente decide

| Tarea | Rama | Módulo que toca | Equipo |
|-------|------|-----------------|--------|
| 3.1 Grafo de decisión | `feat/3.1-grafo-decision` | `agente/src/.../routing/` | A |
| 3.2 Confianza y urgencia | `feat/3.2-score-confianza` | `agente/src/.../scoring/` | A |
| 3.3 Respuesta completa | `feat/3.3-contrato-respuesta` | `backend/` | B |

### Semana 4 — Producto y panel humano

| Tarea | Rama | Módulo que toca | Equipo |
|-------|------|-----------------|--------|
| 4.1 Interfaz y panel | `feat/4.1-panel-auditoria` | `frontend/` | B |
| 4.2 Evaluación y calibración | `test/4.2-evaluacion-corpus` | `agente/tests/` | A |
| 4.3 Diferencial elegido | `feat/4.3-<lo-que-se-elija>` | a definir | A |

### Semana 5 — Entrega

| Tarea | Rama | Módulo que toca | Equipo |
|-------|------|-----------------|--------|
| 5.1 Corrección e instalación limpia | `fix/5.1-instalacion-limpia` | transversal | A |
| 5.2 Video demo | `docs/5.2-video-demo` | `README.md`, `docs/` | B |
| 5.3 Entregables cargados | `docs/5.3-entregables-finales` | `README.md` | B |

---

## Reparto por módulo

La forma más simple de que dos ramas no choquen es que no toquen los mismos
archivos. Este es el orden por defecto:

| Módulo              | Dueño habitual |
|---------------------|----------------|
| `agente/`           | Equipo A       |
| `backend/`          | Equipo B       |
| `frontend/`         | Equipo B       |
| `infrastructure/`   | Equipo B       |
| `docs/`, `README.md`| Equipo B       |

**Esto no es propiedad exclusiva.** Es el orden por defecto. Si necesitás tocar
el módulo de otro equipo, avisá en Discord antes de empezar, no cuando abrís el
pull request.

### Los dos archivos que todos quieren tocar

- **`agente/requirements.txt`** — es el que más conflictos genera, porque
  cualquiera que instale una librería lo modifica. Si agregás una dependencia,
  agregá **solo esa línea**; no regeneres el archivo entero con `pip freeze`,
  porque eso reescribe las 50 líneas y convierte un conflicto trivial en uno
  imposible de leer.
- **`README.md`** de la raíz — es el entregable de documentación. Coordiná en
  Discord antes de editarlo.

---

## El flujo completo, paso a paso

### 1. Partí siempre de `main` actualizado

```bash
git checkout main
git pull origin main
git checkout -b feat/2.1-ingesta-pdf-imagen
```

Si partís de una rama vieja, arrastrás trabajo que no es tuyo al pull request y
la revisión se vuelve ilegible.

### 2. Commiteá seguido, con mensajes que digan qué hacen

```
tipo: que hace el cambio, en presente
```

```bash
git commit -m "feat: ingesta de PDF nativo normalizada a texto plano"
```

Un commit por idea. `cambios varios` no le sirve a nadie, y el enunciado pide
explícitamente *"commits bien documentados"*.

### 3. Antes de abrir el pull request

```bash
git fetch origin
git rebase origin/main       # traé lo último y poné tus commits encima
python -m pytest             # si no pasan, no abras el PR
git diff origin/main         # leé tu propio cambio antes que nadie
```

Revisá en ese último `diff` que no se te cuele:

- el archivo `.env` o cualquier clave, token o credencial de OCI;
- un archivo `.pem`;
- datos reales de un paciente, aunque te parezcan anonimizados.

### 4. Abrí el pull request

En la descripción, tres cosas:

- **Qué tarea cierra** — el id del cronograma.
- **Qué probaste** — el comando que corriste y qué dio.
- **Qué quedó afuera** — si dejaste algo sin terminar, decilo. Un PR honesto e
  incompleto es mucho mejor que uno que aparenta estar completo.

### 5. Revisión

Cada PR necesita la aprobación de **una** persona que no sea quien lo escribió.
El referente de cada equipo revisa lo de su módulo.

No dejes un PR abierto más de 24 horas sin revisar. En una hackathon de cinco
semanas, un PR trabado es una semana perdida.

### 6. Después del merge

```bash
git checkout main
git pull origin main
git branch -d feat/2.1-ingesta-pdf-imagen    # borrá la rama ya mergeada
```

Una rama mergeada que queda viva es una invitación a que alguien siga
commiteando ahí por error.

---

## Casos que van a pasar

### Dos ramas tocan el mismo archivo

Le toca resolverlo al que mergea **segundo**. Es el precio de llegar después, y
es justo: el primero ya no puede hacer nada. Resolvelo en tu rama con
`git rebase origin/main`, nunca en `main`.

### Necesito algo que está en la rama de otro y todavía no se mergeó

Dos opciones, en orden de preferencia:

1. **Pedile que mergee primero.** Casi siempre es lo correcto.
2. **Ramas apiladas.** Creás tu rama *desde* la de esa persona en vez de desde
   `main`, y en el PR aclarás el orden de merge. Sirve, pero si se apilan tres
   ramas nadie entiende nada. Máximo dos.

### Encontré un defecto que no es de mi tarea

No lo arregles dentro de tu rama: mezcla dos cosas en un PR y hace la revisión
más difícil. Abrí una rama `fix/` aparte, corta, y avisá en Discord a quien
escribió ese código. Si no lo vas a arreglar ahora, dejá el aviso escrito en
Discord igual — un defecto detectado y no anotado es un defecto perdido.

### Mi rama quedó muy atrás de `main`

```bash
git fetch origin
git rebase origin/main
```

Hacelo seguido, no una sola vez al final. Una rama que vivió una semana sin
actualizarse genera conflictos en cada archivo que otro tocó.

---

## Lo que nunca va a ninguna rama

- **El archivo `.env`.** Cada quien crea el suyo desde `agente/.env.example`.
- **Claves de API, tokens, claves privadas de OCI, archivos `.pem`.**
- **Documentos clínicos reales**, aunque estén anonimizados. Solo los ejemplos
  ficticios de `agente/examples/`.
- **La carpeta `.venv/`** ni `__pycache__/`.

El `.gitignore` de la raíz cubre todo esto, pero el `.gitignore` es una red de
seguridad, no un sustituto de mirar tu propio `git diff`.

---

## Ramas abiertas ahora

| Rama | Qué trae | Estado |
|------|----------|--------|
| `docs/plan-github-pages` | Página del plan en GitHub Pages, `CONTRIBUTING.md`, este documento | por mergear primero |
| `docs/1.1-readme-y-contrato` | README completo, `docs/CONTRATO.md`, `.gitignore` de la raíz | por mergear después |

Mantené esta tabla al día cuando abras o cierres una rama.
