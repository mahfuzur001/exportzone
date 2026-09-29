/**
 * Export Zone's Tailwind design tokens. The Phase 1 template uses Tailwind's
 * browser build during development; this file is ready for a production build
 * pipeline without changing the templates.
 */
module.exports = {
  content: [
    './templates/**/*.html',
    './apps/**/templates/**/*.html',
    './static/js/**/*.js',
  ],
  theme: {
    extend: {
      colors: {
        ink: '#090b0e',
        charcoal: '#11151a',
        gold: '#d8a83f',
        cream: '#f8f3e8',
      },
    },
  },
  plugins: [],
};
