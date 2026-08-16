import { useEffect, useMemo, useState, type ReactNode } from "react";
import { PreferencesContext, type PreferencesValue, type Theme } from "./preferences-context";

function initialTheme(): Theme {
  const saved = window.localStorage.getItem("farmops-theme");
  if (saved === "light" || saved === "dark") return saved;
  // This is an outdoor operator console: start in the high-contrast light
  // theme unless the operator has explicitly selected a different preference.
  return "light";
}

export function PreferencesProvider({ children }: { children: ReactNode }) {
  const [operatorToken, setToken] = useState(() => window.sessionStorage.getItem("farmops-operator-token") ?? "");
  const [theme, setTheme] = useState<Theme>(initialTheme);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    document.documentElement.style.colorScheme = theme;
    window.localStorage.setItem("farmops-theme", theme);
  }, [theme]);

  const setOperatorToken = (token: string) => {
    const trimmed = token.trim();
    setToken(trimmed);
    if (trimmed) window.sessionStorage.setItem("farmops-operator-token", trimmed);
    else window.sessionStorage.removeItem("farmops-operator-token");
  };

  const value = useMemo<PreferencesValue>(() => ({
    operatorToken,
    setOperatorToken,
    theme,
    toggleTheme: () => setTheme((current) => (current === "light" ? "dark" : "light")),
  }), [operatorToken, theme]);

  return <PreferencesContext.Provider value={value}>{children}</PreferencesContext.Provider>;
}
