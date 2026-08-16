/* Archipelago trajectory viewer — deterministic replay UI.
 *
 * The renderer draws ONLY from (bundle, seq): the replay document's snapshots
 * and the episode's normalized event stream.  No wall-clock, no randomness:
 * scrubbing to seq N always produces the identical picture.  All facts shown
 * in the inspector come from the episode (derived verbatim from raw traces);
 * the town layout is explicitly presentational (see ARCHITECTURE.md).
 */

"use strict";

/* ------------------------------------------------------------- constants */

const GROUP_STYLE = {
  message:   { chip: "g-message",   color: "#7da7e0", label: "message" },
  tool:      { chip: "g-tool",      color: "#d9a05a", label: "tool" },
  lifecycle: { chip: "g-lifecycle", color: "#7fd96a", label: "lifecycle" },
  provider:  { chip: "g-provider",  color: "#c05ad9", label: "provider" },
  artifact:  { chip: "g-artifact",  color: "#d9c85a", label: "artifact" },
  carrier:   { chip: "g-carrier",   color: "#5ad0d9", label: "carrier" },
  outcome:   { chip: "g-outcome",   color: "#d96a6a", label: "outcome" },
  info:      { chip: "g-info",      color: "#8b948b", label: "info" },
};

const ARTIFACT_ICONS = {
  note: "scroll", resource: "chest", carrier: "box", provider_response: "letter",
  seed: "seed", file: "files", artifact: "gear", generic: "gear",
};

const BASE_EVENTS_PER_SEC = 9;

/* ------------------------------------------------------------- state */

const state = {
  bundle: null,      // {episode, replay}
  seq: -1,           // current event index (-1 = before first event)
  playing: false,
  speed: 1,
  pos: 0,            // fractional playback position
  selected: null,    // {type: 'agent'|'artifact'|'carrier'|'event', id}
  hover: null,
  filters: new Set(Object.keys(GROUP_STYLE)),
  sources: [],
};

const el = {
  demoSelect: document.getElementById("demo-select"),
  srcToggle: document.getElementById("src-toggle"),
  srcSelect: document.getElementById("src-select"),
  epTitle: document.getElementById("ep-title"),
  epSub: document.getElementById("ep-sub"),
  epSource: document.getElementById("ep-source-link"),
  canvas: document.getElementById("town"),
  ctx: document.getElementById("town").getContext("2d"),
  tip: document.getElementById("hover-tip"),
  banner: document.getElementById("phase-banner"),
  agentsList: document.getElementById("agents-list"),
  agentsNote: document.getElementById("agents-note"),
  logList: document.getElementById("log-list"),
  logFilters: document.getElementById("log-filters"),
  inspectorTitle: document.getElementById("inspector-title"),
  inspectorBody: document.getElementById("inspector-body"),
  inspectorClose: document.getElementById("inspector-close"),
  timeline: document.getElementById("timeline"),
  tlCtx: document.getElementById("timeline").getContext("2d"),
  readoutTime: document.getElementById("readout-time"),
  readoutEvent: document.getElementById("readout-event"),
  readoutDuration: document.getElementById("readout-duration"),
  btnPlay: document.getElementById("btn-play"),
};

/* ------------------------------------------------------------- helpers */

function $(id) { return document.getElementById(id); }

function esc(text) {
  return String(text ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

function fmtT(seconds) {
  if (!isFinite(seconds)) return "∞";
  return seconds.toFixed(1);
}

function fmtDuration(seconds) {
  const s = Math.round(seconds);
  const m = Math.floor(s / 60);
  return `${m}m ${(s % 60).toString().padStart(2, "0")}s`;
}

function hashStr(text) {
  let h = 2166136261 >>> 0;
  for (let i = 0; i < text.length; i++) {
    h ^= text.charCodeAt(i);
    h = Math.imul(h, 16777619) >>> 0;
  }
  return h;
}

function groupOf(kind) {
  const groups = {
    user_message: "message", assistant_message: "message", system_message: "message",
    tool_message: "message", reasoning_message: "message",
    tool_call: "tool", tool_result: "tool",
    spawn: "lifecycle", teardown: "lifecycle", authorization_revoked: "lifecycle",
    turnover: "lifecycle", phase: "lifecycle",
    provider_request: "provider", provider_response: "provider", network_probe: "provider",
    artifact_create: "artifact", artifact_write: "artifact", artifact_read: "artifact",
    artifact_delete: "artifact",
    carrier_authorize: "carrier", carrier_finalize: "carrier", carrier_read: "carrier",
    carrier_transfer: "carrier",
    reward: "outcome", metric: "outcome", stop: "outcome", failure: "outcome",
  };
  return groups[kind] ?? "info";
}

/* ------------------------------------------------------------- loading */

async function fetchJSON(url) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`${response.status} ${url}`);
  return response.json();
}

async function init() {
  el.demoSelect.addEventListener("change", () => selectDemo(el.demoSelect.value));
  $("btn-play").addEventListener("click", togglePlay);
  $("btn-start").addEventListener("click", () => goto(-1));
  $("btn-end").addEventListener("click", () => goto(eventCount() - 1));
  $("btn-back").addEventListener("click", () => goto(state.seq - 1));
  $("btn-fwd").addEventListener("click", () => goto(state.seq + 1));
  $("speed").addEventListener("change", (e) => { state.speed = parseFloat(e.target.value); });
  el.inspectorClose.addEventListener("click", () => { state.selected = null; renderAll(); });
  document.addEventListener("keydown", onKey);
  el.canvas.addEventListener("mousemove", onCanvasMove);
  el.canvas.addEventListener("mouseleave", () => { state.hover = null; el.tip.hidden = true; });
  el.canvas.addEventListener("click", onCanvasClick);
  el.timeline.addEventListener("mousedown", onTimelineDown);
  window.addEventListener("resize", renderAll);

  buildFilters();
  const demos = await fetchJSON("/api/demos");
  state.demos = demos.demos ?? [];
  el.demoSelect.innerHTML = "";
  for (const demo of state.demos) {
    const option = document.createElement("option");
    option.value = demo.slug;
    option.textContent = `${demo.title} (${demo.events} events)`;
    el.demoSelect.appendChild(option);
  }
  el.srcToggle.addEventListener("change", async (e) => {
    if (e.target.checked) {
      const data = await fetchJSON("/api/sources");
      state.sources = data.sources ?? [];
      el.srcSelect.hidden = false;
      el.srcSelect.innerHTML = "<option value=''>— pick a source file —</option>";
      for (const source of state.sources) {
        const option = document.createElement("option");
        option.value = source.rel;
        option.textContent = `${source.rel} (${source.size} B)`;
        el.srcSelect.appendChild(option);
      }
    } else {
      el.srcSelect.hidden = true;
    }
  });
  el.srcSelect.addEventListener("change", async (e) => {
    if (!e.target.value) return;
    const data = await fetchJSON(`/api/source?path=${encodeURIComponent(e.target.value)}`);
    if (data.error) { el.epSub.textContent = `source error: ${data.error}`; return; }
    applyBundle(data);
    history.replaceState(null, "", `#demo=${el.demoSelect.value || "src"}`);
  });

  const hash = decodeURIComponent(location.hash.replace(/^#/, ""));
  const slug = new URLSearchParams(hash).get("demo") ?? state.demos[0]?.slug;
  if (slug && state.demos.some((d) => d.slug === slug)) {
    el.demoSelect.value = slug;
    await selectDemo(slug);
  } else if (state.demos[0]) {
    await selectDemo(state.demos[0].slug);
  }
  startClock();
}

async function selectDemo(slug) {
  const bundle = await fetchJSON(`/api/demo/${slug}`);
  applyBundle(bundle);
  history.replaceState(null, "", `#demo=${slug}`);
}

function applyBundle(bundle) {
  state.bundle = bundle;
  state.selected = null;
  state.playing = false;
  $("btn-play").textContent = "▶";
  const episode = bundle.episode;
  const replay = bundle.replay;
  el.epTitle.textContent = episode.title;
  const metaBits = [
    `env: ${episode.environment}`,
    episode.model ? `model: ${episode.model}` : null,
    `agents: ${episode.agents.length}`,
    `artifacts: ${episode.artifacts.length}`,
    `carriers: ${episode.carriers.length}`,
    `events: ${episode.events.length}`,
    `duration: ${fmtDuration(replay.duration)}s`,
    episode.meta?.condition ? `condition: ${episode.meta.condition}` : null,
  ].filter(Boolean);
  el.epSub.textContent = metaBits.join(" · ");
  el.epSource.textContent = `read-only · ${episode.source_kind}`;
  el.epSource.title = `source: ${episode.source}`;
  el.epSource.href = "#";
  buildGrass();
  const hash = decodeURIComponent(location.hash.replace(/^#/, ""));
  const seq = parseInt(new URLSearchParams(hash).get("seq") ?? "", 10);
  goto(isFinite(seq) && seq >= 0 && seq < eventCount() ? seq : -1);
  renderAll();
}

function eventCount() { return state.bundle ? state.bundle.episode.events.length : 0; }

/* ------------------------------------------------------------- playback */

function startClock() {
  let last = performance.now();
  setInterval(() => {
    if (!state.playing || !state.bundle) return;
    const now = performance.now();
    const dt = (now - last) / 1000;
    state.pos += dt * BASE_EVENTS_PER_SEC * state.speed;
    const target = Math.min(Math.floor(state.pos), eventCount() - 1);
    if (target !== state.seq) {
      goto(target);
      if (target >= eventCount() - 1) togglePlay();
    }
  }, 50);
  last = performance.now();
}

function togglePlay() {
  if (!state.bundle) return;
  state.playing = !state.playing;
  if (state.playing) {
    state.pos = state.seq < 0 ? 0 : state.seq;
    $("btn-play").textContent = "⏸";
  } else {
    state.pos = state.seq;
    $("btn-play").textContent = "▶";
  }
}

function goto(seq) {
  const count = eventCount();
  if (count === 0) return;
  state.seq = Math.max(-1, Math.min(count - 1, seq));
  state.pos = state.seq;
  renderAll();
}

function onKey(event) {
  switch (event.key) {
    case " ":
      event.preventDefault();
      togglePlay();
      break;
    case "ArrowLeft":
      event.preventDefault();
      goto(state.seq - (event.shiftKey ? 10 : 1));
      break;
    case "ArrowRight":
      event.preventDefault();
      goto(state.seq + (event.shiftKey ? 10 : 1));
      break;
    case "Home":
      event.preventDefault();
      goto(-1);
      break;
    case "End":
      event.preventDefault();
      goto(eventCount() - 1);
      break;
  }
}

/* ------------------------------------------------------------- rendering */

function renderAll() {
  if (!state.bundle) return;
  drawTown();
  drawTimeline();
  renderAgentsPanel();
  renderLog();
  renderInspector();
  updateReadout();
}

function updateReadout() {
  el.readoutTime.textContent = `t=${state.seq < 0 ? 0.0 : state.bundle.replay.sequences[state.seq].t}s`;
  el.readoutEvent.textContent = `event ${state.seq + 1}/${eventCount()}`;
  el.readoutDuration.textContent = `total ${fmtDuration(state.bundle.replay.duration)}s · ${eventCount()} events`;
}

function buildGrass() {
  const canvas = document.createElement("canvas");
  canvas.width = 1000;
  canvas.height = 700;
  const ctx = canvas.getContext("2d");
  ctx.fillStyle = "#33501f";
  ctx.fillRect(0, 0, 1000, 700);
  const seed = hashStr(state.bundle.episode.id);
  let rngState = seed >>> 0;
  const rand = () => {
    rngState ^= rngState << 13; rngState >>>= 0;
    rngState ^= rngState >> 17;
    rngState ^= rngState << 5; rngState >>>= 0;
    return rngState / 4294967296;
  };
  for (let i = 0; i < 2600; i++) {
    const x = rand() * 1000, y = rand() * 700, s = rand() * 2.4 + 0.6;
    ctx.fillStyle = rand() > 0.5 ? "rgba(70,110,45,0.55)" : "rgba(45,80,30,0.55)";
    ctx.fillRect(x, y, s, s);
  }
  for (let i = 0; i < 26; i++) {
    const x = 30 + rand() * 940, y = 30 + rand() * 640, r = 6 + rand() * 10;
    ctx.fillStyle = "rgba(30,52,20,0.8)";
    ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2); ctx.fill();
  }
  state._grass = canvas;
}

function drawTown() {
  const ctx = el.ctx;
  const replay = state.bundle.replay;
  ctx.clearRect(0, 0, 1000, 700);
  if (state._grass) ctx.drawImage(state._grass, 0, 0);

  // paths from plaza to facilities
  ctx.lineCap = "round";
  ctx.strokeStyle = "rgba(150,120,70,0.35)";
  ctx.lineWidth = 14;
  for (const facility of Object.values(replay.facilities)) {
    ctx.beginPath();
    ctx.moveTo(replay.plaza.x, replay.plaza.y);
    ctx.lineTo(facility.x, facility.y);
    ctx.stroke();
  }
  ctx.strokeStyle = "rgba(170,140,85,0.28)";
  ctx.lineWidth = 3;
  for (const facility of Object.values(replay.facilities)) {
    ctx.beginPath();
    ctx.moveTo(replay.plaza.x, replay.plaza.y);
    ctx.lineTo(facility.x, facility.y);
    ctx.stroke();
  }

  // plaza
  ctx.fillStyle = "#5c513a";
  ctx.beginPath(); ctx.arc(replay.plaza.x, replay.plaza.y, 46, 0, Math.PI * 2); ctx.fill();
  ctx.fillStyle = "#6d6045";
  ctx.beginPath(); ctx.arc(replay.plaza.x, replay.plaza.y, 34, 0, Math.PI * 2); ctx.fill();
  ctx.strokeStyle = "rgba(240,230,200,0.35)";
  ctx.beginPath(); ctx.arc(replay.plaza.x, replay.plaza.y, 26, 0, Math.PI * 2); ctx.stroke();

  drawCarriers(ctx, replay);
  drawFacilities(ctx, replay);
  drawArtifacts(ctx, replay);
  drawAgents(ctx, replay);
  drawEffects(ctx, replay);
  drawSelectionAndHover(ctx, replay);
  drawPhaseBanner();
}

function drawFacilities(ctx, replay) {
  const hue = 24;
  for (const facility of Object.values(replay.facilities)) {
    const { x, y } = facility;
    const w = 92, h = 62;
    // shadow
    ctx.fillStyle = "rgba(0,0,0,0.25)";
    roundRect(ctx, x - w / 2 + 4, y - h / 2 + 5, w, h, 8); ctx.fill();
    // body
    ctx.fillStyle = `hsl(${hue} 22% 42%)`;
    roundRect(ctx, x - w / 2, y - h / 2, w, h, 8); ctx.fill();
    // wall band
    ctx.fillStyle = `hsl(${hue} 24% 50%)`;
    roundRect(ctx, x - w / 2, y - h / 2 + 18, w, h - 26, [0, 0, 8, 8]); ctx.fill();
    // roof
    ctx.fillStyle = `hsl(${hue} 30% 30%)`;
    ctx.beginPath();
    ctx.moveTo(x - w / 2 - 6, y - h / 2 + 12);
    ctx.lineTo(x, y - h / 2 - 14);
    ctx.lineTo(x + w / 2 + 6, y - h / 2 + 12);
    ctx.closePath(); ctx.fill();
    // door + window
    ctx.fillStyle = "#2c2417";
    roundRect(ctx, x - 9, y + 4, 18, 24, 4); ctx.fill();
    ctx.fillStyle = "rgba(255,240,180,0.75)";
    roundRect(ctx, x - w / 2 + 14, y - h / 2 + 30, 16, 12, 3); ctx.fill();
    roundRect(ctx, x + w / 2 - 30, y - h / 2 + 30, 16, 12, 3); ctx.fill();
    // sign
    ctx.font = "600 10px system-ui";
    ctx.textAlign = "center";
    ctx.fillStyle = "rgba(16,20,12,0.85)";
    roundRect(ctx, x - 44, y + h / 2 + 2, 88, 17, 9); ctx.fill();
    ctx.fillStyle = "#e8e6d8";
    ctx.fillText(facility.kind === "generic" ? facility.kind.replace("generic", "generic") : facility.kind, x, y + h / 2 + 14);
  }
}

function drawArtifacts(ctx, replay) {
  const snapshot = snapshotAt(state.seq);
  if (!snapshot) return;
  for (const artifact of Object.values(snapshot.artifacts)) {
    const { x, y } = artifact;
    const age = state.seq - artifact.created_seq;
    const fadingIn = artifact.created_seq >= 0 && age >= 0 && age < 8;
    const alpha = fadingIn ? Math.min(1, age / 4 + 0.25) : 1;
    if (!artifact.live && !fadingIn) continue;
    ctx.globalAlpha = alpha;
    ctx.fillStyle = "rgba(0,0,0,0.25)";
    ctx.beginPath(); ctx.ellipse(x + 2, y + 13, 8, 4, 0, 0, Math.PI * 2); ctx.fill();
    drawArtifactIcon(ctx, artifact.kind, x, y);
    ctx.globalAlpha = 1;
    ctx.font = "10px system-ui";
    ctx.textAlign = "center";
    ctx.fillStyle = "rgba(232,230,216,0.85)";
    ctx.fillText(shortName(artifact.name, 14), x, y + 28);
  }
}

function drawArtifactIcon(ctx, kind, x, y) {
  const icon = ARTIFACT_ICONS[kind] ?? "gear";
  ctx.save();
  ctx.translate(x, y);
  ctx.fillStyle = "rgba(0,0,0,0.35)";
  ctx.beginPath(); ctx.arc(0, 1, 11, 0, Math.PI * 2); ctx.fill();
  if (icon === "scroll") {
    ctx.fillStyle = "#e8e0c4";
    roundRect(ctx, -7, -9, 14, 18, 3); ctx.fill();
    ctx.strokeStyle = "#a99f7d"; ctx.lineWidth = 1;
    ctx.strokeRect(-7, -9, 14, 18);
    ctx.strokeStyle = "#8a7f5e";
    ctx.beginPath(); ctx.moveTo(-4, -5); ctx.lineTo(4, -5);
    ctx.moveTo(-4, -1); ctx.lineTo(4, -1);
    ctx.moveTo(-4, 3); ctx.lineTo(4, 3); ctx.stroke();
  } else if (icon === "chest") {
    ctx.fillStyle = "#8a5a2c";
    roundRect(ctx, -9, -6, 18, 13, 3); ctx.fill();
    ctx.fillStyle = "#a96f39";
    roundRect(ctx, -9, -9, 18, 6, 3); ctx.fill();
    ctx.fillStyle = "#d9b35a";
    roundRect(ctx, -2, -4, 4, 6, 1); ctx.fill();
  } else if (icon === "box") {
    ctx.fillStyle = "#5a6f74";
    roundRect(ctx, -9, -7, 18, 14, 2); ctx.fill();
    ctx.strokeStyle = "#9fc7cd"; ctx.lineWidth = 1.4;
    ctx.beginPath(); ctx.moveTo(-9, -2); ctx.lineTo(9, -2); ctx.stroke();
  } else if (icon === "letter") {
    ctx.fillStyle = "#e8e0c4";
    roundRect(ctx, -9, -7, 18, 14, 2); ctx.fill();
    ctx.strokeStyle = "#8a7f5e";
    ctx.beginPath(); ctx.moveTo(-9, -7); ctx.lineTo(0, 1); ctx.lineTo(9, -7); ctx.stroke();
  } else if (icon === "seed") {
    ctx.fillStyle = "#7a5a2c";
    ctx.beginPath(); ctx.arc(0, -2, 7, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = "#5c4422";
    ctx.beginPath(); ctx.arc(0, 3, 5, 0, Math.PI * 2); ctx.fill();
  } else if (icon === "files") {
    ctx.fillStyle = "#cfd6cf";
    roundRect(ctx, -8, -7, 15, 16, 2); ctx.fill();
    ctx.fillStyle = "#aeb6ae";
    roundRect(ctx, -6, -9, 13, 16, 2); ctx.fill();
  } else {
    ctx.fillStyle = "#8b948b";
    ctx.beginPath(); ctx.arc(0, 0, 8, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = "#c9d1c9";
    ctx.beginPath(); ctx.arc(0, 0, 3.4, 0, Math.PI * 2); ctx.fill();
  }
  ctx.restore();
}

function drawCarriers(ctx, replay) {
  const snapshot = snapshotAt(state.seq);
  if (!snapshot) return;
  const episodes = state.bundle.episode;
  for (const carrier of Object.values(snapshot.carriers)) {
    if (!carrier.active) continue;
    const from = snapshot.agents[carrier.from];
    const to = snapshot.agents[carrier.to];
    let x1, y1, x2, y2;
    if (from) { x1 = from.x; y1 = from.y; }
    else if (carrier.artifact_ids[0]) {
      const art = snapshot.artifacts[carrier.artifact_ids[0]];
      x1 = art ? art.x : replay.plaza.x; y1 = art ? art.y : replay.plaza.y;
    } else { x1 = replay.plaza.x; y1 = replay.plaza.y; }
    if (to) { x2 = to.x; y2 = to.y; }
    else if (carrier.artifact_ids[0]) {
      const art = snapshot.artifacts[carrier.artifact_ids[0]];
      x2 = art ? art.x : replay.plaza.x; y2 = art ? art.y : replay.plaza.y;
    } else { x2 = replay.plaza.x; y2 = replay.plaza.y; }
    // dashed animated transfer line
    const kind = carrier.kind === "provider" ? "#c05ad9" : "#5ad0d9";
    const phase = ((state.seq * 2) % 16);
    ctx.save();
    ctx.strokeStyle = "rgba(220,240,245,0.30)";
    ctx.lineWidth = 8;
    ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke();
    ctx.setLineDash([8, 7]);
    ctx.lineDashOffset = -phase;
    ctx.strokeStyle = kind;
    ctx.lineWidth = 2.6;
    ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke();
    ctx.setLineDash([]);
    // arrowhead
    const angle = Math.atan2(y2 - y1, x2 - x1);
    ctx.fillStyle = kind;
    ctx.beginPath();
    ctx.moveTo(x2, y2);
    ctx.lineTo(x2 - 11 * Math.cos(angle - 0.4), y2 - 11 * Math.sin(angle - 0.4));
    ctx.lineTo(x2 - 11 * Math.cos(angle + 0.4), y2 - 11 * Math.sin(angle + 0.4));
    ctx.closePath(); ctx.fill();
    ctx.restore();
  }
}

function drawAgents(ctx, replay) {
  const snapshot = snapshotAt(state.seq);
  if (!snapshot) return;
  const episode = state.bundle.episode;
  for (const agent of Object.values(snapshot.agents)) {
    const { x, y } = agent;
    const hasSpawned = agent.spawn_seq >= 0;
    // shadow
    ctx.fillStyle = "rgba(0,0,0,0.28)";
    ctx.beginPath(); ctx.ellipse(x + 2, y + 13, 11, 5, 0, 0, Math.PI * 2); ctx.fill();
    // body
    ctx.fillStyle = `hsl(${agent.hue} 55% 55%)`;
    ctx.beginPath(); ctx.arc(x, y, 11, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = `hsl(${agent.hue} 55% 68%)`;
    ctx.beginPath(); ctx.arc(x - 2, y - 3, 5.5, 0, Math.PI * 2); ctx.fill();
    ctx.strokeStyle = "rgba(0,0,0,0.4)";
    ctx.lineWidth = 1.2;
    ctx.stroke();
    // face
    ctx.fillStyle = "#1a1a1a";
    ctx.beginPath(); ctx.arc(x - 3.5, y - 3.5, 1.4, 0, Math.PI * 2); ctx.fill();
    ctx.beginPath(); ctx.arc(x + 2.5, y - 3.5, 1.4, 0, Math.PI * 2); ctx.fill();
    // alive/dead marker
    if (!agent.alive && hasSpawned) {
      ctx.strokeStyle = "rgba(217,106,90,0.9)";
      ctx.lineWidth = 3;
      ctx.beginPath();
      ctx.moveTo(x - 7, y - 7); ctx.lineTo(x + 7, y + 7);
      ctx.moveTo(x + 7, y - 7); ctx.lineTo(x - 7, y + 7);
      ctx.stroke();
      ctx.globalAlpha = 0.55;
    }
    // generation rings above head
    const rings = Math.max(0, agent.generation);
    for (let i = 0; i < rings; i++) {
      ctx.strokeStyle = `hsl(${agent.hue} 65% 65%)`;
      ctx.lineWidth = 2;
      ctx.beginPath(); ctx.arc(x, y - 22 - i * 7, 4, 0, Math.PI * 2); ctx.stroke();
    }
    // tool-busy glyph
    if (busyUntil(agent) > state.seq) {
      ctx.fillStyle = "#d9a05a";
      ctx.font = "600 13px system-ui";
      ctx.textAlign = "center";
      ctx.fillText("⚙", x, y - 24 - rings * 7);
    }
    // name
    ctx.globalAlpha = agent.alive ? 1 : 0.55;
    ctx.font = "600 11px system-ui";
    ctx.textAlign = "center";
    ctx.fillStyle = "rgba(232,230,216,0.95)";
    ctx.fillText(shortName(agent.name, 15), x, y + 30);
    ctx.globalAlpha = 1;
  }
}

/* effects window: deterministic flashes derived from events near seq */
function busyUntil(agent) {
  const events = state.bundle.episode.events;
  for (let i = state.seq; i >= Math.max(0, state.seq - 12); i--) {
    const event = events[i];
    if (!event || event.agent_id !== agent.id) continue;
    if (event.kind === "tool_call") return i + 6;
    if (event.kind === "spawn") break;
  }
  return -1;
}

function drawEffects(ctx, replay) {
  const events = state.bundle.episode.events;
  const snapshot = snapshotAt(state.seq);
  if (!snapshot) return;
  const window = 10;
  for (let i = Math.max(0, state.seq - window); i <= state.seq; i++) {
    const event = events[i];
    if (!event) continue;
    const age = state.seq - i;
    const fade = 1 - age / window;
    const agent = event.agent_id ? snapshot.agents[event.agent_id] : null;
    const at = agent ? { x: agent.x, y: agent.y } : null;
    if (!at) continue;
    if (event.kind === "spawn") {
      const r = 14 + age * 6;
      ctx.strokeStyle = `rgba(127,217,106,${0.9 * fade})`;
      ctx.lineWidth = 3;
      ctx.beginPath(); ctx.arc(at.x, at.y, r, 0, Math.PI * 2); ctx.stroke();
      ctx.fillStyle = `rgba(127,217,106,${0.75 * fade})`;
      ctx.beginPath();
      ctx.moveTo(at.x, at.y - 34 - age * 3);
      ctx.lineTo(at.x - 6, at.y - 46 - age * 3);
      ctx.lineTo(at.x + 6, at.y - 46 - age * 3);
      ctx.closePath(); ctx.fill();
    } else if (event.kind === "teardown") {
      const r = 14 + age * 7;
      ctx.strokeStyle = `rgba(217,106,90,${0.9 * fade})`;
      ctx.lineWidth = 3;
      ctx.beginPath(); ctx.arc(at.x, at.y, r, 0, Math.PI * 2); ctx.stroke();
    } else if (event.kind === "artifact_write" || event.kind === "artifact_read") {
      const record = event.payload.record ?? {};
      const artId = event.payload.artifact_id ?? "";
      let art = snapshot.artifacts[artId];
      if (!art && record.argument) {
        art = Object.values(snapshot.artifacts).find((a) => a.name === record.argument);
      }
      if (art) {
        const color = event.kind === "artifact_write" ? "217,190,90" : "90,208,217";
        ctx.strokeStyle = `rgba(${color},${0.85 * fade})`;
        ctx.lineWidth = 2.5;
        ctx.beginPath(); ctx.arc(art.x, art.y, 13 + age * 3, 0, Math.PI * 2); ctx.stroke();
        ctx.beginPath();
        ctx.moveTo(at.x, at.y);
        ctx.lineTo(art.x, art.y);
        ctx.stroke();
      }
    } else if (event.kind === "phase") {
      // handled by banner
    }
  }
}

function drawPhaseBanner() {
  const events = state.bundle.episode.events;
  let latest = null;
  for (let i = state.seq; i >= Math.max(0, state.seq - 4); i--) {
    const event = events[i];
    if (event && event.kind === "phase") { latest = event; break; }
  }
  if (latest) {
    el.banner.hidden = false;
    el.banner.textContent = `✦ ${latest.title}`;
  } else {
    el.banner.hidden = true;
  }
}

function drawSelectionAndHover(ctx, replay) {
  const snapshot = snapshotAt(state.seq);
  if (!snapshot) return;
  const ring = (x, y, color) => {
    ctx.strokeStyle = color;
    ctx.lineWidth = 2.5;
    ctx.beginPath(); ctx.arc(x, y, 17, 0, Math.PI * 2); ctx.stroke();
  };
  if (state.selected && state.selected.type === "agent") {
    const agent = snapshot.agents[state.selected.id];
    if (agent) ring(agent.x, agent.y, "rgba(200,163,78,0.95)");
  }
  if (state.hover && state.hover.type === "agent") {
    const agent = snapshot.agents[state.hover.id];
    if (agent) ring(agent.x, agent.y, "rgba(232,230,216,0.5)");
  }
}

function snapshotAt(seq) {
  if (!state.bundle) return null;
  const replay = state.bundle.replay;
  if (seq < 0) return replay.sequences[0];
  if (seq >= replay.sequences.length) return null;
  return replay.sequences[seq];
}

function roundRect(ctx, x, y, w, h, r) {
  const radius = typeof r === "number" ? [r, r, r, r] : r;
  ctx.beginPath();
  ctx.moveTo(x + radius[0], y);
  ctx.lineTo(x + w - radius[1], y);
  ctx.quadraticCurveTo(x + w, y, x + w, y + radius[1]);
  ctx.lineTo(x + w, y + h - radius[2]);
  ctx.quadraticCurveTo(x + w, y + h, x + w - radius[2], y + h);
  ctx.lineTo(x + radius[3], y + h);
  ctx.quadraticCurveTo(x, y + h, x, y + h - radius[3]);
  ctx.lineTo(x, y + radius[0]);
  ctx.quadraticCurveTo(x, y, x + radius[0], y);
  ctx.closePath();
}

function shortName(name, max) {
  name = String(name ?? "?");
  return name.length > max ? name.slice(0, max - 1) + "…" : name;
}

/* ------------------------------------------------------------- interaction */

function canvasScale() {
  return el.canvas.width / el.canvas.clientWidth;
}

function onCanvasMove(event) {
  if (!state.bundle) return;
  const rect = el.canvas.getBoundingClientRect();
  const x = (event.clientX - rect.left) * canvasScale();
  const y = (event.clientY - rect.top) * canvasScale();
  const hit = hitTest(x, y);
  state.hover = hit;
  if (!hit) { el.tip.hidden = true; return; }
  const snapshot = snapshotAt(state.seq);
  el.tip.hidden = false;
  el.tip.style.left = `${event.clientX - rect.left + 14}px`;
  el.tip.style.top = `${event.clientY - rect.top + 8}px`;
  if (hit.type === "agent") {
    const agent = snapshot.agents[hit.id];
    el.tip.innerHTML = [
      `<b>${esc(agent.name)}</b>`,
      `gen ${agent.generation}${agent.lineage_id ? ` · lineage ${esc(shortName(agent.lineage_id, 8))}` : ""}`,
      agent.alive ? "alive" : `dead @ event ${agent.death_seq}`,
      agent.tool_calls ? `${agent.tool_calls} tool calls` : "",
      agent.artifact_reads + agent.artifact_writes ? `${agent.artifact_reads} reads · ${agent.artifact_writes} writes` : "",
    ].filter(Boolean).join("<br>");
  } else if (hit.type === "artifact") {
    const artifact = snapshot.artifacts[hit.id];
    el.tip.innerHTML = [
      `<b>${esc(artifact.name)}</b>`,
      `kind: ${artifact.kind} · ${artifact.facility}`,
      artifact.created_seq >= 0 ? `created @ event ${artifact.created_seq}` : "present from start",
      artifact.owner_agent ? `owner: ${esc(artifact.owner_agent)}` : "",
    ].filter(Boolean).join("<br>");
  } else if (hit.type === "carrier") {
    const carrier = snapshot.carriers[hit.id];
    el.tip.innerHTML = `<b>carrier</b><br>${esc(carrier.from || "facility")} → ${esc(carrier.to || "facility")}`;
  }
}

function hitTest(x, y) {
  const snapshot = snapshotAt(state.seq);
  if (!snapshot) return null;
  for (const agent of Object.values(snapshot.agents)) {
    if (Math.hypot(x - agent.x, y - agent.y) < 24) return { type: "agent", id: agent.id };
  }
  for (const artifact of Object.values(snapshot.artifacts)) {
    if (artifact.live && Math.hypot(x - artifact.x, y - artifact.y) < 20) {
      return { type: "artifact", id: artifact.id };
    }
  }
  for (const carrier of Object.values(snapshot.carriers)) {
    if (carrier.active) return { type: "carrier", id: carrier.id };
  }
  return null;
}

function onCanvasClick() {
  if (!state.hover) { state.selected = null; renderAll(); return; }
  state.selected = state.hover;
  renderAll();
}

function onTimelineDown(event) {
  if (!state.bundle) return;
  const rect = el.timeline.getBoundingClientRect();
  const x = (event.clientX - rect.left) / rect.width;
  goto(Math.round(x * (eventCount() - 1)) - 1);
  const move = (e) => {
    const r = el.timeline.getBoundingClientRect();
    goto(Math.round(((e.clientX - r.left) / r.width) * (eventCount() - 1)) - 1);
  };
  const up = () => {
    document.removeEventListener("mousemove", move);
    document.removeEventListener("mouseup", up);
  };
  document.addEventListener("mousemove", move);
  document.addEventListener("mouseup", up);
}

/* ------------------------------------------------------------- timeline */

function drawTimeline() {
  const ctx = el.tlCtx;
  const w = el.timeline.width, h = el.timeline.height;
  ctx.clearRect(0, 0, w, h);
  const events = state.bundle.episode.events;
  const count = eventCount();
  if (count === 0) return;
  const pad = 14;
  const trackY = h / 2;
  ctx.strokeStyle = "rgba(232,230,216,0.15)";
  ctx.lineWidth = 4;
  ctx.beginPath(); ctx.moveTo(pad, trackY); ctx.lineTo(w - pad, trackY); ctx.stroke();
  // dense markers: sample up to ~1200 dots
  const step = Math.max(1, Math.ceil(count / 1200));
  for (let i = 0; i < count; i += step) {
    const event = events[i];
    const group = groupOf(event.kind);
    const x = pad + (i / (count - 1)) * (w - 2 * pad);
    ctx.fillStyle = GROUP_STYLE[group].color;
    ctx.globalAlpha = 0.8;
    ctx.beginPath(); ctx.arc(x, trackY, 2, 0, Math.PI * 2); ctx.fill();
  }
  ctx.globalAlpha = 1;
  // playhead
  const pos = state.seq < 0 ? 0 : (state.seq + 1) / count;
  const px = pad + pos * (w - 2 * pad);
  ctx.fillStyle = "#c8a34e";
  ctx.beginPath();
  ctx.moveTo(px, 4);
  ctx.lineTo(px - 7, 14);
  ctx.lineTo(px + 7, 14);
  ctx.closePath(); ctx.fill();
  ctx.strokeStyle = "rgba(0,0,0,0.4)";
  ctx.lineWidth = 1;
  ctx.beginPath(); ctx.moveTo(px, 14); ctx.lineTo(px, h - 6); ctx.stroke();
}

/* ------------------------------------------------------------- panels */

function buildFilters() {
  for (const [group, style] of Object.entries(GROUP_STYLE)) {
    const button = document.createElement("button");
    button.textContent = style.label;
    button.classList.add("on");
    button.addEventListener("click", () => {
      if (state.filters.has(group)) {
        state.filters.delete(group);
        button.classList.remove("on");
      } else {
        state.filters.add(group);
        button.classList.add("on");
      }
      renderLog();
    });
    el.logFilters.appendChild(button);
  }
}

function renderAgentsPanel() {
  if (!state.bundle) return;
  const snapshot = snapshotAt(state.seq);
  el.agentsList.innerHTML = "";
  const agents = state.bundle.episode.agents;
  const alive = agents.filter((a) => snapshot?.agents[a.id]?.alive).length;
  el.agentsNote.textContent = `${alive}/${agents.length} alive`;
  for (const agent of agents) {
    const s = snapshot?.agents[agent.id];
    const row = document.createElement("div");
    row.className = "agent-row" + (s && !s.alive && s.spawn_seq >= 0 ? " agent-dead" : "")
      + (state.selected?.type === "agent" && state.selected.id === agent.id ? " selected" : "");
    const dot = document.createElement("span");
    dot.className = "agent-dot";
    dot.style.background = s ? `hsl(${s.hue} 55% 55%)` : "#555";
    const name = document.createElement("span");
    name.className = "agent-name";
    name.textContent = agent.name;
    name.title = `source id: ${agent.source_id}`;
    const meta = document.createElement("span");
    meta.className = "agent-meta";
    meta.textContent = s
      ? `${s.tool_calls}⌘ ${s.artifact_reads}◑ ${s.artifact_writes}◍`
      : "—";
    const rings = document.createElement("span");
    rings.className = "agent-rings";
    for (let i = 0; i < Math.max(0, agent.generation); i++) {
      rings.appendChild(document.createElement("i"));
    }
    row.append(dot, name, rings, meta);
    row.addEventListener("click", () => {
      state.selected = { type: "agent", id: agent.id };
      renderAll();
    });
    el.agentsList.appendChild(row);
  }
}

function renderLog() {
  if (!state.bundle) return;
  el.logList.innerHTML = "";
  const events = state.bundle.episode.events;
  const shown = [];
  for (let i = events.length - 1; i >= 0 && shown.length < 300; i--) {
    const event = events[i];
    if (!state.filters.has(groupOf(event.kind))) continue;
    shown.push(event);
  }
  for (const event of shown) {
    const row = document.createElement("div");
    row.className = "log-row" + (event.seq === state.seq ? " active" : "");
    const group = groupOf(event.kind);
    const seq = document.createElement("span");
    seq.className = "log-seq"; seq.textContent = String(event.seq);
    const t = document.createElement("span");
    t.className = "log-t"; t.textContent = `t${event.t.toFixed(1)}`;
    const kind = document.createElement("span");
    kind.className = `log-kind ${GROUP_STYLE[group].chip}`;
    kind.textContent = event.kind;
    const title = document.createElement("span");
    title.className = "log-title"; title.textContent = event.title; title.title = event.title;
    const detail = document.createElement("span");
    detail.className = "log-detail"; detail.textContent = event.detail || ""; detail.title = event.detail;
    row.append(seq, t, kind, title, detail);
    row.addEventListener("click", () => {
      state.selected = { type: "event", id: event.seq };
      goto(event.seq);
    });
    el.logList.appendChild(row);
  }
}

function renderInspector() {
  if (!state.selected) {
    el.inspectorTitle.textContent = "Inspector";
    el.inspectorBody.innerHTML = "<div class='insp'><p style='color:var(--ink-dim)'>Click an agent, artifact, carrier, or log event to inspect it.</p></div>";
    return;
  }
  const { type, id } = state.selected;
  if (type === "agent") return inspectAgent(id);
  if (type === "artifact") return inspectArtifact(id);
  if (type === "carrier") return inspectCarrier(id);
  if (type === "event") return inspectEvent(id);
}

function kv(rows) {
  const dl = document.createElement("dl");
  dl.className = "kv";
  for (const [key, value] of rows) {
    const dt = document.createElement("dt"); dt.textContent = key;
    const dd = document.createElement("dd"); dd.textContent = value ?? "—";
    dl.append(dt, dd);
  }
  return dl;
}

function rawBlock(value) {
  const pre = document.createElement("pre");
  pre.className = "raw";
  pre.textContent = typeof value === "string" ? value : JSON.stringify(value, null, 2);
  return pre;
}

function inspectAgent(agentId) {
  const agent = state.bundle.episode.agent(agentId);
  const snapshot = snapshotAt(state.seq);
  const s = snapshot?.agents[agentId];
  el.inspectorTitle.textContent = "Agent";
  const box = document.createElement("div");
  box.className = "insp";
  const head = document.createElement("h3");
  head.textContent = agent.name;
  box.appendChild(head);
  const rows = [
    ["role", agent.role],
    ["lineage", agent.lineage_id || "—"],
    ["generation", agent.generation],
    ["status", s ? (s.alive ? "alive" : "retired") : "—"],
    ["spawn event", s && s.spawn_seq >= 0 ? `#${s.spawn_seq}` : "pre-existing"],
    ["retired at", s && s.death_seq >= 0 ? `#${s.death_seq}` : "—"],
    ["tool calls", s?.tool_calls ?? 0],
    ["artifact reads", s?.artifact_reads ?? 0],
    ["artifact writes", s?.artifact_writes ?? 0],
    ["source id", agent.source_id || "—"],
    ["model", agent.attributes.model || "—"],
  ];
  for (const [key, value] of Object.entries(agent.attributes)) {
    if (key === "model" || key === "record") continue;
    if (typeof value === "object") continue;
    rows.push([key, String(value)]);
  }
  box.appendChild(kv(rows));
  const raw = agent.attributes.record;
  if (raw) {
    const h3 = document.createElement("h3"); h3.textContent = "raw record (from evidence)";
    box.appendChild(h3);
    box.appendChild(rawBlock(raw));
  }
  el.inspectorBody.innerHTML = "";
  el.inspectorBody.appendChild(box);
}

function inspectArtifact(artifactEntryId) {
  const artifact = state.bundle.episode.artifact(artifactEntryId);
  const snapshot = snapshotAt(state.seq);
  const s = snapshot?.artifacts[artifactEntryId];
  el.inspectorTitle.textContent = "Artifact";
  const box = document.createElement("div");
  box.className = "insp";
  const head = document.createElement("h3");
  head.textContent = artifact.name;
  box.appendChild(head);
  box.appendChild(kv([
    ["kind", artifact.kind],
    ["owner", artifact.agent_id || "—"],
    ["created", artifact.created_at >= 0 ? `event #${artifact.created_at}` : "present from start"],
    ["lineage", artifact.lineage_id || "—"],
    ["generation", artifact.generation],
    ["location", s?.facility ?? "—"],
    ["preview", artifact.content_preview || "—"],
  ]));
  const provenance = artifact.provenance || {};
  if (Object.keys(provenance).length) {
    const h3 = document.createElement("h3"); h3.textContent = "provenance";
    box.appendChild(h3);
    box.appendChild(rawBlock(provenance));
  }
  if (Object.keys(artifact.attributes || {}).length) {
    const h3 = document.createElement("h3"); h3.textContent = "attributes";
    box.appendChild(h3);
    box.appendChild(rawBlock(artifact.attributes));
  }
  el.inspectorBody.innerHTML = "";
  el.inspectorBody.appendChild(box);
}

function inspectCarrier(carrierId) {
  const carrier = state.bundle.episode.carriers.find((c) => c.id === carrierId);
  el.inspectorTitle.textContent = "Carrier";
  if (!carrier) return;
  const box = document.createElement("div");
  box.className = "insp";
  box.appendChild(kv([
    ["kind", carrier.kind],
    ["from", carrier.from_agent_id || "facility"],
    ["to", carrier.to_agent_id || "facility"],
    ["capability", carrier.capability || "—"],
    ["artifacts", carrier.artifact_ids.join(", ")],
  ]));
  if (Object.keys(carrier.attributes || {}).length) {
    const h3 = document.createElement("h3"); h3.textContent = "attributes";
    box.appendChild(h3);
    box.appendChild(rawBlock(carrier.attributes));
  }
  el.inspectorBody.innerHTML = "";
  el.inspectorBody.appendChild(box);
}

function inspectEvent(seq) {
  const event = state.bundle.episode.events[seq];
  el.inspectorTitle.textContent = "Event";
  if (!event) return;
  const box = document.createElement("div");
  box.className = "insp";
  box.appendChild(kv([
    ["seq", event.seq],
    ["t", `${event.t.toFixed(2)}s`],
    ["kind", event.kind],
    ["agent", event.agent_id || "—"],
    ["title", event.title],
    ["detail", event.detail || "—"],
  ]));
  if (Object.keys(event.payload || {}).length) {
    const h3 = document.createElement("h3"); h3.textContent = "verbatim source payload";
    box.appendChild(h3);
    box.appendChild(rawBlock(event.payload));
  }
  el.inspectorBody.innerHTML = "";
  el.inspectorBody.appendChild(box);
}

/* ------------------------------------------------------------- boot */

init().catch((error) => {
  el.epSub.textContent = `load error: ${error}`;
  console.error(error);
});
