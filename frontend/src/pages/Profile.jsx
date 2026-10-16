// Your details, and the targets they lead to. gap-analysis works out every target from these.
import { useEffect, useState } from "react";
import { api, nutrientNames } from "../api.js";
import Icon from "../components/Icon.jsx";
import { Callout, Segmented, SkeletonCard, Stepper } from "../components/ui.jsx";
import { amount, niceName, unit } from "../format.js";
import { notify } from "../toast.js";

const EMPTY = {
  sex: "female",
  date_of_birth: "",
  height_cm: "",
  weight_kg: "",
  lifestyle: "seated_some_walking",
  exercise_sessions_per_week: 0,
  goal: "maintain",
  diet: "omnivore",
  pregnant: false,
  due_date: "",
  pre_pregnancy_weight_kg: "",
  breastfeeding: false,
};

// Short names for the lifestyle choices (gap-analysis gives the longer descriptions)
const LIFESTYLE_TITLES = {
  mostly_seated: "Mostly sitting",
  seated_some_walking: "Sitting, with some walking",
  standing_walking: "On my feet most of the day",
  heavy_work: "Heavy physical work",
};

export default function Profile({ user, day, firstTime, onSaved }) {
  const [form, setForm] = useState(EMPTY);
  const [options, setOptions] = useState(null);
  const [result, setResult] = useState(null);      // targets, situation and notes
  const [names, setNames] = useState({});
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    nutrientNames().then(setNames);
    api("/api/gaps/profile-options").then(setOptions).catch((e) => setError(e.message));
    if (firstTime) return;
    api(`/api/gaps/profile/${user.uid}`)
      .then((p) =>
        setForm({
          ...EMPTY,
          ...p,
          pregnant: Boolean(p.due_date),
          due_date: p.due_date || "",
          pre_pregnancy_weight_kg: p.pre_pregnancy_weight_kg ?? "",
        }),
      )
      .catch((e) => setError(e.message));
    api(`/api/gaps/targets/${user.uid}?date=${day}`).then(setResult).catch(() => {});
  }, [user, day, firstTime]);

  function set(field, value) {
    setForm((old) => {
      const next = { ...old, [field]: value };
      if (next.sex === "male") Object.assign(next, { pregnant: false, breastfeeding: false });
      // No weight loss or gain targets during pregnancy or breastfeeding
      if (next.pregnant || next.breastfeeding) next.goal = "maintain";
      return next;
    });
  }

  async function save(event) {
    event.preventDefault();
    setError(null);
    setSaving(true);
    const body = {
      sex: form.sex,
      date_of_birth: form.date_of_birth,
      height_cm: Number(form.height_cm),
      weight_kg: Number(form.weight_kg),
      lifestyle: form.lifestyle,
      exercise_sessions_per_week: Number(form.exercise_sessions_per_week),
      goal: form.goal,
      diet: form.diet,
      due_date: form.pregnant ? form.due_date : null,
      pre_pregnancy_weight_kg: form.pregnant && form.pre_pregnancy_weight_kg !== "" ? Number(form.pre_pregnancy_weight_kg) : null,
      breastfeeding: form.breastfeeding,
    };
    try {
      setResult(await api(`/api/gaps/profile/${user.uid}`, { method: "PUT", body }));
      notify(firstTime ? "All set! Here are your targets." : "Saved. Your targets are updated.");
      onSaved();
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  }

  if (!options) {
    return error ? <Callout kind="amber" icon="alert">{error}</Callout> : <div className="grid grid-profile"><SkeletonCard lines={8} /><SkeletonCard lines={6} /></div>;
  }

  const locked = form.pregnant || form.breastfeeding;

  return (
    <div className="stack">
      <div className="page-head">
        <div>
          <h1 className="display">{firstTime ? "Let's set your targets" : "My details"}</h1>
          <p>
            We use these to work out what you need each day, from the Australian NHMRC Nutrient Reference Values.
            {firstTime && " It takes about a minute."}
          </p>
        </div>
      </div>

      <div className="grid grid-profile">
        <form className="card" onSubmit={save}>
          <section className="form-section">
            <h3><span className="step-num">1</span>About you</h3>
            <Segmented full value={form.sex} onChange={(v) => set("sex", v)} options={[["female", "Female"], ["male", "Male"]]} label="Sex" />
            <p className="faint tiny">Asked because the NHMRC tables and the energy equation are split into male and female.</p>
            <div className="field-row">
              <label className="field">
                Date of birth
                <input className="input" type="date" value={form.date_of_birth} onChange={(e) => set("date_of_birth", e.target.value)} required />
              </label>
              <label className="field">
                <span>Height <span className="hint">cm</span></span>
                <input className="input" type="number" min="100" max="250" step="0.1" value={form.height_cm} onChange={(e) => set("height_cm", e.target.value)} required placeholder="165" />
              </label>
              <label className="field">
                <span>Weight <span className="hint">kg</span></span>
                <input className="input" type="number" min="25" max="350" step="0.1" value={form.weight_kg} onChange={(e) => set("weight_kg", e.target.value)} required placeholder="60" />
              </label>
            </div>
          </section>

          <section className="form-section">
            <h3><span className="step-num">2</span>Your day</h3>
            <div className="choices" role="radiogroup" aria-label="What a normal day looks like">
              {options.lifestyle.map((l) => (
                <button type="button" key={l.value} role="radio" aria-checked={form.lifestyle === l.value} className={form.lifestyle === l.value ? "choice on" : "choice"} onClick={() => set("lifestyle", l.value)}>
                  <span className="radio" />
                  <span><strong>{LIFESTYLE_TITLES[l.value] || l.value}</strong><span>{l.description}</span></span>
                </button>
              ))}
            </div>
            <div className="between" style={{ flexWrap: "wrap" }}>
              <span className="small muted" style={{ maxWidth: "34ch" }}>{options.exercise_sessions_per_week}</span>
              <Stepper value={form.exercise_sessions_per_week} onChange={(v) => set("exercise_sessions_per_week", v)} min={0} max={14} />
            </div>
          </section>

          <section className="form-section">
            <h3><span className="step-num">3</span>Goal and diet</h3>
            <Segmented full value={form.goal} onChange={(v) => !locked && set("goal", v)} options={[["lose", "Lose weight"], ["maintain", "Stay the same"], ["gain", "Gain weight"]]} label="Goal" />
            <Segmented full value={form.diet} onChange={(v) => set("diet", v)} options={[["omnivore", "I eat everything"], ["vegetarian", "Vegetarian"], ["vegan", "Vegan"]]} label="Diet" />
          </section>

          {form.sex === "female" && (
            <section className="form-section">
              <h3><span className="step-num">4</span>Pregnancy and breastfeeding</h3>
              <label className="toggle">
                <input type="checkbox" checked={form.pregnant} onChange={(e) => set("pregnant", e.target.checked)} />
                I'm pregnant
              </label>
              {form.pregnant && (
                <div className="field-row fade-in">
                  <label className="field">
                    Due date
                    <input className="input" type="date" value={form.due_date} onChange={(e) => set("due_date", e.target.value)} required />
                  </label>
                  <label className="field">
                    <span>Weight before pregnancy <span className="hint">kg, optional</span></span>
                    <input className="input" type="number" min="25" max="350" step="0.1" value={form.pre_pregnancy_weight_kg} onChange={(e) => set("pre_pregnancy_weight_kg", e.target.value)} />
                  </label>
                </div>
              )}
              <label className="toggle">
                <input type="checkbox" checked={form.breastfeeding} onChange={(e) => set("breastfeeding", e.target.checked)} />
                I'm breastfeeding
              </label>
              {locked && <Callout icon="heart">Your goal stays "stay the same". Please talk to your doctor or midwife about weight.</Callout>}
            </section>
          )}

          <div style={{ marginTop: "1.5rem" }} className="stack-sm">
            {error && <Callout kind="red" icon="alert">{error}</Callout>}
            <button type="submit" className="btn block" disabled={saving}>
              <Icon name="check" /> {saving ? "Working out your targets..." : firstTime ? "Set my targets" : "Save changes"}
            </button>
          </div>
        </form>

        {result ? <Targets result={result} names={names} /> : <TargetsPlaceholder />}
      </div>
    </div>
  );
}

function TargetsPlaceholder() {
  return (
    <div className="card">
      <h2>Your daily targets</h2>
      <p className="muted small" style={{ marginTop: "0.5rem" }}>Fill in your details and they'll appear here, with where each number comes from.</p>
    </div>
  );
}

function Targets({ result, names }) {
  const s = result.situation;
  const energy = result.targets.find((t) => t.nutrient_key === "energy");
  const groupOf = (key) => {
    if (["energy", "protein", "carbs", "fat", "fibre"].includes(key)) return "macro";
    if (["saturated_fat", "free_sugars", "alcohol", "caffeine"].includes(key)) return "limit";
    return names[key]?.category === "vitamin" ? "vitamin" : names[key]?.category === "mineral" ? "mineral" : "other";
  };
  const groups = [["macro", "Energy and macros"], ["vitamin", "Vitamins"], ["mineral", "Minerals"], ["other", "Other"], ["limit", "Limits"]];

  return (
    <div className="card sticky">
      <div className="card-head">
        <h2>Your daily targets</h2>
        {s.life_stage === "pregnant" && <span className="chip plum"><Icon name="baby" size={14} /> week {s.pregnancy_week}, trimester {s.trimester}</span>}
        {s.life_stage === "breastfeeding" && <span className="chip plum"><Icon name="heart" size={14} /> breastfeeding</span>}
      </div>
      <div className="stats">
        <div className="stat"><div className="k">Energy</div><div className="v num">{amount(energy?.target_amount)} <small>kcal</small></div></div>
        <div className="stat"><div className="k">Kilojoules</div><div className="v num">{s.energy_kj.toLocaleString()} <small>kJ</small></div></div>
        <div className="stat"><div className="k">Resting</div><div className="v num">{s.bmr_kcal.toLocaleString()} <small>kcal</small></div></div>
        <div className="stat"><div className="k">Activity</div><div className="v num">×{s.activity_level}</div></div>
      </div>
      {result.notes.length > 0 && (
        <div style={{ marginTop: "1rem" }}>
          <Callout kind="brand" icon="info"><ul>{result.notes.map((n) => <li key={n}>{n}</li>)}</ul></Callout>
        </div>
      )}
      <div className="table-wrap">
        {groups.map(([key, title]) => {
          const rows = result.targets.filter((t) => groupOf(t.nutrient_key) === key);
          if (rows.length === 0) return null;
          return (
            <div key={key}>
              <div className="group-title">{title}</div>
              <table className="fixed">
                <colgroup><col style={{ width: "32%" }} /><col style={{ width: "24%" }} /><col /></colgroup>
                <tbody>
                  {rows.map((t) => (
                    <tr key={t.nutrient_key}>
                      <td><strong>{niceName(t.nutrient_key, names)}</strong></td>
                      <td className="num nowrap">
                        {t.target_amount !== null && <>{amount(t.target_amount)} {unit(t.unit)}</>}
                        {t.target_amount === null && t.upper_limit !== null && <>under {amount(t.upper_limit)} {unit(t.unit)}</>}
                        {t.target_amount !== null && t.upper_limit !== null && <div className="faint tiny">max {amount(t.upper_limit)}</div>}
                      </td>
                      <td className="faint tiny">{t.source}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          );
        })}
      </div>
    </div>
  );
}
