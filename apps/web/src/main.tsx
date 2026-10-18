import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "@astryxdesign/core/reset.css";
import "@astryxdesign/core/astryx.css";
import { Theme } from "@astryxdesign/core";
import { ToastViewport } from "@astryxdesign/core/Toast";
import { appTheme } from "./theme";
import App from "./App";
import "./styles.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <Theme theme={appTheme} mode="dark">
      <ToastViewport position="bottomEnd" maxVisible={3}>
        <App />
      </ToastViewport>
    </Theme>
  </StrictMode>,
);
