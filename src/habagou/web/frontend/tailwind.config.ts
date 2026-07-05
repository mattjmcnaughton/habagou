import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#0e0f11",
        panel: "#1b1f22",
        panel2: "#22272b",
        porcelain: "#e8ecee",
        mist: "#8a949a",
        jade: "#5fb89a",
        "jade-bright": "#6fc7a8",
        clay: "#c4633f",
        brass: "#b5852e",
        indigo: "#5b5fa8",
      },
      fontFamily: {
        sans: ["Hanken Grotesk", "ui-sans-serif", "system-ui", "sans-serif"],
        hanzi: ["Noto Sans SC", "PingFang SC", "sans-serif"],
      },
      boxShadow: {
        panel: "0 18px 60px rgb(0 0 0 / 0.28)",
      },
    },
  },
  plugins: [],
} satisfies Config;
