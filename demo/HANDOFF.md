# Demo video handoff — for Claude Code (run on the recording Mac)

Goal: produce a **narrated MP4** of the Gujarat TSR Agent doing the whole flow
live — visible Streamlit form → live AnyRoR scrape (the scraper's Chrome window
pops up on screen) → extraction → finished Title Search Report — with a Gemini
Indian-English voiceover. Output lands at `demo/out/demo_final.mp4`.

**One command does everything once prereqs are met:**

```bash
bash demo/make_demo_video.sh
```

It: checks AnyRoR is reachable → generates the voiceover → launches Streamlit
with a *visible* scraper → screen-records while a Selenium script fills the form
and clicks Generate → stops recording → muxes the voiceover. Read it; it's short.

---

## Prereqs (Claude Code: verify/fix each before running)

1. **ffmpeg** — `command -v ffmpeg || brew install ffmpeg`
2. **Screen Recording permission** — THE human must grant this; you cannot.
   System Settings → Privacy & Security → Screen Recording → enable the terminal
   app hosting this session (Terminal/iTerm/VS Code) → **fully quit & reopen it**.
   Verify it works (should NOT be all-black ~YAVG 16):
   ```bash
   SCR=$(ffmpeg -f avfoundation -list_devices true -i "" 2>&1 | grep "Capture screen 0" | grep -oE "\[[0-9]+\]" | head -1 | tr -d '[]')
   ffmpeg -y -f avfoundation -i "${SCR}:none" -t 2 /tmp/perm.mp4 >/dev/null 2>&1
   ffmpeg -i /tmp/perm.mp4 -vf "signalstats,metadata=print:key=lavfi.signalstats.YAVG" -frames:v 1 -f null - 2>&1 | grep YAVG
   ```
   YAVG well above 16 = real capture (good). ~16 = permission missing.
3. **Gemini TTS key** — `export GEMINI_TTS_API_KEY=AIza...` (the user will text it).
   Must be a **billing-enabled** key; the free key returns "project denied access"
   for TTS. Cost is a fraction of a cent for the ~5-sentence script.
4. **GEMINI_API_KEY in `.env`** — for captcha/translation/extraction. Confirm the
   extraction backend too: `.env` has `EXTRACTION_BACKEND` — if `claude`, the
   `claude` CLI must be logged in on this Mac (it is, since you're running here);
   if you hit trouble, set `EXTRACTION_BACKEND=gemini` in `.env`.
5. **Python deps** — Selenium + Streamlit live in the repo `venv`. If missing:
   `venv/bin/pip install -r requirements.txt selenium streamlit`. (Chrome + a
   matching driver are auto-managed by Selenium Manager; just have Chrome installed.)
6. **A FRESH, CLEAN INDIAN IP** — AnyRoR's WAF blocks IPs that have burst-scraped.
   The script aborts if blocked. Manual check:
   ```bash
   curl -s -o /dev/null -w "http=%{http_code} exit=will-follow\n" --max-time 20 https://anyror.gujarat.gov.in/LandRecordRural.aspx; echo "curl_exit=$?"
   ```
   `curl_exit=35` / `http=000` (TLS reset) = **still blocked** → switch network
   (phone hotspot / toggle mobile data — NOT a proxy) and retry. A real `200`
   with `__VIEWSTATE` in the body = clear.
   Also note: AnyRoR has daily maintenance ~14:00–15:00 IST — don't record then.
7. **Survey must be UNCACHED** — the UI has no skip-cache toggle, so a cached
   record would skip the live scrape (no browser = no demo). On a fresh clone the
   cache is empty, so you're fine. To be safe, clear it:
   `rm -rf ~/.cache/gujrat_tsr_agent/cache`

---

## What to customize (optional)

- **Narration**: edit `demo/narration.md` (one spoken segment per `- ` bullet),
  re-run `python demo/generate_voiceover.py` to preview `demo/out/voice.wav`.
- **Voice**: env `GEMINI_TTS_VOICE` (default `Charon`), `GEMINI_TTS_LANG`
  (default `en-IN`). Other warmer options tried: `Sulafat`, `Orus`.
- **Demo record**: env `DEMO_DISTRICT/DEMO_TALUKA/DEMO_VILLAGE/DEMO_SURVEY`
  (default `Kutch / Lakhpat / Baranda / 220`). Pick one with an interesting
  encumbrance for a better story. Send survey numbers as ASCII (e.g. `220`, `145/1`).

---

## Before you hit record (clean screen)

The recording captures the **whole screen**. Close personal tabs/windows, silence
notifications (Do Not Disturb), and make sure Chrome can open windows in front.
Two Chrome windows will be visible during the run: the Selenium-driven Streamlit
window, and the scraper's own window driving AnyRoR — that's expected and looks good.

## If something breaks

- Streamlit didn't start → `demo/out/streamlit.log`
- Recording is black → permission (prereq 2) not actually granted / terminal not restarted
- UI driver couldn't find fields → Streamlit markup changed; field selectors are
  placeholders in `demo/drive_ui.py` (match `app/components/single_record_form.py`)
- Scrape hangs/fails → almost always the WAF IP block (prereq 6) or the 14:00–15:00
  IST maintenance window. Re-check reachability.
- Final video too long/has dead air → trim in Loom/iMovie; `demo/out/screen.mp4`
  (raw) and `demo/out/voice.wav` are kept so you can re-mux.
