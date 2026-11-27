import { create } from "zustand";

/** system: OS の設定に追従する */
export type ThemePreference = "system" | "light" | "dark";
export type ResolvedTheme = "light" | "dark";

// index.html の初期化スクリプトと同じキー
const STORAGE_KEY = "theme";
const media = window.matchMedia("(prefers-color-scheme: dark)");

function readPreference(): ThemePreference {
  try {
    const v = localStorage.getItem(STORAGE_KEY);
    return v === "light" || v === "dark" ? v : "system";
  } catch {
    return "system";
  }
}

function resolve(pref: ThemePreference): ResolvedTheme {
  if (pref === "system") return media.matches ? "dark" : "light";
  return pref;
}

function apply(theme: ResolvedTheme) {
  document.documentElement.classList.toggle("dark", theme === "dark");
}

type ThemeState = {
  preference: ThemePreference;
  resolved: ResolvedTheme;
  setPreference: (pref: ThemePreference) => void;
};

const initial = readPreference();

export const useThemeStore = create<ThemeState>((set) => ({
  preference: initial,
  resolved: resolve(initial),
  setPreference: (preference) => {
    try {
      if (preference === "system") localStorage.removeItem(STORAGE_KEY);
      else localStorage.setItem(STORAGE_KEY, preference);
    } catch {
      // プライベートモード等で保存できなくても、この画面では切り替える
    }
    const resolved = resolve(preference);
    apply(resolved);
    set({ preference, resolved });
  },
}));

// OS の設定が変わったら、system を選んでいるときだけ追従する
media.addEventListener("change", () => {
  const { preference } = useThemeStore.getState();
  if (preference !== "system") return;
  const resolved = resolve(preference);
  apply(resolved);
  useThemeStore.setState({ resolved });
});

apply(resolve(initial));
