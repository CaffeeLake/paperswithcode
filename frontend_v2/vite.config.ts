import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react-swc";
import path from "path";

// PLAN.md §1, §13.1: prod runs on :8080; staging runs on :8081.
// For DNS-backed staging, set VITE_HMR_HOST / VITE_HMR_PROTOCOL / VITE_HMR_CLIENT_PORT.
// Without those env vars, Vite uses the browser's current origin, which keeps raw-IP
// previews like http://167.235.148.241:8081 from reconnecting to the wrong HMR host.
export default defineConfig(({ mode }) => {
  const isStaging = mode === "staging";
  const env = loadEnv(mode, process.cwd(), "");
  const hmrHost = env.VITE_HMR_HOST;
  const hmrProtocol = env.VITE_HMR_PROTOCOL as "ws" | "wss" | undefined;
  const hmrClientPort = env.VITE_HMR_CLIENT_PORT
    ? Number(env.VITE_HMR_CLIENT_PORT)
    : undefined;
  const hmr = hmrHost
    ? {
        host: hmrHost,
        ...(hmrProtocol ? { protocol: hmrProtocol } : {}),
        ...(hmrClientPort ? { clientPort: hmrClientPort } : {}),
      }
    : undefined;

  return {
    server: {
      host: "::",
      port: isStaging ? 8081 : 8080,
      strictPort: true,
      allowedHosts: isStaging
        ? ["staging.paperswithcode.co", "167.235.148.241"]
        : ["paperswithcode.co", "www.paperswithcode.co"],
      ...(hmr ? { hmr } : {}),
      proxy: {
        "/api": {
          target: "http://127.0.0.1:8000",
          changeOrigin: true,
          secure: false,
        },
      },
    },
    plugins: [react()],
    resolve: {
      alias: {
        "@": path.resolve(__dirname, "./src"),
      },
    },
  };
});
