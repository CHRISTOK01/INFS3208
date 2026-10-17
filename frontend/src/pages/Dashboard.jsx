// The day at a glance, and the bigger picture over the last 7 days.
//
//   [ Today: energy ring + macros        ] [ Your focus: biggest gaps ]
//   [ Vitamins and minerals today (chart)                             ]
//   [ Energy over the last 14 days       ] [ Limits today             ]
//   [ Your nutrient report: gap cards, and every nutrient in a table  ]
import { BarElement, CategoryScale, Chart, LinearScale, Tooltip } from "chart.js";
import { useEffect, useState } from "react";
import { Bar } from "react-chartjs-2";
import { api, nutrientNames } from "../api.js";
import Icon from "../components/Icon.jsx";
import { Callout, Empty, Meter, Ring, Segmented, SkeletonCard } from "../components/ui.jsx";
import { LIMITS, MACROS, MACRO_COLOURS, amount, cssColour, niceDate, niceName, shiftDate, todayString, unit, withAlpha } from "../format.js";

// Chart.js only includes the parts you register, which keeps the download small
Chart.register(BarElement, CategoryScale, LinearScale, Tooltip);
Chart.defaults.font.family = "'Inter Variable', system-ui, sans-serif";

export default function Dashboard({ user, day, onGoTo }) {
  const [today, setToday] = useState(null);
  const [report, setReport] = useState(null);
  const [history, setHistory] = useState(null);
  const [names, setNames] = useState({});
  const [errors, setErrors] = useState({});

  useEffect(() => {
    nutrientNames().then(setNames);
    setToday(null);
    setReport(null);
    setHistory(null);
    setErrors({});
    const failed = (part) => (e) => setErrors((old) => ({ ...old, [part]: e.message }));
    // Separate calls, so if one part of the app is down the rest of the page still shows
    api(`/api/gaps/today/${user.uid}?date=${day}`).then(setToday).catch(failed("today"));
    api(`/api/gaps/report/${user.uid}?date=${day}`).then(setReport).catch(failed("report"));
    api(`/api/nutrients/daily/${user.uid}?start=${shiftDate(day, -13)}&end=${day}`)
      .then((r) => setHistory(r.days))
      .catch(failed("history"));
  }, [user, day]);

  const byKey = today ? Object.fromEntries(today.nutrients.map((n) => [n.nutrient_key, n])) : {};

  return (
    <div className="stack">
      <div className="page-head">
        <div>
          <h1 className="display">{niceDate(day)}</h1>
          <p>How {day === todayString() ? "your eating today compares" : "your eating on this day compared"} with the targets made for you.</p>
        </div>
        <button className="btn" onClick={() => onGoTo("log")}><Icon name="plus" /> Log food</button>
      </div>

      <div className="grid grid-hero">
        {errors.today ? <ErrorCard message={errors.today} /> : today ? <TodayCard byKey={byKey} remaining={today.remaining} onGoTo={onGoTo} /> : <SkeletonCard lines={6} />}
        {errors.report ? <ErrorCard message={errors.report} /> : report ? <FocusCard report={report} names={names} onGoTo={onGoTo} /> : <SkeletonCard lines={4} />}
      </div>

      {today && <MicroCard rows={today.nutrients} names={names} nothingLogged={byKey.energy?.amount === null} />}

      <div className="grid grid-2">
        {errors.history ? <ErrorCard message={errors.history} /> : history && today ? <TrendCard days={history} day={day} target={byKey.energy?.target_amount} /> : <SkeletonCard lines={5} />}
        {today ? <LimitsCard byKey={byKey} names={names} isToday={day === todayString()} /> : <SkeletonCard lines={5} />}
      </div>

      {report && <ReportCard report={report} names={names} />}
    </div>
  );
}

// "vitamin", "mineral", or "other" for everything else (fibre, omega-3, saturated fat and so on)
function groupOf(key, names) {
  const category = names[key]?.category;
  return category === "vitamin" || category === "mineral" ? category : "other";
}

// How chart pop-ups look: dark text on a light box in dark mode, and the other way round in
// light mode. The colours come from the stylesheet, so both charts always match.
function tooltipLook() {
  return {
    backgroundColor: cssColour("--ink"),
    titleColor: cssColour("--bg"),
    bodyColor: cssColour("--bg"),
    padding: 10,
    cornerRadius: 8,
    displayColors: false,
    titleFont: { weight: 700 },
  };
}

function ErrorCard({ message }) {
  return <div className="card"><Callout kind="amber" icon="alert">{message}</Callout></div>;
}

// ---------------------------------------------------------------- today: energy ring and macros

function TodayCard({ byKey, remaining, onGoTo }) {
  const energy = byKey.energy;
  const eaten = energy?.amount ?? 0;
  const nothingLogged = energy?.amount === null;

  return (
    <div className="card">
      <div className="card-head">
        <h2>Energy and macros</h2>
        <span className="sub">target {amount(energy?.target_amount)} kcal</span>
      </div>
      {nothingLogged ? (
        <Empty icon="apple" title="Nothing logged yet" action={<button className="btn small" onClick={() => onGoTo("log")}>Log your first meal</button>}>
          Log what you eat and your numbers fill in here.
        </Empty>
      ) : (
        <div className="today-hero">
          <Ring pct={energy?.pct_of_target}>
            <div className="big num">{amount(eaten)}</div>
            <div className="label">of {amount(energy?.target_amount)} kcal</div>
            {eaten > energy.target_amount ? (
              <div className="chip amber" style={{ marginTop: "0.5rem" }}>{amount(eaten - energy.target_amount)} over</div>
            ) : (
              <div className="chip brand" style={{ marginTop: "0.5rem" }}>{amount(remaining.energy)} left</div>
            )}
          </Ring>
          <div className="macro-list">
            {["protein", "carbs", "fat", "fibre"].map((key) => {
              const row = byKey[key];
              if (!row) return null;
              return (
                <div key={key} className="macro-row">
                  <div className="top">
                    <span className="name"><i className="swatch" style={{ background: MACRO_COLOURS[key] }} />{key === "carbs" ? "Carbs" : key[0].toUpperCase() + key.slice(1)}</span>
                    <span className="num small"><strong>{amount(row.amount ?? 0)}</strong> / {amount(row.target_amount)} {unit(row.unit)}</span>
                  </div>
                  <Meter pct={row.pct_of_target} color={MACRO_COLOURS[key]} thick />
                  {remaining[key] !== undefined && <div className="left">{remaining[key] > 0 ? `${amount(remaining[key])} ${unit(row.unit)} to go` : "Target reached"}</div>}
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------- your focus: the biggest gaps

function FocusCard({ report, names, onGoTo }) {
  const week = report.windows[0];      // the last 7 days
  const rows = Object.fromEntries(week.nutrients.map((n) => [n.nutrient_key, n]));
  const top = week.top_gaps.slice(0, 3);
  const enoughDays = week.days_logged === undefined || week.days_logged >= 3;

  return (
    <div className="card focus-card">
      <div className="card-head">
        <h2>Your focus this week</h2>
        <span className="sub">last 7 days</span>
      </div>
      {!enoughDays ? (
        <Empty icon="calendar" title="Not enough days yet">
          Log at least 3 days and we'll show what you're often short on.
        </Empty>
      ) : top.length === 0 ? (
        <Empty icon="check" title="No gaps. Nice work!">Everything we can check is at least 70% of your target.</Empty>
      ) : (
        <>
          <p className="small muted">You're often short on these. A little more each day would help.</p>
          <div className="focus-list">
            {top.map((key) => {
              const n = rows[key];
              return (
                <div key={key} className="focus-item">
                  <div className="top">
                    <strong>{niceName(key, names)}</strong>
                    <span className="num muted">{Math.round(n.pct_of_target)}% of target</span>
                  </div>
                  <Meter pct={n.pct_of_target} thick />
                </div>
              );
            })}
          </div>
          {week.excesses.length > 0 && (
            <p className="small muted" style={{ marginBottom: "1rem" }}>
              Over the limit:{" "}
              {week.excesses.map((k) => <span key={k} className="chip red" style={{ marginRight: "0.3rem" }}>{niceName(k, names)}</span>)}
            </p>
          )}
          <button className="btn block" onClick={() => onGoTo("suggestions")}><Icon name="sparkle" /> Foods that would help</button>
        </>
      )}
    </div>
  );
}

// ---------------------------------------------------------------- vitamins and minerals chart

// Draws a dashed line on a chart at one value (the 100% mark, or the energy target)
const targetLine = {
  id: "targetLine",
  afterDatasetsDraw(chart, _args, options) {
    if (options.value === undefined || options.value === null) return;
    const { ctx, chartArea } = chart;
    ctx.save();
    ctx.strokeStyle = options.colour;
    ctx.setLineDash([5, 4]);
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    if (options.axis === "x") {
      const x = chart.scales.x.getPixelForValue(options.value);
      ctx.moveTo(x, chartArea.top);
      ctx.lineTo(x, chartArea.bottom);
    } else {
      const y = chart.scales.y.getPixelForValue(options.value);
      ctx.moveTo(chartArea.left, y);
      ctx.lineTo(chartArea.right, y);
    }
    ctx.stroke();
    ctx.restore();
  },
};

function MicroCard({ rows, names, nothingLogged }) {
  const [kind, setKind] = useState("vitamin");
  const shown = rows.filter((r) => r.target_amount && !MACROS.includes(r.nutrient_key) && groupOf(r.nutrient_key, names) === kind);

  const colours = {
    met: cssColour("--brand"), close: cssColour("--sky"), low: cssColour("--coral"), unknown: cssColour("--surface-3"),
  };
  function colourFor(r) {
    if (r.amount !== null && r.coverage_pct !== null && r.coverage_pct < 80) return colours.unknown;   // partly unknown
    if ((r.pct_of_target ?? 0) >= 100) return colours.met;
    if ((r.pct_of_target ?? 0) >= 70) return colours.close;
    return colours.low;
  }

  const data = {
    labels: shown.map((r) => niceName(r.nutrient_key, names)),
    datasets: [{
      data: shown.map((r) => Math.min(r.pct_of_target ?? 0, 150)),   // so one huge number doesn't squash the rest
      backgroundColor: shown.map(colourFor),
      borderRadius: 6,
      borderSkipped: false,
      barThickness: 14,
    }],
  };
  const grid = cssColour("--line");
  const text = cssColour("--ink-2");
  const options = {
    indexAxis: "y",
    maintainAspectRatio: false,
    scales: {
      x: { min: 0, max: 150, grid: { color: grid }, border: { display: false }, ticks: { color: text, callback: (v) => `${v}%`, stepSize: 25 } },
      y: { grid: { display: false }, border: { display: false }, ticks: { color: cssColour("--ink"), font: { weight: 600 } } },
    },
    plugins: {
      targetLine: { axis: "x", value: 100, colour: cssColour("--ink-3") },
      tooltip: {
        ...tooltipLook(),
        callbacks: {
          label: (ctx) => {
            const r = shown[ctx.dataIndex];
            const partial = r.coverage_pct !== null && r.coverage_pct < 80 ? " (some food has no value, so maybe more)" : "";
            return `${amount(r.amount)} of ${amount(r.target_amount)} ${unit(r.unit)}: ${r.pct_of_target ?? 0}%${partial}`;
          },
        },
      },
    },
  };

  return (
    <div className="card">
      <div className="card-head">
        <div>
          <h2>Vitamins and minerals so far</h2>
          <p className="sub">As a share of your daily target. The dashed line is 100%.</p>
        </div>
        <Segmented value={kind} onChange={setKind} options={[["vitamin", "Vitamins"], ["mineral", "Minerals"], ["other", "Other"]]} label="Which nutrients" />
      </div>
      {nothingLogged ? (
        <Empty icon="leaf" title="Nothing to show yet">Log some food and each vitamin and mineral fills up here.</Empty>
      ) : (
        <div style={{ height: `${shown.length * 30 + 40}px` }}>
          <Bar data={data} options={options} plugins={[targetLine]} />
        </div>
      )}
      <div className="legend" style={{ marginTop: "0.75rem" }}>
        <span><i style={{ background: colours.met }} />target met</span>
        <span><i style={{ background: colours.close }} />70% or more</span>
        <span><i style={{ background: colours.low }} />under 70%</span>
        <span><i style={{ background: colours.unknown }} />some food has no value</span>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- energy over the last 14 days

function TrendCard({ days, day, target }) {
  const byDate = Object.fromEntries(days.map((d) => [String(d.date), d.nutrients.energy?.amount ?? null]));
  const dates = Array.from({ length: 14 }, (_, i) => shiftDate(day, i - 13));
  const values = dates.map((d) => byDate[d] ?? null);
  const logged = values.filter((v) => v !== null);
  const average = logged.length ? logged.reduce((a, b) => a + b, 0) / logged.length : null;

  const data = {
    labels: dates.map((d) => new Date(`${d}T12:00:00`).toLocaleDateString(undefined, { day: "numeric", month: "short" })),
    datasets: [{
      data: values,
      // The chosen day in full colour, the days before it see-through
      backgroundColor: dates.map((d) => (d === day ? cssColour("--brand") : withAlpha(cssColour("--brand"), 0.35))),
      hoverBackgroundColor: cssColour("--brand"),
      borderRadius: 6,
      borderSkipped: false,
    }],
  };
  const options = {
    maintainAspectRatio: false,
    scales: {
      x: { grid: { display: false }, border: { display: false }, ticks: { color: cssColour("--ink-3"), maxRotation: 0, autoSkipPadding: 8 } },
      y: { beginAtZero: true, grid: { color: cssColour("--line") }, border: { display: false }, ticks: { color: cssColour("--ink-3") } },
    },
    plugins: {
      targetLine: { axis: "y", value: target, colour: cssColour("--coral") },
      tooltip: {
        ...tooltipLook(),
        callbacks: { label: (ctx) => (ctx.raw === null ? "nothing logged" : `${amount(ctx.raw)} kcal`) },
      },
    },
  };

  return (
    <div className="card">
      <div className="card-head">
        <div>
          <h2>Energy, last 14 days</h2>
          <p className="sub">The dashed line is your target of {amount(target)} kcal.</p>
        </div>
        {average !== null && <span className="chip brand num">avg {amount(average)} kcal</span>}
      </div>
      {logged.length === 0 ? (
        <Empty icon="trend" title="No history yet">Each day you log shows up here as a bar.</Empty>
      ) : (
        <div style={{ height: 220 }}>
          <Bar data={data} options={options} plugins={[targetLine]} />
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------- limits

function LimitsCard({ byKey, names, isToday }) {
  const rows = LIMITS.map((k) => byKey[k]).filter(Boolean);
  return (
    <div className="card">
      <div className="card-head">
        <div>
          <h2>{isToday ? "Limits today" : "Limits on this day"}</h2>
          <p className="sub">{isToday ? "So far today. The report below averages the days before today." : "Things it's best to keep under."}</p>
        </div>
        <Icon name="shield" />
      </div>
      <div className="stack-sm" style={{ gap: "1rem" }}>
        {rows.map((n) => {
          const had = n.amount ?? 0;
          const none = n.upper_limit === 0;
          const pct = none ? (had > 0 ? 100 : 0) : (100 * had) / n.upper_limit;
          const state = pct > 100 || (none && had > 0) ? "over" : pct >= 80 ? "near" : "";
          return (
            <div key={n.nutrient_key} className={`limit-row ${state}`}>
              <strong className="small">{niceName(n.nutrient_key, names)}</strong>
              <span className="small num muted">
                {amount(had)} {none ? `${unit(n.unit)} (none advised)` : `of ${amount(n.upper_limit)} ${unit(n.unit)}`}
                {state === "over" && <span className="chip red" style={{ marginLeft: "0.4rem" }}>over</span>}
              </span>
              <Meter pct={pct} />
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- the 7-day report

function ReportCard({ report, names }) {
  const period = report.windows[0];      // the last 7 days
  const size = period.window_days;
  const rows = Object.fromEntries(period.nutrients.map((n) => [n.nutrient_key, n]));
  const groups = [["vitamin", "Vitamins"], ["mineral", "Minerals"], ["other", "Fibre, fats, sugar and more"]];

  return (
    <div className="card">
      <div className="card-head">
        <div>
          <h2>Your week</h2>
          <p className="sub">
            Daily averages over the {size} days before {niceDate(report.date).toLowerCase()}
            {period.days_logged !== undefined ? ` (${period.days_logged} with food logged)` : ""}.
            {report.date === todayString() ? " Today is added once it's over." : ""}
          </p>
        </div>
      </div>

      <div className="stack-sm" style={{ gap: "0.85rem" }}>
        {report.stale && (
          <Callout kind="amber" icon="alert">
            The nutrient calculator isn't answering, so this is your last saved report
            {report.computed_at && ` (from ${new Date(report.computed_at).toLocaleString()})`}.
          </Callout>
        )}
        {period.excesses.length > 0 && (
          <>
            <div className="group-title" style={{ marginTop: 0 }}>Over the limit</div>
            <div className="gap-cards">
              {period.excesses.map((key) => <ExcessCard key={key} n={rows[key]} name={niceName(key, names)} />)}
            </div>
          </>
        )}
        <div className="group-title" style={period.excesses.length ? undefined : { marginTop: 0 }}>Short on</div>
        {period.top_gaps.length === 0 ? (
          <Callout kind="brand" icon="check">
            {period.days_logged !== undefined && period.days_logged < 3
              ? "Log at least 3 days to see your gaps."
              : "No gaps in this period. Everything we can check is at least 70% of your target."}
          </Callout>
        ) : (
          <div className="gap-cards">
            {period.top_gaps.map((key) => <GapCard key={key} n={rows[key]} name={niceName(key, names)} />)}
          </div>
        )}
      </div>

      <details className="more">
        <summary><Icon name="chevronRight" size={16} /> Every nutrient</summary>
        <div className="table-wrap">
          {groups.map(([category, title]) => {
            const inGroup = period.nutrients.filter((n) => groupOf(n.nutrient_key, names) === category);
            if (inGroup.length === 0) return null;
            return (
              <div key={category}>
                <div className="group-title">{title}</div>
                <table>
                  <thead>
                    <tr><th>Nutrient</th><th>Average a day</th><th>Target</th><th>Status</th></tr>
                  </thead>
                  <tbody>
                    {inGroup.map((n) => (
                      <tr key={n.nutrient_key}>
                        <td><strong>{niceName(n.nutrient_key, names)}</strong></td>
                        <td className="num">{n.avg_intake === null ? <span className="faint">-</span> : `${n.is_minimum ? "at least " : ""}${amount(n.avg_intake)} ${unit(n.unit)}`}</td>
                        <td className="num">{n.target_amount ? `${amount(n.target_amount)} ${unit(n.unit)}` : n.upper_limit !== null ? `under ${amount(n.upper_limit)} ${unit(n.unit)}` : "-"}</td>
                        <td>
                          <span className={`status ${n.status}`}>{n.status}{n.pct_of_target !== null && n.status !== "unknown" ? ` · ${Math.round(n.pct_of_target)}%` : ""}</span>
                          {n.reason && <div className="faint tiny" style={{ marginTop: "0.2rem" }}>{n.reason}</div>}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            );
          })}
        </div>
      </details>
    </div>
  );
}

// Something you've been having too much of, on average
function ExcessCard({ n, name }) {
  const none = n.upper_limit === 0;
  const pct = none ? null : Math.round((100 * n.avg_intake) / n.upper_limit);
  return (
    <div className="gap-card excess">
      <div className="between">
        <strong>{name}</strong>
        <span className="pct num">{none ? "none" : `${pct}%`}</span>
      </div>
      <Meter pct={none ? 100 : pct} />
      <div className="small muted num">
        about {amount(n.avg_intake)} {unit(n.unit)} a day, {none ? "where the advice is none" : `limit ${amount(n.upper_limit)} ${unit(n.unit)}`}
      </div>
      {n.days_over !== undefined && (
        <div>
          <div className="days-dots" title={`Over on ${n.days_over} of ${n.days_with_data} days`}>
            {Array.from({ length: n.days_with_data }, (_, i) => <i key={i} className={i < n.days_over ? "over" : ""} />)}
          </div>
          <div className="faint tiny" style={{ marginTop: "0.3rem" }}>over the limit on {n.days_over} of {n.days_with_data} days</div>
        </div>
      )}
    </div>
  );
}

function GapCard({ n, name }) {
  return (
    <div className="gap-card">
      <div className="between">
        <strong>{name}</strong>
        <span className="pct num">{Math.round(n.pct_of_target)}%</span>
      </div>
      <Meter pct={n.pct_of_target} marker={70} />
      <div className="small muted num">
        about {amount(n.avg_intake)} of {amount(n.target_amount)} {unit(n.unit)} a day
      </div>
      <div>
        <div className="days-dots" title={`Target met on ${n.days_met} of ${n.days_with_data} days`}>
          {Array.from({ length: n.days_with_data }, (_, i) => <i key={i} className={i < n.days_met ? "met" : ""} />)}
        </div>
        <div className="faint tiny" style={{ marginTop: "0.3rem" }}>target met on {n.days_met} of {n.days_with_data} days</div>
      </div>
    </div>
  );
}
