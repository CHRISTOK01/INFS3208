import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
// The two fonts are bundled with the app (no calls to Google Fonts): Inter for text, Fraunces for headings
import "@fontsource-variable/inter";
import "@fontsource-variable/fraunces";
import App from "./App.jsx";
import "./styles.css";

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
