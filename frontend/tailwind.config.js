/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "SFMono-Regular", "monospace"],
      },
      colors: {
        ink: { 950: "#0b1120", 900: "#0f172a", 800: "#1e293b", 700: "#334155" },
      },
      keyframes: {
        pulseRing: { "0%": { boxShadow: "0 0 0 0 rgba(99,102,241,.55)" }, "100%": { boxShadow: "0 0 0 10px rgba(99,102,241,0)" } },
        slideIn: { "0%": { opacity: 0, transform: "translateY(6px)" }, "100%": { opacity: 1, transform: "translateY(0)" } },
      },
      animation: { pulseRing: "pulseRing 1.2s ease-out infinite", slideIn: "slideIn .25s ease-out" },
    },
  },
  plugins: [],
};
