import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        taurus: {
          bg: "#08111f",
          shell: "#0e1728",
          surface: "#121d31",
          surfaceRaised: "#17243a",
          outline: "#263754",
          muted: "#8fa3bf",
          text: "#e8f0fb",
          primary: "#38bdf8",
          secondary: "#818cf8",
          success: "#34d399",
          caution: "#fbbf24",
          failure: "#fb7185",
        },
      },
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "SFMono-Regular", "monospace"],
      },
      boxShadow: {
        panel: "0 16px 48px rgba(0, 0, 0, 0.25)",
      },
    },
  },
  plugins: [],
} satisfies Config;
