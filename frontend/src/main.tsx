import React from "react";
import { createRoot } from "react-dom/client";
import { ThemeProvider } from "next-themes";

import "./index.css";
import "./styles.css";
import App from "./App";

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
      <App />
    </ThemeProvider>
  </React.StrictMode>,
);
