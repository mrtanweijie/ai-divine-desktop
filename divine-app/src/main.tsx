import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { RouterProvider } from "react-router/dom";
import { router } from "@/app/router";
import "@/styles/index.less";

if (import.meta.env.VITE_DISABLE_CONTEXT_MENU === "true") {
  window.addEventListener("contextmenu", (event) => {
    const target = event.target;
    if (
      target instanceof HTMLElement &&
      (target.tagName === "INPUT" ||
        target.tagName === "TEXTAREA" ||
        target.isContentEditable)
    ) {
      return;
    }
    event.preventDefault();
  });
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <RouterProvider router={router} />
  </StrictMode>
);
