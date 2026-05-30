/** @type {import('tailwindcss').Config} */
export default {
  darkMode: "class",
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        'brand-base': '#0a0a0b',
        'brand-panel': '#111113',
        'border-subtle': '#1f1f23',
        'border-strong': '#2a2a2f',
        'text-primary': '#ededed',
        'text-secondary': '#8c8c94',
        'text-dim': '#4a4a54',
        'accent-amber': '#f5a623',
        'accent-green': '#00c96b',
        'accent-red': '#ff4458',
        'accent-cyan': '#00d4ff',
        'accent-indigo': '#6366f1',
        
        long: "hsl(var(--primary))",
        short: "hsl(var(--destructive))",
        warn: "hsl(var(--warning))",
        info: "hsl(var(--info))",
        accent: "hsl(var(--accent))",
        bg1: "#0a0a0a",
        bg2: "#111111",
        bg3: "#1a1a1a",
        bd1: "#1f1f1f",
        bd2: "#2a2a2a",
        bd3: "#3a3a3a",
        fg1: "#ededed",
        fg2: "#a1a1a1",
        fg3: "#6b6b6b",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        card: {
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },
        popover: {
          DEFAULT: "hsl(var(--popover))",
          foreground: "hsl(var(--popover-foreground))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
      },
      fontFamily: {
        sans: ["Geist", "var(--font-sans)", "ui-sans-serif", "system-ui", "sans-serif", "Inter"],
        mono: ["Geist Mono", "var(--font-mono)", "ui-monospace", "monospace"],
      },
      borderRadius: {
        lg: "6px",
        md: "6px",
        sm: "4px",
      },
      transitionTimingFunction: {
        deri: "cubic-bezier(.2, .8, .2, 1)",
      },
      keyframes: {
        "status-pulse": {
          "0%, 100%": { opacity: "1", transform: "scale(1)" },
          "50%": { opacity: "0.45", transform: "scale(0.85)" },
        },
        "flash-up": {
          "0%": { background: "rgba(0,255,136,0.18)" },
          "100%": { background: "transparent" },
        },
        "flash-down": {
          "0%": { background: "rgba(255,59,48,0.18)" },
          "100%": { background: "transparent" },
        },
      },
      animation: {
        "status-pulse": "status-pulse 1.6s ease-in-out infinite",
        "flash-up": "flash-up 200ms cubic-bezier(.2,.8,.2,1)",
        "flash-down": "flash-down 200ms cubic-bezier(.2,.8,.2,1)",
      },
    },
  },
  plugins: [require("tailwindcss-animate")],
};
