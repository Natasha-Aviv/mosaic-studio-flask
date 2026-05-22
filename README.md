# Mosaic Studio Pro — Render Free Version 1

This version is optimized for Render Free hosting. It keeps the premium UI and Python mosaic processing, but removes lead collection for now and limits heavy settings to reduce crashes.

## What changed for Version 1

- No name/email/phone collection.
- Direct download after mosaic generation.
- Maximum 120 tile photos by default.
- Safer upload limit: 150 MB total request size.
- Default tile resolution changed to 32 px for stability.
- Grid density capped at 160 tiles across.
- Large main portraits are resized safely before processing.
- Original tile photos are not kept in RAM during processing.
- Old generated files are cleaned automatically.
- Render deployment files included: `Procfile` and `render.yaml`.

## Run locally

```bash
python -m venv venv
venv\Scripts\activate
python -m pip install -r requirements.txt
python app.py
```

Open:

```text
http://127.0.0.1:5000
```

## Deploy on Render Free

1. Push this folder to GitHub.
2. In Render, create a new Web Service from the repository.
3. Use these commands if Render does not auto-detect them:

Build command:

```bash
pip install -r requirements.txt
```

Start command:

```bash
gunicorn app:app --workers 1 --threads 2 --timeout 240 --max-requests 20 --max-requests-jitter 5
```

## Important Render Free note

Render Free can sleep after inactivity. This version reduces crashes and heavy memory use, but free hosting cannot guarantee always-awake loading. For no idle sleep, upgrade to a paid web service later.

## Version 1.1 additions

- Shows a photo scanning progress bar after tile photos are selected.
- Automatically suggests the best 3 likely portrait photos from the uploaded tile set using browser-side image checks.
- Lets the user select one suggested portrait or upload a separate custom main portrait.
- Shows upload/generation progress while creating the mosaic.

Note: The portrait suggestion uses a lightweight browser-side heuristic for free hosting stability. It ranks photos by portrait shape, brightness, center clarity, sharpness, and resolution. It does not require paid face-detection APIs.
