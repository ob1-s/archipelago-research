/* sprites.js — High-tech procedural drawing engine for Archipelago trajectory viewer.
 *
 * Designed for a grounded industrial/scientific mega-facility aesthetic:
 * - Cleanroom & containment architecture (raised ESD flooring, perimeter bulkheads, status beacons)
 * - Specialized operator agents with glowing HUD visors, directional motion, telemetry backpacks
 * - Server blade racks, dual-monitor consoles, cryptographic carrier vault, and fiber-optic conduits
 * - 100% deterministic: every pixel is a pure function of (bundle, seq, pos)
 */

"use strict";

function roundRect(ctx, x, y, w, h, r) {
  const radius = typeof r === "number" ? [r, r, r, r] : (Array.isArray(r) ? r : [r || 0, r || 0, r || 0, r || 0]);
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
  loaded: true,
  load(onDone) {
    onDone?.();
  },
  tile(name) { return null; },
  has(name) { return false; },
};

/* ------------------------------------------------------------- Floor & Campus */

function drawCampusGrid(ctx, x, y, w, h) {
  // Deep technical slate foundation
  ctx.fillStyle = "#0a0f13";
  ctx.fillRect(x, y, w, h);

  // Subtle 32px precision containment grid
  ctx.strokeStyle = "rgba(148, 163, 184, 0.04)";
  ctx.lineWidth = 1;
  ctx.beginPath();
  for (let gx = x; gx <= x + w; gx += 32) {
    ctx.moveTo(gx, y);
    ctx.lineTo(gx, y + h);
  }
  for (let gy = y; gy <= y + h; gy += 32) {
    ctx.moveTo(x, gy);
    ctx.lineTo(x + w, gy);
  }
  ctx.stroke();

  // Subtle coordinate grid intersection dots
  ctx.fillStyle = "rgba(56, 189, 248, 0.15)";
  for (let gx = x + 32; gx < x + w; gx += 96) {
    for (let gy = y + 32; gy < y + h; gy += 96) {
      ctx.fillRect(gx - 1, gy - 1, 2, 2);
    }
  }
}

function drawRoomContainer(ctx, room, accentColor, headerTag) {
  const { x, y, w, h } = room;
  accentColor = accentColor || "#38bdf8";

  ctx.save();
  // Room drop shadow
  ctx.fillStyle = "rgba(0, 0, 0, 0.5)";
  roundRect(ctx, x + 4, y + 4, w, h, 8);
  ctx.fill();

  // Room interior background (cleanroom dark slate)
  const bgGrad = ctx.createLinearGradient(x, y, x, y + h);
  bgGrad.addColorStop(0, "#131b22");
  bgGrad.addColorStop(1, "#0f161c");
  ctx.fillStyle = bgGrad;
  roundRect(ctx, x, y, w, h, 8);
  ctx.fill();

  // Subtle inner grid texture
  ctx.strokeStyle = "rgba(255, 255, 255, 0.02)";
  ctx.lineWidth = 1;
  ctx.beginPath();
  for (let gx = x + 16; gx < x + w; gx += 24) {
    ctx.moveTo(gx, y + 28);
    ctx.lineTo(gx, y + h - 6);
  }
  for (let gy = y + 36; gy < y + h; gy += 24) {
    ctx.moveTo(x + 6, gy);
    ctx.lineTo(x + w - 6, gy);
  }
  ctx.stroke();

  // Perimeter border with tech bevels
  ctx.strokeStyle = "rgba(71, 85, 105, 0.5)";
  ctx.lineWidth = 1.5;
  roundRect(ctx, x, y, w, h, 8);
  ctx.stroke();

  // Top header bar
  const headGrad = ctx.createLinearGradient(x, y, x + w, y);
  headGrad.addColorStop(0, "#1c2630");
  headGrad.addColorStop(1, "#141c22");
  ctx.fillStyle = headGrad;
  roundRect(ctx, x, y, w, 26, [8, 8, 0, 0]);
  ctx.fill();
  ctx.strokeStyle = "rgba(255, 255, 255, 0.08)";
  ctx.beginPath();
  ctx.moveTo(x, y + 26);
  ctx.lineTo(x + w, y + 26);
  ctx.stroke();

  // Accent LED indicator on top-left of header
  ctx.fillStyle = accentColor;
  ctx.shadowColor = accentColor;
  ctx.shadowBlur = 6;
  ctx.beginPath();
  ctx.arc(x + 14, y + 13, 3.5, 0, Math.PI * 2);
  ctx.fill();
  ctx.shadowBlur = 0;

  // Header Title Plaque
  ctx.font = "600 11px ui-monospace, 'SF Mono', Menlo, monospace";
  ctx.textAlign = "left";
  ctx.fillStyle = "#f1f5f9";
  const displayLabel = room.label || "FACILITY BAY";
  ctx.fillText(displayLabel, x + 24, y + 17);

  // Sector / Unit Code on top-right
  if (headerTag) {
    ctx.font = "500 9px ui-monospace, 'SF Mono', monospace";
    ctx.textAlign = "right";
    ctx.fillStyle = "rgba(148, 163, 184, 0.7)";
    ctx.fillText(headerTag, x + w - 12, y + 17);
  }

  ctx.restore();
}

/* ------------------------------------------------------------- Station Props */

function drawConsoleStation(ctx, cx, cy, w, h, label, color) {
  color = color || "#38bdf8";
  ctx.save();

  // Desk base shadow
  ctx.fillStyle = "rgba(0, 0, 0, 0.4)";
  roundRect(ctx, cx - w / 2 + 2, cy - h / 2 + 3, w, h, 6);
  ctx.fill();

  // Sleek titanium desk base
  ctx.fillStyle = "#1e293b";
  roundRect(ctx, cx - w / 2, cy - h / 2, w, h, 6);
  ctx.fill();
  ctx.strokeStyle = "#334155";
  ctx.lineWidth = 1.2;
  roundRect(ctx, cx - w / 2, cy - h / 2, w, h, 6);
  ctx.stroke();

  // Dual CRT / LCD terminal screens
  const screenW = (w - 14) / 2;
  const screenH = h * 0.45;

  // Left Screen
  ctx.fillStyle = "#090d10";
  roundRect(ctx, cx - w / 2 + 5, cy - h / 2 + 5, screenW, screenH, 3);
  ctx.fill();
  ctx.strokeStyle = color;
  ctx.lineWidth = 1;
  roundRect(ctx, cx - w / 2 + 5, cy - h / 2 + 5, screenW, screenH, 3);
  ctx.stroke();

  // Screen telemetry waveform / lines
  ctx.strokeStyle = color;
  ctx.lineWidth = 1.2;
  ctx.beginPath();
  ctx.moveTo(cx - w / 2 + 7, cy - h / 2 + 12);
  ctx.lineTo(cx - w / 2 + 13, cy - h / 2 + 8);
  ctx.lineTo(cx - w / 2 + 18, cy - h / 2 + 15);
  ctx.lineTo(cx - w / 2 + 23, cy - h / 2 + 10);
  ctx.stroke();

  // Right Screen
  ctx.fillStyle = "#090d10";
  roundRect(ctx, cx + 2, cy - h / 2 + 5, screenW, screenH, 3);
  ctx.fill();
  ctx.strokeStyle = "rgba(148, 163, 184, 0.4)";
  ctx.lineWidth = 1;
  roundRect(ctx, cx + 2, cy - h / 2 + 5, screenW, screenH, 3);
  ctx.stroke();

  // Diagnostic data lines on right screen
  ctx.fillStyle = "rgba(56, 189, 248, 0.6)";
  ctx.fillRect(cx + 5, cy - h / 2 + 8, screenW - 6, 2);
  ctx.fillRect(cx + 5, cy - h / 2 + 12, screenW - 10, 2);

  // Keyboard / Control surface
  ctx.fillStyle = "#0f172a";
  roundRect(ctx, cx - w / 2 + 6, cy + 2, w - 12, h * 0.32, 2);
  ctx.fill();

  // LED Status bank
  for (let i = 0; i < 4; i++) {
    ctx.fillStyle = ["#10b981", "#38bdf8", "#f59e0b", "#a855f7"][i];
    ctx.beginPath();
    ctx.arc(cx - w / 2 + 10 + i * 6, cy + h / 2 - 5, 1.8, 0, Math.PI * 2);
    ctx.fill();
  }

  // Station Label Plaque
  if (label) {
    drawStationLabel(ctx, label, cx, cy + h / 2 + 14);
  }

  ctx.restore();
}

function drawServerRack(ctx, cx, cy, w, h, label, glowColor) {
  glowColor = glowColor || "#a855f7";
  ctx.save();

  // Shadow
  ctx.fillStyle = "rgba(0, 0, 0, 0.45)";
  roundRect(ctx, cx - w / 2 + 2, cy - h / 2 + 3, w, h, 4);
  ctx.fill();

  // Outer Rack Frame
  ctx.fillStyle = "#0f172a";
  roundRect(ctx, cx - w / 2, cy - h / 2, w, h, 4);
  ctx.fill();
  ctx.strokeStyle = "#334155";
  ctx.lineWidth = 1.4;
  roundRect(ctx, cx - w / 2, cy - h / 2, w, h, 4);
  ctx.stroke();

  // Blade Server Units
  const blades = 4;
  const bladeH = (h - 10) / blades;
  for (let i = 0; i < blades; i++) {
    const by = cy - h / 2 + 5 + i * bladeH;
    ctx.fillStyle = i % 2 === 0 ? "#1e293b" : "#192231";
    ctx.fillRect(cx - w / 2 + 3, by, w - 6, bladeH - 2);

    // Glowing Fiber Optic LED indicators
    ctx.fillStyle = i % 2 === 0 ? glowColor : "#38bdf8";
    ctx.shadowColor = ctx.fillStyle;
    ctx.shadowBlur = 4;
    ctx.beginPath();
    ctx.arc(cx - w / 2 + 8, by + bladeH / 2 - 1, 2, 0, Math.PI * 2);
    ctx.fill();
    ctx.shadowBlur = 0;

    // Vent slot lines
    ctx.strokeStyle = "rgba(0,0,0,0.5)";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(cx - w / 2 + 16, by + bladeH / 2 - 1);
    ctx.lineTo(cx + w / 2 - 8, by + bladeH / 2 - 1);
    ctx.stroke();
  }

  if (label) {
    drawStationLabel(ctx, label, cx, cy + h / 2 + 14);
  }

  ctx.restore();
}

function drawCarrierVault(ctx, cx, cy, w, h, label) {
  ctx.save();

  // Shadow
  ctx.fillStyle = "rgba(0, 0, 0, 0.5)";
  roundRect(ctx, cx - w / 2 + 3, cy - h / 2 + 4, w, h, 6);
  ctx.fill();

  // Reinforced Titanium Safe Housing
  const vGrad = ctx.createLinearGradient(cx - w / 2, cy, cx + w / 2, cy);
  vGrad.addColorStop(0, "#1e293b");
  vGrad.addColorStop(0.5, "#334155");
  vGrad.addColorStop(1, "#1e293b");
  ctx.fillStyle = vGrad;
  roundRect(ctx, cx - w / 2, cy - h / 2, w, h, 6);
  ctx.fill();
  ctx.strokeStyle = "#0ea5e9";
  ctx.lineWidth = 1.5;
  roundRect(ctx, cx - w / 2, cy - h / 2, w, h, 6);
  ctx.stroke();

  // High-Security Lock Wheel / Cryptographic Core
  ctx.fillStyle = "#090d16";
  ctx.beginPath();
  ctx.arc(cx, cy, 14, 0, Math.PI * 2);
  ctx.fill();
  ctx.strokeStyle = "#38bdf8";
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.arc(cx, cy, 14, 0, Math.PI * 2);
  ctx.stroke();

  // Cyan Vault Hub Glow
  ctx.fillStyle = "#38bdf8";
  ctx.shadowColor = "#38bdf8";
  ctx.shadowBlur = 8;
  ctx.beginPath();
  ctx.arc(cx, cy, 5, 0, Math.PI * 2);
  ctx.fill();
  ctx.shadowBlur = 0;

  // Vault Status Slots (Carrier cells on left and right)
  for (let s = 0; s < 3; s++) {
    ctx.fillStyle = "rgba(56, 189, 248, 0.25)";
    roundRect(ctx, cx - w / 2 + 8, cy - h / 2 + 8 + s * 14, 18, 9, 2);
    ctx.fill();
    roundRect(ctx, cx + w / 2 - 26, cy - h / 2 + 8 + s * 14, 18, 9, 2);
    ctx.fill();
  }

  if (label) {
    drawStationLabel(ctx, label, cx, cy + h / 2 + 14);
  }

  ctx.restore();
}

function drawSecurityPortal(ctx, cx, cy, w, h, isExit) {
  ctx.save();
  const color = isExit ? "#f43f5e" : "#10b981";

  // Bulkhead Door frame
  ctx.fillStyle = "#0f172a";
  roundRect(ctx, cx - w / 2, cy - h / 2, w, h, 4);
  ctx.fill();
  ctx.strokeStyle = color;
  ctx.lineWidth = 2;
  roundRect(ctx, cx - w / 2, cy - h / 2, w, h, 4);
  ctx.stroke();

  // Caution hazard diagonal stripes on portal frame
  ctx.strokeStyle = "rgba(245, 158, 11, 0.4)";
  ctx.lineWidth = 2;
  for (let i = -h / 2 + 4; i < h / 2; i += 10) {
    ctx.beginPath();
    ctx.moveTo(cx - w / 2 + 2, cy + i);
    ctx.lineTo(cx + w / 2 - 2, cy + i + 6);
    ctx.stroke();
  }

  // Glowing status beacon
  ctx.fillStyle = color;
  ctx.shadowColor = color;
  ctx.shadowBlur = 8;
  ctx.beginPath();
  ctx.arc(cx, cy - h / 2 + 6, 3, 0, Math.PI * 2);
  ctx.fill();
  ctx.shadowBlur = 0;

  // Text label
  ctx.font = "700 8px ui-monospace, 'SF Mono', monospace";
  ctx.textAlign = "center";
  ctx.fillStyle = "#e2e8f0";
  ctx.fillText(isExit ? "EXIT" : "ENTRY", cx, cy + 3);

  ctx.restore();
}

function drawStationLabel(ctx, text, x, y) {
  ctx.save();
  ctx.font = "600 10px ui-monospace, 'SF Mono', Menlo, monospace";
  const tw = ctx.measureText(text).width;
  ctx.fillStyle = "rgba(15, 23, 42, 0.88)";
  roundRect(ctx, x - tw / 2 - 6, y - 9, tw + 12, 16, 4);
  ctx.fill();
  ctx.strokeStyle = "rgba(148, 163, 184, 0.3)";
  ctx.lineWidth = 1;
  roundRect(ctx, x - tw / 2 - 6, y - 9, tw + 12, 16, 4);
  ctx.stroke();

  ctx.textAlign = "center";
  ctx.fillStyle = "#cbd5e1";
  ctx.fillText(text, x, y + 3);
  ctx.restore();
}

/* ------------------------------------------------------------- Operator Agents */

function drawNPC(ctx, o) {
  const { x, y, hue = 190, generation = 0, walking = 0, dead = false,
          busy = false, alpha = 1, size = 26, idle = 0, label = "" } = o;

  ctx.save();
  ctx.globalAlpha = alpha;

  const sway = Math.sin(idle * Math.PI * 2) * 1.5;
  const yy = y - (walking === 0 ? sway : 0);

  // Operator ground shadow
  ctx.fillStyle = "rgba(0, 0, 0, 0.45)";
  ctx.beginPath();
  ctx.ellipse(x, yy + size / 2, size * 0.45, size * 0.18, 0, 0, Math.PI * 2);
  ctx.fill();

  const step = Math.sin(walking * Math.PI * 2);
  const legSwing = step * size * 0.22;
  const bodyW = size * 0.58;
  const bodyH = size * 0.44;
  const bx = x;
  const by = yy - size * 0.05;

  // Legs with tactical boots
  ctx.fillStyle = "#1e293b";
  ctx.fillRect(bx - bodyW * 0.38, by + bodyH * 0.4, bodyW * 0.28, size * 0.32 + legSwing);
  ctx.fillRect(bx + bodyW * 0.10, by + bodyH * 0.4, bodyW * 0.28, size * 0.32 - legSwing);

  // Boots
  ctx.fillStyle = "#0f172a";
  ctx.fillRect(bx - bodyW * 0.42, by + bodyH * 0.4 + size * 0.28 + legSwing, bodyW * 0.34, 4);
  ctx.fillRect(bx + bodyW * 0.08, by + bodyH * 0.4 + size * 0.28 - legSwing, bodyW * 0.34, 4);

  // Tactical Cleanroom Torso / Suit (Hue-coded)
  const suitColor = `hsl(${hue}, 65%, 42%)`;
  const suitHighlight = `hsl(${hue}, 70%, 55%)`;

  ctx.fillStyle = suitColor;
  roundRect(ctx, bx - bodyW / 2, by - bodyH / 2, bodyW, bodyH, 4);
  ctx.fill();
  ctx.strokeStyle = "rgba(15, 23, 42, 0.9)";
  ctx.lineWidth = 1.5;
  roundRect(ctx, bx - bodyW / 2, by - bodyH / 2, bodyW, bodyH, 4);
  ctx.stroke();

  // Chest Armor Plate / Telemetry Rig
  ctx.fillStyle = "#0f172a";
  roundRect(ctx, bx - bodyW * 0.32, by - bodyH * 0.35, bodyW * 0.64, bodyH * 0.7, 2);
  ctx.fill();

  // Glowing Telemetry Core / Heartbeat LED
  ctx.fillStyle = suitHighlight;
  ctx.shadowColor = suitHighlight;
  ctx.shadowBlur = 6;
  ctx.beginPath();
  ctx.arc(bx, by - 1, 2.5, 0, Math.PI * 2);
  ctx.fill();
  ctx.shadowBlur = 0;

  // Backpack Telemetry Rig
  ctx.fillStyle = "#334155";
  ctx.fillRect(bx - bodyW * 0.45, by - bodyH * 0.4, 3, bodyH * 0.6);
  ctx.fillRect(bx + bodyW * 0.45 - 3, by - bodyH * 0.4, 3, bodyH * 0.6);

  // High-Tech Cybernetic Helmet
  const headR = bodyW * 0.36;
  const headY = by - bodyH / 2 - headR + 2;

  // Helmet shell
  ctx.fillStyle = "#1e293b";
  ctx.beginPath();
  ctx.arc(bx, headY, headR, 0, Math.PI * 2);
  ctx.fill();
  ctx.strokeStyle = "rgba(15, 23, 42, 0.9)";
  ctx.lineWidth = 1.4;
  ctx.stroke();

  // Glowing Visor (Visor HUD)
  const visorColor = `hsl(${hue}, 95%, 62%)`;
  ctx.fillStyle = visorColor;
  ctx.shadowColor = visorColor;
  ctx.shadowBlur = 8;
  roundRect(ctx, bx - headR * 0.75, headY - headR * 0.25, headR * 1.5, headR * 0.6, 2);
  ctx.fill();
  ctx.shadowBlur = 0;

  // Visor reflection shine
  ctx.fillStyle = "rgba(255, 255, 255, 0.7)";
  ctx.fillRect(bx - headR * 0.55, headY - headR * 0.2, headR * 0.5, 1.5);

  // Generation Rank Rings (Clean concentric orbital rings)
  for (let i = 0; i < Math.max(0, generation); i++) {
    ctx.strokeStyle = visorColor;
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.arc(bx, headY - headR - 6 - i * 6, 3.5, 0, Math.PI * 2);
    ctx.stroke();
  }

  // Active / Busy Telemetry Badge
  if (busy) {
    ctx.save();
    ctx.fillStyle = "#f59e0b";
    ctx.shadowColor = "#f59e0b";
    ctx.shadowBlur = 6;
    ctx.font = "700 12px system-ui";
    ctx.textAlign = "center";
    ctx.fillText("⚡", bx, headY - headR - 8 - generation * 6);
    ctx.restore();
  }

  // Decommissioned / Purged Status
  if (dead) {
    ctx.strokeStyle = "#f43f5e";
    ctx.lineWidth = 2.5;
    ctx.beginPath();
    ctx.moveTo(bx - 8, yy - 8); ctx.lineTo(bx + 8, yy + 8);
    ctx.moveTo(bx + 8, yy - 8); ctx.lineTo(bx - 8, yy + 8);
    ctx.stroke();
  }

  ctx.restore();
}

/* ------------------------------------------------------------- Artifact & Carrier Icons */

function drawArtifactIcon(ctx, kind, x, y, scale) {
  const s = scale || 1;
  ctx.save();
  ctx.translate(x, y);
  ctx.scale(s, s);

  // Glowing base ring
  ctx.fillStyle = "rgba(15, 23, 42, 0.85)";
  ctx.beginPath();
  ctx.arc(0, 0, 13, 0, Math.PI * 2);
  ctx.fill();
  ctx.strokeStyle = "#38bdf8";
  ctx.lineWidth = 1.5;
  ctx.stroke();

  if (kind === "carrier") {
    // Encrypted Carrier Capsule
    ctx.fillStyle = "#0284c7";
    roundRect(ctx, -7, -9, 14, 18, 3);
    ctx.fill();
    ctx.fillStyle = "#38bdf8";
    ctx.fillRect(-5, -6, 10, 4);
    ctx.fillStyle = "#f8fafc";
    ctx.font = "700 8px ui-monospace";
    ctx.textAlign = "center";
    ctx.fillText("⬢", 0, 6);
  } else if (kind === "provider_response") {
    // Telemetry Payload Packet
    ctx.fillStyle = "#7c3aed";
    roundRect(ctx, -8, -6, 16, 12, 2);
    ctx.fill();
    ctx.strokeStyle = "#c084fc";
    ctx.lineWidth = 1;
    ctx.strokeRect(-8, -6, 16, 12);
    ctx.fillStyle = "#f8fafc";
    ctx.font = "700 8px ui-monospace";
    ctx.textAlign = "center";
    ctx.fillText("⇄", 0, 3);
  } else if (kind === "note" || kind === "file") {
    // Research Report Document
    ctx.fillStyle = "#f1f5f9";
    roundRect(ctx, -6, -8, 12, 16, 2);
    ctx.fill();
    ctx.strokeStyle = "#cbd5e1";
    ctx.lineWidth = 1;
    ctx.strokeRect(-6, -8, 12, 16);
    ctx.fillStyle = "#3b82f6";
    ctx.fillRect(-3, -5, 6, 2);
    ctx.fillRect(-3, -1, 6, 2);
    ctx.fillRect(-3, 3, 4, 2);
  } else {
    // Generic Secure State Unit
    ctx.fillStyle = "#d97706";
    roundRect(ctx, -7, -7, 14, 14, 3);
    ctx.fill();
    ctx.strokeStyle = "#fbbf24";
    ctx.lineWidth = 1;
    ctx.strokeRect(-7, -7, 14, 14);
    ctx.fillStyle = "#ffffff";
    ctx.beginPath();
    ctx.arc(0, 0, 2.5, 0, Math.PI * 2);
    ctx.fill();
  }

  ctx.restore();
}

/* Telemetry bubble for messages & events */
function drawBubble(ctx, x, y, text, alpha) {
  ctx.save();
  ctx.globalAlpha = Math.max(0, Math.min(1, alpha));
  ctx.font = "600 11px ui-monospace, 'SF Mono', Menlo, monospace";
  const tw = ctx.measureText(text).width;
  const w = Math.min(220, tw + 20);
  const h = 24;

  // Background HUD card
  ctx.fillStyle = "rgba(15, 23, 42, 0.95)";
  roundRect(ctx, x - w / 2, y - h - 10, w, h, 5);
  ctx.fill();

  ctx.strokeStyle = "#38bdf8";
  ctx.lineWidth = 1.2;
  roundRect(ctx, x - w / 2, y - h - 10, w, h, 5);
  ctx.stroke();

  // Pointer indicator
  ctx.fillStyle = "#38bdf8";
  ctx.beginPath();
  ctx.moveTo(x - 4, y - 10);
  ctx.lineTo(x + 4, y - 10);
  ctx.lineTo(x, y - 6);
  ctx.closePath();
  ctx.fill();

  // Text
  ctx.textAlign = "center";
  ctx.fillStyle = "#f8fafc";
  ctx.fillText(text, x, y - 10 - 7);

  ctx.restore();
}


