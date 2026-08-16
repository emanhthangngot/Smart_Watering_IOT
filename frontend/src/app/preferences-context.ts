import { createContext } from "react";

export type Theme = "light" | "dark";

export interface PreferencesValue {
  operatorToken: string;
  setOperatorToken: (token: string) => void;
  theme: Theme;
  toggleTheme: () => void;
}

export const PreferencesContext = createContext<PreferencesValue | undefined>(undefined);
