# Presentación de 5 minutos

Sin preguntas al final: todo lo que el jurado va a saber tiene que estar
adentro de estos cinco minutos.

Cinco minutos son unas **700 palabras habladas**. Este guion tiene 690. No
sobra lugar para nada que no gane algo.

---

## Lo que hay que decidir antes

### No hagas demo en vivo

La cuota gratuita de Gemini son **15 pedidos por minuto**. Si el jurado tiene
la sala conectada a una red lenta, o alguien del equipo probó la aplicación
diez minutos antes, vas a quedar mirando una pantalla que carga. En cinco
minutos sin margen, eso te come la presentación.

**Usá tres capturas fijas** o, si lo permiten, treinta segundos del video ya
grabado. La aplicación está en línea y el enlace queda en la última
diapositiva: el que quiera probarla, la prueba.

### La idea que tienen que recordar

Si de los cinco minutos se llevan una sola frase, que sea esta:

> **El agente podía completar la dosis, y no lo hizo.**

Todo lo demás —el grafo, los destinos, el despliegue— lo tiene cualquier
proyecto de la cohorte. Esa decisión es lo que distingue un sistema clínico de
una demo de IA, y es la que vale la pena repetir dos veces.

---

## El guion

Los tiempos son acumulativos. Si a los 3:20 no empezaste el bloque de
confianza, salteá el de diferenciales.

### 0:00 – 0:35 · Abrir con el problema, no con la tecnología

> Un hospital recibe todos los días miles de documentos: recetas escritas a
> mano, informes de tomografía, órdenes de estudios. Alguien los lee uno por
> uno y los carga a mano en el sistema.
>
> Eso es lento y caro. Pero el problema de verdad es otro: mientras un informe
> con un hallazgo crítico espera su turno en una pila, hay un paciente
> esperando.

Pausa de un segundo.

> MediFlow es un agente autónomo que lee esos documentos, los clasifica,
> extrae los datos clínicos y los enruta al departamento que corresponde. Los
> casos estándar pasan solos. Los dudosos van a una persona.

### 0:35 – 1:05 · Qué es, en concreto

> Está funcionando ahora, en una dirección pública, sobre una máquina Always
> Free de Oracle Cloud. No es un notebook ni una maqueta: es una aplicación
> desplegada que cualquiera puede abrir.
>
> Recibe PDFs, fotos de recetas manuscritas y texto. Un modelo multimodal
> transcribe lo que no es texto, y un grafo de decisión de nueve pasos resuelve
> a dónde va cada documento.

### 1:05 – 2:45 · Los tres escenarios

Este es el cuerpo. Una captura por escenario.

**Rutina.**

> Una orden de laboratorio, completa y legible. El agente la clasifica, extrae
> paciente, médico, matrícula y estudios, y la manda sola a Auditoría de
> Autorizaciones. Nadie la toca.

**Urgencia.**

> Un informe de tomografía compatible con tromboembolismo pulmonar. El agente
> lo marca urgente, lo manda a la Cola de Emergencia Médica, sugiere el código
> CIE-10 y dispara una alerta a la guardia.
>
> Y explica por qué: nombra los términos clínicos que lo llevaron a esa
> conclusión. La decisión queda auditable.

**Ambigüedad.** Bajá el ritmo acá.

> Una receta manuscrita donde la transcripción no pudo leer la dosis. Miren el
> campo de medicamentos: Metformina, sin dosis.
>
> El agente podía completarla. La Metformina se receta casi siempre en 850 o
> en 1000 miligramos, y el modelo lo sabe. No lo hizo.
>
> Un dato inventado en una receta es peor que un dato faltante, porque el
> faltante se ve y el inventado no.

Pausa.

> El caso va a un auditor humano, que completa lo que falta y aprueba. Y acá
> está la diferencia entre un agente y un formulario: al aprobar, **el agente
> vuelve a decidir**. El auditor corrige el contenido; el destino lo sigue
> eligiendo el grafo.

### 2:45 – 3:40 · Por qué se le puede creer

> El peor fallo posible de este sistema es que un hallazgo urgente se trate
> como rutina. Por eso la detección de urgencia corre antes que cualquier otra
> regla y gana sobre todas: un hallazgo crítico va a emergencia aunque el tipo
> de documento indique otra ruta.
>
> Y no depende de una sola vía. Funciona con una lista de 185 términos
> clínicos y con el modelo, en paralelo, combinados con un O lógico: alcanza
> con que una de las dos diga urgente.

> Lo medimos. 318 pruebas automáticas, ninguna de las cuales llama al modelo.
> Y una evaluación sobre 30 documentos etiquetados: 29 de 30 en clasificación,
> y **cero falsos negativos de urgencia en tres corridas independientes**.
>
> Tres corridas, y no una, porque el modelo no es determinista: una sola
> medición no alcanza para afirmar nada.

### 3:40 – 4:25 · Los diferenciales

Rápido, en lista. Si vas con el tiempo justo, decí solo los dos primeros.

> Además del requisito obligatorio de OCI Object Storage, cubrimos cuatro de
> los cinco diferenciales:
>
> La aplicación está **desplegada en OCI Compute** con acceso público.
>
> Las **reglas de triaje se cambian desde la pantalla** —el umbral de
> confianza, los canales de urgencia y el destino de cada tipo de documento—
> sin tocar el código y sin reiniciar. Protegido con clave, porque la página
> es pública.
>
> **Lectura multimodal** de fotos de recetas manuscritas y escaneos.
>
> Y un **panel de auditoría** donde el revisor ve el documento original junto
> a los datos extraídos.

### 4:25 – 5:00 · Cerrar

> Lo que nos llevamos de esto no es el modelo: los modelos los tiene
> cualquiera. Es que en salud **el sistema tiene que saber cuándo no sabe**, y
> tiene que decirlo en lugar de completar el hueco con algo verosímil.
>
> La aplicación está en línea, el código está en GitHub, y las pruebas y la
> evaluación se corren con un comando.
>
> Gracias.

Última diapositiva en pantalla, con el enlace y el repositorio, mientras
agradecés.

---

## La tarjeta

Esto es lo único que mirás mientras hablás. No leas el guion: se nota.

```
1. PROBLEMA      miles de documentos a mano · el urgente espera en la pila
2. QUE ES        agente autonomo · desplegado y publico · PDF, foto, texto
3. RUTINA        orden de laboratorio -> Auditoria, sola
4. URGENCIA      TEP -> Emergencia + alerta + CIE-10 · y explica por que
5. AMBIGUEDAD    receta ilegible -> NO invento la dosis
                 auditor corrige -> EL AGENTE VUELVE A DECIDIR
6. CONFIANZA     urgencia corre primero y gana · doble via con O
                 318 pruebas · 29/30 · CERO falsos negativos en 3 corridas
7. DIFERENCIALES OCI Compute · reglas por pantalla · multimodal · panel
8. CIERRE        saber cuando no sabe · enlace · gracias
```

---

## Cómo decirlo

**Ensayá en voz alta tres veces, con cronómetro.** Leerlo en silencio no sirve:
siempre se tarda más de lo que parece. Si la primera pasada te da seis minutos,
no hables más rápido — **sacá el bloque de diferenciales**.

**Las pausas que están marcadas no son adorno.** Después de "no lo hizo" hay
que callarse un segundo. Es la frase que querés que les quede.

**No pidas disculpas por nada.** Ni por lo que falta, ni por el tiempo, ni por
los nervios. No hay preguntas: lo que no mencionás, no existe.

**Si te quedás en blanco**, volvé a la tarjeta y seguí por el número que
sigue. Nadie sabe qué ibas a decir.

**Si te pasás de tiempo**, cortá en el cierre y decí las dos últimas frases.
Terminar con el enlace en pantalla y un "gracias" es mejor que que te corten
hablando de diferenciales.
