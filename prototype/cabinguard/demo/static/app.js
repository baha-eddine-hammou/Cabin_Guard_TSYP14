// CabinGuard-ADI jury dashboard. Renders one engine record per 100 ms; sends operator commands.
"use strict";
const $ = (id) => document.getElementById(id);
const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
const PHASES = ["NORMAL", "PHASE_1_PRE_ALERT", "PHASE_2_ESCALATION", "PHASE_3_ACTIVE_MRM", "PHASE_4_STANDSTILL"];
const CLASSES = ["Normal", "Syncope", "Seizure"];
const CLASS_VAR = { Normal: "--normal", Syncope: "--syncope", Seizure: "--seizure" };
const BRANCHES = [["cardiac", "Pulse rhythm", "camera"], ["vision", "Eyes, head", "camera"],
                  ["motion", "Headrest motion", "IMU"], ["posture", "Seat, wheel", "seat"]];
// [record field, title, decimals, fixed axis range]: fixed ranges so an event looks like an event, not rescaled noise
const STRIPS = [["ear", "Eyes (EAR)", 2, [0, 0.4]], ["hr_bpm", "Pulse, bpm", 0, [30, 150]],
                ["imu_rms_g", "Headrest, g", 3, [0, 0.25]], ["psi", "Seat slump \u03C8", 2, [0, 1]],
                ["torque_nm", "Torque, Nm", 1, [0, 5]]];
const HISTORY = 600;                       // 60 s at 10 Hz
const hist = Object.fromEntries(STRIPS.map(([k]) => [k, []]));
let rejects = [];
let logs = [];
let lastK = 0;
let sock = null;

// ------------------------------------------------------------------ socket ---
function connect() {
  sock = new WebSocket(`ws://${location.host}/ws`);
  sock.onopen = () => { $("conn").textContent = "live"; };
  sock.onclose = () => { $("conn").textContent = "reconnecting"; setTimeout(connect, 800); };
  sock.onmessage = (m) => render(JSON.parse(m.data));
}
function send(cmd, arg) { if (sock && sock.readyState === 1) sock.send(JSON.stringify({ cmd, arg })); }

document.querySelectorAll("button[data-cmd]").forEach((b) =>
  b.addEventListener("click", () => send(b.dataset.cmd, b.dataset.arg)));
const KEYS = { s: ["event", "seizure"], y: ["event", "syncope"], f: ["attack", "forge"], r: ["attack", "replay"],
  t: ["attack", "tamper"], i: ["attack", "implausible"], b: ["fault", "blind"], u: ["fault", "imu_drop"],
  h: ["fault", "ecu_hang"], c: ["fault", "cellular_down"], p: ["script", "seizure"] };
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") return send("reset");
  if (e.key === "l") { const r = document.documentElement; r.dataset.theme = r.dataset.theme === "light" ? "dark" : "light"; return; }
  const k = KEYS[e.key.toLowerCase()];
  if (k) send(...k);
});

// ------------------------------------------------------------------ render ---
function render(r) {
  if (r.k < lastK) { rejects = []; logs = []; STRIPS.forEach(([k]) => (hist[k] = [])); }   // engine was reset
  lastK = r.k;
  $("clock").textContent = `${r.t.toFixed(1)} s`;
  $("cue").textContent = r.cue || "";
  renderChips(r.provenance);
  renderStepper(r);
  renderRoad(r);
  renderCabin(r);
  renderDecision(r);
  renderCan(r);
  renderEcall(r);
  const tm = r.timing || {};
  $("timing").textContent = `ECU ${r.ecu.compute_ms.toFixed(1)} ms (p99 ${tm.compute_p99_ms ?? "-"}) of 100 ms`;
  document.querySelectorAll("button.toggle").forEach((b) =>
    b.classList.toggle("on", r.provenance.injected.includes(b.dataset.arg)));
}

function chip(label, cls, detail) {
  return `<span class="chip ${cls.toLowerCase()}" title="${detail}"><b>${label}</b>${cls}${detail ? ": " + detail : ""}</span>`;
}
function renderChips(p) {
  const names = { pulse: "Pulse", face: "Face", imu: "Headrest IMU", seat: "Seat+wheel" };
  let h = Object.entries(p.channels).map(([ch, v]) => chip(names[ch], v.class, v.class === "LIVE" ? v.detail : "")).join("");
  h += p.injected.map((x) => chip("Injected", "INJECTED", x)).join("");
  h += chip("Key", p.key === "DEMO KEY" ? "SYNTHETIC" : "LIVE", p.key);
  $("chips").innerHTML = h;
  $("vehTag").textContent = p.vehicle;
  $("busTag").textContent = `${p.bus}, SecOC profile 1 (24-bit AES-CMAC, 8-bit freshness)`;
  $("commsTag").textContent = p.comms;
  const synth = Object.values(p.channels).every((v) => v.class === "SYNTHETIC");
  $("cabinTag").textContent = synth ? "SYNTHETIC signals" : "mixed: see chips";
}

function renderStepper(r) {
  const idx = PHASES.indexOf(r.mrm.state);
  document.querySelectorAll(".step").forEach((el, i) => {
    el.classList.toggle("active", i === idx);
    el.classList.toggle("done", idx >= 0 && i < idx);
  });
  const ev = r.event.kind ? `event: ${r.event.kind}${r.event.onset_in_s > 0 ? ` in ${r.event.onset_in_s.toFixed(1)} s` : ""}` : "no event";
  const st = r.mrm.state === "ECU_FAILED" ? "ECU failed silent" : (idx > 0 ? `${r.mrm.etiology}, ${r.mrm.timer_s.toFixed(1)} s since alert` : "");
  $("mrmInfo").innerHTML = `<div>${ev}</div><div>${st}</div>`;
}

// Road: top view, travel lanes and the hard shoulder on the right; the car drives up the screen.
const PX = 26, LANE = 3.5, X0 = 150;              // px per metre; centre of the travel lane
function renderRoad(r) {
  const v = r.vehicle, blink = Math.floor(performance.now() / 333) % 2 === 0;
  const xLane = (m) => X0 + m * PX;               // lateral metres to the right of the lane centre
  const left = xLane(-LANE / 2), mid1 = xLane(LANE / 2), mid2 = xLane(1.5 * LANE), right = xLane(2.5 * LANE);
  const dash = (v.distance_m * PX) % 60;
  const carX = xLane(-v.lateral_m), carY = 250, w = 1.9 * PX, l = 4.6 * PX;
  const brake = v.decel < -0.3 || v.epb;
  const haz = v.hazards && blink;
  let s = `<rect x="0" y="0" width="560" height="430" fill="var(--surface-2)"/>`;
  s += `<rect x="${left}" y="0" width="${right - left}" height="430" fill="var(--road)"/>`;
  s += `<line x1="${left}" y1="0" x2="${left}" y2="430" stroke="var(--paint)" stroke-width="3"/>`;
  s += `<line x1="${mid1}" y1="0" x2="${mid1}" y2="430" stroke="var(--paint)" stroke-width="2" stroke-dasharray="30 30" stroke-dashoffset="${-dash}"/>`;
  s += `<line x1="${mid2}" y1="0" x2="${mid2}" y2="430" stroke="var(--paint)" stroke-width="3"/>`;
  s += `<line x1="${right}" y1="0" x2="${right}" y2="430" stroke="var(--paint)" stroke-width="2"/>`;
  s += `<text x="${(left + mid1) / 2}" y="420" text-anchor="middle" fill="var(--paint)" font-size="12">lane</text>`;
  s += `<text x="${(mid1 + mid2) / 2}" y="420" text-anchor="middle" fill="var(--paint)" font-size="12">lane</text>`;
  s += `<text x="${(mid2 + right) / 2}" y="420" text-anchor="middle" fill="var(--paint)" font-size="12">hard shoulder</text>`;
  if (r.telematics.denm_sent) {
    const ph = (performance.now() / 1500) % 1;
    for (const k of [0, 0.5]) {
      const rr = 30 + ((ph + k) % 1) * 140;
      s += `<circle cx="${carX}" cy="${carY}" r="${rr}" fill="none" stroke="var(--text-2)" stroke-opacity="${1 - ((ph + k) % 1)}" stroke-width="2"/>`;
    }
    s += `<text x="${carX}" y="${carY - 95}" text-anchor="middle" fill="var(--text)" font-size="12" paint-order="stroke" stroke="var(--surface)" stroke-width="4">DENM (simulated radio): cause 93, sub-cause 0</text>`;
  }
  s += `<g transform="translate(${carX - w / 2},${carY - l / 2})">`;
  s += `<rect width="${w}" height="${l}" rx="9" fill="var(--normal)" stroke="var(--text)" stroke-width="1.5"/>`;
  s += `<rect x="6" y="${l * 0.22}" width="${w - 12}" height="${l * 0.2}" rx="4" fill="var(--surface)" opacity=".75"/>`;
  s += `<rect x="6" y="${l * 0.68}" width="${w - 12}" height="${l * 0.14}" rx="4" fill="var(--surface)" opacity=".75"/>`;
  for (const x of [3, w - 13]) {
    s += `<rect x="${x}" y="${l - 7}" width="10" height="5" rx="2" fill="${brake ? "#ff2d2d" : "#5a1d1d"}"/>`;
    s += `<rect x="${x}" y="2" width="10" height="5" rx="2" fill="${haz ? "#ffb000" : "#e8e6dc"}"/>`;
    s += `<rect x="${x}" y="${l - 14}" width="10" height="5" rx="2" fill="${haz ? "#ffb000" : "transparent"}"/>`;
  }
  s += `</g>`;
  $("road").innerHTML = s;
  let hud = `<div class="speed">${v.speed_kmh.toFixed(0)}</div><div class="unit">km/h</div>`;
  hud += `<div class="row">decel ${v.decel.toFixed(1)} m/s² (plant = command)</div>`;
  hud += `<div class="row">lateral ${(-v.lateral_m).toFixed(1)} m to the right</div>`;
  if (v.hazards) hud += `<div><span class="telltale warn">⚠ hazards</span></div>`;
  if (v.shoulder) hud += `<div><span class="telltale warn">↴ to shoulder</span></div>`;
  if (v.epb) hud += `<div><span class="telltale warn">(P) parking brake</span></div>`;
  if (v.doors_unlock) hud += `<div><span class="telltale warn">doors unlocked</span></div>`;
  if (v.ecu_fault) hud += `<div><span class="telltale crit">✕ ECU fault</span></div>`;
  if (v.ecu_fault && !v.fail_operational && v.phase < 2) hud += `<div class="row">driver in control: warning only</div>`;
  if (v.fail_operational) hud += `<div><span class="telltale crit">gateway completes the stop</span></div>`;
  $("hud").innerHTML = hud;
}

// Cabin: live webcam when the face channel is live, otherwise a schematic driven by the signals.
let camShown = false;
function renderCabin(r) {
  const face = r.provenance.channels.face, live = face.class === "LIVE";
  if (live !== camShown) {
    $("cam").hidden = !live; $("driver").style.display = live ? "none" : "";
    if (live) $("cam").src = "/video.mjpg?" + Date.now();
    camShown = live;
  }
  $("cabinCaption").textContent = live
    ? "LIVE webcam with landmarks; nothing is stored. Signals below follow each channel's chip."
    : "Schematic driver drawn from SYNTHETIC scenario signals: not a camera image.";
  if (!live) drawDriver(r.inputs);
  STRIPS.forEach(([k]) => { hist[k].push(r.inputs[k]); if (hist[k].length > HISTORY) hist[k].shift(); });
  if (!$("strips").children.length) {
    $("strips").innerHTML = STRIPS.map(([k, t]) =>
      `<div class="strip"><div class="t">${t}<b id="v_${k}"></b></div><canvas id="c_${k}"></canvas></div>`).join("");
  }
  STRIPS.forEach(([k, , dp, range]) => {
    const x = r.inputs[k];
    $("v_" + k).textContent = x == null ? "–" : Number(x).toFixed(dp);
    spark($("c_" + k), hist[k], range);
  });
}

function spark(cv, data, [lo, hi]) {
  const dpr = window.devicePixelRatio || 1, W = cv.clientWidth, H = cv.clientHeight;
  if (cv.width !== W * dpr) { cv.width = W * dpr; cv.height = H * dpr; }
  const g = cv.getContext("2d");
  g.setTransform(dpr, 0, 0, dpr, 0, 0);
  g.clearRect(0, 0, W, H);
  g.strokeStyle = css("--text-2"); g.lineWidth = 2; g.lineJoin = "round"; g.beginPath();
  let pen = false;
  data.forEach((x, i) => {
    if (x == null) { pen = false; return; }
    const y = Math.max(lo, Math.min(hi, x));
    const px = (i / (HISTORY - 1)) * W, py = H - 3 - ((y - lo) / (hi - lo)) * (H - 6);
    pen ? g.lineTo(px, py) : g.moveTo(px, py); pen = true;
  });
  g.stroke();
}

function drawDriver(inp) {
  const pitch = inp.pitch ?? 0, ear = inp.ear ?? 0.3, psi = inp.psi ?? 0.15, grip = inp.grip || "ACTIVE";
  const shake = Math.min(6, (inp.imu_rms_g || 0) * 40) * Math.sin(performance.now() / 40);
  const lean = Math.max(0, Math.min(1, (psi - 0.15) / 0.55)) * 22;     // torso forward, degrees
  const eye = Math.max(1, Math.min(7, (ear / 0.3) * 7));
  const hands = grip !== "DISENGAGED";
  let s = `<rect x="0" y="0" width="320" height="240" fill="var(--surface-2)"/>`;
  s += `<rect x="96" y="70" width="20" height="150" rx="8" fill="var(--line)"/>`;                      // seat back
  s += `<rect x="96" y="196" width="120" height="22" rx="8" fill="var(--line)"/>`;                     // seat base
  s += `<g transform="translate(${shake},0) rotate(${lean} 120 190)">`;
  s += `<rect x="112" y="110" width="44" height="90" rx="18" fill="var(--text-2)"/>`;                  // torso
  s += `<g transform="rotate(${-pitch * 0.8} 140 104)">`;
  s += `<circle cx="146" cy="82" r="26" fill="var(--text-2)" stroke="var(--text)" stroke-width="1.5"/>`;
  s += `<ellipse cx="160" cy="78" rx="6" ry="${eye}" fill="var(--surface)"/>`;
  s += `</g>`;
  s += hands ? `<path d="M150 130 L205 150" stroke="var(--text-2)" stroke-width="12" stroke-linecap="round"/>`
             : `<path d="M140 135 L150 192" stroke="var(--text-2)" stroke-width="12" stroke-linecap="round"/>`;
  s += `</g>`;
  s += `<line x1="215" y1="120" x2="222" y2="185" stroke="var(--text)" stroke-width="7" stroke-linecap="round"/>`;  // wheel
  if (grip === "CLENCHED") s += `<text x="230" y="118" fill="var(--text)" font-size="12">grip clenched</text>`;
  if (!hands) s += `<text x="228" y="118" fill="var(--text)" font-size="12">hands off</text>`;
  $("driver").innerHTML = s;
}

function renderDecision(r) {
  const d = r.decision;
  if (!d) {                                        // nothing stale may stay on screen while the ECU is silent
    $("modeTag").textContent = "no output";
    $("post").innerHTML = `<div class="alert">ECU failed silent: no decision. The gateway supervises the alive counter.</div>`;
    $("persistLabel").textContent = ""; $("persistFill").style.width = "0";
    $("llr").innerHTML = ""; $("corro").innerHTML = ""; $("alerts").innerHTML = "";
    return;
  }
  $("modeTag").textContent = d.mode;
  $("post").innerHTML = CLASSES.map((c) => {
    const p = d.posteriors[c] ?? 0;
    return `<div class="bar-row"><span>${c}</span><div class="bar-track">
      <div class="bar-fill" style="width:${(p * 100).toFixed(1)}%;background:var(${CLASS_VAR[c]})"></div>
      <div class="bar-gamma" style="left:${d.gamma * 100}%" title="Gamma ${d.gamma}"></div></div>
      <span class="bar-val">${p.toFixed(2)}</span></div>`;
  }).join("");
  const frac = Math.min(1, d.persistence_s / d.persistence_needed_s);
  $("persistFill").style.width = `${frac * 100}%`;
  $("persistLabel").textContent = d.candidate === "Normal"
    ? "No event candidate"
    : `${d.candidate} held for ${d.persistence_s.toFixed(1)} of ${d.persistence_needed_s} s` + (d.trigger ? ": confirmed" : "");
  const cls = d.candidate === "Normal" ? (d.posteriors.Seizure > d.posteriors.Syncope ? "Seizure" : "Syncope") : d.candidate;
  $("llr").innerHTML = BRANCHES.map(([b, name, sensor]) => {
    const l = d.branch_llr[b] ? d.branch_llr[b][cls] : null;
    if (l == null) return `<div class="llr-row"><span>${name} <span class="muted">${sensor}</span></span><div class="llr-track"><div class="llr-zero"></div></div><span class="bar-val muted">off</span></div>`;
    const x = Math.max(-3, Math.min(3, l)), wpc = Math.abs(x) / 6 * 100, lpc = x >= 0 ? 50 : 50 - wpc;
    return `<div class="llr-row"><span>${name} <span class="muted">${sensor}</span></span><div class="llr-track">
      <div class="llr-fill" style="left:${lpc}%;width:${wpc}%;background:var(${CLASS_VAR[cls]})"></div><div class="llr-zero"></div></div>
      <span class="bar-val">${l >= 0 ? "+" : ""}${l.toFixed(1)}</span></div>`;
  }).join("") + `<div class="muted llr-note" style="font-size:12px">bars show evidence for ${cls}; right = for, left = against</div>`;
  const sensors = d.corroborating.length;
  $("corro").innerHTML = `Physical sensors agreeing on ${cls}: <span class="ok">${sensors ? d.corroborating.join(", ") : "none"}</span> (${sensors} of 3; a manoeuvre needs 2)`;
  let al = "";
  if (d.spoof) al += `<div class="alert">Spoofing interlock: camera says unconscious, seat and wheel show an active driver. Camera distrusted for ${d.distrust_s} s.</div>`;
  if (d.override_suppressed) al += `<div class="alert info">Steering torque coincides with clonic motion: it cannot cancel the alert.</div>`;
  if (d.degraded > 0) al += `<div class="alert">${d.mode}</div>`;
  // gateway lines are already itemised in the CAN panel; here only the watchdog speaks
  logs = logs.concat((r.log || []).filter((x) => x.startsWith("[watchdog]"))).slice(-3);
  logs.forEach((x) => (al += `<div class="alert info">${x}</div>`));
  $("alerts").innerHTML = al;
}

const WHY = {
  forge: "attacker without the key: MAC does not verify",
  replay: "frame captured 3 s ago: the freshness counter moved on, so its MAC no longer verifies",
  tamper: "copied frame with modified bits: MAC does not verify",
  implausible: "valid MAC (compromised ECU) but phase 0 to 3 at -4 m/s²: plausibility gate",
};
function renderCan(r) {
  const cmd = [...r.can].reverse().find((x) => x.id === "0x120" && x.verdict === "OK");
  if (cmd) $("latestCmd").innerHTML = `<b>0x120 MRM_Cmd</b> &nbsp; ${cmd.signals}<br>freshness ${cmd.fv} &nbsp; MAC ${cmd.mac} &nbsp; <span class="v-ok">✓ OK</span> &nbsp; <span class="muted">(+0x121 health every 100 ms, 0x122 telematics every 1 s)</span>`;
  const attack = (r.provenance.injected.find((x) => x.startsWith("attack:")) || "").slice(7);
  r.can.filter((x) => !["OK", "-", "status (not authenticated)"].includes(x.verdict)).forEach((x) => {
    rejects.unshift({ ...x, why: WHY[attack] || "" });
  });
  rejects = rejects.slice(0, 40);
  const c = r.counters;
  $("counters").innerHTML = `MAC failures <b>${c.mac}</b> replays <b>${c.replay}</b> wrong ID <b>${c.data_id}</b> implausible <b>${c.implausible}</b>`;
  $("rejects").innerHTML = rejects.slice(0, 12).map((x) =>
    `<li><span>${x.t.toFixed(1)} s</span><span>${x.id}</span><span class="verdict">${x.verdict}</span><span class="why">${x.sender}: ${x.why || x.signals}</span></li>`).join("")
    || `<li><span class="muted">none</span></li>`;
}

function renderEcall(r) {
  const tm = r.telematics, st = tm.state;
  const order = ["Sending", "Acknowledged"];
  let h = `<div class="stage">` + ["Idle", ...order].map((s) =>
    `<span class="${s === st ? "on" : ""} ${order.indexOf(s) >= 0 && order.indexOf(s) < order.indexOf(st) ? "done" : ""}">${s}</span>`).join("") +
    (st === "Queued" ? `<span class="on">Queued: retry every 30 s</span>` : "") + `</div>`;
  if (tm.bearer_log.length) h += `<div>${tm.bearer_log.map(([t, b, ok]) => `${t.toFixed(1)} s ${b} ${ok ? "✓" : "✕"}`).join(" &nbsp; ")}</div>`;
  if (tm.sealed_hex) {
    h += `<div class="subhead">Sealed to the emergency centre: ${tm.sealed_len} B = 33 B ephemeral key + 12 B nonce + 76 B MEC + 16 B tag (ECIES, AES-GCM)</div>`;
    h += `<div class="hex">${tm.sealed_hex.slice(0, 160)}…</div>`;
  }
  if (tm.mec) {
    const m = tm.mec;
    h += `<div class="subhead">Received, decrypted, ECDSA signature and freshness verified</div><dl>
      <dt>Etiology</dt><dd>${m.etiology}</dd><dt>Confidence</dt><dd>${m.confidence.toFixed(2)}</dd>
      <dt>Heart rate</dt><dd>${m.hr_bpm == null ? "–" : m.hr_bpm.toFixed(0) + " bpm"}</dd>
      <dt>Sensors OK</dt><dd>${m.sensors_ok.join(", ")}</dd><dt>Not included</dt><dd>${m.not_included.join("; ")}</dd></dl>`;
  }
  h += tm.denm
    ? `<div class="subhead">V2X DENM to nearby vehicles: cause ${tm.denm.cause} (human problem), sub-cause ${tm.denm.sub_cause} (unavailable): the diagnosis is never broadcast</div>`
    : `<div class="muted">No DENM yet (sent from phase 3)</div>`;
  $("ecall").innerHTML = h;
}

connect();
