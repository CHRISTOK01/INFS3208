// Small building blocks used across the pages
import { useEffect, useState } from "react";
import { onToast } from "../toast.js";
import { niceDate, shiftDate, todayString } from "../format.js";
import Icon from "./Icon.jsx";

// A progress bar. `pct` is how full it is (0-100); `marker` draws a line at that percentage.
export function Meter({ pct, color, thick, marker }) {
  const width = Math.max(0, Math.min(100, pct || 0));
  return (
    <div className={thick ? "meter thick" : "meter"}>
      <i style={{ width: `${width}%`, background: color }} />
      {marker !== undefined && <span className="marker" style={{ left: `${marker}%` }} />}
    </div>
  );
}

// A ring that fills up, with anything you like in the middle
export function Ring({ pct, size = 176, stroke = 14, color = "var(--brand)", children }) {
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const filled = Math.max(0, Math.min(100, pct || 0));
  return (
    <div className="ring-wrap" style={{ width: size, height: size }}>
      <svg width={size} height={size} style={{ transform: "rotate(-90deg)" }}>
        <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke="var(--surface-2)" strokeWidth={stroke} />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={circumference * (1 - filled / 100)}
        />
      </svg>
      <div className="ring-center"><div>{children}</div></div>
    </div>
  );
}

// A row of buttons where you pick one. `options` is [[value, label, icon?], ...].
export function Segmented({ value, onChange, options, full, label }) {
  return (
    <div className={full ? "segmented full" : "segmented"} role="radiogroup" aria-label={label}>
      {options.map(([v, text, icon]) => (
        <button key={v} type="button" role="radio" aria-checked={value === v} className={value === v ? "on" : ""} onClick={() => onChange(v)}>
          {icon && <Icon name={icon} size={15} />}
          {text}
        </button>
      ))}
    </div>
  );
}

// A number with - and + buttons either side
export function Stepper({ value, onChange, step = 1, min = 0, max = 99 }) {
  const set = (v) => onChange(Math.min(max, Math.max(min, Math.round(v * 100) / 100)));
  return (
    <div className="stepper">
      <button type="button" aria-label="Less" onClick={() => set(Number(value) - step)}>−</button>
      <input type="number" value={value} min={min} max={max} step={step} onChange={(e) => onChange(e.target.value)} aria-label="Amount" />
      <button type="button" aria-label="More" onClick={() => set(Number(value) + step)}>+</button>
    </div>
  );
}

// The day picker in the top bar: back a day, the date (click to pick any), forward a day
export function DateNav({ day, onChange }) {
  const today = todayString();
  return (
    <div className="date-nav">
      <button className="icon-btn" onClick={() => onChange(shiftDate(day, -1))} aria-label="Day before">
        <Icon name="chevronLeft" />
      </button>
      <label title="Pick a day">
        <Icon name="calendar" size={16} />
        {niceDate(day)}
        <input type="date" value={day} max={today} onChange={(e) => e.target.value && onChange(e.target.value)} />
      </label>
      <button className="icon-btn" onClick={() => onChange(shiftDate(day, 1))} disabled={day >= today} aria-label="Day after">
        <Icon name="chevronRight" />
      </button>
      {day !== today && <button className="today-btn" onClick={() => onChange(today)}>Today</button>}
    </div>
  );
}

// Grey shimmering blocks shown while something loads
export function Skeleton({ height = 16, width = "100%", style }) {
  return <div className="skeleton" style={{ height, width, ...style }} />;
}

export function SkeletonCard({ lines = 4 }) {
  return (
    <div className="card stack-sm">
      <Skeleton height={20} width="40%" />
      {Array.from({ length: lines }, (_, i) => <Skeleton key={i} width={`${90 - i * 12}%`} />)}
    </div>
  );
}

// A friendly message when there's nothing to show yet
export function Empty({ icon = "leaf", title, children, action }) {
  return (
    <div className="empty">
      <div className="bubble"><Icon name={icon} size={26} /></div>
      <strong>{title}</strong>
      {children && <p>{children}</p>}
      {action}
    </div>
  );
}

export function Callout({ kind = "", icon = "info", children }) {
  return (
    <div className={`callout ${kind}`}>
      <Icon name={icon} />
      <div>{children}</div>
    </div>
  );
}

// The pop-up messages (see toast.js). Each one disappears after a few seconds.
export function Toasts() {
  const [toasts, setToasts] = useState([]);
  useEffect(
    () =>
      onToast((toast) => {
        setToasts((old) => [...old, toast]);
        setTimeout(() => setToasts((old) => old.filter((t) => t.id !== toast.id)), 4000);
      }),
    [],
  );
  const icons = { ok: "check", warn: "alert", error: "alert" };
  return (
    <div className="toasts" role="status" aria-live="polite">
      {toasts.map((t) => (
        <div key={t.id} className={`toast ${t.kind}`}>
          <Icon name={icons[t.kind]} />
          <span>{t.message}</span>
        </div>
      ))}
    </div>
  );
}
