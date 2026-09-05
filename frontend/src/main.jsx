import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App from "./App.jsx";
import "./index.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 60_000,
      // 401 (signed out) and 428 (no FPL account linked) are states, not
      // failures -- retrying them just delays the UI that explains them.
      retry: (failureCount, error) =>
        error?.status === 401 || error?.status === 428 ? false : failureCount < 1,
    },
  },
});

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </React.StrictMode>
);
