// The food diary: one section per meal, each listing what you had with its calories, an edit and
// a delete button on every food, and "+ Add food". Adding opens a panel to search, scan a barcode
// or pick a saved recipe, and logs it straight away.
//
//   Breakfast                       320 kcal
//     Banana, cavendish   1 medium   122 kcal   [edit] [delete]
//     + Add food
//   Lunch ...
import { useCallback, useEffect, useState } from "react";
import { api } from "../api.js";
import Icon from "../components/Icon.jsx";
import { Callout, Empty, Meter, Segmented, Skeleton, Stepper } from "../components/ui.jsx";
import { amount, dataLabel, niceDate, splitName, todayString } from "../format.js";
import { notify } from "../toast.js";

const MEALS = [
  ["breakfast", "Breakfast", "sun"],
  ["lunch", "Lunch", "bowl"],
  ["dinner", "Dinner", "moon"],
  ["snack", "Snacks", "apple"],
];

// Energy per 100 g of each food, from nutrient-calc. Fetched once per food and kept, so the
// diary can show calories next to every item.
const kcalCache = new Map();
function kcalPer100g(fdcId) {
  if (!kcalCache.has(fdcId)) {
    kcalCache.set(fdcId, api(`/api/nutrients/foods/${fdcId}`)
      .then((f) => f.per_100g.find((n) => n.key === "energy")?.amount ?? null)
      .catch(() => null));
  }
  return kcalCache.get(fdcId);
}

export default function LogMeal({ user, day }) {
  const [meals, setMeals] = useState(null);       // everything logged on the day
  const [recipes, setRecipes] = useState([]);
  const [energy, setEnergy] = useState(null);     // today's energy row from gap-analysis
  const [kcal, setKcal] = useState({});           // fdc_id -> kcal per 100 g
  const [adding, setAdding] = useState(null);     // which meal the "add food" panel is for

  const loadDay = useCallback(() => {
    api(`/api/meals/meals?start=${day}`).then(setMeals).catch((e) => notify(e.message, "error"));
    api(`/api/gaps/today/${user.uid}?date=${day}`)
      .then((t) => setEnergy({ row: t.nutrients.find((n) => n.nutrient_key === "energy"), left: t.remaining.energy }))
      .catch(() => setEnergy(null));
  }, [day, user]);
  const loadRecipes = useCallback(() => {
    api("/api/meals/recipes").then(setRecipes).catch(() => {});
  }, []);

  useEffect(loadDay, [loadDay]);
  useEffect(loadRecipes, [loadRecipes]);

  // Look up the calories for any foods we haven't seen yet
  useEffect(() => {
    if (!meals) return;
    const ids = [...new Set(meals.flatMap((m) => m.items.map((i) => i.fdc_id)))].filter((id) => !(id in kcal));
    ids.forEach((id) => kcalPer100g(id).then((v) => setKcal((old) => ({ ...old, [id]: v }))));
  }, [meals]);   // eslint-disable-line react-hooks/exhaustive-deps

  function itemKcal(item) {
    const per100 = kcal[item.fdc_id];
    return per100 === undefined || per100 === null ? null : (per100 * item.grams) / 100;
  }

  // Add one food to a meal: into the meal of that type already logged today, or a new one
  async function addFood(mealType, item) {
    const existing = meals?.find((m) => m.meal_type === mealType);
    try {
      const saved = existing
        ? await api(`/api/meals/meals/${existing.id}/items`, { method: "POST", body: { items: [item] } })
        : await api("/api/meals/meals", { method: "POST", body: { meal_date: day, meal_type: mealType, items: [item] } });
      notifySaved(saved, `Added to ${labelOf(mealType).toLowerCase()}`);
      loadDay();
      return true;
    } catch (e) {
      notify(e.message, "error");
      return false;
    }
  }

  async function logRecipe(mealType, recipe) {
    try {
      const saved = await api(`/api/meals/recipes/${recipe.id}/log`, { method: "POST", body: { meal_date: day, meal_type: mealType } });
      notifySaved(saved, `Added "${recipe.name}" to ${labelOf(mealType).toLowerCase()}`);
      loadDay();
    } catch (e) {
      notify(e.message, "error");
    }
  }

  async function changeItem(meal, item, amountBody) {
    try {
      const saved = await api(`/api/meals/meals/${meal.id}/items/${item.id}`, { method: "PATCH", body: amountBody });
      notifySaved(saved, "Updated");
      loadDay();
      return true;
    } catch (e) {
      notify(e.message, "error");
      return false;
    }
  }

  async function deleteItem(meal, item) {
    try {
      // The last food in a meal takes the (now empty) meal with it
      if (meal.items.length === 1) await api(`/api/meals/meals/${meal.id}`, { method: "DELETE" });
      else await api(`/api/meals/meals/${meal.id}/items/${item.id}`, { method: "DELETE" });
      notify(`Removed ${splitName(item.name)[0].toLowerCase()}`);
      loadDay();
    } catch (e) {
      notify(e.message, "error");
    }
  }

  async function saveRecipe(mealType, name) {
    const items = (meals || []).filter((m) => m.meal_type === mealType).flatMap((m) => m.items)
      .map((i) => ({ fdc_id: i.fdc_id, grams: Number(i.grams) }));
    try {
      await api("/api/meals/recipes", { method: "POST", body: { name, items } });
      notify(`Saved "${name}" as a recipe`);
      loadRecipes();
      return true;
    } catch (e) {
      notify(e.message, "error");
      return false;
    }
  }

  async function catchUp() {
    try {
      await api("/api/meals/meals/recalculate-pending", { method: "POST" });
      notify("Your totals are up to date");
      loadDay();
    } catch (e) {
      notify(e.message, "error");
    }
  }

  const anyPending = meals?.some((m) => m.calc_status === "pending");

  return (
    <div className="diary stack">
      <div className="page-head">
        <div>
          <h1 className="display">Food diary</h1>
          <p>{day === todayString() ? "What you've eaten today." : `What you ate on ${niceDate(day)}.`} Tap + to add food to a meal.</p>
        </div>
      </div>

      <DaySummary energy={energy} />

      {anyPending && (
        <Callout kind="amber" icon="refresh">
          <div className="between" style={{ flexWrap: "wrap" }}>
            <span>Some food was saved while the nutrient calculator was down, so its totals are waiting.</span>
            <button className="btn small" onClick={catchUp}>Update my totals</button>
          </div>
        </Callout>
      )}

      {!meals ? (
        MEALS.map(([key]) => <Skeleton key={key} height={110} />)
      ) : (
        MEALS.map(([type, label, icon]) => (
          <MealSection
            key={type}
            type={type}
            label={label}
            icon={icon}
            meals={meals.filter((m) => m.meal_type === type)}
            itemKcal={itemKcal}
            onAdd={() => setAdding(type)}
            onChange={changeItem}
            onDelete={deleteItem}
            onSaveRecipe={(name) => saveRecipe(type, name)}
          />
        ))
      )}

      {adding && (
        <AddFoodSheet
          mealType={adding}
          recipes={recipes}
          onAdd={(item) => addFood(adding, item)}
          onLogRecipe={(recipe) => logRecipe(adding, recipe)}
          onClose={() => setAdding(null)}
        />
      )}
    </div>
  );
}

function labelOf(type) {
  return MEALS.find(([key]) => key === type)[1];
}

function notifySaved(saved, message) {
  if (saved?.calc_status === "pending") notify("Saved. The nutrient calculator is busy or down, so your totals will catch up shortly.", "warn");
  else notify(message);
}

// ---------------------------------------------------------------- the day's energy, at the top

function DaySummary({ energy }) {
  if (!energy?.row) return null;
  const eaten = energy.row.amount ?? 0;
  const target = energy.row.target_amount;
  const over = eaten > target;
  return (
    <div className="card diary-summary">
      <div className="summary-numbers">
        <div><span className="num big">{amount(eaten)}</span><span className="faint small">eaten</span></div>
        <span className="faint">/</span>
        <div><span className="num big">{amount(target)}</span><span className="faint small">target</span></div>
        <span className="faint">=</span>
        <div className={over ? "over" : ""}>
          <span className="num big">{amount(Math.abs(target - eaten))}</span>
          <span className="faint small">{over ? "over" : "left"}</span>
        </div>
        <span className="faint small">kcal</span>
      </div>
      <Meter pct={(100 * eaten) / target} color={over ? "var(--amber)" : undefined} thick />
    </div>
  );
}

// ---------------------------------------------------------------- one meal

function MealSection({ type, label, icon, meals, itemKcal, onAdd, onChange, onDelete, onSaveRecipe }) {
  const [naming, setNaming] = useState(false);
  const [name, setName] = useState("");
  const rows = meals.flatMap((meal) => meal.items.map((item) => ({ meal, item })));
  const known = rows.map(({ item }) => itemKcal(item)).filter((k) => k !== null);
  const total = known.reduce((a, b) => a + b, 0);

  async function save(event) {
    event.preventDefault();
    if (await onSaveRecipe(name.trim())) {
      setNaming(false);
      setName("");
    }
  }

  return (
    <section className="card diary-section">
      <header className="diary-head">
        <span className={`meal-icon ${type}`}><Icon name={icon} /></span>
        <h2>{label}</h2>
        {rows.length > 0 && <span className="num diary-total">{amount(total)} kcal</span>}
      </header>

      {rows.length > 0 && (
        <ul className="diary-items">
          {rows.map(({ meal, item }) => (
            <DiaryItem key={item.id} meal={meal} item={item} kcal={itemKcal(item)} onChange={onChange} onDelete={onDelete} />
          ))}
        </ul>
      )}

      <div className="diary-actions">
        <button className="add-food" onClick={onAdd}><Icon name="plus" /> Add food</button>
        {rows.length > 0 && !naming && (
          <button className="link-btn small" onClick={() => setNaming(true)}><Icon name="bookmark" size={14} /> Save as recipe</button>
        )}
      </div>
      {naming && (
        <form className="row" onSubmit={save} style={{ marginTop: "0.6rem" }}>
          <input className="input" style={{ flex: "1 1 180px" }} value={name} onChange={(e) => setName(e.target.value)}
                 placeholder={`Name, like "Usual ${label.toLowerCase()}"`} maxLength={100} autoFocus />
          <button className="btn small" disabled={!name.trim()}>Save</button>
          <button type="button" className="btn small ghost" onClick={() => setNaming(false)}>Cancel</button>
        </form>
      )}
    </section>
  );
}

// One food in the diary. The edit button opens it up to change the amount.
function DiaryItem({ meal, item, kcal, onChange, onDelete }) {
  const [editing, setEditing] = useState(false);
  const [main, rest] = splitName(item.name);
  const howMuch = item.portion_desc && !item.portion_desc.startsWith("from recipe")
    ? `${item.portion_desc.replace(" x ", " × ")} · ${Math.round(item.grams)} g`
    : `${Math.round(item.grams)} g`;

  return (
    <li className={editing ? "diary-item editing" : "diary-item"}>
      <div className="diary-row">
        <div className="what">
          <span className="name"><strong>{main}</strong>{rest && <span className="faint">, {rest}</span>}</span>
          <span className="faint small">{howMuch}{meal.calc_status === "pending" && " · totals pending"}</span>
        </div>
        <span className="num kcal">{kcal === null ? "" : `${amount(kcal)} kcal`}</span>
        <button className="icon-btn" onClick={() => setEditing(!editing)} aria-label={`Change how much ${main}`} title="Edit amount"><Icon name="pencil" size={16} /></button>
        <button className="icon-btn danger" onClick={() => onDelete(meal, item)} aria-label={`Remove ${main}`} title="Delete"><Icon name="trash" size={16} /></button>
      </div>
      {editing && (
        <AmountPicker
          fdcId={item.fdc_id}
          start={item}
          buttonLabel="Save"
          onCancel={() => setEditing(false)}
          onPick={async (body) => { if (await onChange(meal, item, body)) setEditing(false); }}
        />
      )}
    </li>
  );
}

// ---------------------------------------------------------------- choosing an amount

// Pick how much: a household portion and how many, or grams. Used when adding and when editing.
// `start` is an item already logged (when editing), so it opens on what was there.
function AmountPicker({ fdcId, start, buttonLabel, onPick, onCancel }) {
  const [portions, setPortions] = useState(null);
  const [portionId, setPortionId] = useState("grams");
  const [quantity, setQuantity] = useState(1);
  const [grams, setGrams] = useState(start ? Math.round(start.grams) : 100);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api(`/api/meals/foods/${fdcId}`)
      .then((food) => {
        setPortions(food.portions);
        if (start) {
          // Opening an item to edit: find the portion it was logged with ("2 x 1 cup"), if any
          const match = /^([\d.]+) x (.+)$/.exec(start.portion_desc || "");
          const portion = match && food.portions.find((p) => p.description === match[2]);
          if (portion) {
            setPortionId(String(portion.id));
            setQuantity(Number(match[1]));
          }
        } else {
          const usual = usualPortion(food.portions);
          if (usual) setPortionId(String(usual.id));
        }
      })
      .catch((e) => notify(e.message, "error"));
  }, [fdcId]);   // eslint-disable-line react-hooks/exhaustive-deps

  if (!portions) return <div className="picker"><Skeleton height={38} /></div>;
  const portion = portions.find((p) => String(p.id) === portionId);
  const totalGrams = portion ? Math.round(portion.gram_weight * quantity) : Number(grams);

  async function pick() {
    setBusy(true);
    await onPick(portion ? { portion_id: portion.id, quantity: Number(quantity) } : { grams: Number(grams) });
    setBusy(false);
  }

  return (
    <div className="picker">
      <select className="input" value={portionId} onChange={(e) => setPortionId(e.target.value)} aria-label="Portion">
        {portions.map((p) => <option key={p.id} value={p.id}>{p.description} ({Math.round(p.gram_weight)} g)</option>)}
        <option value="grams">Weigh it in grams</option>
      </select>
      {portion ? (
        <Stepper value={quantity} onChange={setQuantity} step={0.5} min={0.25} max={50} />
      ) : (
        <div className="stepper" style={{ paddingRight: "0.7rem" }}>
          <input type="number" min="1" max="5000" value={grams} onChange={(e) => setGrams(e.target.value)} style={{ width: "4.5rem" }} aria-label="Grams" />
          <span className="muted small">g</span>
        </div>
      )}
      <span className="small muted num">≈ {totalGrams || 0} g</span>
      <button className="btn small" onClick={pick} disabled={busy || !totalGrams || totalGrams <= 0}>{buttonLabel}</button>
      {onCancel && <button className="btn small ghost" onClick={onCancel}>Cancel</button>}
    </div>
  );
}

// The portion to start with: a "medium" one if there is one, otherwise the first that's a decent
// size (so not "1 piece, bite-size"), otherwise whatever comes first
function usualPortion(portions) {
  return portions.find((p) => /medium/i.test(p.description))
    || portions.find((p) => p.gram_weight >= 40)
    || portions[0];
}

// ---------------------------------------------------------------- the "add food" panel

function AddFoodSheet({ mealType, recipes, onAdd, onLogRecipe, onClose }) {
  const [mode, setMode] = useState("search");     // "search", "barcode" or "recipes"
  const [query, setQuery] = useState("");
  const [state, setState] = useState("");         // "", "raw" or "cooked"
  const [results, setResults] = useState(null);
  const [searching, setSearching] = useState(false);
  const [openId, setOpenId] = useState(null);
  const [error, setError] = useState(null);
  const label = labelOf(mealType);

  // Close with the Escape key
  useEffect(() => {
    const onKey = (e) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  async function search(event) {
    event?.preventDefault();
    if (query.trim().length < 2) return;
    setError(null);
    setSearching(true);
    setOpenId(null);
    try {
      if (mode === "barcode") {
        const food = await api(`/api/meals/foods/barcode/${encodeURIComponent(query.trim())}`);
        setResults([food]);
        setOpenId(food.fdc_id);
      } else {
        const params = new URLSearchParams({ q: query });
        if (state) params.set("state", state);
        setResults(await api(`/api/meals/foods/search?${params}`));
      }
    } catch (e) {
      setError(e.message);
      setResults(null);
    } finally {
      setSearching(false);
    }
  }

  // Search again straight away when raw/cooked changes
  useEffect(() => {
    if (results && mode === "search") search();
  }, [state]);   // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="sheet-backdrop" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="sheet" role="dialog" aria-modal="true" aria-label={`Add food to ${label}`}>
        <div className="between">
          <h2>Add to {label.toLowerCase()}</h2>
          <button className="icon-btn" onClick={onClose} aria-label="Close"><Icon name="x" /></button>
        </div>
        <Segmented full value={mode} onChange={(m) => { setMode(m); setResults(null); setError(null); }}
                   options={[["search", "Search", "search"], ["barcode", "Barcode", "barcode"], ["recipes", "Recipes", "bookmark"]]} label="How to add" />

        {mode === "recipes" ? (
          recipes.length === 0 ? (
            <Empty icon="bookmark" title="No saved recipes yet">Use "Save as recipe" under a meal to log the same foods again in one tap.</Empty>
          ) : (
            <div className="recipes">
              {recipes.map((r) => (
                <div key={r.id} className="recipe">
                  <span className="food-avatar"><Icon name="bookmark" size={16} /></span>
                  <span className="what">
                    <strong className="small">{r.name}</strong>
                    <small>{r.items.map((i) => splitName(i.name)[0]).join(", ")}</small>
                  </span>
                  <button className="btn small" onClick={() => onLogRecipe(r)}><Icon name="plus" size={15} /> Add</button>
                </div>
              ))}
            </div>
          )
        ) : (
          <>
            <form onSubmit={search} className="row">
              <div className="search-box">
                <Icon name={mode === "barcode" ? "barcode" : "search"} />
                <input className="input" value={query} onChange={(e) => setQuery(e.target.value)} autoFocus
                       placeholder={mode === "barcode" ? "Type the numbers under the barcode" : "Try \"banana\" or \"rice boiled\""}
                       inputMode={mode === "barcode" ? "numeric" : "search"} />
              </div>
              <button type="submit" className="btn" disabled={query.trim().length < 2 || searching}>{searching ? "..." : mode === "barcode" ? "Look up" : "Search"}</button>
            </form>
            {mode === "search" && (
              <div className="row">
                <span className="small muted">Show first:</span>
                <Segmented value={state} onChange={setState} options={[["", "Either"], ["raw", "Raw"], ["cooked", "Cooked"]]} label="Raw or cooked" />
              </div>
            )}
            {error && <Callout kind="amber" icon="alert">{error}</Callout>}
            {searching && <div className="stack-sm">{[1, 2, 3].map((i) => <Skeleton key={i} height={52} />)}</div>}
            {!searching && !results && !error && (
              <Empty icon={mode === "barcode" ? "barcode" : "search"} title={`What did you have for ${label.toLowerCase()}?`}>
                {mode === "barcode"
                  ? "Type the numbers under a packaged food's barcode."
                  : "Search for a food, pick how much, and it's added straight away. Australian foods come first."}
              </Empty>
            )}
            {!searching && results && results.length === 0 && <Empty icon="search" title="No foods found">Try fewer or different words.</Empty>}
            {!searching && results && results.length > 0 && (
              <ul className="results">
                {results.map((food) => (
                  <SearchResult key={food.fdc_id} food={food} open={openId === food.fdc_id} label={label}
                                onToggle={() => setOpenId(openId === food.fdc_id ? null : food.fdc_id)}
                                onAdd={async (body) => { if (await onAdd({ fdc_id: food.fdc_id, ...body })) setOpenId(null); }} />
                ))}
              </ul>
            )}
          </>
        )}

        <button className="btn secondary block" onClick={onClose}>Done</button>
      </div>
    </div>
  );
}

function SearchResult({ food, open, label, onToggle, onAdd }) {
  const [main, rest] = splitName(food.name);
  return (
    <li className={open ? "result open" : "result"}>
      <button className="result-main" onClick={onToggle} aria-expanded={open}>
        <span className="food-avatar">{main[0]}</span>
        <span className="names">
          <strong>{main}</strong>{rest && <span className="rest">, {rest}</span>}
          <span className="meta">
            <span className="chip">{dataLabel(food.data_type)}</span>
            <Quality confidence={food.confidence} />
          </span>
        </span>
        <Icon name={open ? "x" : "plus"} />
      </button>
      {open && <AmountPicker fdcId={food.fdc_id} buttonLabel={`Add to ${label.toLowerCase()}`} onPick={onAdd} />}
    </li>
  );
}

// How much we know about a food's vitamins and minerals
function Quality({ confidence }) {
  const kind = confidence === "complete micronutrient data" ? "complete" : confidence === "label data only" ? "label" : "partial";
  const text = { complete: "full nutrient data", partial: "some nutrients missing", label: "label data only" }[kind];
  return <span className={`quality ${kind}`} title={confidence}><i />{text}</span>;
}
