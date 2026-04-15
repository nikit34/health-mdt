import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        bg: {
          DEFAULT: "#0a0a0b",
          elevated: "#121214",
          card: "#17181b",
        },
        fg: {
          DEFAULT: "#e9ebef",
          muted: "#8a8f9a",
          faint: "#5a5f6a",
        },
        accent: {
          DEFAULT: "#7cc4ff",
          soft: "#1e3a55",
        },
        danger: "#ff7a7a",
        warn: "#ffc46b",
        ok: "#7ee09f",
        border: "#24262b",
      },
      fontFamily: {
        sans: ["-apple-system", "BlinkMacSystemFont", "Inter", "system-ui", "sans-serif"],
        mono: ["ui-monospace", "SF Mono", "Menlo", "monospace"],
      },
      borderRadius: {
        lg: "0.625rem",
        xl: "0.875rem",
      },
    },
  },
  plugins: [],
};
export default config;
