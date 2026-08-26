/* sprites.js — asset manager + procedural drawing for the v2 viewer.
 *
 * Lab tiles: viewer/assets/lab/*.png (16px; CC0 / CC-BY — see ASSET_LICENSES).
 * Characters: drawn procedurally (body/legs/head/hard hat), fully
 * deterministic per actor (hue, generation).  No randomness anywhere:
 * every pixel is a pure function of (bundle, seq, pos).
 */

"use strict";

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

const Lab = {
  tiles: {},
  loaded: false,
  PATH: "assets/lab/",
  NAMES: [
    "floor_plain", "floor_stripe", "floor_variant", "floor_cell",
    "wall_gray", "wall_window", "wall_plain",
    "deco_yellow", "deco_pipe", "prop_rack", "prop_terminal", "prop_locker",
  ],
  load(onDone) {
    let pending = this.NAMES.length;
    const finish = () => { if (--pending <= 0) { this.loaded = true; onDone?.(); } };
    for (const name of this.NAMES) {
      const img = new Image();
      this.tiles[name] = img;
      img.onload = finish;
      img.onerror = () => { this.tiles[name] = null; finish(); };
      img.src = this.PATH + name + ".png";
    }
  },
  tile(name) { return this.tiles[name] || null; },
  has(name) { return Boolean(this.tiles[name]); },
};

/* deterministic rng (FNV-1a seed) — used only for cosmetic texture */
function seededRng(seedText) {
  let h = 2166136261 >>> 0;
  for (let i = 0; i < seedText.length; i++) {
    h ^= seedText.charCodeAt(i);
    h = Math.imul(h, 16777619) >>> 0;
  }
  let t = h >>> 0;
  return () => {
    t ^= t << 13; t >>>= 0;
    t ^= t >> 17;
    t ^= t << 5; t >>>= 0;
    return t / 4294967296;
  };
}

/* ------------------------------------------------------------- floor */

/* Tile a floor area with a 16px pattern. `paint(px, py, name)` lets the
 * caller decorate tiles (scatter stripes, borders).  Deterministic. */
function tileFloor(ctx, x0, y0, w, h, tile, paint) {
  for (let ty = 0; ty < h; ty += 16) {
    for (let tx = 0; tx < w; tx += 16) {
      const name = paint ? paint(tx, ty) : null;
      const img = name ? Lab.tile(name) : null;
      if (img) {
        ctx.drawImage(img, x0 + tx, y0 + ty);
      } else {
        const parity = ((x0 + tx) / 16 + (y0 + ty) / 16) % 2;
        ctx.fillStyle = parity < 1 ? "#313d38" : "#2c3632";
        ctx.fillRect(x0 + tx, y0 + ty, 16, 16);
      }
    }
  }
}

function floorPaintPlain() { return "floor_plain"; }

function floorPaintCells(x0, y0) {
  // accent: caution stripe every 5th tile along the walkway band
  if (y0 % 80 === 0 && (x0 / 16) % 5 === 0) return "floor_stripe";
  return ((x0 / 16 + y0 / 16) % 7 === 3) ? "floor_variant" : "floor_plain";
}

function fillRectShade(ctx, x, y, w, h, color, r) {
  ctx.fillStyle = color;
  roundRect(ctx, x, y, w, h, r ?? 4);
  ctx.fill();
}

/* ------------------------------------------------------------- props */

/* Draw a 16px lab tile scaled to a station footprint (nearest-neighbor). */
function drawTileProp(ctx, name, cx, cy, w, h) {
  const img = Lab.tile(name);
  ctx.save();
  ctx.fillStyle = "rgba(0,0,0,0.30)";
  roundRect(ctx, cx - w / 2 + 3, cy - h / 2 + 4, w, h, 5);
  ctx.fill();
  if (img) {
    ctx.imageSmoothingEnabled = false;
    ctx.drawImage(img, cx - w / 2, cy - h / 2, w, h);
  } else {
    ctx.fillStyle = "#3a4a44";
    roundRect(ctx, cx - w / 2, cy - h / 2, w, h, 5);
    ctx.fill();
    ctx.strokeStyle = "rgba(0,0,0,0.4)";
    ctx.stroke();
  }
  ctx.restore();
}

/* Decorative wall strip along a rect's top edge (windowed panels). */
function drawWallStrip(ctx, x, y, w, name) {
  const img = Lab.tile(name);
  for (let tx = 0; tx < w; tx += 16) {
    const seg = Math.min(16, w - tx);
    if (img) {
      ctx.imageSmoothingEnabled = false;
      ctx.drawImage(img, x + tx, y, seg, 16);
    } else {
      ctx.fillStyle = "#49554f";
      ctx.fillRect(x + tx, y, seg, 16);
    }
  }
}

/* procedural control panel (used when tiles are unavailable) */
function drawPanel(ctx, cx, cy, w, h) {
  fillRectShade(ctx, cx - w / 2, cy - h / 2, w, h, "#202b28", 4);
  ctx.fillStyle = "#0e1513";
  ctx.fillRect(cx - w / 2 + 4, cy - h / 2 + 4, w - 8, h - 8);
  for (let i = 0; i < 6; i++) {
    ctx.fillStyle = ["#d96a5a", "#d9a94e", "#86b56a", "#5ad0d9"][i % 4];
    ctx.beginPath();
    ctx.arc(cx - w / 2 + 9 + i * 7, cy + 2, 2, 0, Math.PI * 2);
    ctx.fill();
  }
}

/* procedural gate (auth gate / door frame) */
function drawGate(ctx, cx, cy, w, h) {
  ctx.strokeStyle = "#c8a34e";
  ctx.lineWidth = 3;
  roundRect(ctx, cx - w / 2, cy - h / 2, w, h, 3);
  ctx.stroke();
  ctx.strokeStyle = "rgba(200,163,78,0.35)";
  for (let i = 0; i < 4; i++) {
    ctx.beginPath();
    ctx.moveTo(cx - w / 2 + 4, cy - h / 2 + 6 + i * 7);
    ctx.lineTo(cx + w / 2 - 4, cy - h / 2 + 6 + i * 7);
    ctx.stroke();
  }
}

/* ------------------------------------------------------------- NPCs */

/* Deterministic game-like character: hard hat, body in actor hue,
 * 2-frame walk bob, generation rings, busy/retired glyphs. */
function drawNPC(ctx, o) {
  const { x, y, hue, generation = 0, walking = 0, dead = false,
          busy = false, alpha = 1, size = 20, idle = 0 } = o;
  ctx.save();
  ctx.globalAlpha = alpha;
  const sway = Math.sin(idle * Math.PI * 2) * 1.6 + 1;
  const yy = y - (walking === 0 ? sway : 0);
  // shadow
  ctx.fillStyle = "rgba(0,0,0,0.30)";
  ctx.beginPath();
  ctx.ellipse(x + 2, yy + size / 2 - 1, size * 0.42, size * 0.18, 0, 0, Math.PI * 2);
  ctx.fill();
  const step = Math.sin(walking * Math.PI * 2);
  const legSwing = step * size * 0.16;
  const bodyW = size * 0.5, bodyH = size * 0.42;
  const bx = x, by = yy - size * 0.08;
  // legs
  ctx.fillStyle = "#2a312e";
  ctx.fillRect(bx - bodyW / 2 + 1, by + bodyH / 2 - 1, bodyW * 0.26, size * 0.28 + legSwing * 0.4);
  ctx.fillRect(bx + bodyW / 2 - 1 - bodyW * 0.26, by + bodyH / 2 - 1, bodyW * 0.26, size * 0.28 - legSwing * 0.4);
  // torso
  ctx.fillStyle = `hsl(${hue} 48% 52%)`;
  roundRect(ctx, bx - bodyW / 2, by - bodyH / 2, bodyW, bodyH, 4);
  ctx.fill();
  ctx.strokeStyle = "rgba(10,14,13,0.9)";
  ctx.lineWidth = 1.4;
  roundRect(ctx, bx - bodyW / 2, by - bodyH / 2, bodyW, bodyH, 4);
  ctx.stroke();
  // hi-vis chest stripe
  ctx.fillStyle = "rgba(255,255,255,0.30)";
  ctx.fillRect(bx - bodyW / 2 + 2, by - 2, bodyW - 4, 3);
  // hard hat (safety amber dome + brim, distinct from body hue)
  ctx.fillStyle = "#e8c36a";
  roundRect(ctx, bx - bodyW / 2 - 1.5, by - bodyH / 2 - 4, bodyW + 3, 6, 2);
  ctx.fill();
  ctx.fillStyle = "#c89f4a";
  ctx.beginPath();
  ctx.arc(bx, by - bodyH / 2 - 5, bodyW * 0.34, Math.PI, 0);
  ctx.fill();
  ctx.strokeStyle = "rgba(10,14,13,0.9)";
  ctx.lineWidth = 1.2;
  roundRect(ctx, bx - bodyW / 2 - 1.5, by - bodyH / 2 - 4, bodyW + 3, 6, 2);
  ctx.stroke();
  // head
  ctx.fillStyle = "#e0b48c";
  ctx.beginPath();
  ctx.arc(bx, by - bodyH / 2 - 2, bodyW * 0.22, 0, Math.PI * 2);
  ctx.fill();
  ctx.fillStyle = "#3a2a1e";
  ctx.beginPath();
  ctx.arc(bx - 2, by - bodyH / 2 - 2, 1.4, 0, Math.PI * 2);
  ctx.arc(bx + 2, by - bodyH / 2 - 2, 1.4, 0, Math.PI * 2);
  ctx.fill();
  // generation rings
  for (let i = 0; i < Math.max(0, generation); i++) {
    ctx.strokeStyle = `hsl(${hue} 70% 68%)`;
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.arc(x, y - size / 2 - 8 - i * 7, 4, 0, Math.PI * 2);
    ctx.stroke();
  }
  // busy gear
  if (busy) {
    ctx.fillStyle = "#d9a05a";
    ctx.font = "700 13px system-ui";
    ctx.textAlign = "center";
    ctx.fillText("⚙", x, y - size / 2 - 10 - generation * 7);
  }
  // retired cross
  if (dead) {
    ctx.strokeStyle = "rgba(217,106,90,0.95)";
    ctx.lineWidth = 3;
    ctx.beginPath();
    ctx.moveTo(x - 7, y - 7); ctx.lineTo(x + 7, y + 7);
    ctx.moveTo(x + 7, y - 7); ctx.lineTo(x - 7, y + 7);
    ctx.stroke();
  }
  ctx.restore();
}

/* ------------------------------------------------------------- icons */

const ARTIFACT_ICONS = {
  note: "scroll", resource: "chest", carrier: "box", provider_response: "letter",
  seed: "seed", file: "files", artifact: "gear", generic: "gear",
};

function drawArtifactIcon(ctx, kind, x, y, scale) {
  const icon = ARTIFACT_ICONS[kind] ?? "gear";
  const s = scale ?? 1;
  ctx.save();
  ctx.translate(x, y);
  ctx.scale(s, s);
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

/* speech bubble for message events */
function drawBubble(ctx, x, y, text, alpha) {
  ctx.save();
  ctx.globalAlpha = alpha;
  ctx.font = "600 10px system-ui";
  const tw = ctx.measureText(text).width;
  const w = Math.min(150, tw + 16);
  fillRectShade(ctx, x - w / 2, y - 26, w, 20, "rgba(20,26,24,0.92)", 6);
  ctx.fillStyle = "rgba(232,230,216,0.95)";
  ctx.fillText(text, x, y - 13);
  ctx.restore();
}
