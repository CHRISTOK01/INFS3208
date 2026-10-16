// Small helpers for showing numbers, units, names and dates.

// Today's date where the person is, as YYYY-MM-DD (the services work in whole days)
export function todayString() {
  return toDateString(new Date());
}

function toDateString(d) {
  const local = new Date(d.getTime() - d.getTimezoneOffset() * 60000);
  return local.toISOString().slice(0, 10);
}

// "2026-10-17" plus or minus some days
export function shiftDate(day, days) {
  const d = new Date(`${day}T12:00:00`);   // midday, so daylight saving can't push it to another day
  d.setDate(d.getDate() + days);
  return toDateString(d);
}

// "Today", "Yesterday" or "Thu 15 Oct"
export function niceDate(day) {
  if (day === todayString()) return "Today";
  if (day === shiftDate(todayString(), -1)) return "Yesterday";
  return new Date(`${day}T12:00:00`).toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short" });
}

export function unit(u) {
  return u === "ug" ? "µg" : u;
}

// 1790.4 -> "1,790", 28.94 -> "29", 6.62 -> "6.6", 0.143 -> "0.14", null -> "?"
export function amount(x) {
  if (x === null || x === undefined) return "?";
  if (Math.abs(x) >= 10) return Math.round(x).toLocaleString();
  return String(Number(x.toPrecision(2)));
}

export function niceName(key, names) {
  return names[key]?.name || key.replaceAll("_", " ");
}

// Split a food name into the main part and the details:
// "Banana, cavendish, peeled, raw" -> ["Banana", "cavendish, peeled, raw"]
export function splitName(name) {
  const i = name.indexOf(",");
  return i === -1 ? [name, ""] : [name.slice(0, i), name.slice(i + 1).trim()];
}

export const MACROS = ["energy", "protein", "carbs", "fat", "fibre"];
// Things with a limit but no target
export const LIMITS = ["sodium", "saturated_fat", "free_sugars", "alcohol", "caffeine"];

// The colour each macro uses everywhere (they're set in styles.css)
export const MACRO_COLOURS = {
  energy: "var(--c-energy)",
  protein: "var(--c-protein)",
  carbs: "var(--c-carbs)",
  fat: "var(--c-fat)",
  fibre: "var(--c-fibre)",
};

// Read a colour from the stylesheet, for Chart.js (which can't use CSS variables directly)
export function cssColour(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

// "#1f6b4f" -> "rgba(31, 107, 79, 0.35)", for see-through chart colours
export function withAlpha(hex, alpha) {
  const n = parseInt(hex.replace("#", ""), 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`;
}

// What kind of food data we have, for the label next to each food
export function dataLabel(dataType) {
  if (dataType === "ausnut_food") return "Australian";
  if (dataType === "branded_food") return "Packaged";
  return "USDA";
}
