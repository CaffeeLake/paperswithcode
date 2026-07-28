import React from "react";
import { createRoot } from "react-dom/client";
import { ThemeProvider } from "next-themes";

import AppErrorBoundary from "./components/AppErrorBoundary";
import "./index.css";
import { installChunkReloadRecovery } from "./lib/chunkReload";
import "./styles.css";
import App from "./App";

installChunkReloadRecovery();

const root = createRoot(document.getElementById("root")!);
root.render(
  <React.StrictMode>
    <ThemeProvider
      attribute="class"
      defaultTheme="system"
      enableSystem
      disableTransitionOnChange
      storageKey="pwc-theme"
    >
      <AppErrorBoundary>
        <App />
      </AppErrorBoundary>
    </ThemeProvider>
  </React.StrictMode>,
);
