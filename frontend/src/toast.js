// Little pop-up messages ("Meal saved") in the corner of the screen.
// Any page can call notify("Saved"), and the <Toasts /> component in App shows it for a few seconds.
const listeners = new Set();
let nextId = 1;

export function notify(message, kind = "ok") {
  const toast = { id: nextId++, message, kind };   // kind: "ok", "warn" or "error"
  listeners.forEach((listener) => listener(toast));
}

export function onToast(listener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}
