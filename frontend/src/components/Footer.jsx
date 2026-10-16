// The footer shows whether each service is up and which version it's running, and which container
// (or Kubernetes pod) answered the last request. Handy for showing load balancing, rolling updates
// and rollbacks.
import { useEffect, useState } from "react";
import { api, onServedBy } from "../api.js";

const SERVICES = [
  ["meal-logging", "/api/meals/version"],
  ["nutrient-calc", "/api/nutrients/version"],
  ["gap-analysis", "/api/gaps/version"],
  ["food-recommender", "/api/recommend/version"],
];

export default function Footer({ tab }) {
  const [last, setLast] = useState(null);
  const [versions, setVersions] = useState({});

  useEffect(() => onServedBy(setLast), []);

  // Check the versions when the page opens, on every tab change, and every 30 seconds
  useEffect(() => {
    function check() {
      for (const [name, path] of SERVICES) {
        api(path)
          .then((v) => setVersions((old) => ({ ...old, [name]: v.version })))
          .catch(() => setVersions((old) => ({ ...old, [name]: "down" })));
      }
    }
    check();
    const timer = setInterval(check, 30000);
    return () => clearInterval(timer);
  }, [tab]);

  return (
    <footer className="app-footer">
      <div className="services">
        {SERVICES.map(([name]) => {
          const v = versions[name];
          return (
            <span key={name} className="service-chip" title={v === "down" ? `${name} isn't answering` : `${name} is up`}>
              <span className={v === "down" ? "dot down" : v ? "dot ok" : "dot"} />
              {name} <span className="faint">{v && v !== "down" ? `v${v}` : v || "..."}</span>
            </span>
          );
        })}
      </div>
      <div className="served-by">
        {last ? <>Last answer from <strong>{last.service}</strong> on <code>{last.pod}</code></> : "Waiting for the first answer"}
      </div>
      <p className="disclaimer">
        Estimates from food composition data (FSANZ AUSNUT 2023 and USDA FoodData Central), with targets from the
        NHMRC Nutrient Reference Values. Not medical advice: talk to a doctor or dietitian about your diet, especially in pregnancy.
      </p>
    </footer>
  );
}
