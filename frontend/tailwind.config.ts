import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "class",
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        background: "#faf9f7",
        surface: "#faf9f7",
        "surface-container": "#efeeec",
        "surface-container-low": "#f4f3f1",
        "surface-container-lowest": "#ffffff",
        "surface-container-high": "#e9e8e6",
        "surface-container-highest": "#e3e2e0",
        "surface-variant": "#e3e2e0",
        "on-surface": "#1a1c1b",
        "on-surface-variant": "#444841",
        "on-background": "#1a1c1b",
        primary: "#1d2d18",
        "primary-container": "#32432c",
        "on-primary": "#ffffff",
        "on-primary-container": "#9cb092",
        secondary: "#596154",
        "secondary-container": "#dee5d5",
        "on-secondary-container": "#5f675a",
        tertiary: "#3b212c",
        outline: "#747870",
        "outline-variant": "#c4c8be",
        hint: "#8C8375",
        accent: "#5D4037",
        error: "#ba1a1a",
      },
      borderRadius: {
        DEFAULT: "0.125rem",
        lg: "0.25rem",
        xl: "0.5rem",
        "2xl": "0.75rem",
        full: "9999px",
      },
      fontFamily: {
        headline: ["'Noto Serif'", "serif"],
        body: ["Inter", "sans-serif"],
        ui: ["Inter", "sans-serif"],
        display: ["'Noto Serif'", "serif"],
      },
      keyframes: {
        "upload-progress": {
          "0%": { transform: "translateX(-100%) scaleX(0.3)" },
          "50%": { transform: "translateX(0%) scaleX(0.7)" },
          "100%": { transform: "translateX(100%) scaleX(0.3)" },
        },
      },
      animation: {
        "upload-progress": "upload-progress 1.4s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};

export default config;
