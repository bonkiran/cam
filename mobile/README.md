# CrickAnalysis Mobile

React Native + Expo mobile client for the existing CrickAnalysis FastAPI backend.

## Current mobile MVP

- Dashboard connected to `/api/dashboard`
- Upload from iOS/Android photo library
- Quick Review / Specific Shot / Full Scan mode selection
- Real upload progress
- Analyses list
- Players list + CricClubs public lookup bridge
- Crick AI screen using `/api/assistant`
- Native video review with 0.1x / 0.25x / 0.5x / 1x playback
- Exact ±1 / ±10 frame stepping using source FPS
- Evidence-sequence extraction
- Reference-tool library
- EAS development / preview / production build profiles

## Requirements

Expo SDK 57 requires Node.js 22.13.x or newer.

## Run locally

```bash
cd mobile
npm install
cp .env.example .env
npx expo start
```

The default API is already `https://crickanalysis.onrender.com`. Override it with:

```bash
EXPO_PUBLIC_API_BASE_URL=https://your-api.example.com
```

## Create installable development builds

Install/log into EAS CLI, then:

```bash
npm install -g eas-cli
eas login
eas build:configure
eas build --profile development --platform android
eas build --profile development --platform ios
```

Or build both:

```bash
eas build --profile development --platform all
```

The first EAS configuration may add an Expo project ID to `app.json`; commit that generated configuration afterward.

## Important MVP limitation

The current Render Free backend uses ephemeral local storage. A production mobile release should move videos/evidence to object storage and persistent metadata to Postgres before public distribution.
