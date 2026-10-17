import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev proxy keeps the browser on one origin; the API key (later: Gemini) never reaches the frontend.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
        ws: true,
        // inteGREAT uses no cookies. Browsers send every localhost cookie from other dev projects, which can
        // overflow the WebSocket server's header limit (HTTP 431) — so strip them.
        configure: (proxy) => {
          proxy.on("proxyReq", (req) => req.removeHeader("cookie"));
          proxy.on("proxyReqWs", (req) => req.removeHeader("cookie"));
        },
      },
    },
  },
});
