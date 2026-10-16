// A small wrapper around fetch for calling our services.
//
// Every address starts with /api/..., with no server name. The browser sends it to whatever
// served the page: the gateway when running locally, the Ingress on Kubernetes. So the same build
// works in both places.
import { getToken } from "./auth.js";

// Every service adds an X-Served-By header naming the container (or pod) that answered. The footer
// listens for it, to show load balancing in action.
const listeners = new Set();

export function onServedBy(listener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export async function api(path, { method = "GET", body } = {}) {
  const headers = {};
  const token = await getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  if (body !== undefined) headers["Content-Type"] = "application/json";

  const response = await fetch(path, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  });

  const servedBy = response.headers.get("X-Served-By");
  if (servedBy) listeners.forEach((listener) => listener({ pod: servedBy, service: serviceFor(path) }));

  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const error = new Error(errorMessage(data, response.status));
    error.status = response.status;
    throw error;
  }
  return data;
}

function serviceFor(path) {
  if (path.startsWith("/api/meals")) return "meal-logging";
  if (path.startsWith("/api/nutrients")) return "nutrient-calc";
  if (path.startsWith("/api/gaps")) return "gap-analysis";
  if (path.startsWith("/api/recommend")) return "food-recommender";
  return "?";
}

function errorMessage(data, status) {
  const detail = data?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((d) => d.msg.replace(/^Value error, /, "")).join("; ");   // form errors
  if (status === 502 || status === 503 || status === 504) {
    return "That part of MacroScope isn't answering right now. Please try again in a moment.";
  }
  return `Something went wrong (error ${status}).`;
}

// Each nutrient's display name and kind, fetched once and kept:
// {"vitamin_b12": {"name": "Vitamin B12", "category": "vitamin"}, ...}
let namesPromise = null;

export function nutrientNames() {
  if (!namesPromise) {
    namesPromise = api("/api/nutrients/nutrients")
      .then((rows) => Object.fromEntries(rows.map((n) => [n.key, { name: n.name, category: n.category }])))
      .catch(() => {
        namesPromise = null;   // try again next time
        return {};
      });
  }
  return namesPromise;
}
