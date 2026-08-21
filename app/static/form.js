"use strict";

const DATA = JSON.parse(document.getElementById("form-data").textContent);

// ---------- Estado ----------
const state = {
  modo: null,          // "checkin" | "checkout"
  jugadorId: null,
  respuestas: {},      // acumulado de campos del payload
  escalaQueue: [],     // escalas pendientes por mostrar
  molestiaCampo: null, // "molestia_previa" | "molestia_nueva"
  zonaCampo: null,     // "molestia_zona"
};

// ---------- Definición de escalas ----------
const ESCALAS = {
  sueno:        { titulo: "😴 Sueño",         pregunta: "¿Cómo dormiste anoche?",              min: "Muy mal", max: "Excelente" },
  energia:      { titulo: "⚡ Energía",        pregunta: "¿Cuánta energía tienes hoy?",         min: "Agotado", max: "A tope" },
  animo:        { titulo: "🙂 Ánimo",          pregunta: "¿Cómo está tu ánimo?",                min: "Muy bajo", max: "Muy bien" },
  dolor_pre:    { titulo: "🩹 Dolor",          pregunta: "¿Tienes dolor muscular hoy?",         min: "Sin dolor", max: "Mucho dolor" },
  alimentacion: { titulo: "🍽️ Alimentación",  pregunta: "Tu comida antes de entrenar fue suficiente", min: "Nada suficiente", max: "Muy suficiente" },
  estres:       { titulo: "🧠 Estrés",         pregunta: "¿Cómo está tu nivel de estrés hoy?",         min: "Sin estrés",     max: "Muy estresado" },
  fisico_post:  { titulo: "⚡ Explosividad",   pregunta: "¿Qué tan explosivo te sentiste hoy?", min: "Nada explosivo", max: "Muy explosivo" },
  rendimiento:  { titulo: "⭐ Rendimiento",    pregunta: "¿Cómo evalúas tu entrenamiento hoy?", min: "Muy malo", max: "Excelente" },
};

const RPE = [
  { v: 0,  t: "Reposo total",     c: "#90a4ae" },
  { v: 1,  t: "Muy, muy suave",   c: "#43a047" },
  { v: 2,  t: "Suave",            c: "#66bb6a" },
  { v: 3,  t: "Moderado",         c: "#7cb342" },
  { v: 4,  t: "Algo duro",        c: "#c0ca33", dark: true },
  { v: 5,  t: "Duro",             c: "#fdd835", dark: true },
  { v: 6,  t: "Más duro",         c: "#ffb300", dark: true },
  { v: 7,  t: "Muy duro",         c: "#fb8c00" },
  { v: 8,  t: "Muy, muy duro",    c: "#f4511e" },
  { v: 9,  t: "Casi máximo",      c: "#e53935" },
  { v: 10, t: "Esfuerzo máximo",  c: "#b71c1c" },
];

// ---------- Navegación ----------
function show(id) {
  document.querySelectorAll(".screen").forEach(s => s.classList.remove("active"));
  document.getElementById(id).classList.add("active");
  window.scrollTo(0, 0);
}

function reset() {
  state.modo = null;
  state.jugadorId = null;
  state.respuestas = {};
  state.escalaQueue = [];
  document.getElementById("select-jugador").value = "";
  document.getElementById("btn-jugador").disabled = true;
  document.querySelectorAll(".chip.selected").forEach(c => c.classList.remove("selected"));
  document.getElementById("motivo-otro").classList.add("hidden");
  document.getElementById("motivo-otro").value = "";
  document.getElementById("zona-otra").classList.add("hidden");
  document.getElementById("zona-otra").value = "";
  document.getElementById("btn-motivo").disabled = true;
  document.getElementById("btn-zona").disabled = true;
  show("screen-inicio");
}

// ---------- Poblar jugadores ----------
const sel = document.getElementById("select-jugador");
DATA.jugadores.forEach(j => {
  const opt = document.createElement("option");
  opt.value = j.id;
  opt.textContent = j.nombre;
  sel.appendChild(opt);
});
sel.addEventListener("change", () => {
  document.getElementById("btn-jugador").disabled = !sel.value;
});

// ---------- Escalas ----------
function nextEscala() {
  if (state.escalaQueue.length === 0) {
    afterEscalas();
    return;
  }
  const campo = state.escalaQueue[0];
  const def = ESCALAS[campo];
  const total = state.escalaTotal;
  const done = total - state.escalaQueue.length;
  document.getElementById("escala-progreso").textContent =
    "●".repeat(done) + "○".repeat(state.escalaQueue.length);
  document.getElementById("escala-titulo").textContent = def.titulo;
  document.getElementById("escala-pregunta").textContent = def.pregunta;
  document.getElementById("escala-label-min").textContent = "1 = " + def.min;
  document.getElementById("escala-label-max").textContent = "7 = " + def.max;

  const cont = document.getElementById("escala-botones");
  cont.innerHTML = "";
  for (let v = 1; v <= 7; v++) {
    const b = document.createElement("button");
    b.textContent = v;
    b.addEventListener("click", () => {
      state.respuestas[campo] = v;
      state.escalaQueue.shift();
      nextEscala();
    });
    cont.appendChild(b);
  }
  show("screen-escala");
}

function startEscalas(campos, after) {
  state.escalaQueue = [...campos];
  state.escalaTotal = campos.length;
  state.afterEscalas = after;
  nextEscala();
}
function afterEscalas() { state.afterEscalas(); }

// ---------- RPE ----------
const rpeGrid = document.getElementById("rpe-grid");
RPE.forEach(r => {
  const b = document.createElement("button");
  b.style.background = r.c;
  if (r.dark) b.style.color = "#333";
  b.innerHTML = `<span class="rpe-num">${r.v}</span> ${r.t}`;
  b.addEventListener("click", () => {
    state.respuestas.rpe = r.v;
    _iniciarEscalasCheckout();
  });
  rpeGrid.appendChild(b);
});

// ---------- Checkout: escalas post-RPE ----------
function _iniciarEscalasCheckout() {
  startEscalas(["fisico_post", "rendimiento"], () => {
    state.molestiaCampo = "molestia_nueva";
    state.zonaCampo = "molestia_zona";
    document.getElementById("molestia-titulo").textContent = "¿Te quedó alguna molestia nueva?";
    show("screen-molestia");
  });
}

// ---------- Motivo inasistencia ----------
document.querySelectorAll("#chips-motivo .chip").forEach(chip => {
  chip.addEventListener("click", () => {
    document.querySelectorAll("#chips-motivo .chip").forEach(c => c.classList.remove("selected"));
    chip.classList.add("selected");
    const esOtro = chip.dataset.motivo === "Otro";
    document.getElementById("motivo-otro").classList.toggle("hidden", !esOtro);
    state.respuestas.motivo_inasistencia = esOtro ? "" : chip.dataset.motivo;
    document.getElementById("btn-motivo").disabled = esOtro && !document.getElementById("motivo-otro").value.trim();
  });
});
document.getElementById("motivo-otro").addEventListener("input", e => {
  state.respuestas.motivo_inasistencia = e.target.value.trim();
  document.getElementById("btn-motivo").disabled = !e.target.value.trim();
});

// ---------- Zona molestia ----------
document.querySelectorAll("#chips-zona .chip").forEach(chip => {
  chip.addEventListener("click", () => {
    document.querySelectorAll("#chips-zona .chip").forEach(c => c.classList.remove("selected"));
    chip.classList.add("selected");
    const esOtra = chip.dataset.zona === "Otra";
    document.getElementById("zona-otra").classList.toggle("hidden", !esOtra);
    if (esOtra) {
      const texto = document.getElementById("zona-otra").value.trim();
      state.respuestas[state.zonaCampo] = texto;
      document.getElementById("btn-zona").disabled = !texto;
      document.getElementById("zona-otra").focus();
    } else {
      state.respuestas[state.zonaCampo] = chip.dataset.zona;
      document.getElementById("btn-zona").disabled = false;
    }
  });
});
document.getElementById("zona-otra").addEventListener("input", e => {
  state.respuestas[state.zonaCampo] = e.target.value.trim();
  document.getElementById("btn-zona").disabled = !e.target.value.trim();
});

// ---------- Envío ----------
async function enviar() {
  show("screen-enviando");
  const esCheckin = state.modo === "checkin";
  const url = esCheckin ? "/api/checkin" : "/api/checkout";
  const payload = { jugador_id: state.jugadorId, fecha: DATA.fecha, ...state.respuestas };
  try {
    const resp = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await resp.json();
    if (!resp.ok) {
      const msg = typeof data.detail === "string" ? data.detail : "Revisa tus respuestas e intenta de nuevo.";
      document.getElementById("error-msg").textContent = msg;
      show("screen-error");
      return;
    }
    mostrarFeedback(data);
  } catch (e) {
    document.getElementById("error-msg").textContent = "Sin conexión. Revisa tu internet e intenta de nuevo.";
    show("screen-error");
  }
}

function mostrarFeedback(data) {
  const emoji = document.getElementById("feedback-emoji");
  const titulo = document.getElementById("feedback-titulo");
  const msg = document.getElementById("feedback-msg");

  if (state.modo === "checkin" && state.respuestas.asistencia === false) {
    emoji.textContent = "💙";
    titulo.textContent = "Gracias por avisar";
    msg.textContent = "Le avisamos al profe. ¡Nos vemos pronto!";
  } else if (state.modo === "checkin") {
    emoji.textContent = "🎉";
    titulo.textContent = "¡Listo!";
    msg.textContent = data.feedback || "Check-in registrado. ¡Buen entrenamiento!";
  } else {
    emoji.textContent = "💪";
    titulo.textContent = "¡Buen entrenamiento!";
    msg.textContent = `Carga de hoy: ${data.carga} puntos (RPE ${data.rpe} × ${data.duracion_min} min)`;
  }
  show("screen-feedback");
}

// ---------- Hora inicio (checkin) ----------
function _irAHoraInicio() {
  if (state.modo === "checkin" && state.respuestas.asistencia) {
    document.getElementById("input-hora-inicio").value = "";
    show("screen-hora-inicio");
  } else {
    enviar();
  }
}

// ---------- Acciones ----------
const acciones = {
  "ir-checkin":  () => { state.modo = "checkin"; show("screen-jugador"); },
  "ir-checkout": () => { state.modo = "checkout"; show("screen-jugador"); },
  "volver-inicio": reset,
  "reiniciar": reset,
  "reintentar": reset,

  "jugador-listo": () => {
    state.jugadorId = parseInt(sel.value, 10);
    if (state.modo === "checkin") {
      show("screen-asistencia");
    } else {
      document.getElementById("input-hora-termino").value = "";
      show("screen-hora-termino");
    }
  },

  "asiste-si": () => {
    state.respuestas.asistencia = true;
    startEscalas(["sueno", "energia", "animo", "dolor_pre", "alimentacion", "estres"], () => {
      state.molestiaCampo = "molestia_previa";
      state.zonaCampo = "molestia_zona";
      document.getElementById("molestia-titulo").textContent = "¿Tienes alguna molestia física?";
      show("screen-molestia");
    });
  },
  "asiste-no": () => {
    state.respuestas.asistencia = false;
    show("screen-motivo");
  },
  "enviar-inasistencia": enviar,

  "molestia-no": () => {
    state.respuestas[state.molestiaCampo] = false;
    _irAHoraInicio();
  },
  "molestia-si": () => {
    state.respuestas[state.molestiaCampo] = true;
    show("screen-zona");
  },
  "zona-lista": () => {
    const pregunta = state.modo === "checkin"
      ? "¿Puedes entrenar con esta molestia?"
      : "¿Qué tan grave es esta molestia?";
    document.getElementById("severidad-pregunta").textContent = pregunta;
    show("screen-severidad");
  },
  "sev-leve":       () => { state.respuestas.molestia_severidad = "leve";       _irAHoraInicio(); },
  "sev-limitante":  () => { state.respuestas.molestia_severidad = "limitante";  _irAHoraInicio(); },
  "sev-bloqueante": () => { state.respuestas.molestia_severidad = "bloqueante"; _irAHoraInicio(); },

  "hora-inicio-lista": () => {
    const val = document.getElementById("input-hora-inicio").value;
    if (val) state.respuestas.hora_inicio_declarada = val;
    enviar();
  },
  "hora-inicio-saltar": () => { enviar(); },

  "hora-termino-lista": () => {
    const val = document.getElementById("input-hora-termino").value;
    if (val) state.respuestas.hora_termino = val;
    show("screen-rpe");
  },
  "hora-termino-saltar": () => { show("screen-rpe"); },

};

document.querySelectorAll("[data-action]").forEach(el => {
  el.addEventListener("click", () => acciones[el.dataset.action]());
});
