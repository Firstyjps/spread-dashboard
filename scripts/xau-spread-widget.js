// XAU Spread Widget for iOS Scriptable
// Setup: Install "Scriptable" from App Store → Create new script → Paste this code
// Then add a Scriptable widget to your home screen and select this script.
//
// CHANGE THIS to your dashboard URL:
const API_URL = "https://dash.firstyjps.com/api/v1/spreads?symbol=XAUTUSDT&minutes=60";

// --- Fetch data ---
let data;
try {
  const req = new Request(API_URL);
  req.timeoutInterval = 10;
  data = await req.loadJSON();
} catch (e) {
  const w = new ListWidget();
  w.addText("Failed to load").font = Font.caption1();
  Script.setWidget(w);
  Script.complete();
  return;
}

const current = data.current;
const stats = data.stats;

// Convert to bps
const midBps = current ? (current.exchange_spread_mid * 10000).toFixed(1) : "-";
const longBps = current ? (current.long_spread * 10000).toFixed(1) : "-";
const shortBps = current ? (current.short_spread * 10000).toFixed(1) : "-";
const meanBps = stats?.mean != null ? (stats.mean * 10000).toFixed(1) : "-";
const p10Bps = stats?.p10 != null ? (stats.p10 * 10000).toFixed(1) : "-";
const p90Bps = stats?.p90 != null ? (stats.p90 * 10000).toFixed(1) : "-";

// Color based on spread value
function spreadColor(bps) {
  const v = parseFloat(bps);
  if (isNaN(v)) return Color.gray();
  if (v >= 80) return new Color("#34d399"); // green — good spread
  if (v >= 60) return new Color("#fbbf24"); // yellow — moderate
  return new Color("#f87171");              // red — tight
}

// --- Build widget ---
const w = new ListWidget();
w.backgroundColor = new Color("#0a0a0a");
w.setPadding(12, 14, 12, 14);

// Header
const header = w.addStack();
const title = header.addText("XAU SPREAD");
title.font = Font.boldSystemFont(11);
title.textColor = new Color("#6b7280");
header.addSpacer();
const dot = header.addText("●");
dot.font = Font.systemFont(8);
dot.textColor = new Color("#34d399");

w.addSpacer(6);

// Main spread value
const mainStack = w.addStack();
mainStack.centerAlignContent();
const mainVal = mainStack.addText(midBps);
mainVal.font = Font.boldMonospacedSystemFont(32);
mainVal.textColor = spreadColor(midBps);
mainStack.addSpacer(4);
const mainUnit = mainStack.addText("bps");
mainUnit.font = Font.systemFont(12);
mainUnit.textColor = new Color("#6b7280");

w.addSpacer(6);

// Long / Short row
const lsStack = w.addStack();
lsStack.spacing = 12;

const longLabel = lsStack.addText("L ");
longLabel.font = Font.systemFont(10);
longLabel.textColor = new Color("#6b7280");
const longVal = lsStack.addText(longBps);
longVal.font = Font.monospacedDigitSystemFont(12, false);
longVal.textColor = new Color("#60a5fa");

lsStack.addSpacer();

const shortLabel = lsStack.addText("S ");
shortLabel.font = Font.systemFont(10);
shortLabel.textColor = new Color("#6b7280");
const shortVal = lsStack.addText(shortBps);
shortVal.font = Font.monospacedDigitSystemFont(12, false);
shortVal.textColor = new Color("#f87171");

w.addSpacer(6);

// Stats row (P10 / Mean / P90)
const statsStack = w.addStack();
statsStack.spacing = 4;

function addStat(stack, label, value, color) {
  const s = stack.addStack();
  s.layoutVertically();
  s.centerAlignContent();
  const l = s.addText(label);
  l.font = Font.systemFont(8);
  l.textColor = new Color("#4b5563");
  const v = s.addText(value);
  v.font = Font.monospacedDigitSystemFont(10, false);
  v.textColor = color;
}

addStat(statsStack, "P10", p10Bps, new Color("#38bdf8"));
statsStack.addSpacer();
addStat(statsStack, "MEAN", meanBps, new Color("#fbbf24"));
statsStack.addSpacer();
addStat(statsStack, "P90", p90Bps, new Color("#f472b6"));

w.addSpacer(4);

// Updated time
const now = new Date();
const timeStr = `${now.getHours().toString().padStart(2, "0")}:${now.getMinutes().toString().padStart(2, "0")}`;
const updated = w.addText(`Updated ${timeStr}`);
updated.font = Font.systemFont(8);
updated.textColor = new Color("#374151");
updated.rightAlignText();

// --- Set widget ---
Script.setWidget(w);
Script.complete();

// Preview in app
if (config.runsInApp) {
  w.presentSmall();
}
