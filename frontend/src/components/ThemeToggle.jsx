import { useEffect, useState } from "react";

const STORAGE_KEY = "fpl-theme";

function systemTheme() {
  return window.matchMedia?.("(prefers-color-scheme: light)").matches ? "light" : "dark";
}

function storedTheme() {
  try {
    return localStorage.getItem(STORAGE_KEY);
  } catch {
    // Private browsing can throw on access; fall back to the system setting.
    return null;
  }
}

export default function ThemeToggle() {
  const [theme, setTheme] = useState(() => storedTheme() || systemTheme());

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    try {
      localStorage.setItem(STORAGE_KEY, theme);
    } catch {
      /* not fatal -- the theme just won't persist */
    }
  }, [theme]);

  const next = theme === "dark" ? "light" : "dark";

  return (
    <button
      type="button"
      className="theme-toggle"
      onClick={() => setTheme(next)}
      title={`Switch to ${next} mode`}
      aria-label={`Switch to ${next} mode`}
    >
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
           strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        {theme === "dark" ? (
          // Moon: currently dark, click for light.
          <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79" />
        ) : (
          // Sun: currently light, click for dark.
          <>
            <circle cx="12" cy="12" r="4" />
            <path d="M12 2v2m0 16v2M4.93 4.93l1.41 1.41m11.32 11.32 1.41 1.41M2 12h2m16 0h2M4.93 19.07l1.41-1.41m11.32-11.32 1.41-1.41" />
          </>
        )}
      </svg>
    </button>
  );
}
