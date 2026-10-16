// Logging food.
//
//   [ Find a food: search or barcode, results open up   ] [ Meal tray: what you're adding ]
//   [ to pick a portion                                 ] [ Saved recipes                 ]
//   [ Your day: everything logged, meal by meal                                         ]
import { useCallback, useEffect, useState } from "react";
import { api } from "../api.js";
import Icon from "../components/Icon.jsx";
import { Callout, Empty, Segmented, Skeleton, Stepper } from "../components/ui.jsx";
import { dataLabel, niceDate, splitName } from "../format.js";
import { notify } from "../toast.js";

const MEALS = [
  ["breakfast", "Breakfast", "sun"],
  ["lunch", "Lunch", "bowl"],
  ["dinner", "Dinner", "moon"],
  ["snack", "Snack", "apple"],
];
const MEAL_ICONS = Object.fromEntries(MEALS.map(([key, , icon]) => [key, icon]));

export default function LogMeal({ day }) {
  const [mealType, setMealType] = useState(guessMealType());
  const [items, setItems] = useState([]);        // the meal being put together
  const [meals, setMeals] = useState(null);      // what's already logged on the day
  const [recipes, setRecipes] = useState([]);
  const [busy, setBusy] = useState(false);

  const loadDay = useCallback(() => {
    api(`/api/meals/meals?start=${day}`).then(setMeals).catch((e) => notify(e.message, "error"));
  }, [day]);
  const loadRecipes = useCallback(() => {
    api("/api/meals/recipes").then(setRecipes).catch(() => {});
  }, []);

  useEffect(loadDay, [loadDay]);
  useEffect(loadRecipes, [loadRecipes]);

  // Run an API call; show a message if it worked, or the error if it didn't
  async function run(action, success) {
    setBusy(true);
    try {
      const result = await action();
      const message = typeof success === "function" ? success(result) : success;
      if (message) notify(message);
      return result;
    } catch (e) {
      notify(e.message, "error");
      return null;
    } finally {
      setBusy(false);
    }
  }

  function savedMessage(meal) {
    if (meal.calc_status === "pending") {
      notify("Saved. The nutrient calculator is busy or down, so your totals will catch up shortly.", "warn");
      return null;
    }
    return `${titleCase(meal.meal_type)} saved`;
  }

  async function saveMeal() {
    const meal = await run(
      () => api("/api/meals/meals", { method: "POST", body: { meal_date: day, meal_type: mealType, items: items.map(toApiItem) } }),
      savedMessage,
    );
    if (meal) {
      setItems([]);
      loadDay();
    }
  }

  async function saveRecipe(name) {
    const recipe = await run(
      () => api("/api/meals/recipes", { method: "POST", body: { name, items: items.map(toApiItem) } }),
      `Saved "${name}" as a recipe`,
    );
    if (recipe) loadRecipes();
    return Boolean(recipe);
  }

  async function logRecipe(recipe) {
    const meal = await run(
      () => api(`/api/meals/recipes/${recipe.id}/log`, { method: "POST", body: { meal_date: day, meal_type: mealType } }),
      savedMessage,
    );
    if (meal) loadDay();
  }

  async function deleteRecipe(recipe) {
    if (await run(() => api(`/api/meals/recipes/${recipe.id}`, { method: "DELETE" }), `Deleted "${recipe.name}"`)) loadRecipes();
  }

  async function deleteMeal(meal) {
    if (await run(() => api(`/api/meals/meals/${meal.id}`, { method: "DELETE" }), `${titleCase(meal.meal_type)} deleted`)) loadDay();
  }

  async function deleteItem(meal, item) {
    if (await run(() => api(`/api/meals/meals/${meal.id}/items/${item.id}`, { method: "DELETE" }), "Removed")) loadDay();
  }

  async function catchUp() {
    if (await run(() => api("/api/meals/meals/recalculate-pending", { method: "POST" }), "Your totals are up to date")) loadDay();
  }

  return (
    <div className="stack">
      <div className="page-head">
        <div>
          <h1 className="display">Log food</h1>
          <p>Search for what you ate, pick how much, and add it to a meal for {niceDate(day).toLowerCase()}.</p>
        </div>
      </div>

      <div className="grid grid-log">
        <FoodFinder onAdd={(item) => { setItems((old) => [...old, item]); notify(`Added ${splitName(item.name)[0].toLowerCase()} to your ${mealType}`); }} />

        <div className="stack sticky">
          <MealTray
            items={items}
            mealType={mealType}
            setMealType={setMealType}
            onRemove={(i) => setItems(items.filter((_, j) => j !== i))}
            onSave={saveMeal}
            onSaveRecipe={saveRecipe}
            busy={busy}
          />
          <Recipes recipes={recipes} mealType={mealType} onLog={logRecipe} onDelete={deleteRecipe} busy={busy} />
        </div>
      </div>

      <DayTimeline day={day} meals={meals} onDeleteMeal={deleteMeal} onDeleteItem={deleteItem} onCatchUp={catchUp} />
    </div>
  );
}

// ---------------------------------------------------------------- finding a food

function FoodFinder({ onAdd }) {
  const [mode, setMode] = useState("search");      // "search" or "barcode"
  const [query, setQuery] = useState("");
  const [state, setState] = useState("");          // "", "raw" or "cooked"
  const [results, setResults] = useState(null);
  const [searching, setSearching] = useState(false);
  const [openId, setOpenId] = useState(null);      // which result has its portion picker open
  const [error, setError] = useState(null);

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
    <div className="card">
      <div className="card-head">
        <h2>Find a food</h2>
        <Segmented value={mode} onChange={(m) => { setMode(m); setResults(null); setError(null); }} options={[["search", "Search", "search"], ["barcode", "Barcode", "barcode"]]} label="Search or barcode" />
      </div>
      <form onSubmit={search} className="row">
        <div className="search-box">
          <Icon name={mode === "barcode" ? "barcode" : "search"} />
          <input
            className="input"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={mode === "barcode" ? "Type the numbers under the barcode" : "Try \"banana\", \"rice boiled\" or \"chicken breast\""}
            inputMode={mode === "barcode" ? "numeric" : "search"}
            autoFocus
          />
        </div>
        <button type="submit" className="btn" disabled={query.trim().length < 2 || searching}>{searching ? "Looking..." : mode === "barcode" ? "Look up" : "Search"}</button>
      </form>
      {mode === "search" && (
        <div className="row" style={{ marginTop: "0.75rem" }}>
          <span className="small muted">Show first:</span>
          <Segmented value={state} onChange={setState} options={[["", "Either"], ["raw", "Raw"], ["cooked", "Cooked"]]} label="Raw or cooked" />
        </div>
      )}

      {error && <div style={{ marginTop: "0.9rem" }}><Callout kind="amber" icon="alert">{error}</Callout></div>}
      {searching && (
        <div className="stack-sm" style={{ marginTop: "0.9rem" }}>
          {[1, 2, 3, 4].map((i) => <Skeleton key={i} height={52} />)}
        </div>
      )}
      {!searching && results && results.length === 0 && (
        <Empty icon="search" title="No foods found">Try fewer words, or a more general name like "bread" instead of a brand.</Empty>
      )}
      {!searching && !results && !error && (
        <Empty icon="apple" title="What did you eat?">
          Australian foods come first, with full vitamin and mineral data. Say "raw" or "cooked" to get the right one.
        </Empty>
      )}
      {!searching && results && results.length > 0 && (
        <ul className="results">
          {results.map((r) => (
            <ResultRow key={r.fdc_id} food={r} open={openId === r.fdc_id} onToggle={() => setOpenId(openId === r.fdc_id ? null : r.fdc_id)} onAdd={(item) => { onAdd(item); setOpenId(null); }} />
          ))}
        </ul>
      )}
    </div>
  );
}

function ResultRow({ food, open, onToggle, onAdd }) {
  const [detail, setDetail] = useState(null);
  const [portionId, setPortionId] = useState("grams");
  const [quantity, setQuantity] = useState(1);
  const [grams, setGrams] = useState(100);
  const [main, rest] = splitName(food.name);

  // Load the household portions the first time the row is opened
  useEffect(() => {
    if (!open || detail) return;
    api(`/api/meals/foods/${food.fdc_id}`)
      .then((d) => {
        setDetail(d);
        const usual = usualPortion(d.portions);
        if (usual) setPortionId(String(usual.id));
      })
      .catch((e) => notify(e.message, "error"));
  }, [open, detail, food.fdc_id]);

  const portion = detail?.portions.find((p) => String(p.id) === portionId);
  const totalGrams = portion ? Math.round(portion.gram_weight * quantity) : Number(grams);

  function add() {
    if (portion) {
      onAdd({ fdc_id: food.fdc_id, name: food.name, portion_id: portion.id, quantity: Number(quantity), grams: totalGrams, label: `${quantity} × ${portion.description}` });
    } else {
      onAdd({ fdc_id: food.fdc_id, name: food.name, grams: Number(grams), label: `${grams} g` });
    }
  }

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
      {open && (
        <div className="picker">
          {!detail ? (
            <Skeleton height={38} />
          ) : (
            <>
              <select className="input" value={portionId} onChange={(e) => setPortionId(e.target.value)} aria-label="Portion">
                {detail.portions.map((p) => <option key={p.id} value={p.id}>{p.description} ({Math.round(p.gram_weight)} g)</option>)}
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
              <button className="btn small" onClick={add} disabled={!totalGrams || totalGrams <= 0}><Icon name="plus" size={15} /> Add</button>
            </>
          )}
        </div>
      )}
    </li>
  );
}

// How much we know about a food's vitamins and minerals
function Quality({ confidence }) {
  const kind = confidence === "complete micronutrient data" ? "complete" : confidence === "label data only" ? "label" : "partial";
  const text = { complete: "full nutrient data", partial: "some nutrients missing", label: "label data only" }[kind];
  return <span className={`quality ${kind}`} title={confidence}><i />{text}</span>;
}

// ---------------------------------------------------------------- the meal being put together

function MealTray({ items, mealType, setMealType, onRemove, onSave, onSaveRecipe, busy }) {
  const [naming, setNaming] = useState(false);
  const [recipeName, setRecipeName] = useState("");
  const total = items.reduce((sum, i) => sum + (i.grams || 0), 0);

  async function submitRecipe(event) {
    event.preventDefault();
    if (await onSaveRecipe(recipeName.trim())) {
      setNaming(false);
      setRecipeName("");
    }
  }

  return (
    <div className="card">
      <div className="card-head">
        <h2>Your meal</h2>
        {items.length > 0 && <span className="chip num">{items.length} {items.length === 1 ? "food" : "foods"} · {Math.round(total)} g</span>}
      </div>
      <Segmented full value={mealType} onChange={setMealType} options={MEALS.map(([v, label, icon]) => [v, label, icon])} label="Which meal" />

      {items.length === 0 ? (
        <Empty icon={MEAL_ICONS[mealType]} title="Nothing added yet">Find a food on the left and press Add.</Empty>
      ) : (
        <ul className="tray-items" style={{ margin: "0.75rem 0" }}>
          {items.map((item, i) => {
            const [main, rest] = splitName(item.name);
            return (
              <li key={i}>
                <span className="food-avatar">{main[0]}</span>
                <span className="what">
                  <strong className="small">{main}</strong>{rest && <span className="small muted">, {rest}</span>}
                  <small>{item.label}</small>
                </span>
                <button className="icon-btn danger" onClick={() => onRemove(i)} aria-label={`Remove ${item.name}`}><Icon name="x" size={16} /></button>
              </li>
            );
          })}
        </ul>
      )}

      {naming ? (
        <form onSubmit={submitRecipe} className="row">
          <input className="input" style={{ flex: "1 1 160px" }} value={recipeName} onChange={(e) => setRecipeName(e.target.value)} placeholder="Name, like &quot;Usual breakfast&quot;" maxLength={100} autoFocus />
          <button className="btn small" disabled={!recipeName.trim() || busy}>Save</button>
          <button type="button" className="btn small ghost" onClick={() => setNaming(false)}>Cancel</button>
        </form>
      ) : (
        <div className="row">
          <button className="btn" style={{ flex: 1 }} disabled={items.length === 0 || busy} onClick={onSave}>
            <Icon name="check" /> Save {mealType}
          </button>
          <button className="btn secondary" disabled={items.length === 0 || busy} onClick={() => setNaming(true)} title="Save these foods as a recipe to log again later">
            <Icon name="bookmark" /> Recipe
          </button>
        </div>
      )}
    </div>
  );
}

function Recipes({ recipes, mealType, onLog, onDelete, busy }) {
  if (recipes.length === 0) return null;
  return (
    <div className="card">
      <div className="card-head">
        <h2>Saved recipes</h2>
        <span className="sub">log again in one click</span>
      </div>
      <div className="recipes">
        {recipes.map((r) => (
          <div key={r.id} className="recipe">
            <span className="food-avatar"><Icon name="bookmark" size={16} /></span>
            <span className="what">
              <strong className="small">{r.name}</strong>
              <small>{r.items.map((i) => splitName(i.name)[0]).join(", ")}</small>
            </span>
            <button className="btn small secondary" disabled={busy} onClick={() => onLog(r)}>Log as {mealType}</button>
            <button className="icon-btn danger" onClick={() => onDelete(r)} aria-label={`Delete ${r.name}`}><Icon name="trash" size={16} /></button>
          </div>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- everything logged on the day

function DayTimeline({ day, meals, onDeleteMeal, onDeleteItem, onCatchUp }) {
  const order = MEALS.map(([key]) => key);
  const sorted = meals ? [...meals].sort((a, b) => order.indexOf(a.meal_type) - order.indexOf(b.meal_type)) : [];
  const anyPending = sorted.some((m) => m.calc_status === "pending");

  return (
    <div className="card">
      <div className="card-head">
        <div>
          <h2>{niceDate(day)}'s food</h2>
          <p className="sub">Everything logged on {niceDate(day).toLowerCase()}.</p>
        </div>
      </div>
      {anyPending && (
        <div style={{ marginBottom: "0.75rem" }}>
          <Callout kind="amber" icon="refresh">
            <div className="between" style={{ flexWrap: "wrap" }}>
              <span>Some meals were saved while the nutrient calculator was down, so their totals are waiting.</span>
              <button className="btn small" onClick={onCatchUp}>Update my totals</button>
            </div>
          </Callout>
        </div>
      )}
      {!meals ? (
        <div className="stack-sm">{[1, 2].map((i) => <Skeleton key={i} height={56} />)}</div>
      ) : sorted.length === 0 ? (
        <Empty icon="calendar" title="Nothing logged on this day">Meals you save show up here.</Empty>
      ) : (
        <div className="timeline">
          {sorted.map((meal) => (
            <div key={meal.id} className="meal">
              <span className={`meal-icon ${meal.meal_type}`}><Icon name={MEAL_ICONS[meal.meal_type]} /></span>
              <div>
                <div className="between">
                  <strong>
                    {titleCase(meal.meal_type)}{" "}
                    {meal.calc_status === "pending" && <span className="chip amber">totals pending</span>}
                  </strong>
                  <button className="btn small danger" onClick={() => onDeleteMeal(meal)}><Icon name="trash" size={15} /> Delete</button>
                </div>
                <ul>
                  {meal.items.map((item) => (
                    <li key={item.id}>
                      <span>
                        {splitName(item.name)[0]} <span className="faint">· {Math.round(item.grams)} g{item.portion_desc ? ` · ${item.portion_desc}` : ""}</span>
                      </span>
                      <button className="icon-btn danger" onClick={() => onDeleteItem(meal, item)} aria-label={`Remove ${item.name}`}><Icon name="x" size={14} /></button>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------- helpers

// The portion to start with: a "medium" one if there is one, otherwise the first that's a decent
// size (so not "1 piece, bite-size"), otherwise whatever comes first
function usualPortion(portions) {
  return portions.find((p) => /medium/i.test(p.description))
    || portions.find((p) => p.gram_weight >= 40)
    || portions[0];
}

function toApiItem(item) {
  return item.portion_id
    ? { fdc_id: item.fdc_id, portion_id: item.portion_id, quantity: item.quantity }
    : { fdc_id: item.fdc_id, grams: item.grams };
}

function titleCase(text) {
  return text[0].toUpperCase() + text.slice(1);
}

function guessMealType() {
  const hour = new Date().getHours();
  if (hour < 10) return "breakfast";
  if (hour < 15) return "lunch";
  if (hour < 21) return "dinner";
  return "snack";
}
