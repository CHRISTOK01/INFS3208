// Food ideas from food-recommender, three ways:
//   Today       what would fill the most of what you still need to hit today's targets (the default)
//   This week   what would help with what you've been short on over the last 7 days
//   Rich in...  good sources of any one nutrient
import { useEffect, useState } from "react";
import { api, nutrientNames } from "../api.js";
import Icon from "../components/Icon.jsx";
import { Callout, Empty, Meter, Segmented, SkeletonCard } from "../components/ui.jsx";
import { MACROS, amount, niceName, splitName, unit } from "../format.js";

// Each food group gets a colour, used for the strip along the top of its cards
const GROUP_COLOURS = {
  "vegetables and legumes": "brand",
  fruit: "coral",
  "grain foods": "amber",
  "milk, yoghurt, cheese and alternatives": "sky",
  "lean meats, fish, eggs, nuts, seeds and tofu": "plum",
};

export default function Suggestions({ user, day }) {
  const [mode, setMode] = useState("today");       // "today", "week" or "nutrient"
  const [nutrient, setNutrient] = useState("iron");
  const [choices, setChoices] = useState([]);
  const [result, setResult] = useState(null);
  const [names, setNames] = useState({});
  const [error, setError] = useState(null);

  // The nutrients you can ask about: anything with a daily target except energy and the macros
  useEffect(() => {
    nutrientNames().then(setNames);
    api(`/api/gaps/targets/${user.uid}?date=${day}`)
      .then((t) => setChoices(t.targets.filter((r) => r.target_amount && !MACROS.slice(0, 4).includes(r.nutrient_key))))
      .catch(() => {});
  }, [user, day]);

  useEffect(() => {
    setResult(null);
    setError(null);
    const extra = mode === "nutrient" ? `&nutrient=${nutrient}` : `&period=${mode}`;
    api(`/api/recommend/foods/${user.uid}?date=${day}${extra}`).then(setResult).catch((e) => setError(e.message));
  }, [user, day, mode, nutrient]);

  return (
    <div className="stack">
      <div className="page-head">
        <div>
          <h1 className="display">Food ideas</h1>
          <p>Everyday Australian foods, scored on one standard serve, that fit the energy you have left today.</p>
        </div>
        <div className="row">
          <Segmented value={mode} onChange={setMode} options={[["today", "Today", "sun"], ["week", "This week", "calendar"], ["nutrient", "Rich in...", "search"]]} label="What to suggest" />
          {mode === "nutrient" && (
            <select className="input" style={{ width: "auto" }} value={nutrient} onChange={(e) => setNutrient(e.target.value)} aria-label="Nutrient">
              {choices.map((c) => <option key={c.nutrient_key} value={c.nutrient_key}>{niceName(c.nutrient_key, names)}</option>)}
            </select>
          )}
        </div>
      </div>

      {error && <Callout kind="amber" icon="alert">{error}</Callout>}

      {result && (
        <div className="card">
          <div className="summary">
            <div className="stack-sm">
              <h2>
                {mode === "today" && "To hit today's targets, you still need"}
                {mode === "week" && "Over the last 7 days, you've been short on"}
                {mode === "nutrient" && `Good sources of ${niceName(nutrient, names).toLowerCase()}`}
              </h2>
              {mode !== "nutrient" && result.gaps.length > 0 && (
                <div className="gap-chips">
                  {result.gaps.map((g) => (
                    <span key={g.nutrient_key} className="chip coral num">
                      {niceName(g.nutrient_key, names)} · {amount(g.shortfall)} {unit(g.unit)} {mode === "today" ? "to go" : "a day short"}
                    </span>
                  ))}
                </div>
              )}
              <p className="small muted">
                {mode === "today" && "These are the furthest from their targets. The foods below are scored on everything you haven't reached yet today."}
                {mode === "week" && "For catching up on a low week. This needs at least 3 days logged, and doesn't count today until it's over."}
                {mode === "nutrient" && "Scored against your whole daily target, whether you're short or not."}
              </p>
            </div>
            {result.energy_left_kcal !== null && (
              <div className="stat" style={{ minWidth: 170 }}>
                <div className="k">Energy left today</div>
                {result.energy_left_kcal > 0 ? (
                  <div className="v num">{amount(result.energy_left_kcal)} <small>kcal</small></div>
                ) : (
                  <>
                    <div className="v">All used</div>
                    <div className="faint tiny">so only light foods (150 kcal or less)</div>
                  </>
                )}
              </div>
            )}
          </div>
        </div>
      )}

      {!result && !error && (
        <div className="suggestions">{[1, 2, 3, 4, 5, 6].map((i) => <SkeletonCard key={i} lines={4} />)}</div>
      )}

      {result && result.suggestions.length === 0 && (
        <div className="card">
          <Empty
            icon={result.gaps.length === 0 && mode !== "nutrient" ? "check" : "search"}
            title={result.gaps.length === 0 && mode !== "nutrient" ? (mode === "today" ? "Every target reached today" : "No gaps this week") : "No foods fit right now"}
          >
            {result.notes[0]}
          </Empty>
        </div>
      )}

      {result && result.suggestions.length > 0 && (
        <div className="suggestions">
          {result.suggestions.map((s, i) => <SuggestionCard key={s.fdc_id} s={s} rank={i + 1} names={names} />)}
        </div>
      )}

      {result && result.notes.length > 0 && result.suggestions.length > 0 && (
        <Callout icon="info">
          <ul>{result.notes.map((n) => <li key={n}>{n}</li>)}</ul>
        </Callout>
      )}
    </div>
  );
}

function SuggestionCard({ s, rank, names }) {
  const [main, rest] = splitName(s.name);
  const colour = GROUP_COLOURS[s.food_group] || "brand";
  return (
    <article className="card suggestion fade-in" style={{ animationDelay: `${rank * 40}ms` }}>
      <span className="band" style={{ background: `var(--${colour})` }} />
      <span className="rank">#{rank}</span>
      <div>
        <span className={`chip ${colour}`}>{s.food_group}</span>
        <h3 style={{ marginTop: "0.6rem" }}>{main}</h3>
        {rest && <p className="rest">{rest}</p>}
      </div>
      <div className="row">
        <span className="chip"><Icon name="scale" size={13} /> 1 serve · {s.serve_g} g</span>
        {s.kcal !== null && <span className="chip"><Icon name="flame" size={13} /> {s.kcal} kcal</span>}
      </div>
      <div className="covers">
        {s.covers.map((c) => (
          <div key={c.nutrient_key} className="cover">
            <div className="top">
              <strong>{niceName(c.nutrient_key, names)}</strong>
              <span className="num muted">{amount(c.amount)} {unit(c.unit)} · {c.pct_of_shortfall}%</span>
            </div>
            <Meter pct={c.pct_of_shortfall} />
          </div>
        ))}
      </div>
      <p className="why">{s.why}</p>
    </article>
  );
}
