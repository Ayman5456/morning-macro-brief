from __future__ import annotations

import argparse
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BRIEF_TYPES = ("morning", "evening")


def _sort_key(path: Path) -> tuple[float, str]:
    return (path.stat().st_mtime, path.name)


def latest_brief_json(output_dir: Path, brief_type: str) -> Path | None:
    paths = [
        path
        for path in output_dir.glob(f"{brief_type}_brief_*.json")
        if "_sample" not in path.name and "_fallback" not in path.name and not path.name.endswith(".audio.json")
    ]
    return max(paths, key=_sort_key) if paths else None


def _copy_file(src: Path, dest: Path, site_dir: Path) -> str:
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    return dest.relative_to(site_dir).as_posix()


def _audio_segments_for(json_path: Path) -> list[Path]:
    manifest_path = json_path.with_suffix(".audio.json")
    if not manifest_path.exists():
        return []

    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    segments: list[Path] = []
    for raw_name in payload.get("segments", []):
        segment = Path(raw_name)
        segment = segment if segment.is_absolute() else manifest_path.parent / segment
        if segment.exists():
            segments.append(segment)
    return segments


def _audio_files_for(json_path: Path) -> list[Path]:
    files = []
    for suffix in [".m4a", ".aac", ".mp3", ".opus", ".flac", ".wav"]:
        candidate = json_path.with_suffix(suffix)
        if candidate.exists():
            files.append(candidate)
    return files or _audio_segments_for(json_path)


def _estimated_minutes(brief: dict[str, Any]) -> int:
    words = len(re.findall(r"\b\w+\b", brief.get("audio_script", "")))
    return max(1, round(words / 155)) if words else 0


def _brief_payload(output_dir: Path, site_dir: Path, brief_type: str) -> dict[str, Any] | None:
    json_path = latest_brief_json(output_dir, brief_type)
    if not json_path:
        return None

    brief = json.loads(json_path.read_text(encoding="utf-8"))
    artifact_dir = site_dir / "artifacts" / brief_type
    json_url = _copy_file(json_path, artifact_dir / json_path.name, site_dir)

    markdown_path = json_path.with_suffix(".md")
    markdown_url = None
    if markdown_path.exists():
        markdown_url = _copy_file(markdown_path, artifact_dir / markdown_path.name, site_dir)

    audio_urls = []
    for audio_file in _audio_files_for(json_path):
        audio_urls.append(_copy_file(audio_file, artifact_dir / audio_file.name, site_dir))

    return {
        "brief_type": brief_type,
        "title": brief.get("title", f"{brief_type.title()} Brief"),
        "market_date": brief.get("market_date"),
        "generated_at": brief.get("generated_at"),
        "json_url": json_url,
        "markdown_url": markdown_url,
        "audio_urls": audio_urls,
        "audio_parts": len(audio_urls),
        "estimated_minutes": _estimated_minutes(brief),
        "risk_flags": brief.get("risk_flags", []),
        "citations": brief.get("citations", []),
        "chapters": brief.get("audio_chapters", []),
    }


def build_static_site(output_dir: Path = Path("outputs"), site_dir: Path = Path("site")) -> dict[str, Any]:
    if site_dir.exists():
        shutil.rmtree(site_dir)
    site_dir.mkdir(parents=True, exist_ok=True)

    brief_payloads = {
        brief_type: payload
        for brief_type in BRIEF_TYPES
        if (payload := _brief_payload(output_dir, site_dir, brief_type)) is not None
    }
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "briefs": brief_payloads,
    }

    (site_dir / "latest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (site_dir / "index.html").write_text(INDEX_HTML, encoding="utf-8")
    (site_dir / "styles.css").write_text(STYLES_CSS, encoding="utf-8")
    (site_dir / "app.js").write_text(APP_JS, encoding="utf-8")
    (site_dir / "service-worker.js").write_text(SERVICE_WORKER_JS, encoding="utf-8")
    (site_dir / "manifest.webmanifest").write_text(WEB_MANIFEST, encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Export latest brief artifacts as a static iPhone-friendly PWA.")
    parser.add_argument("--output-dir", type=Path, default=Path("outputs"))
    parser.add_argument("--site-dir", type=Path, default=Path("site"))
    args = parser.parse_args()
    manifest = build_static_site(args.output_dir, args.site_dir)
    print(f"Static site: {args.site_dir}")
    print(f"Briefs: {', '.join(manifest['briefs']) or 'none'}")


INDEX_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
  <meta name="theme-color" content="#090b0f">
  <title>MRT Markets Console</title>
  <link rel="manifest" href="manifest.webmanifest">
  <link rel="stylesheet" href="styles.css">
</head>
<body>
  <main class="shell">
    <header class="topbar">
      <div>
        <div class="kicker">MRT Markets Console</div>
        <h1>Global Macro Briefing Terminal</h1>
        <p>Static commute edition. Generated by the brief engine and hosted from GitHub Pages.</p>
      </div>
      <button id="refreshBtn" type="button">Refresh</button>
    </header>

    <section class="switcher" aria-label="Brief selector">
      <button class="mode active" data-mode="morning" type="button">Morning</button>
      <button class="mode" data-mode="evening" type="button">Evening</button>
    </section>

    <section id="status" class="status">Loading latest brief...</section>

    <section class="metrics" aria-label="Brief summary">
      <article><span>Mode</span><strong id="metricMode">-</strong><small>commute profile</small></article>
      <article><span>Generated</span><strong id="metricGenerated">-</strong><small id="metricDate">market date</small></article>
      <article><span>Audio</span><strong id="metricAudio">-</strong><small>single-file player</small></article>
      <article><span>Runtime</span><strong id="metricMinutes">-</strong><small>estimated listen</small></article>
    </section>

    <nav class="tabs" aria-label="Sections">
      <button class="tab active" data-tab="today" type="button">Today</button>
      <button class="tab" data-tab="macro" type="button">Macro</button>
      <button class="tab" data-tab="portfolio" type="button">Portfolio</button>
      <button class="tab" data-tab="ideas" type="button">Diversify</button>
      <button class="tab" data-tab="audio" type="button">Audio</button>
      <button class="tab" data-tab="transcript" type="button">Transcript</button>
    </nav>

    <section id="today" class="panel active"></section>
    <section id="macro" class="panel"></section>
    <section id="portfolio" class="panel"></section>
    <section id="ideas" class="panel"></section>
    <section id="audio" class="panel"></section>
    <section id="transcript" class="panel"></section>
  </main>
  <script src="app.js"></script>
</body>
</html>
"""


STYLES_CSS = """:root {
  --bg: #090b0f;
  --panel: #111821;
  --panel-2: #151f2b;
  --line: #273342;
  --text: #e7edf3;
  --muted: #8ea0b4;
  --green: #2dd4a4;
  --red: #ff647c;
  --amber: #f7c948;
  --cyan: #5bd7ff;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--text);
  font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  letter-spacing: 0;
}
button {
  color: inherit;
  font: inherit;
}
.shell {
  width: min(1120px, 100%);
  margin: 0 auto;
  padding: calc(16px + env(safe-area-inset-top)) 14px calc(36px + env(safe-area-inset-bottom));
}
.topbar {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
  border-bottom: 1px solid var(--line);
  padding-bottom: 14px;
}
.kicker {
  color: var(--cyan);
  font-size: 12px;
  font-weight: 800;
  text-transform: uppercase;
}
h1 {
  margin: 4px 0 4px;
  font-size: clamp(24px, 6vw, 34px);
  line-height: 1.05;
}
p {
  color: var(--muted);
  line-height: 1.45;
}
.topbar p {
  margin: 0;
  font-size: 14px;
}
#refreshBtn, .mode, .tab, .download {
  border: 1px solid var(--line);
  background: var(--panel);
  border-radius: 6px;
  padding: 10px 12px;
  text-decoration: none;
}
#refreshBtn {
  min-width: 84px;
}
.switcher, .tabs {
  display: flex;
  gap: 8px;
  overflow-x: auto;
  padding: 14px 0 8px;
}
.mode, .tab {
  flex: 0 0 auto;
}
.mode.active, .tab.active {
  color: var(--cyan);
  border-color: var(--cyan);
}
.status {
  border-left: 3px solid var(--amber);
  background: #171511;
  color: #f5e6b8;
  padding: 12px;
  border-radius: 4px;
  margin: 8px 0 14px;
}
.status.ok {
  border-left-color: var(--green);
  background: #0e1917;
  color: #c7f5e7;
}
.metrics {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 10px;
}
.metrics article, .panel {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 6px;
}
.metrics article {
  padding: 12px;
  min-height: 86px;
}
.metrics span {
  display: block;
  color: var(--muted);
  font-size: 11px;
  font-weight: 800;
  text-transform: uppercase;
}
.metrics strong {
  display: block;
  margin-top: 4px;
  font-size: 20px;
  line-height: 1.2;
}
.metrics small {
  color: var(--muted);
}
.panel {
  display: none;
  padding: 16px;
  overflow-x: auto;
}
.panel.active {
  display: block;
}
h2 {
  margin: 18px 0 8px;
  font-size: 20px;
}
h3 {
  margin: 14px 0 8px;
  font-size: 16px;
}
table {
  width: 100%;
  border-collapse: collapse;
  margin: 12px 0;
  font-size: 14px;
}
th, td {
  border-bottom: 1px solid var(--line);
  padding: 9px 8px;
  text-align: left;
  vertical-align: top;
}
th {
  color: var(--cyan);
  background: var(--panel-2);
}
audio {
  width: 100%;
  margin: 10px 0 2px;
}
.audio-card {
  padding: 12px;
  border: 1px solid var(--line);
  border-radius: 6px;
  margin: 10px 0;
  background: #0d131b;
}
.risk {
  color: #f5e6b8;
  margin: 8px 0;
}
.download {
  display: inline-block;
  margin-top: 12px;
  color: var(--cyan);
}
@media (max-width: 720px) {
  .topbar {
    display: block;
  }
  #refreshBtn {
    margin-top: 12px;
    width: 100%;
  }
  .metrics {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .panel {
    padding: 12px;
  }
  table {
    font-size: 12px;
  }
  th, td {
    padding: 8px 6px;
  }
}
"""


APP_JS = """const state = {
  manifest: null,
  currentMode: "morning",
  currentBrief: null,
};

const el = (id) => document.getElementById(id);

function fmtDate(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value).slice(0, 16);
  return date.toLocaleString([], { month: "short", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}

function escapeHtml(text) {
  return String(text ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function inlineMarkdown(text) {
  return escapeHtml(text)
    .replace(/\\*\\*(.*?)\\*\\*/g, "<strong>$1</strong>")
    .replace(/\\*(.*?)\\*/g, "<em>$1</em>");
}

function markdownToHtml(markdown) {
  const lines = String(markdown || "").split(/\\r?\\n/);
  let html = "";
  let inList = false;
  let table = [];

  const closeList = () => {
    if (inList) {
      html += "</ul>";
      inList = false;
    }
  };
  const flushTable = () => {
    if (table.length < 2) {
      table = [];
      return;
    }
    const rows = table.filter((line, idx) => idx !== 1 || !/^\\|?\\s*:?-+:?/.test(line.replace(/\\|/g, "").trim()));
    if (!rows.length) {
      table = [];
      return;
    }
    html += "<table>";
    rows.forEach((line, idx) => {
      const cells = line.replace(/^\\||\\|$/g, "").split("|").map((cell) => inlineMarkdown(cell.trim()));
      html += idx === 0 ? "<thead><tr>" : "<tr>";
      html += cells.map((cell) => idx === 0 ? `<th>${cell}</th>` : `<td>${cell}</td>`).join("");
      html += idx === 0 ? "</tr></thead><tbody>" : "</tr>";
    });
    html += "</tbody></table>";
    table = [];
  };

  for (const raw of lines) {
    const line = raw.trimEnd();
    if (line.startsWith("|")) {
      closeList();
      table.push(line);
      continue;
    }
    flushTable();
    if (!line.trim()) {
      closeList();
      continue;
    }
    if (line.startsWith("### ")) {
      closeList();
      html += `<h3>${inlineMarkdown(line.slice(4))}</h3>`;
    } else if (line.startsWith("## ")) {
      closeList();
      html += `<h2>${inlineMarkdown(line.slice(3))}</h2>`;
    } else if (line.startsWith("# ")) {
      closeList();
      html += `<h2>${inlineMarkdown(line.slice(2))}</h2>`;
    } else if (/^[-*]\\s+/.test(line)) {
      if (!inList) {
        html += "<ul>";
        inList = true;
      }
      html += `<li>${inlineMarkdown(line.replace(/^[-*]\\s+/, ""))}</li>`;
    } else {
      closeList();
      html += `<p>${inlineMarkdown(line)}</p>`;
    }
  }
  flushTable();
  closeList();
  return html;
}

function section(markdown, headingPattern) {
  const lines = String(markdown || "").split(/\\r?\\n/);
  const start = lines.findIndex((line) => /^##\\s+/.test(line) && headingPattern.test(line));
  if (start < 0) return "";
  let end = lines.length;
  for (let i = start + 1; i < lines.length; i += 1) {
    if (/^##\\s+/.test(lines[i])) {
      end = i;
      break;
    }
  }
  return lines.slice(start, end).join("\\n");
}

async function loadJson(url) {
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) throw new Error(`Could not load ${url}`);
  return res.json();
}

async function loadBrief(mode) {
  const meta = state.manifest.briefs[mode];
  if (!meta) {
    state.currentBrief = null;
    render();
    return;
  }
  state.currentBrief = await loadJson(meta.json_url);
  render();
}

function renderMetrics(meta) {
  el("metricMode").textContent = state.currentMode.toUpperCase();
  el("metricGenerated").textContent = fmtDate(meta?.generated_at);
  el("metricDate").textContent = meta?.market_date ? `market ${meta.market_date}` : "market date";
  el("metricAudio").textContent = meta ? `${meta.audio_parts} file${meta.audio_parts === 1 ? "" : "s"}` : "-";
  el("metricMinutes").textContent = meta?.estimated_minutes ? `${meta.estimated_minutes} min` : "-";
}

function renderAudio(meta) {
  if (!meta?.audio_urls?.length) {
    el("audio").innerHTML = "<h2>Brief Audio</h2><p>No compressed audio has been generated for this brief yet.</p>";
    return;
  }
  el("audio").innerHTML = `<h2>Brief Audio</h2>${meta.audio_urls.map((url, idx) => `
    <div class="audio-card">
      <strong>${meta.audio_urls.length === 1 ? `${state.currentMode[0].toUpperCase()}${state.currentMode.slice(1)} Brief` : `Part ${String(idx + 1).padStart(2, "0")}`}</strong>
      <audio controls preload="metadata" src="${escapeHtml(url)}"></audio>
      <a class="download" href="${escapeHtml(url)}" download>Download audio</a>
    </div>
  `).join("")}`;
}

function render() {
  const meta = state.manifest?.briefs?.[state.currentMode];
  renderMetrics(meta);

  if (!meta || !state.currentBrief) {
    el("status").className = "status";
    el("status").textContent = `No ${state.currentMode} brief artifact found in this static export.`;
    ["today", "macro", "portfolio", "ideas", "audio", "transcript"].forEach((id) => { el(id).innerHTML = ""; });
    return;
  }

  const markdown = state.currentBrief.markdown || "";
  el("status").className = "status ok";
  const firstRisk = state.currentBrief.risk_flags?.[0] ? ` Caveat: ${state.currentBrief.risk_flags[0]}` : "";
  el("status").textContent = `Loaded ${state.currentMode} brief generated ${fmtDate(meta.generated_at)}.${firstRisk}`;

  el("today").innerHTML = markdownToHtml(section(markdown, /Opening dashboard|Dashboard/i) || markdown.split("\\n").slice(0, 80).join("\\n"));
  el("macro").innerHTML = markdownToHtml([
    section(markdown, /Global market snapshot/i),
    section(markdown, /Rates|Macro|Economy|Calendar/i),
  ].filter(Boolean).join("\\n\\n") || markdown);
  el("portfolio").innerHTML = markdownToHtml(section(markdown, /Portfolio/i) || "## Portfolio\\nNo portfolio section found.");
  el("ideas").innerHTML = markdownToHtml(section(markdown, /Diversification/i) || "## Diversification Research Watchlist\\nNo diversification section found.");
  renderAudio(meta);
  el("transcript").innerHTML = markdownToHtml(markdown) + (meta.markdown_url ? `<a class="download" href="${escapeHtml(meta.markdown_url)}" download>Download Markdown</a>` : "");
}

async function refresh() {
  el("status").className = "status";
  el("status").textContent = "Refreshing latest manifest...";
  state.manifest = await loadJson("latest.json");
  await loadBrief(state.currentMode);
  try {
    localStorage.setItem("mrt-markets-manifest", JSON.stringify(state.manifest));
  } catch {}
}

document.querySelectorAll(".mode").forEach((button) => {
  button.addEventListener("click", async () => {
    document.querySelectorAll(".mode").forEach((item) => item.classList.remove("active"));
    button.classList.add("active");
    state.currentMode = button.dataset.mode;
    await loadBrief(state.currentMode);
  });
});

document.querySelectorAll(".tab").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((item) => item.classList.remove("active"));
    document.querySelectorAll(".panel").forEach((item) => item.classList.remove("active"));
    button.classList.add("active");
    el(button.dataset.tab).classList.add("active");
  });
});

el("refreshBtn").addEventListener("click", () => refresh().catch((err) => {
  el("status").className = "status";
  el("status").textContent = err.message;
}));

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("service-worker.js").catch(() => {});
}

refresh().catch((err) => {
  try {
    state.manifest = JSON.parse(localStorage.getItem("mrt-markets-manifest") || "null");
  } catch {}
  if (state.manifest) {
    loadBrief(state.currentMode);
  } else {
    el("status").textContent = err.message;
  }
});
"""


SERVICE_WORKER_JS = """const CACHE_NAME = "mrt-markets-console-v1";
const CORE_ASSETS = [
  "./",
  "index.html",
  "styles.css",
  "app.js",
  "latest.json",
  "manifest.webmanifest",
];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.addAll(CORE_ASSETS)).catch(() => undefined));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))))
  );
});

self.addEventListener("fetch", (event) => {
  if (event.request.method !== "GET") return;
  event.respondWith(
    fetch(event.request)
      .then((response) => {
        const copy = response.clone();
        caches.open(CACHE_NAME).then((cache) => cache.put(event.request, copy));
        return response;
      })
      .catch(() => caches.match(event.request))
  );
});
"""


WEB_MANIFEST = """{
  "name": "MRT Markets Console",
  "short_name": "Markets Brief",
  "start_url": "./",
  "display": "standalone",
  "background_color": "#090b0f",
  "theme_color": "#090b0f",
  "description": "Morning and evening macro brief for iPhone commute use."
}
"""


if __name__ == "__main__":
    main()
