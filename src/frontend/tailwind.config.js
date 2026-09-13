/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        ink: {
          950: '#0b0f17',
          900: '#0f1522',
          850: '#131b2b',
          800: '#182234',
          700: '#223049',
          600: '#2e405f',
        },
      },
    },
  },
  plugins: [],
};
