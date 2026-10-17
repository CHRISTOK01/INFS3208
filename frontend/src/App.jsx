// The whole app: login first, then four tabs. The chosen day is shared by every tab, so you can
// look back at (or log food for) an earlier day.
import { useEffect, useRef, useState } from "react";
import { api } from "./api.js";
import { logOut, startAuth } from "./auth.js";
import Footer from "./components/Footer.jsx";
import Icon, { Logo } from "./components/Icon.jsx";
import { DateNav, SkeletonCard, Toasts } from "./components/ui.jsx";
import { todayString } from "./format.js";
import Dashboard from "./pages/Dashboard.jsx";
import LogMeal from "./pages/LogMeal.jsx";
import Login from "./pages/Login.jsx";
import Profile from "./pages/Profile.jsx";
import Suggestions from "./pages/Suggestions.jsx";

const TABS = [
  ["dashboard", "Dashboard", "dashboard"],
  ["log", "Log food", "plusCircle"],
  ["suggestions", "Suggestions", "sparkle"],
  ["profile", "My details", "user"],
];

export default function App() {
  const [user, setUser] = useState(undefined);         // undefined while we check, then a user or null
  const [setupError, setSetupError] = useState(null);
  const [hasProfile, setHasProfile] = useState(null);  // null until we know
  const [tab, setTab] = useState("dashboard");
  const [day, setDay] = useState(todayString());
  const [suggestMode, setSuggestMode] = useState("today");   // which mode Suggestions opens on

  useEffect(() => {
    startAuth(setUser).catch((error) => setSetupError(error.message));
  }, []);

  // New users fill in their details first, because every target depends on them
  useEffect(() => {
    if (!user) return;
    setHasProfile(null);
    api(`/api/gaps/profile/${user.uid}`)
      .then(() => setHasProfile(true))
      .catch((error) => {
        if (error.status === 404) {
          setHasProfile(false);
          setTab("profile");
        } else {
          setHasProfile(true);   // some other problem: let the pages show their own errors
        }
      });
  }, [user]);

  // Go to a tab. For Suggestions you can also say which mode to open on ("today" or "week").
  function goTo(next, mode) {
    if (mode) setSuggestMode(mode);
    setTab(next);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  let page;
  if (setupError) {
    page = <div className="card"><p className="muted">{setupError}</p></div>;
  } else if (user === undefined || (user && hasProfile === null)) {
    page = <div className="grid grid-hero"><SkeletonCard lines={6} /><SkeletonCard lines={4} /></div>;
  } else if (!user) {
    page = <Login />;
  } else if (!hasProfile || tab === "profile") {
    page = (
      <Profile
        user={user}
        day={day}
        firstTime={!hasProfile}
        onSaved={() => {
          if (!hasProfile) goTo("dashboard");
          setHasProfile(true);
        }}
      />
    );
  } else if (tab === "log") {
    page = <LogMeal user={user} day={day} />;
  } else if (tab === "suggestions") {
    page = <Suggestions user={user} day={day} startMode={suggestMode} />;
  } else {
    page = <Dashboard user={user} day={day} onGoTo={goTo} />;
  }

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand"><Logo /><span>MacroScope</span></div>
        {user && hasProfile && (
          <nav className="nav" aria-label="Main">
            {TABS.map(([key, label, icon]) => (
              <button key={key} className={tab === key ? "nav-item active" : "nav-item"} onClick={() => goTo(key)} aria-current={tab === key ? "page" : undefined}>
                <Icon name={icon} />
                {label}
              </button>
            ))}
          </nav>
        )}
        {user && (
          <div className="topbar-right">
            {hasProfile && <DateNav day={day} onChange={setDay} />}
            <UserMenu user={user} onDetails={() => goTo("profile")} />
          </div>
        )}
      </header>
      <main key={tab} className="fade-in">{page}</main>
      <Footer tab={tab} />
      <Toasts />
    </div>
  );
}

// The round button with your initial, which opens a small menu
function UserMenu({ user, onDetails }) {
  const [open, setOpen] = useState(false);
  const box = useRef(null);

  // Close the menu when you click anywhere else
  useEffect(() => {
    if (!open) return;
    const close = (e) => box.current && !box.current.contains(e.target) && setOpen(false);
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);

  const initial = (user.displayName || user.email || "?")[0].toUpperCase();
  return (
    <div className="user-menu" ref={box}>
      <button className="avatar" onClick={() => setOpen(!open)} aria-label="Account menu" aria-expanded={open}>{initial}</button>
      {open && (
        <div className="menu">
          <div className="who"><span className="faint tiny">Logged in as</span><br />{user.email}</div>
          <button onClick={() => { setOpen(false); onDetails(); }}><Icon name="user" /> My details</button>
          <button onClick={() => logOut()}><Icon name="logout" /> Log out</button>
        </div>
      )}
    </div>
  );
}
