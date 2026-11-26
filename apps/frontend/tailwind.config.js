/**
 * 明暗で切り替わる色は CSS 変数 (src/index.css の :root / .dark) で定義し、
 * ここではその変数を参照するデザイントークンとして公開する。
 * - surface: 背景 (カード・ページ・ホバー)
 * - ink:     文字 (数字が大きいほど強い)
 * - line:    枠線・区切り線
 */
const token = (name) => `rgb(var(--${name}) / <alpha-value>)`;

/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        brand: {
          50: "#eef4ff",
          100: "#d9e5ff",
          // ダークモードの文字色用
          300: "#91a7ff",
          400: "#748ffc",
          500: "#3b5bdb",
          600: "#2f48b3",
          700: "#253a8f",
        },
        surface: {
          DEFAULT: token("surface"),
          subtle: token("surface-subtle"),
          muted: token("surface-muted"),
          strong: token("surface-strong"),
          hover: token("surface-hover"),
        },
        ink: {
          900: token("ink-900"),
          800: token("ink-800"),
          700: token("ink-700"),
          600: token("ink-600"),
          500: token("ink-500"),
          400: token("ink-400"),
          300: token("ink-300"),
        },
        line: {
          DEFAULT: token("line"),
          strong: token("line-strong"),
        },
      },
    },
  },
  plugins: [],
};
