# Cómo trabajamos — Equipo 46

Ocho personas sobre un mismo repositorio en cinco semanas. Estas reglas existen
para que nadie pise el trabajo de otro y para que el jueves haya algo que mostrar.

## Las tres reglas cortas

1. **Nadie commitea directo a `main`.** Toda tarea entra por una rama y un pull
   request. `main` siempre tiene que estar en un estado que se pueda mostrar en
   la Sprint Demo.
2. **Una rama, una tarea, un pull request.** El nombre de la rama lleva el id de
   la tarea del cronograma: `feat/2.1-ingesta-pdf-imagen`.
3. **Cada PR lo aprueba alguien que no lo escribió.**

## Dónde está cada cosa

| Necesito saber... | Está en |
|-------------------|---------|
| Cómo nombro mi rama, y qué archivos me toca tocar | **[docs/RAMAS.md](docs/RAMAS.md)** |
| Qué forma exacta tiene el JSON que devuelve la API | **[docs/CONTRATO.md](docs/CONTRATO.md)** |
| Qué hay que entregar y cuándo | **[docs/index.html](docs/index.html)** |
| Cómo corro el agente en mi máquina | **[agente/README.md](agente/README.md)** |

**[docs/RAMAS.md](docs/RAMAS.md) es la referencia completa de organización:**
el mapa de las quince tareas del cronograma con su rama y su módulo, el flujo
paso a paso con los comandos, y qué hacer cuando dos ramas chocan.

## Mensajes de commit

```
tipo: que hace el cambio, en presente
```

Ejemplos: `feat: endpoint de triaje que clasifica y persiste en OCI`,
`fix: el clasificador ya no falla si falta la especialidad`.

El enunciado pide explícitamente *"commits bien documentados"*. Un commit por
idea; `cambios varios` no le sirve a nadie.

## Antes de abrir el pull request

1. Traé lo último de `main`: `git fetch origin && git rebase origin/main`.
2. Corré las pruebas del módulo que tocaste. Si no pasan, no abras el PR.
3. Leé tu propio cambio con `git diff origin/main` y verificá que no se te cuele
   un `.env`, una credencial de OCI, un `.pem` ni un dato real de paciente.
4. En la descripción del PR: qué tarea cierra, qué probaste, qué quedó afuera.

## Lo que no se negocia

Las dos reglas del agente, copiadas del plan porque aplican a todo el código:

1. Ante cualquier duda, fallo del modelo o documento ilegible, el caso **escala
   a una persona**; nunca a aprobación automática.
2. Si un dato no está en el documento, el campo va en `null` y baja la
   confianza. Un código CIE-10 inventado es peor que un campo vacío.
