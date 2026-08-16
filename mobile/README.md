# CrickAnalysis Mobile

React Native + Expo mobile client for the existing CrickAnalysis FastAPI backend.

## Current mobile MVP

- Dashboard connected to `/api/dashboard`
- Upload from iPhone photo library
- Quick Review / Specific Shot / Full Scan mode selection
- Real upload progress
- Analyses list
- Players list + CricClubs public lookup bridge
- Crick AI screen using `/api/assistant`
- Native video review with 0.1x / 0.25x / 0.5x / 1x playback
- Exact ±1 / ±10 frame stepping using source FPS
- Evidence-sequence extraction
- Reference-tool library

## iPhone testing with Expo Go

This branch is intentionally pinned to Expo SDK 54 because the App Store version of Expo Go on physical iPhones currently supports SDK 54.

Expo SDK 54 uses React Native 0.81 and React 19.1 and requires Node.js 20.19.x or newer.

### On the iPhone

1. Install **Expo Go** from the Apple App Store.
2. Keep the iPhone on the same Wi-Fi network as the development PC.

### On the Windows PC

From the existing CrickAnalysis repository:

```bat
git pull
cd mobile
npm install
npx expo start --go
```

A QR code will appear in the terminal/browser. Scan it with the iPhone Camera and choose **Open in Expo Go**.

If Metro shows stale dependency errors after changing SDK versions, run:

```bat
npx expo start --go --clear
```

The default backend is already `https://crickanalysis.onrender.com`. Override it when needed with:

```text
EXPO_PUBLIC_API_BASE_URL=https://your-api.example.com
```

## First iPhone test path

1. Open CrickAnalysis in Expo Go.
2. Confirm Dashboard loads from the live backend.
3. Open Upload and select a short cricket video from Photos.
4. Use Quick Review first.
5. Open the finished analysis.
6. Test 0.25x playback, ±1 frame, ±10 frames, fullscreen and evidence extraction.
7. Open Crick AI and test an app-help question.

## Important MVP limitation

The current Render Free backend uses ephemeral local storage. A production mobile release should move videos/evidence to object storage and persistent metadata to Postgres before public distribution.

When the mobile UX is stable, move back to the current Expo SDK and create signed development/TestFlight builds for App Store distribution.
