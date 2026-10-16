/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        // --- Core Brand Tokens ---
        primary: {
          DEFAULT: "#4F46E5", // Indigo-600
          hover: "#4338CA",   // Indigo-700
          tint: "#E0E7FF",    // Indigo-100
          50: "#EEF2FF",
          100: "#E0E7FF",
          200: "#C7D2FE",
          300: "#A5B4FC",
          400: "#818CF8",
          500: "#6366F1",
          600: "#4F46E5",
          700: "#4338CA",
          800: "#3730A3",
          900: "#312E81",
        },
        page: {
          DEFAULT: "#FAFAFA",
        },
        surface: {
          DEFAULT: "#FFFFFF",
          subtle: "#F8FAFC",
        },
        border: {
          DEFAULT: "#E2E8F0",
          subtle: "#F1F5F9",
        },
        text: {
          primary: "#0F172A",
          secondary: "#475569",
          muted: "#94A3B8",
        },
        // --- Semantic Status Tokens ---
        genuine: {
          DEFAULT: "#059669",
          tint: "#ECFDF5",
          border: "#A7F3D0",
          text: "#065F46",
        },
        suspicious: {
          DEFAULT: "#D97706",
          tint: "#FFFBEB",
          border: "#FDE68A",
          text: "#92400E",
        },
        fake: {
          DEFAULT: "#DC2626",
          tint: "#FEF2F2",
          border: "#FECACA",
          text: "#991B1B",
        },
        // --- Compatibility aliases ---
        brand: {
          DEFAULT: "#4F46E5",
          indigo: "#4F46E5",
          50: "#EEF2FF",
          100: "#E0E7FF",
          600: "#4F46E5",
          700: "#4338CA",
        },
      },
      fontFamily: {
        sans: ["var(--font-inter)", "Inter", "system-ui", "-apple-system", "BlinkMacSystemFont", "Segoe UI", "Roboto", "sans-serif"],
        mono: ["var(--font-jetbrains-mono)", "JetBrains Mono", "monospace"],
      },
      borderRadius: {
        card: "12px",
        btn: "8px",
        input: "8px",
        badge: "6px",
      },
      boxShadow: {
        card: "0 1px 3px 0 rgba(0, 0, 0, 0.05), 0 1px 2px -1px rgba(0, 0, 0, 0.05)",
        "card-hover": "0 4px 6px -1px rgba(0, 0, 0, 0.08), 0 2px 4px -2px rgba(0, 0, 0, 0.05)",
        dropdown: "0 10px 15px -3px rgba(0, 0, 0, 0.08), 0 4px 6px -4px rgba(0, 0, 0, 0.04)",
      },
    },
  },
  plugins: [],
};
