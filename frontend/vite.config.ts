import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In dev, the API runs separately (uvicorn on :8000); the proxy keeps the frontend same-origin.
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: { "/api": "http://localhost:8000" } },
});
