// Vite builds the React app into plain files (in dist/) that Nginx serves.
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  // Google's login library makes the one JavaScript file about 500 kB (160 kB once compressed),
  // which is fine for this app, so don't warn about it
  build: { chunkSizeWarningLimit: 600 },
  server: {
    // Only used by `npm run dev` (the hot-reloading dev server). It passes /api calls on to the
    // gateway, so the dev server behaves like the real site.
    proxy: { "/api": "http://localhost:8080" },
  },
});
