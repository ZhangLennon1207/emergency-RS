# Emergency RS Agent Platform

A production-style emergency management dashboard for remote sensing disaster assessment.  
The UI is designed for demos with emergency management departments and showcases how an uncertainty-aware RS agent system can be exposed as a commercial command platform.

## Features

- Command-center style dashboard for disaster monitoring
- Region-level assessment table with confidence-aware outputs
- Evidence-chain workflow for image, mask, and text alignment
- AI-agent report center for structured disaster briefing
- Static deployment-ready build for GitHub Pages, Vercel, or Netlify

## Tech Stack

- React 19
- Vite 8
- Recharts
- Lucide React

## Local Development

```bash
npm install
npm run dev
```

## Production Build

```bash
npm run build
npm run preview
```

## GitHub Pages

This repo includes `.github/workflows/deploy.yml` for GitHub Pages deployment.

1. Push the repository to GitHub on the `main` branch.
2. In GitHub repository settings, enable Pages with `GitHub Actions` as the source.
3. Every push to `main` will build and publish the site automatically.

## Manual `gh-pages` Deployment

```bash
npm run deploy
```

## Suggested Repository Name

`emergency-rs-agent-platform`
