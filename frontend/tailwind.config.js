// file: frontend/tailwind.config.js
/** @type {import('tailwindcss').Config} */
export default {
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
      },
      fontFamily: {
        sans: ['Geist', 'Inter', '-apple-system', 'sans-serif'],
        mono: ['Geist Mono', 'monospace'],
      },
    },
  },
  plugins: [],
};

