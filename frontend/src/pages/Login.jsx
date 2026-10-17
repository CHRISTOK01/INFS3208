// The front door: what MacroScope does on the left, and logging in or signing up on the right
import { useState } from "react";
import { logIn, logInWithGoogle, loginError, signUp } from "../auth.js";
import Icon, { GoogleG } from "../components/Icon.jsx";
import { Callout, Segmented } from "../components/ui.jsx";

const FEATURES = [
  ["target", "Targets made for you", "From the Australian NHMRC values, for your age, size, activity, diet and pregnancy."],
  ["search", "Spot what's missing", "See what you still need today, and what you've been short on this week."],
  ["sparkle", "Food ideas that fit", "Everyday Australian foods that fill your gaps, within the energy you have left."],
];

export default function Login() {
  const [mode, setMode] = useState("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const newAccount = mode === "signup";

  async function attempt(action) {
    setError(null);
    setBusy(true);
    try {
      await action();   // App notices the login by itself and moves on
    } catch (e) {
      setError(loginError(e));
    } finally {
      setBusy(false);
    }
  }

  function submit(event) {
    event.preventDefault();
    attempt(() => (newAccount ? signUp(email, password) : logIn(email, password)));
  }

  return (
    <div className="auth">
      <section className="auth-hero">
        <svg className="art" width="420" height="420" viewBox="0 0 420 420" aria-hidden="true">
          {[200, 160, 120, 80].map((r) => <circle key={r} cx="210" cy="210" r={r} fill="none" stroke="#fff" strokeWidth="14" />)}
        </svg>
        <div>
          <h1>Find the nutrients your diet is missing.</h1>
          <p className="lead">Log what you eat. MacroScope checks it against more than 25 nutrients and tells you what would help.</p>
        </div>
        <ul>
          {FEATURES.map(([icon, title, text]) => (
            <li key={title}>
              <span className="ico"><Icon name={icon} /></span>
              <div><strong>{title}</strong><span>{text}</span></div>
            </li>
          ))}
        </ul>
      </section>

      <section className="auth-form">
        <div>
          <h2 className="display" style={{ fontSize: "1.6rem" }}>{newAccount ? "Make your account" : "Welcome back"}</h2>
          <p className="muted small" style={{ marginTop: "0.3rem" }}>
            {newAccount ? "It takes a minute. Then we'll ask a few questions to set your targets." : "Log in to see today's numbers."}
          </p>
        </div>
        <Segmented full value={mode} onChange={(m) => { setMode(m); setError(null); }} options={[["login", "Log in"], ["signup", "Sign up"]]} label="Log in or sign up" />
        <form onSubmit={submit} className="stack-sm">
          <label className="field">
            Email
            <input className="input" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoComplete="email" placeholder="you@example.com" />
          </label>
          <label className="field">
            Password
            <input
              className="input"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              minLength={6}
              autoComplete={newAccount ? "new-password" : "current-password"}
              placeholder={newAccount ? "At least 6 characters" : ""}
            />
          </label>
          <button type="submit" className="btn block" disabled={busy} style={{ marginTop: "0.4rem" }}>
            {busy ? "One moment..." : newAccount ? "Make account" : "Log in"}
          </button>
        </form>
        <div className="divider">or</div>
        <button className="btn secondary block" disabled={busy} onClick={() => attempt(logInWithGoogle)}>
          <GoogleG /> Continue with Google
        </button>
        {error && <Callout kind="red" icon="alert">{error}</Callout>}
        <p className="faint tiny">Logins are handled by Google. MacroScope never sees your password.</p>
      </section>
    </div>
  );
}
