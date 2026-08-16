/* Archipelago trajectory viewer — v2 deterministic replay UI.
 *
 * The renderer draws ONLY from (bundle, seq, pos): the scene projection
 * document, the replay snapshots and the normalized event stream.  No
 * wall-clock, no randomness: scrubbing to seq N always reproduces the
 * identical picture.  Movement is choreography — actors walk between
 * stations as a visualization convention for events; the raw payload stays
 * canonical in the inspector (see ARCHITECTURE.md).
 *
 * Scene kinds (bundle.replay.scene): h1_megafacility, parallel_cells,
 * conversation_hall.  Bundles without a scene doc fall back to the v1
 * town renderer (legacy bundles).
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

const BASE_EVENTS_PER_SEC = 2.5;  // comfortable watching speed
const EFFECT_WINDOW = 10;

/* fractional playback position inside an event where a return-home walk
 * starts (actor dwells/acts at the station first) */
const RETURN_HOME_AT = 0.45;

/* ------------------------------------------------------------- state */

const state = {
  bundle: null,
  seq: -1,
  playing: false,
  speed: 1,
  pos: 0,
  eventsPerSec: BASE_EVENTS_PER_SEC,
  selected: null,
  hover: null,
  filters: new Set(Object.keys(GROUP_STYLE)),
  sources: [],
  actors: new Map(),   // actorId -> {home, hue, generation, spawn, exit, timeline}
};

const el = {
  demoSelect: document.getElementById("demo-select"),
  srcBtn: document.getElementById("btn-sources"),
  sceneTag: document.getElementById("scene-tag"),
  fixtureBanner: document.getElementById("fixture-banner"),
  pillFixture: document.getElementById("pill-fixture"),
  srcOpen: document.getElementById("src-open"),
  epTitle: document.getElementById("ep-title"),
  epSub: document.getElementById("ep-sub"),
  canvas: document.getElementById("town"),
  ctx: document.getElementById("town").getContext("2d"),
  tip: document.getElementById("hover-tip"),
  banner: document.getElementById("phase-banner"),
  agentsList: document.getElementById("agents-list"),
  agentsNote: document.getElementById("agents-note"),
  logList: document.getElementById("log"),
  logFilters: document.getElementById("log-filters"),
  inspectorTitle: document.getElementById("inspector-title"),
  inspectorBody: document.getElementById("inspector"),
  inspectorClose: document.getElementById("inspector-close"),
  timeline: document.getElementById("timeline"),
  tlCtx: document.getElementById("timeline").getContext("2d"),
  readoutTime: document.getElementById("readout-time"),
  readoutEvent: document.getElementById("readout-event"),
  readoutDuration: document.getElementById("readout-duration"),
  readoutSpeed: document.getElementById("readout-speed"),
  speed: document.getElementById("scr-speed"),
  legend: document.getElementById("legend"),
  btnPlay: document.getElementById("btn-play"),
};

/* ------------------------------------------------------------- helpers */

function esc(text) {
  return String(text ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
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

function shortName(name, max) {
  name = String(name ?? "?");
  return name.length > max ? name.slice(0, max - 1) + "…" : name;
}

function easeInOut(x) { return x < 0.5 ? 2 * x * x : 1 - Math.pow(-2 * x + 2, 2) / 2; }

/* ------------------------------------------------------------- scene */

function sceneDoc() {
  return state.bundle?.scene ?? state.bundle?.replay?.scene ?? null;
}

function stationOf(scene, id) {
  return scene.stations[id] ?? null;
}

function stationPoint(scene, id) {
  const s = stationOf(scene, id);
  return s ? { x: s.x, y: s.y } : { x: 0, y: 0 };
}

function buildActorIndex() {
  state.actors.clear();
  const scene = sceneDoc();
  if (!scene) return;
  for (const [id, actor] of Object.entries(scene.actors)) {
    state.actors.set(id, {
      home: actor.home, hue: actor.hue, generation: actor.generation,
      spawn: actor.spawn, exit: actor.exit, timeline: [],
    });
  }
  scene.script.forEach((entry, i) => {
    const info = entry.actor ? state.actors.get(entry.actor) : null;
    if (info) info.timeline.push({ i, entry });
  });
  for (const info of state.actors.values()) {
    info.timeline.sort((a, b) => a.i - b.i);
  }
}

function lastEntry(info, seq) {
  if (!info) return null;
  let hit = null;
  for (const item of info.timeline) {
    if (item.i > seq) break;
    hit = item;
  }
  return hit;
}

function firstSpawn(info) {
  if (!info) return null;
  return info.timeline.find((it) => it.entry.phase === "enter") ?? null;
}

function teardownEntry(info) {
  if (!info) return null;
  return info.timeline.find((it) => it.entry.phase === "exit") ?? null;
}

/* Position of an actor at the END of event `seq` (discrete, deterministic). */
function endPosAt(scene, actorId, seq) {
  const info = state.actors.get(actorId);
  const item = lastEntry(info, seq);
  if (!item) return stationPoint(scene, info.home);
  const entry = item.entry;
  if (entry.via.length === 0) {
    // purely local event (bubble/link in place): no movement
    return endPosAt(scene, actorId, seq - 1);
  }
  const target = entry.interact || entry.via[entry.via.length - 1];
  if (entry.return_home && entry.phase !== "enter") return stationPoint(scene, info.home);
  return stationPoint(scene, target);
}

/* Fractional choreography: position during event `seq` given fractional
 * playback pos `frac` in [0,1].  Returns {x, y, walking, progress}. */
function actorVisible(info, seq) {
  if (!info) return false;
  const spawn = firstSpawn(info);
  if (!spawn) return true; // pre-existing actor (controller, etc.)
  const teardown = teardownEntry(info);
  if (teardown) return seq >= spawn.i && seq <= teardown.i;
  return seq >= spawn.i;
}

/* divide the fractional mover from the visibility predicate above */
function actorMove(scene, actorId, seq, frac) {
  const info = state.actors.get(actorId);
  const home = stationPoint(scene, info.home);
  const item = lastEntry(info, seq);
  if (!item) return { x: home.x, y: home.y, walking: false, progress: 1 };
  const entry = item.entry;

  // return-home walks: walk home→station during [0, RETURN_HOME_AT],
  // act at the station at the turning point, then walk back home
  if (entry.return_home && entry.phase !== "enter") {
    const viaIds = entry.via.length ? entry.via : [entry.interact];
    const pts = viaIds.map((id) => stationPoint(scene, id));
    const out = Math.min(1, frac / RETURN_HOME_AT);
    const back = Math.min(1, (frac - RETURN_HOME_AT) / (1 - RETURN_HOME_AT));
    const pOut = easeInOut(out);
    const pBack = easeInOut(back);
    const outP = pts.length >= 2
      ? { x: pts[0].x + (pts[pts.length - 1].x - pts[0].x) * pOut,
          y: pts[0].y + (pts[pts.length - 1].y - pts[0].y) * pOut }
      : { x: pts[0].x, y: pts[0].y };
    return {
      x: outP.x + (pts[0].x - outP.x) * pBack,
      y: outP.y + (pts[0].y - outP.y) * pBack,
      walking: true, progress: frac < RETURN_HOME_AT ? pOut : pBack,
    };
  }

  // walk along waypoint polyline (enter/exit/deposit/retrieve/etc.)
  const viaIds = entry.via.length ? entry.via : (entry.interact ? [entry.interact] : []);
  const pts = viaIds.map((id) => stationPoint(scene, id));
  if (pts.length === 0) return { x: home.x, y: home.y, walking: false, progress: 1 };
  const lens = [];
  let total = 0;
  for (let i = 1; i < pts.length; i++) {
    const d = Math.hypot(pts[i].x - pts[i - 1].x, pts[i].y - pts[i - 1].y);
    lens.push(d); total += d;
  }
  const p = easeInOut(Math.max(0, Math.min(1, frac)));
  const dist = p * total;
  let acc = 0;
  let x = pts[pts.length - 1].x, y = pts[pts.length - 1].y;
  for (let i = 1; i < pts.length; i++) {
    const seg = lens[i - 1];
    if (dist <= acc + seg || i === pts.length - 1) {
      const t = seg === 0 ? 0 : Math.min(1, Math.max(0, (dist - acc) / seg));
      x = pts[i - 1].x + (pts[i].x - pts[i - 1].x) * t;
      y = pts[i - 1].y + (pts[i].y - pts[i - 1].y) * t;
      break;
    }
    acc += seg;
  }
  return { x, y, walking: total > 1, progress: p };
}

/* ------------------------------------------------------------- loading */

async function fetchJSON(url) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`${response.status} ${url}`);
  return response.json();
}

async function init() {
  el.demoSelect.addEventListener("change", () => selectDemo(el.demoSelect.value));
  el.btnPlay.addEventListener("click", togglePlay);
  $("btn-back").addEventListener("click", () => goto(state.seq - 1));
  $("btn-fwd").addEventListener("click", () => goto(state.seq + 1));
  el.speed.addEventListener("input", (e) => {
    state.speed = parseFloat(e.target.value);
    el.readoutSpeed.textContent = `${state.speed.toFixed(2)}×`;
    el.readoutSpeed.hidden = false;
  });
  el.inspectorClose.addEventListener("click", () => { state.selected = null; renderAll(); });
  document.addEventListener("keydown", onKey);
  el.canvas.addEventListener("mousemove", onCanvasMove);
  el.canvas.addEventListener("mouseleave", () => { state.hover = null; el.tip.hidden = true; });
  el.canvas.addEventListener("click", onCanvasClick);
  el.timeline.addEventListener("mousedown", onTimelineDown);
  el.srcBtn.addEventListener("click", toggleSources);
  el.srcOpen.addEventListener("click", () => {
    if (state.srcPath) selectSource(state.srcPath);
  });
  window.addEventListener("resize", renderAll);
  window.addEventListener("hashchange", async () => {
    const hash = decodeURIComponent(location.hash.replace(/^#/, ""));
    const params = new URLSearchParams(hash);
    const slug = params.get("demo");
    const seqParam = params.get("seq");
    const seq = seqParam !== null ? parseInt(seqParam, 10) : null;
    if (slug && el.demoSelect.value !== slug) {
      el.demoSelect.value = slug;
      await selectDemo(slug, seq ?? 0);
    } else if (seq !== null && seq !== state.seq) {
      goto(seq);
    }
  });

  buildFilters();
  buildLegend();
  const demos = await fetchJSON("/api/demos");
  state.demos = demos.demos ?? [];
  el.demoSelect.innerHTML = "";
  for (const demo of state.demos) {
    const option = document.createElement("option");
    option.value = demo.slug;
    option.textContent = `${demo.title} (${demo.events} events)`;
    el.demoSelect.appendChild(option);
  }

  const hash = decodeURIComponent(location.hash.replace(/^#/, ""));
  const params = new URLSearchParams(hash);
  const slug = params.get("demo") ?? state.demos[0]?.slug;
  const seqParam = params.get("seq");
  const initSeq = seqParam !== null ? parseInt(seqParam, 10) : 0;
  if (slug && state.demos.some((d) => d.slug === slug)) {
    el.demoSelect.value = slug;
    await selectDemo(slug, initSeq);
  } else if (state.demos[0]) {
    await selectDemo(state.demos[0].slug, initSeq);
  }
  startClock();
}

function $(id) { return document.getElementById(id); }

async function selectDemo(slug, initialSeq) {
  const bundle = await fetchJSON(`/api/demo/${slug}`);
  state.srcPath = null;
  applyBundle(bundle);
  if (typeof initialSeq === "number" && initialSeq >= 0) {
    goto(initialSeq);
  } else {
    goto(0);
  }
  history.replaceState(null, "", `#demo=${slug}${state.seq >= 0 ? `&seq=${state.seq}` : ""}`);
}

async function selectSource(path) {
  const data = await fetchJSON(`/api/source?path=${encodeURIComponent(path)}`);
  if (data.error) { el.epSub.textContent = `source error: ${data.error}`; return; }
  state.srcPath = path;
  applyBundle(data);
  goto(0);
  el.srcOpen.textContent = shortName(path, 34);
  el.srcOpen.hidden = false;
  history.replaceState(null, "", `#demo=${el.demoSelect.value || "src"}`);
}

function applyBundle(bundle) {
  state.bundle = bundle;
  state.selected = null;
  state.playing = false;
  el.btnPlay.textContent = "▶";
  cleanSources();
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
    `duration: ${fmtDuration(replay.duration)}`,
  ].filter(Boolean);
  el.epSub.textContent = metaBits.join(" · ");
  const isFixture = episode.meta?.fixture === true;
  el.fixtureBanner.hidden = !isFixture;
  el.pillFixture.hidden = !isFixture;
  el.fixtureBanner.classList.toggle('hidden', !isFixture);
  el.pillFixture.classList.toggle('hidden', !isFixture);
  const scene = sceneDoc();
  el.sceneTag.textContent = scene ? scene.scene_kind.replace("_", " · ") : "legacy town";
  el.sceneTag.className = "pill" + (scene ? " scene-" + scene.scene_kind : " scene-legacy");
  buildActorIndex();
  const bounds = sceneDoc()?.bounds;
  if (bounds) {
    const dpr = window.devicePixelRatio || 1;
    el.canvas.width = Math.ceil(bounds.w * dpr);
    el.canvas.height = Math.ceil(bounds.h * dpr);
    el.canvas.style.width = bounds.w + 'px';
    el.canvas.style.height = bounds.h + 'px';
    el.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  } else {
    const dpr = window.devicePixelRatio || 1;
    el.canvas.width = 1000 * dpr;
    el.canvas.height = 700 * dpr;
    el.canvas.style.width = '1000px';
    el.canvas.style.height = '700px';
    el.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }
}

function eventCount() { return state.bundle ? state.bundle.episode.events.length : 0; }

function snapshotAt(seq) {
  if (!state.bundle) return null;
  const replay = state.bundle.replay;
  if (seq < 0) return replay.sequences[0];
  const idx = seq + 1;
  if (idx >= replay.sequences.length) return replay.sequences[replay.sequences.length - 1];
  return replay.sequences[idx];
}

/* ------------------------------------------------------------- playback */

function startClock() {
  let last = performance.now();
  function tick(now) {
    requestAnimationFrame(tick);
    if (!state.playing || !state.bundle) { last = now; return; }
    const dt = Math.min(0.1, Math.max(0, (now - last) / 1000));
    last = now;
    // Advance the fractional position
    state.pos += dt * state.eventsPerSec * state.speed;
    const target = Math.min(Math.floor(state.pos), eventCount() - 1);
    if (target >= eventCount() - 1) {
      state.pos = eventCount() - 1;
      state.seq = eventCount() - 1;
      togglePlay();
    }
    if (target !== state.seq) {
      state.seq = Math.max(-1, target);
    }
    renderAll();
  }
  requestAnimationFrame(tick);
}

function togglePlay() {
  if (!state.bundle) return;
  state.playing = !state.playing;
  if (state.playing) {
    if (state.seq >= eventCount() - 1) state.pos = 0;
    else state.pos = state.seq < 0 ? 0 : state.seq;
    el.btnPlay.textContent = "⏸";
  } else {
    el.btnPlay.textContent = "▶";
  }
}

function goto(seq) {
  const count = eventCount();
  if (count === 0) return;
  state.seq = Math.max(-1, Math.min(count - 1, seq));
  if (!state.playing) {
    state.pos = state.seq;
  }
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
  const snap = snapshotAt(state.seq);
  el.readoutTime.textContent = snap ? `t=${snap.t}s` : 't=0.0s';
  el.readoutEvent.textContent = `event ${state.seq + 1}/${eventCount()}`;
  el.readoutDuration.textContent = `total ${fmtDuration(state.bundle.replay.duration)} · ${eventCount()} events`;
}

function drawTown() {
  const ctx = el.ctx;
  ctx.save();
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.clearRect(0, 0, el.canvas.width, el.canvas.height);
  ctx.restore();
  if (sceneDoc()) {
    drawSceneScene();
  } else {
    drawLegacyTown();
  }
}

function drawSceneScene() {
  const scene = sceneDoc();
  const ctx = el.ctx;
  const { w, h } = scene.bounds;
  ctx.save();
  if (scene.scene_kind === "h1_megafacility") drawMegafacility(scene, ctx);
  else if (scene.scene_kind === "parallel_cells") drawCells(scene, ctx);
  else if (scene.scene_kind === "conversation_hall") drawHall(scene, ctx);
  else drawScratch(scene, ctx);
  ctx.restore();
  drawArtifacts(ctx, scene);
  drawCarriers(ctx, scene);
  drawChoreography(ctx, scene);
  drawEffects(ctx, scene);
  drawSelectionHover(ctx);
  drawPhaseBanner();
}

/* ---------------------------------------------- h1 megafacility renderer */

const H1_ROOM_CONFIG = {
  workcell_a: { accent: "#38bdf8", tag: "[SEC-01 · GEN-0 BAY]" },
  workcell_b: { accent: "#f59e0b", tag: "[SEC-02 · GEN-1 BAY]" },
  lifecycle:  { accent: "#10b981", tag: "[SYS-L0 · CONTROL]" },
  hall:       { accent: "#14b8a6", tag: "[COMMAND · OPS DESK]" },
  archive:    { accent: "#0ea5e9", tag: "[VAULT · STATE STORE]" },
  gateway:    { accent: "#a855f7", tag: "[GATEWAY · LLM BUS]" },
  network:    { accent: "#22c55e", tag: "[BENCH · PROBE ARRAY]" },
};

function drawMegafacility(scene, ctx) {
  const { w, h } = scene.bounds;
  drawCampusGrid(ctx, 0, 0, w, h);

  // Central Transit Corridor (Dark reinforced deck with caution borders)
  ctx.save();
  ctx.fillStyle = "rgba(15, 23, 42, 0.75)";
  roundRect(ctx, 40, 290, w - 80, 140, 6);
  ctx.fill();
  ctx.strokeStyle = "rgba(148, 163, 184, 0.15)";
  ctx.lineWidth = 1;
  roundRect(ctx, 40, 290, w - 80, 140, 6);
  ctx.stroke();

  // Yellow hazard strips along corridor edges
  ctx.strokeStyle = "rgba(245, 158, 11, 0.4)";
  ctx.lineWidth = 3;
  ctx.setLineDash([12, 10]);
  ctx.beginPath();
  ctx.moveTo(50, 295); ctx.lineTo(w - 50, 295);
  ctx.moveTo(50, 425); ctx.lineTo(w - 50, 425);
  ctx.stroke();
  ctx.setLineDash([]);
  ctx.restore();

  // Rooms
  for (const room of scene.rooms) {
    const cfg = H1_ROOM_CONFIG[room.id] || { accent: "#38bdf8", tag: `[${room.kind.toUpperCase()}]` };
    drawRoomContainer(ctx, room, cfg.accent, cfg.tag);
  }

  // Stations
  for (const station of Object.values(scene.stations)) {
    if (station.kind === "waypoint") continue;
    drawStation(station, ctx);
  }
}

function drawStation(station, ctx) {
  const cx = station.x, cy = station.y;
  const w = station.w || 40, h = station.h || 30;
  ctx.save();
  switch (station.kind) {
    case "door":
      drawSecurityPortal(ctx, cx, cy, Math.max(26, w), Math.max(48, h), station.id === "exit");
      break;
    case "workbench":
      drawConsoleStation(ctx, cx, cy, w, h, station.label, "#38bdf8");
      break;
    case "terminal":
      drawConsoleStation(ctx, cx, cy, w, h, station.label, "#0ea5e9");
      break;
    case "panel":
      drawConsoleStation(ctx, cx, cy, w, h, station.label, "#10b981");
      break;
    case "gate":
      drawSecurityPortal(ctx, cx, cy, w, h, false);
      break;
    case "desk":
      drawConsoleStation(ctx, cx, cy, w, h, station.label, "#f59e0b");
      break;
    case "archive":
      drawCarrierVault(ctx, cx, cy, w, h, station.label);
      break;
    case "rack":
      drawServerRack(ctx, cx, cy, w, h, station.label, "#a855f7");
      break;
    case "bench":
      drawConsoleStation(ctx, cx, cy, w, h, station.label, "#10b981");
      break;
    case "shelf":
      drawCarrierVault(ctx, cx, cy, w, h, station.label);
      break;
    case "lamp":
      ctx.fillStyle = "#10b981";
      ctx.shadowColor = "#10b981";
      ctx.shadowBlur = 8;
      ctx.beginPath();
      ctx.arc(cx, cy, 5, 0, Math.PI * 2);
      ctx.fill();
      ctx.shadowBlur = 0;
      break;
    default:
      drawConsoleStation(ctx, cx, cy, w, h, station.label || "", "#64748b");
  }
  ctx.restore();
}

/* ---------------------------------------------- parallel cells renderer */

function drawCells(scene, ctx) {
  const { w, h } = scene.bounds;
  drawCampusGrid(ctx, 0, 0, w, h);

  for (let i = 0; i < scene.rooms.length; i++) {
    const room = scene.rooms[i];
    const agent = state.bundle.episode.agents[i];
    const hue = state.actors.get(agent?.id)?.hue ?? 190;
    const accent = `hsl(${hue}, 80%, 55%)`;
    const tag = `[BAY-${String(i + 1).padStart(2, '0')}] · ${agent ? esc(shortName(agent.id, 8)) : 'ACTIVE'}`;
    
    drawRoomContainer(ctx, room, accent, tag);
  }

  for (const station of Object.values(scene.stations)) {
    if (station.kind === "waypoint") continue;
    drawStation(station, ctx);
  }
}

/* -------------------------------------------- conversation hall renderer */

function drawHall(scene, ctx) {
  const { w, h } = scene.bounds;
  drawCampusGrid(ctx, 0, 0, w, h);
  const studio = scene.rooms.find((r) => r.kind === "studio") ?? scene.rooms[0];
  drawRoomContainer(ctx, studio, "#38bdf8", "[CONVERSATION FORUM · ARCHIPELAGO TREE]");

  for (const station of Object.values(scene.stations)) {
    if (station.kind === "screen") {
      ctx.save();
      ctx.fillStyle = "#090d10";
      roundRect(ctx, station.x - station.w / 2, station.y - station.h / 2, station.w, station.h, 6);
      ctx.fill();
      ctx.strokeStyle = "#38bdf8";
      ctx.lineWidth = 1.5;
      roundRect(ctx, station.x - station.w / 2, station.y - station.h / 2, station.w, station.h, 6);
      ctx.stroke();

      // Oscilloscope thread line
      ctx.strokeStyle = "rgba(56, 189, 248, 0.75)";
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(station.x - 110, station.y - 15);
      ctx.lineTo(station.x - 50, station.y + 15);
      ctx.lineTo(station.x + 10, station.y - 10);
      ctx.lineTo(station.x + 70, station.y + 20);
      ctx.lineTo(station.x + 110, station.y - 8);
      ctx.stroke();

      drawStationLabel(ctx, station.label, station.x, station.y + station.h / 2 + 14);
      ctx.restore();
    } else if (station.kind === "table") {
      ctx.save();
      ctx.fillStyle = "#1e293b";
      roundRect(ctx, station.x - station.w / 2, station.y - station.h / 2, station.w, station.h, 8);
      ctx.fill();
      ctx.strokeStyle = "#334155";
      ctx.lineWidth = 1.5;
      roundRect(ctx, station.x - station.w / 2, station.y - station.h / 2, station.w, station.h, 8);
      ctx.stroke();
      drawStationLabel(ctx, station.label, station.x, station.y + station.h / 2 + 14);
      ctx.restore();
    } else if (station.kind === "seat") {
      ctx.save();
      ctx.strokeStyle = "rgba(148, 163, 184, 0.5)";
      ctx.lineWidth = 2;
      roundRect(ctx, station.x - station.w / 2, station.y - station.h / 2, station.w, station.h, 6);
      ctx.stroke();
      drawStationLabel(ctx, station.label, station.x, station.y + station.h / 2 + 14);
      ctx.restore();
    } else {
      drawStation(station, ctx);
    }
  }
}

/* fallback scratch renderer for unknown scene kinds */
function drawScratch(scene, ctx) {
  const { w, h } = scene.bounds;
  drawCampusGrid(ctx, 0, 0, w, h);
  for (const station of Object.values(scene.stations)) {
    if (station.kind !== "waypoint" && station.kind !== "door") drawStation(station, ctx);
  }
}

/* ---------------------------------------------- artifacts & carriers */

const ART_SHORT = {
  provider_response: "provider", carrier: "carrier", note: "note",
  file: "file", seed: "seed",
};

function drawArtifacts(ctx, scene) {
  const snapshot = snapshotAt(state.seq);
  if (!snapshot) return;
  for (const [artId, art] of Object.entries(scene.artifacts)) {
    const snap = snapshot.artifacts[artId];
    const created = snap?.created_seq ?? -1;
    const age = state.seq - created;
    const fadingIn = created >= 0 && age >= 0 && age < 8;
    if (snap && !snap.live && !fadingIn) continue;
    const pos = stationPoint(scene, art.station);
    const slot = art.slot ?? 0;
    const sx = pos.x + (slot % 3 - 1) * 18;
    const sy = pos.y + Math.floor(slot / 3) * 16;
    ctx.save();
    ctx.globalAlpha = fadingIn ? Math.min(1, age / 4 + 0.25) : 1;
    drawArtifactIcon(ctx, art.kind, sx, sy, 1.1);
    ctx.font = "600 10px ui-monospace, 'SF Mono', monospace";
    ctx.textAlign = "center";
    ctx.fillStyle = "#f1f5f9";
    ctx.fillText(shortName(ART_SHORT[art.kind] ?? art.label, 14), sx, sy + 24);
    ctx.restore();
  }
}

function drawCarriers(ctx, scene) {
  const snapshot = snapshotAt(state.seq);
  if (!snapshot) return;
  for (const [carrierId, carrier] of Object.entries(scene.carriers)) {
    const snap = snapshot.carriers[carrierId];
    if (!snap || !snap.active) continue;
    const fromPos = actorPoint(carrier.from) ?? stationPoint(scene, carrier.station || "archive_shelf");
    const toPos = actorPoint(carrier.to) ?? stationPoint(scene, carrier.station || "archive_shelf");
    const offs = Object.keys(scene.carriers).indexOf(carrierId) - Object.keys(scene.carriers).length / 2;
    const target = carrier.station === "archive_shelf" ? toPos : toPos;
    const p1 = { x: fromPos.x, y: fromPos.y };
    const p2 = { x: target.x + offs * 10, y: target.y + Math.abs(offs) * 4 };
    const kind = carrier.kind === "provider" ? "#a855f7" : "#0ea5e9";

    // Subterranean glowing conduit line
    ctx.save();
    ctx.strokeStyle = "rgba(15, 23, 42, 0.8)";
    ctx.lineWidth = 10;
    ctx.beginPath(); ctx.moveTo(p1.x, p1.y); ctx.lineTo(p2.x, p2.y); ctx.stroke();

    // Animated energy conduit
    ctx.strokeStyle = kind;
    ctx.shadowColor = kind;
    ctx.shadowBlur = 10;
    ctx.lineWidth = 3;
    ctx.setLineDash([10, 8]);
    ctx.lineDashOffset = -(state.pos * 18 % 36);
    ctx.beginPath(); ctx.moveTo(p1.x, p1.y); ctx.lineTo(p2.x, p2.y); ctx.stroke();
    ctx.setLineDash([]);
    ctx.shadowBlur = 0;

    // Moving encrypted carrier capsule payload
    const flowPhase = (state.pos * 0.4) % 1;
    const capX = p1.x + (p2.x - p1.x) * flowPhase;
    const capY = p1.y + (p2.y - p1.y) * flowPhase;
    drawArtifactIcon(ctx, "carrier", capX, capY, 1.2);

    ctx.restore();
  }
}

function actorPoint(actorId) {
  if (!actorId || !state.actors.has(actorId)) return null;
  const info = state.actors.get(actorId);
  const p = endPosAt(sceneDoc(), actorId, state.seq);
  return info ? p : null;
}

/* ------------------------------------------------------------- actors */

function drawChoreography(ctx, scene) {
  const episode = state.bundle.episode;
  const seq = state.seq;
  const frac = Math.max(0, Math.min(1, state.pos - Math.floor(state.pos)));
  for (const agent of episode.agents) {
    const info = state.actors.get(agent.id);
    if (!info) continue;
    const visible = actorVisible(info, seq);
    if (!visible) continue;
    const snap = snapshotAt(seq)?.agents?.[agent.id];
    const move = actorMove(scene, agent.id, seq, frac);
    const teardown = teardownEntry(info);
    const fading = teardown && seq === teardown.i && frac > 0.6 ? 1 - (frac - 0.6) / 0.4 : 1;
    ctx.save();
    ctx.globalAlpha = fading;
    const busy = busyUntil(agent.id) > seq;
    drawNPC(ctx, {
      x: move.x, y: move.y,
      hue: info.hue ?? 200,
      generation: info.generation,
      walking: move.walking ? frac : 0,
      idle: ((seq * 0.6 + hashStr(agent.id) % 7 * 0.13) % 1),
      busy,
      dead: snap ? !snap.alive && snap.spawn_seq >= 0 : false,
      alpha: fading,
      label: agent.name,
    });

    // Operator Name HUD Tag
    ctx.font = "600 11px ui-monospace, 'SF Mono', monospace";
    ctx.textAlign = "center";
    const tw = ctx.measureText(agent.name).width;
    ctx.fillStyle = "rgba(15, 23, 42, 0.85)";
    roundRect(ctx, move.x - tw / 2 - 5, move.y + 18, tw + 10, 16, 3);
    ctx.fill();
    ctx.strokeStyle = "rgba(148, 163, 184, 0.3)";
    ctx.lineWidth = 1;
    roundRect(ctx, move.x - tw / 2 - 5, move.y + 18, tw + 10, 16, 3);
    ctx.stroke();

    ctx.fillStyle = "#f8fafc";
    ctx.fillText(agent.name, move.x, move.y + 30);

    ctx.restore();
  }
}

function busyUntil(actorId) {
  const events = state.bundle.episode.events;
  for (let i = state.seq; i >= Math.max(0, state.seq - 12); i--) {
    const event = events[i];
    if (!event || event.agent_id !== actorId) continue;
    if (event.kind === "tool_call") return i + 6;
    if (event.kind === "spawn") break;
  }
  return -1;
}

/* ------------------------------------------------------------- effects */

function drawEffects(ctx, scene) {
  const events = state.bundle.episode.events;
  const window = EFFECT_WINDOW;
  const frac = Math.max(0, Math.min(1, state.pos - Math.floor(state.pos)));
  for (let i = Math.max(0, state.seq - window); i <= state.seq; i++) {
    const entry = scene.script[i];
    if (!entry) continue;
    const age = state.seq - i;
    const fade = Math.max(0, 1 - age / window);
    const fx = entry.fx;
    const sfx = stationPoint(scene, entry.interact);
    const actorPos = entry.actor ? actorMove(scene, entry.actor, i, frac) : null;
    const at = fxAt(fx, entry, sfx, actorPos);
    if (!at) continue;
    switch (fx) {
      case "spawn_ring": {
        const r = 14 + age * 6;
        ctx.strokeStyle = `rgba(127,217,106,${0.9 * fade})`;
        ctx.lineWidth = 3;
        ctx.beginPath(); ctx.arc(at.x, at.y, r, 0, Math.PI * 2); ctx.stroke();
        ctx.fillStyle = `rgba(127,217,106,${0.75 * fade})`;
        ctx.beginPath();
        ctx.moveTo(at.x, at.y - 30 - age * 2);
        ctx.lineTo(at.x - 5, at.y - 40 - age * 2);
        ctx.lineTo(at.x + 5, at.y - 40 - age * 2);
        ctx.closePath(); ctx.fill();
        break;
      }
      case "dissolve": {
        const r = 14 + age * 7;
        ctx.strokeStyle = `rgba(217,106,90,${0.9 * fade})`;
        ctx.lineWidth = 3;
        ctx.beginPath(); ctx.arc(at.x, at.y, r, 0, Math.PI * 2); ctx.stroke();
        break;
      }
      case "auth_flash": {
        const intensity = (age % 2 === 0 ? 1 : 0.4) * fade;
        ctx.fillStyle = `rgba(217,106,90,${0.35 * intensity})`;
        roundRect(ctx, at.x - 34, at.y - 34, 68, 14, 4);
        ctx.fill();
        for (let k = 0; k < 4; k++) {
          ctx.fillStyle = `rgba(255,140,120,${(0.35 + 0.65 * ((age + k) % 2)) * intensity})`;
          ctx.beginPath();
          ctx.arc(at.x - 24 + k * 16, at.y - 27, 3, 0, Math.PI * 2);
          ctx.fill();
        }
        break;
      }
      case "puck_finalize":
      case "archive_link": {
        const r = 12 + age * 4;
        ctx.strokeStyle = `rgba(90,208,217,${0.85 * fade})`;
        ctx.lineWidth = 2.5;
        ctx.beginPath(); ctx.arc(at.x, at.y, r, 0, Math.PI * 2); ctx.stroke();
        ctx.strokeStyle = `rgba(217,190,90,${0.55 * fade})`;
        ctx.beginPath(); ctx.arc(at.x, at.y, r * 0.55, 0, Math.PI * 2); ctx.stroke();
        break;
      }
      case "deposit":
      case "retrieve": {
        const color = fx === "deposit" ? "217,190,90" : "90,208,217";
        ctx.strokeStyle = `rgba(${color},${0.85 * fade})`;
        ctx.lineWidth = 2.5;
        ctx.beginPath(); ctx.arc(at.x, at.y, 13 + age * 3, 0, Math.PI * 2); ctx.stroke();
        if (actorPos) {
          ctx.beginPath();
          ctx.moveTo(actorPos.x, actorPos.y);
          ctx.lineTo(at.x, at.y);
          ctx.stroke();
        }
        break;
      }
      case "terminal_activity":
      case "gateway_glow": {
        const color = fx === "gateway_glow" ? "192,90,217" : "90,208,217";
        ctx.fillStyle = `rgba(${color},${0.2 * fade})`;
        ctx.beginPath(); ctx.arc(at.x, at.y, 22, 0, Math.PI * 2); ctx.fill();
        ctx.fillStyle = `rgba(${color},${0.9 * fade})`;
        ctx.font = "700 10px system-ui";
        ctx.textAlign = "center";
        ctx.fillText(fx === "gateway_glow" ? "◉" : "▞", at.x, at.y + 4);
        break;
      }
      case "probe_arc": {
        ctx.strokeStyle = `rgba(134,181,106,${0.8 * fade})`;
        ctx.lineWidth = 2;
        for (let k = 0; k < 3; k++) {
          ctx.beginPath();
          ctx.arc(at.x, at.y, 12 + k * 6 + age, (i * 1.3 + k) * 0.7, (i * 1.3 + k) * 0.7 + 1.2);
          ctx.stroke();
        }
        break;
      }
      case "tool_activity":
      case "tool_done": {
        ctx.fillStyle = `rgba(217,160,90,${0.9 * fade})`;
        ctx.font = "700 14px system-ui";
        ctx.textAlign = "center";
        ctx.fillText("⚙", at.x, at.y - 28);
        break;
      }
      case "bubble": {
        const text = shortName(entry.title, 26).replace(/\s+/g, " ").trim();
        const by = actorPos ? at.y - 30 - age * 5 : at.y - 20 - age * 3;
        drawBubble(ctx, at.x, by, text, fade * 0.95);
        break;
      }
      case "stamp": {
        ctx.strokeStyle = `rgba(217,169,78,${0.75 * fade})`;
        ctx.lineWidth = 3;
        roundRect(ctx, at.x - 24, at.y - 34, 32, 20, 4);
        ctx.stroke();
        ctx.fillStyle = `rgba(217,169,78,${0.5 * fade})`;
        ctx.font = "700 8px system-ui";
        ctx.textAlign = "center";
        ctx.fillText("NOTE", at.x - 8, at.y - 21);
        break;
      }
      case "score_glow": {
        ctx.fillStyle = `rgba(127,217,106,${0.22 * fade})`;
        ctx.beginPath(); ctx.arc(at.x, at.y, 24 + age * 2, 0, Math.PI * 2); ctx.fill();
        break;
      }
      case "done_light": {
        ctx.fillStyle = `rgba(217,190,90,${0.5 * fade})`;
        ctx.beginPath(); ctx.arc(at.x, at.y, 12 + age * 3, 0, Math.PI * 2); ctx.fill();
        ctx.strokeStyle = `rgba(217,190,90,${0.9 * fade})`;
        ctx.lineWidth = 2.5;
        ctx.beginPath(); ctx.arc(at.x, at.y, 12 + age * 3, 0, Math.PI * 2); ctx.stroke();
        break;
      }
      case "info_tag": {
        ctx.fillStyle = `rgba(139,148,139,${0.5 * fade})`;
        ctx.font = "600 9px system-ui";
        ctx.textAlign = "center";
        ctx.fillText("· " + shortName(entry.title, 20) + " ·", at.x, at.y - 16);
        break;
      }
      default:
        break;
    }
  }
}

/* choose where an effect lands */
function fxAt(fx, entry, station, actorPos) {
  if (actorPos) {
    if (fx === "bubble" || fx === "tool_activity" || fx === "tool_done" ||
        fx === "score_glow" || fx === "done_light" || fx === "info_tag") {
      return actorPos;
    }
  }
  return station;
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

function drawSelectionHover(ctx) {
  const ring = (x, y, color) => {
    ctx.strokeStyle = color;
    ctx.lineWidth = 2.5;
    ctx.beginPath(); ctx.arc(x, y, 17, 0, Math.PI * 2); ctx.stroke();
  };
  const scene = sceneDoc();
  const pointOf = (type, id) => {
    if (type === "agent") {
      const info = state.actors.get(id);
      if (info) return actorMove(scene, id, state.seq, 0);
    }
    if (type === "artifact") {
      const art = scene?.artifacts?.[id];
      if (art) return stationPoint(scene, art.station);
    }
    return null;
  };
  if (state.selected) {
    const p = pointOf(state.selected.type, state.selected.id);
    if (p) ring(p.x, p.y, "rgba(200,163,78,0.95)");
  }
  if (state.hover && state.hover.type === "agent") {
    const p = pointOf("agent", state.hover.id);
    if (p) ring(p.x, p.y, "rgba(232,230,216,0.5)");
  }
}

/* ------------------------------------------------------- legacy (v1) */

function drawLegacyTown() {
  const replay = state.bundle.replay;
  const ctx = el.ctx;
  // grass
  ctx.fillStyle = "#33501f";
  ctx.fillRect(0, 0, 1000, 700);
  const rand = seededRng(state.bundle.episode.id);
  for (let i = 0; i < 2600; i++) {
    const x = rand() * 1000, y = rand() * 700, s = rand() * 2.4 + 0.6;
    ctx.fillStyle = rand() > 0.5 ? "rgba(70,110,45,0.55)" : "rgba(45,80,30,0.55)";
    ctx.fillRect(x, y, s, s);
  }
  // plaza + paths
  ctx.lineCap = "round";
  ctx.strokeStyle = "rgba(150,120,70,0.35)";
  ctx.lineWidth = 14;
  for (const facility of Object.values(replay.facilities)) {
    ctx.beginPath();
    ctx.moveTo(replay.plaza.x, replay.plaza.y);
    ctx.lineTo(facility.x, facility.y);
    ctx.stroke();
  }
  ctx.fillStyle = "#5c513a";
  ctx.beginPath(); ctx.arc(replay.plaza.x, replay.plaza.y, 46, 0, Math.PI * 2); ctx.fill();
  ctx.fillStyle = "#6d6045";
  ctx.beginPath(); ctx.arc(replay.plaza.x, replay.plaza.y, 34, 0, Math.PI * 2); ctx.fill();
  const snapshot = snapshotAt(state.seq);
  if (snapshot) {
    for (const facility of Object.values(replay.facilities)) {
      ctx.fillStyle = "hsl(24 22% 42%)";
      roundRect(ctx, facility.x - 46, facility.y - 31, 92, 62, 8);
      ctx.fill();
      ctx.font = "600 10px system-ui";
      ctx.textAlign = "center";
      ctx.fillStyle = "#e8e6d8";
      ctx.fillText(facility.kind, facility.x, facility.y + 4);
      ctx.font = "600 10px system-ui";
      ctx.fillStyle = "rgba(232,230,216,0.7)";
      ctx.fillText(`${Object.values(snapshot.artifacts).filter((a) => a.facility === facility.kind && a.live).length}`, facility.x, facility.y + 18);
    }
    for (const artifact of Object.values(snapshot.artifacts)) {
      if (!artifact.live) continue;
      drawArtifactIcon(ctx, artifact.kind, artifact.x, artifact.y);
      ctx.font = "10px system-ui";
      ctx.textAlign = "center";
      ctx.fillStyle = "rgba(232,230,216,0.85)";
      ctx.fillText(shortName(artifact.name, 14), artifact.x, artifact.y + 28);
    }
    for (const agent of Object.values(snapshot.agents)) {
      if (agent.spawn_seq < 0) continue;
      ctx.fillStyle = `hsl(${agent.hue} 55% 55%)`;
      ctx.beginPath(); ctx.arc(agent.x, agent.y, 11, 0, Math.PI * 2); ctx.fill();
      ctx.fillStyle = `hsl(${agent.hue} 55% 68%)`;
      ctx.beginPath(); ctx.arc(agent.x - 2, agent.y - 3, 5.5, 0, Math.PI * 2); ctx.fill();
      ctx.font = "600 11px system-ui";
      ctx.textAlign = "center";
      ctx.fillStyle = "rgba(232,230,216,0.95)";
      ctx.fillText(shortName(agent.name, 15), agent.x, agent.y + 30);
    }
  }
  drawPhaseBanner();
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

function buildLegend() {
  el.legend.innerHTML = "";
  for (const [group, style] of Object.entries(GROUP_STYLE)) {
    const item = document.createElement("span");
    item.className = "lg";
    item.title = group;
    const dot = document.createElement("i");
    dot.style.background = style.color;
    item.appendChild(dot);
    item.appendChild(document.createTextNode(style.label));
    el.legend.appendChild(item);
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
    const info = state.actors.get(agent.id);
    const row = document.createElement("div");
    row.className = "agent-row" + (s && !s.alive && s.spawn_seq >= 0 ? " agent-dead" : "")
      + (state.selected?.type === "agent" && state.selected.id === agent.id ? " selected" : "");
    const dot = document.createElement("span");
    dot.className = "agent-dot";
    dot.style.background = info ? `hsl(${info.hue} 55% 52%)` : (s ? `hsl(${s.hue} 55% 55%)` : "#555");
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
    const episode = state.bundle.episode;
    const snapshot = snapshotAt(state.seq);
    const alive = episode.agents.filter((a) => snapshot?.agents[a.id]?.alive).length;
    const last = episode.events[state.seq];
    const scene = sceneDoc();
    const box = document.createElement("div");
    box.className = "insp";
    box.appendChild(kv([
      ["scene", scene ? scene.scene_kind.replace("_", " ") : "legacy town"],
      ["environment", episode.environment],
      ["agents alive", `${alive}/${episode.agents.length}`],
      ["artifacts", episode.artifacts.length],
      ["carriers", episode.carriers.length],
      ["current event", last ? `#${last.seq} ${last.kind}` : "—"],
      ["playback", `${BASE_EVENTS_PER_SEC * state.speed} events/s`],
    ]));
    el.inspectorBody.innerHTML = "";
    el.inspectorBody.appendChild(box);
    return;
  }
  const { type, id } = state.selected;
  if (type === "agent") return inspectAgent(id);
  if (type === "artifact") return inspectArtifact(id);
  if (type === "event") return inspectEvent(id);
  if (type === "station") return inspectStation(id);
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
  const episode = state.bundle.episode;
  const agent = episode.agent(agentId);
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
  const info = state.actors.get(agentId);
  if (info) {
    const scene = sceneDoc();
    rows.push(["home station", stationOf(scene, info.home)?.label ?? info.home]);
  }
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
  const rows = [
    ["kind", artifact.kind],
    ["owner", artifact.agent_id || "—"],
    ["created", artifact.created_at >= 0 ? `event #${artifact.created_at}` : "present from start"],
    ["lineage", artifact.lineage_id || "—"],
    ["generation", artifact.generation],
    ["live now", s ? (s.live ? "yes" : "no") : "—"],
    ["preview", artifact.content_preview || "—"],
  ];
  const art = sceneDoc()?.artifacts?.[artifactEntryId];
  if (art) rows.push(["station", stationOf(sceneDoc(), art.station)?.label ?? art.station]);
  box.appendChild(kv(rows));
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
  const entry = sceneDoc()?.script?.[seq];
  if (entry) {
    const h3 = document.createElement("h3"); h3.textContent = "choreography (presentational)";
    box.appendChild(h3);
    box.appendChild(rawBlock({
      phase: entry.phase, fx: entry.fx,
      interact: stationOf(sceneDoc(), entry.interact)?.label ?? entry.interact,
      via: (entry.via || []).map((v) => stationOf(sceneDoc(), v)?.label ?? v),
      object: entry.object, return_home: entry.return_home,
    }));
  }
  if (Object.keys(event.payload || {}).length) {
    const h3 = document.createElement("h3"); h3.textContent = "verbatim source payload";
    box.appendChild(h3);
    box.appendChild(rawBlock(event.payload));
  }
  el.inspectorBody.innerHTML = "";
  el.inspectorBody.appendChild(box);
}

function inspectStation(stationId) {
  const scene = sceneDoc();
  const station = stationOf(scene, stationId);
  el.inspectorTitle.textContent = "Station";
  if (!station) return;
  const box = document.createElement("div");
  box.className = "insp";
  box.appendChild(kv([
    ["id", station.id],
    ["kind", station.kind],
    ["label", station.label || "—"],
    ["position", `${station.x}, ${station.y}`],
    ["size", `${station.w} × ${station.h}`],
  ]));
  el.inspectorBody.innerHTML = "";
  el.inspectorBody.appendChild(box);
}

/* ------------------------------------------------------------- interaction */

function onCanvasMove(event) {
  if (!state.bundle) return;
  const scene = sceneDoc();
  const bounds = scene?.bounds || { w: el.canvas.width, h: el.canvas.height };
  const rect = el.canvas.getBoundingClientRect();
  if (rect.width === 0 || rect.height === 0) return;
  const x = (event.clientX - rect.left) * (bounds.w / rect.width);
  const y = (event.clientY - rect.top) * (bounds.h / rect.height);
  state.hover = hitTest(x, y);
  if (!state.hover) { el.tip.hidden = true; return; }
  el.tip.hidden = false;
  el.tip.style.left = `${event.clientX - rect.left + 14}px`;
  el.tip.style.top = `${event.clientY - rect.top + 8}px`;
  const { type, id } = state.hover;
  const snapshot = snapshotAt(state.seq);
  if (type === "agent") {
    const agent = state.bundle.episode.agent(id);
    const s = snapshot?.agents[id];
    el.tip.innerHTML = [
      `<b>${esc(agent.name)}</b>`,
      `gen ${agent.generation}${agent.lineage_id ? ` · lineage ${esc(shortName(agent.lineage_id, 8))}` : ""}`,
      s ? (s.alive ? "alive" : `dead @ event ${s.death_seq}`) : "",
      s?.tool_calls ? `${s.tool_calls} tool calls` : "",
      s && (s.artifact_reads + s.artifact_writes) ? `${s.artifact_reads} reads · ${s.artifact_writes} writes` : "",
    ].filter(Boolean).join("<br>");
  } else if (type === "artifact") {
    const artifact = state.bundle.episode.artifact(id);
    const art = sceneDoc()?.artifacts?.[id];
    el.tip.innerHTML = [
      `<b>${esc(artifact.name)}</b>`,
      `kind: ${artifact.kind}`,
      artifact.created_at >= 0 ? `created @ event ${artifact.created_at}` : "present from start",
      art ? `station: ${esc(stationOf(sceneDoc(), art.station)?.label ?? art.station)}` : "",
      artifact.owner_agent ? `owner: ${esc(artifact.owner_agent)}` : "",
    ].filter(Boolean).join("<br>");
  } else if (type === "station") {
    const station = stationOf(sceneDoc(), id);
    el.tip.innerHTML = `<b>${esc(station.label || id)}</b><br>${station.kind}`;
  } else if (type === "carrier") {
    el.tip.innerHTML = `<b>carrier dependency</b><br>${esc(id)}`;
  }
}

function hitTest(x, y) {
  const scene = sceneDoc();
  if (!scene) return legacyHitTest(x, y);
  const snapshot = snapshotAt(state.seq);
  const frac = Math.max(0, Math.min(1, state.pos - Math.floor(state.pos)));
  for (const agent of state.bundle.episode.agents) {
    if (!state.actors.has(agent.id)) continue;
    if (!actorVisible(state.actors.get(agent.id), state.seq)) continue;
    const move = actorMove(scene, agent.id, state.seq, frac);
    if (Math.abs(x - move.x) < 18 && Math.abs(y - move.y) < 26) {
      return { type: "agent", id: agent.id };
    }
  }
  for (const [artId, art] of Object.entries(scene.artifacts)) {
    const pos = stationPoint(scene, art.station);
    const slot = art.slot ?? 0;
    const sx = pos.x + (slot % 3 - 1) * 16;
    const sy = pos.y + Math.floor(slot / 3) * 14;
    if (Math.hypot(x - sx, y - sy) < 20) return { type: "artifact", id: artId };
  }
  for (const station of Object.values(scene.stations)) {
    if (station.kind === "waypoint") continue;
    if (x >= station.x - station.w / 2 && x <= station.x + station.w / 2 &&
        y >= station.y - station.h / 2 && y <= station.y + station.h / 2) {
      return { type: "station", id: station.id };
    }
  }
  return null;
}

function legacyHitTest(x, y) {
  const snapshot = snapshotAt(state.seq);
  if (!snapshot) return null;
  for (const agent of Object.values(snapshot.agents)) {
    if (agent.spawn_seq < 0) continue;
    if (Math.hypot(x - agent.x, y - agent.y) < 24) return { type: "agent", id: agent.id };
  }
  for (const artifact of Object.values(snapshot.artifacts)) {
    if (artifact.live && Math.hypot(x - artifact.x, y - artifact.y) < 20) {
      return { type: "artifact", id: artifact.id };
    }
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

/* ------------------------------------------------------------- sources */

let srcListEl = null;

function cleanSources() {
  if (srcListEl) { srcListEl.remove(); srcListEl = null; }
}

async function toggleSources() {
  if (srcListEl) { cleanSources(); return; }
  try {
    const data = await fetchJSON("/api/sources");
    state.sources = data.sources ?? [];
  } catch (error) {
    el.epSub.textContent = `sources error: ${error}`;
    return;
  }
  const rect = el.srcBtn.getBoundingClientRect();
  srcListEl = document.createElement("div");
  srcListEl.className = "src-list";
  srcListEl.style.top = `${rect.bottom + 6}px`;
  srcListEl.style.left = `${rect.left}px`;
  const title = document.createElement("div");
  title.className = "src-title";
  title.textContent = "raw sources (read-only)";
  srcListEl.appendChild(title);
  for (const source of state.sources) {
    const item = document.createElement("button");
    item.className = "src-item";
    item.textContent = `${source.rel} · ${source.size} B`;
    item.title = source.rel;
    item.addEventListener("click", () => {
      cleanSources();
      selectSource(source.rel);
    });
    srcListEl.appendChild(item);
  }
  document.body.appendChild(srcListEl);
  const hide = (e) => {
    if (srcListEl && !srcListEl.contains(e.target) && e.target !== el.srcBtn) {
      cleanSources();
      document.removeEventListener("click", hide, true);
    }
  };
  document.addEventListener("click", hide, true);
}

/* ------------------------------------------------------------- boot */

window.addEventListener("error", (event) => {
  const msg = `runtime error: ${event.message}`;
  el.epSub.textContent = msg;
  console.error(msg);
});

init().catch((error) => {
  el.epSub.textContent = `load error: ${error}`;
  console.error(error);
});