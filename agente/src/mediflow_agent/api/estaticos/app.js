/* Pagina web de triaje MediFlow.
 *
 * Habla con la misma API que cualquier otro consumidor: no hay atajos ni
 * endpoints privados para la interfaz. Si algo se ve en pantalla, es porque
 * el contrato lo devuelve.
 */

"use strict";

const $ = (id) => document.getElementById(id);

const EJEMPLOS = {
  urgencia: {
    canal: "Guardia_Emergencias",
    texto:
      "HOSPITAL SANTA LUCIA - INFORME DE ESTUDIO RADIOLOGICO\n" +
      "Paciente: Carlos Eduardo Mendes, 52 anos\n" +
      "Medico Solicitante: Dra. Renata Silveira - MP 145892\n" +
      "Estudio: Tomografia de Torax con contraste\n" +
      "Indicacion: Sospecha de embolia pulmonar aguda, disnea subita.\n" +
      "Hallazgos: Defecto de llenado en arteria pulmonar principal derecha.\n" +
      "CONCLUSION: Cuadro compatible con Tromboembolismo Pulmonar Agudo.",
  },
  rutina: {
    canal: "Recepcion",
    texto:
      "OBRA SOCIAL UNIFICADA - ORDEN DE ESTUDIOS COMPLEMENTARIOS\n" +
      "Paciente: Adriana Carolina Paredes, 45 anos\n" +
      "Se solicita: Hemograma completo, Glucemia en ayunas, Perfil tiroideo.\n" +
      "Caracter: Ambulatorio, no urgente.\n" +
      "Dr. Guillermo Segovia - Clinica Medica MP 30958",
  },
  ambiguo: {
    canal: "Recepcion",
    texto:
      "CONSULTORIO EXTERNO - RECETA MANUSCRITA (transcripcion)\n" +
      "Paciente: Rosa Mabel Aguero, 58 anos\n" +
      "Rp/ Metformina [ilegible] mg - [ilegible] veces al dia\n" +
      "Glibenclamida 5 mg - 1 comprimido antes del desayuno\n" +
      "Dr. Ernesto Caballero - MP [ilegible]",
  },
};

const CLASE_PRIORIDAD = {
  Urgente: "urgente",
  Prioritario: "revision",
  Rutina: "rutina",
};

// El destino manda sobre la prioridad para elegir el color: lo que importa
// visualmente es a donde fue el documento, no con que etiqueta.
function claseDe(decision, prioridad) {
  if (decision.destino_principal === "Cola_Emergencia_Medica") return "urgente";
  if (decision.requiere_auditoria_humana) return "revision";
  return CLASE_PRIORIDAD[prioridad] || "rutina";
}

function legible(valor) {
  if (valor === null || valor === undefined || valor === "") return null;
  if (Array.isArray(valor)) return valor.length ? valor.join(" · ") : null;
  return String(valor);
}

function escapar(texto) {
  const d = document.createElement("div");
  d.textContent = texto;
  return d.innerHTML;
}

function nombreDestino(destino) {
  return destino.replace(/_/g, " ");
}

/* ===================== hilo ===================== */

function agregarAlHilo(nodo) {
  const bienvenida = $("bienvenida");
  if (bienvenida) bienvenida.remove();

  const hilo = $("hilo");
  hilo.appendChild(nodo);
  hilo.scrollTop = hilo.scrollHeight;
}

function mensajePropio(texto, documentoId) {
  const div = document.createElement("div");
  div.className = "mensaje propio";
  div.innerHTML =
    '<span class="autor">' + escapar(documentoId) + "</span>" +
    '<div class="globo">' + escapar(texto) + "</div>";
  return div;
}

function mensajeAgente(contenidoHtml, clase) {
  const div = document.createElement("div");
  div.className = "mensaje";
  div.innerHTML =
    '<span class="autor">MediFlow</span>' +
    '<div class="globo decision ' + clase + '">' + contenidoHtml + "</div>";
  return div;
}

function dato(etiqueta, valor, esCodigo) {
  const v = legible(valor);
  const clase = v === null ? "nulo" : esCodigo ? "codigo" : "";
  const texto = v === null ? "sin dato" : escapar(v);
  return (
    '<div class="dato"><dt>' + etiqueta + "</dt>" +
    '<dd class="' + clase + '">' + texto + "</dd></div>"
  );
}

function tarjetaDecision(r) {
  const d = r.decision_enrutamiento;
  const c = r.clasificacion;
  const x = r.datos_extraidos;
  const clase = claseDe(d, c.nivel_prioridad);

  let html =
    '<div class="encabezado-decision">' +
    '<span class="tipo">' + escapar(c.tipo_documento) + "</span>" +
    '<span class="chip chip-' + clase + '">' + escapar(c.nivel_prioridad) + "</span>" +
    '<span class="chip chip-neutro">' +
    Math.round(c.score_confianza_clasificacion * 100) + "% confianza</span>" +
    '<span class="destino">&rarr; ' + escapar(nombreDestino(d.destino_principal)) + "</span>" +
    "</div>";

  html += '<div class="justificacion">' + escapar(d.justificacion_enrutamiento) + "</div>";

  html +=
    '<dl class="campos">' +
    dato("Paciente", x.paciente.nombre) +
    dato("Edad", x.paciente.edad) +
    dato("Profesional", x.medico_solicitante.nombre) +
    dato("Matrícula", x.medico_solicitante.matricula, true) +
    dato("Estudio", x.estudio_realizado) +
    dato("Diagnóstico", x.diagnostico_principal) +
    dato("CIE-10", x.cie10_sugerido, true) +
    dato("Medicamentos", x.medicamentos) +
    "</dl>";

  if (d.notificacion_generada) {
    html +=
      '<div class="alerta"><span class="canal">' +
      escapar(d.notificacion_generada.canal) + "</span>" +
      escapar(d.notificacion_generada.mensaje) + "</div>";
  }

  const ok = r.almacenamiento_oci.status_backup === "exito";
  html +=
    '<div class="ruta"><span class="' + (ok ? "ok" : "mal") + '">' +
    (ok ? "guardado" : "fallo el respaldo") + "</span>" +
    escapar(r.almacenamiento_oci.bucket + "/" + r.almacenamiento_oci.ruta_objeto) +
    "</div>";

  return mensajeAgente(html, clase);
}

function mensajeError(texto) {
  return mensajeAgente(
    '<div class="justificacion"><strong>No se pudo procesar.</strong> ' +
      escapar(texto) + "</div>",
    "urgente"
  );
}

/* ===================== envío ===================== */

function identificador() {
  const puesto = $("documento-id").value.trim();
  if (puesto) return puesto;

  const ahora = new Date();
  const sello =
    ahora.getFullYear() +
    String(ahora.getMonth() + 1).padStart(2, "0") +
    String(ahora.getDate()).padStart(2, "0") +
    "-" +
    String(ahora.getHours()).padStart(2, "0") +
    String(ahora.getMinutes()).padStart(2, "0") +
    String(ahora.getSeconds()).padStart(2, "0");

  return "DOC-" + sello;
}

async function enviar(evento) {
  evento.preventDefault();

  const boton = $("enviar");
  const archivo = $("archivo").files[0];
  const texto = $("texto").value.trim();

  if (!archivo && !texto) return;

  const documentoId = identificador();
  const canal = $("canal").value;

  agregarAlHilo(
    mensajePropio(archivo ? "Archivo: " + archivo.name : texto, documentoId)
  );

  boton.disabled = true;
  boton.querySelector(".etiqueta").textContent = "Triando…";

  try {
    let respuesta;

    if (archivo) {
      const cuerpo = new FormData();
      cuerpo.append("documento_id", documentoId);
      cuerpo.append("tipo_archivo", archivo.type === "application/pdf" ? "PDF" : "IMAGEN");
      cuerpo.append("canal_origen", canal);
      cuerpo.append("archivo", archivo);
      respuesta = await fetch("/triaje/archivo", { method: "POST", body: cuerpo });
    } else {
      respuesta = await fetch("/triaje", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          documento_id: documentoId,
          tipo_archivo: "TEXTO",
          documento_texto: texto,
          canal_origen: canal,
        }),
      });
    }

    const datos = await respuesta.json();

    if (!respuesta.ok) {
      const detalle = datos.detail;
      agregarAlHilo(
        mensajeError(
          typeof detalle === "string" ? detalle : JSON.stringify(detalle)
        )
      );
    } else {
      agregarAlHilo(tarjetaDecision(datos));
      $("texto").value = "";
      $("archivo").value = "";
      $("documento-id").value = "";
      cargarBandeja();
    }
  } catch (err) {
    agregarAlHilo(mensajeError(String(err)));
  } finally {
    boton.disabled = false;
    boton.querySelector(".etiqueta").textContent = "Triar";
  }
}

/* ===================== bandeja ===================== */

let prefijoActivo = "auditoria_humana";

async function cargarBandeja() {
  const prefijos = ["auditoria_humana", "procesados/urgentes", "procesados/rutina"];

  for (const prefijo of prefijos) {
    try {
      const r = await fetch("/bandeja?prefijo=" + encodeURIComponent(prefijo));
      const casos = await r.json();

      const cuenta = document.querySelector('[data-cuenta="' + prefijo + '"]');
      if (cuenta) cuenta.textContent = casos.length;

      if (prefijo === prefijoActivo) dibujarLista(casos);
    } catch (err) {
      if (prefijo === prefijoActivo) {
        $("lista").innerHTML =
          '<p class="vacio">No se pudo leer el almacén.</p>';
      }
    }
  }
}

function dibujarLista(casos) {
  const lista = $("lista");

  if (!casos.length) {
    lista.innerHTML = '<p class="vacio">Sin casos en esta bandeja.</p>';
    return;
  }

  lista.innerHTML = "";

  for (const caso of casos) {
    const clase = CLASE_PRIORIDAD[caso.nivel_prioridad] || "rutina";
    const boton = document.createElement("button");
    boton.type = "button";
    boton.className = "caso";
    boton.innerHTML =
      '<div class="fila">' +
      '<span class="chip chip-' + clase + '">' + escapar(caso.nivel_prioridad) + "</span>" +
      '<span class="doc-id">' + escapar(caso.documento_id) + "</span></div>" +
      '<div class="paciente">' + escapar(caso.paciente || "sin identificar") + "</div>" +
      '<div class="tipo-doc">' + escapar(caso.tipo_documento) + "</div>";
    boton.addEventListener("click", () => abrirAuditoria(caso.documento_id));
    lista.appendChild(boton);
  }
}

/* ===================== panel de auditoría ===================== */

let documentoEnRevision = null;

async function abrirAuditoria(documentoId) {
  try {
    const r = await fetch("/documentos/" + encodeURIComponent(documentoId));
    if (!r.ok) return;

    const datos = await r.json();
    documentoEnRevision = documentoId;

    const d = datos.decision;
    const x = d.datos_extraidos;

    $("auditoria-id").textContent = documentoId;
    $("auditoria-original").textContent = datos.original || "(no se archivó el original)";
    $("auditoria-motivo").textContent = d.decision_enrutamiento.justificacion_enrutamiento;

    const campos = [
      ["c-paciente", x.paciente.nombre],
      ["c-edad", x.paciente.edad],
      ["c-medico", x.medico_solicitante.nombre],
      ["c-matricula", x.medico_solicitante.matricula],
      ["c-estudio", x.estudio_realizado],
      ["c-diagnostico", x.diagnostico_principal],
      ["c-cie10", x.cie10_sugerido],
      ["c-medicamentos", x.medicamentos ? x.medicamentos.join("; ") : ""],
    ];

    for (const [id, valor] of campos) {
      const campo = $(id);
      campo.value = valor === null || valor === undefined ? "" : valor;
      // Se marcan los vacíos: son los que el auditor vino a completar.
      campo.classList.toggle("falta", !campo.value);
    }

    $("auditoria-aviso").textContent = "";
    $("velo").hidden = false;
  } catch (err) {
    /* el panel simplemente no abre */
  }
}

function cerrarAuditoria() {
  $("velo").hidden = true;
  documentoEnRevision = null;
}

function valorONulo(id) {
  const v = $(id).value.trim();
  return v === "" ? null : v;
}

async function aprobar() {
  if (!documentoEnRevision) return;

  const boton = $("aprobar");
  boton.disabled = true;
  boton.textContent = "Re-enrutando…";

  const medicamentos = $("c-medicamentos").value.trim();
  const edad = $("c-edad").value.trim();

  try {
    const r = await fetch(
      "/documentos/" + encodeURIComponent(documentoEnRevision) + "/aprobar",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          paciente_nombre: valorONulo("c-paciente"),
          paciente_edad: edad === "" ? null : Number(edad),
          medico_nombre: valorONulo("c-medico"),
          medico_matricula: valorONulo("c-matricula"),
          estudio_realizado: valorONulo("c-estudio"),
          diagnostico_principal: valorONulo("c-diagnostico"),
          cie10_sugerido: valorONulo("c-cie10"),
          medicamentos: medicamentos
            ? medicamentos.split(";").map((m) => m.trim()).filter(Boolean)
            : null,
          auditor: $("c-auditor").value.trim(),
        }),
      }
    );

    const datos = await r.json();

    if (!r.ok) {
      $("auditoria-aviso").textContent =
        typeof datos.detail === "string" ? datos.detail : "No se pudo aprobar.";
      return;
    }

    cerrarAuditoria();
    agregarAlHilo(tarjetaDecision(datos));
    cargarBandeja();
  } catch (err) {
    $("auditoria-aviso").textContent = String(err);
  } finally {
    boton.disabled = false;
    boton.textContent = "Aprobar y re-enrutar";
  }
}

/* ===================== arranque ===================== */

async function comprobarSalud() {
  try {
    const r = await fetch("/salud");
    const ok = r.ok;
    $("punto-estado").className = "punto " + (ok ? "vivo" : "caido");
    $("texto-estado").textContent = ok ? "servicio activo" : "servicio caído";
  } catch (err) {
    $("punto-estado").className = "punto caido";
    $("texto-estado").textContent = "sin conexión";
  }
}

async function mostrarOrigen() {
  try {
    const r = await fetch("/bandeja?prefijo=recibidos");
    if (r.ok) $("origen-almacen").textContent = "leyendo del almacén configurado";
  } catch (err) {
    $("origen-almacen").textContent = "almacén no disponible";
  }
}

document.addEventListener("DOMContentLoaded", () => {
  $("redactor").addEventListener("submit", enviar);
  $("refrescar").addEventListener("click", cargarBandeja);
  $("cerrar-auditoria").addEventListener("click", cerrarAuditoria);
  $("cancelar-auditoria").addEventListener("click", cerrarAuditoria);
  $("aprobar").addEventListener("click", aprobar);

  $("velo").addEventListener("click", (e) => {
    if (e.target === $("velo")) cerrarAuditoria();
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !$("velo").hidden) cerrarAuditoria();
  });

  document.querySelectorAll("[data-ejemplo]").forEach((boton) => {
    boton.addEventListener("click", () => {
      const ej = EJEMPLOS[boton.dataset.ejemplo];
      $("texto").value = ej.texto;
      $("canal").value = ej.canal;
      $("texto").focus();
    });
  });

  document.querySelectorAll("[data-prefijo]").forEach((pestana) => {
    pestana.addEventListener("click", () => {
      document.querySelectorAll("[data-prefijo]").forEach((p) =>
        p.classList.remove("activa")
      );
      pestana.classList.add("activa");
      prefijoActivo = pestana.dataset.prefijo;
      cargarBandeja();
    });
  });

  // Enviar con Ctrl+Enter desde el área de texto.
  $("texto").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
      $("redactor").requestSubmit();
    }
  });

  comprobarSalud();
  mostrarOrigen();
  cargarBandeja();
});
