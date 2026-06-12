# Morning Macro Brief Engine

V2 engine for a global, data-heavy morning financial brief with a portfolio section and long-form audio.

The engine generates:

- a full Markdown brief
- structured JSON metadata
- a 15-minute target narration script
- one compressed long-form audio file for browser and iPhone playback

## Run

```bash
python3 -m morning_brief.cli --mode both
```

Audio defaults to AAC internally and is merged into one iPhone-friendly `.m4a` file.

```bash
python3 -m morning_brief.cli --mode both --audio-format aac --keep-audio 1 --delete-audio-segments
python3 -m morning_brief.cli --cleanup-audio --keep-audio 1
```

Retention only applies to audio artifacts. Markdown and JSON briefs are preserved.

Morning and evening commute modes:

```bash
python3 -m morning_brief.cli --brief-type morning --mode both
python3 -m morning_brief.cli --brief-type evening --mode both
```

Morning mode focuses on the overnight US close, Asia open, Europe context, macro/rates, and the day ahead. Evening mode is built for Singapore commute timing and focuses on the upcoming US cash open, pre-market setup, US macro/events, earnings, and what to watch around the New York open.

No-cost deterministic smoke test:

```bash
python3 -m morning_brief.cli --sample-data --no-agent --mode text
```

Live public-data fallback without OpenAI synthesis:

```bash
python3 -m morning_brief.cli --no-agent --mode text
```

## Server

```bash
PORT=8421 python3 -m morning_brief.server
```

## Mobile Streamlit Console

```bash
streamlit run app.py
```

The Streamlit console is mobile-first and reads the latest generated `morning` or `evening` artifacts from `outputs/`. Generation buttons are manual so the app does not spend API calls on page load.

## Static iPhone PWA

For GitHub Pages deployment, export the latest artifacts into a static app:

```bash
python3 -m morning_brief.static_site --output-dir outputs --site-dir site
```

Then preview locally:

```bash
python3 -m http.server 8787 --directory site
```

The static app is interactive in the browser: morning/evening toggle, section tabs, audio playback, transcript view, Markdown download, and service-worker caching for the latest loaded files. It cannot run the OpenAI agents directly; generation happens locally or in GitHub Actions.

## GitHub Pages Deployment

The workflow in `.github/workflows/pages.yml` publishes the static PWA only when manually run. There are no scheduled runs, so OpenAI credits are spent only when you choose `Run workflow`.

Setup:

1. Push this project to a GitHub repository.
2. In the repo, add an Actions secret named `OPENAI_API_KEY`.
3. In GitHub Pages settings, select GitHub Actions as the Pages source.
4. Run the `Publish Markets Brief` workflow manually for `morning` or `evening`.
5. Open the Pages URL on iPhone Safari and use Share -> Add to Home Screen.

Manual runs:

- Choose `morning` before your morning commute.
- Choose `evening` before your evening commute.
- Keep `mode=both` when you want the one-file audio output.
- Use `mode=text` only when you want to save TTS cost.

The workflow caches `outputs/` between runs so the static page can keep both the latest morning and evening artifacts when available.

Endpoints:

- `GET /health`
- `GET /brief?format=text`
- `GET /brief?format=audio`
- `GET /brief?format=json`

## Portfolio

Default holdings live in `data/portfolio.json`. Add position sizes, cost basis, and notes there later to make portfolio impact more personalized.

## Caveat

This is informational research support only, not investment advice.
