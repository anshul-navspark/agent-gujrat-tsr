#!/usr/bin/env bash
# =============================================================================
# Gujarat TSR Agent — Loom demo recorder (fully local, macOS).
#
# Records a narrated MP4 of the end-to-end flow:
#   visible Streamlit UI (form fill) -> live AnyRoR scrape (Chrome pops up)
#   -> extraction -> finished TSR, with a Gemini "Charon" Indian-English voiceover.
#
# Run from the repo root:
#     bash demo/make_demo_video.sh
#
# Output: demo/out/demo_final.mp4
#
# PREREQS (see demo/HANDOFF.md for the full checklist):
#   * ffmpeg installed            (brew install ffmpeg)
#   * Screen Recording permission GRANTED to your terminal app (System Settings
#     -> Privacy & Security -> Screen Recording), terminal then restarted.
#   * GEMINI_TTS_API_KEY exported  (a TTS/billing-enabled Gemini key)
#   * GEMINI_API_KEY set in .env   (captcha/translation/extraction)
#   * A FRESH, CLEAN INDIAN IP     (AnyRoR WAF blocks burst-scraping IPs; verify
#     with the reachability check below — it must NOT be curl exit 35 / TLS reset)
#   * The chosen survey must NOT already be cached locally (we want a live scrape)
# =============================================================================
set -uo pipefail
cd "$(dirname "$0")/.."          # repo root
ROOT="$(pwd)"
OUT="$ROOT/demo/out"
mkdir -p "$OUT"

PY="$ROOT/venv/bin/python"
[ -x "$PY" ] || PY="python3"
STREAMLIT="$ROOT/venv/bin/streamlit"
[ -x "$STREAMLIT" ] || STREAMLIT="streamlit"

log() { printf "\n\033[1;36m==> %s\033[0m\n" "$*"; }
die() { printf "\n\033[1;31mERROR: %s\033[0m\n" "$*" >&2; exit 1; }

# --- 0. preflight ------------------------------------------------------------
command -v ffmpeg >/dev/null || die "ffmpeg not found. brew install ffmpeg"
[ -n "${GEMINI_TTS_API_KEY:-${GEMINI_API_KEY:-}}" ] || die "set GEMINI_TTS_API_KEY"

log "Checking AnyRoR reachability (WAF/IP block detector)"
http=$(curl -s -o /dev/null -w "%{http_code}" --max-time 20 \
  -A "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124 Safari/537.36" \
  "https://anyror.gujarat.gov.in/LandRecordRural.aspx") ; cexit=$?
if [ "$cexit" = "35" ] || [ "$http" = "000" ]; then
  die "AnyRoR unreachable (curl exit $cexit, http $http) — IP is still WAF-blocked. Switch to a fresh clean Indian IP (mobile hotspot) and retry."
fi
log "AnyRoR reachable (http $http) — proceeding."

# --- 1. voiceover ------------------------------------------------------------
log "Generating voiceover (Gemini Charon, en-IN) -> demo/out/voice.wav"
"$PY" demo/generate_voiceover.py || die "voiceover generation failed"

# --- 2. detect screen capture device ----------------------------------------
SCR_IDX=$(ffmpeg -f avfoundation -list_devices true -i "" 2>&1 \
  | grep "Capture screen 0" | grep -oE "\[[0-9]+\]" | head -1 | tr -d '[]')
[ -n "$SCR_IDX" ] || die "could not find an avfoundation 'Capture screen 0' device"
log "Screen capture device index: $SCR_IDX"

# --- 3. launch Streamlit with a VISIBLE scraper (HEADLESS=false) -------------
log "Starting Streamlit (HEADLESS=false, in-process backend) on :8501"
HEADLESS=false USE_INPROCESS=true \
  "$STREAMLIT" run app/streamlit_app_cloud.py \
  --server.headless true --server.port 8501 \
  >"$OUT/streamlit.log" 2>&1 &
ST_PID=$!
cleanup() { kill "$ST_PID" 2>/dev/null; kill "${FF_PID:-}" 2>/dev/null; }
trap cleanup EXIT

# wait for Streamlit to answer
for i in $(seq 1 40); do
  curl -sf "http://localhost:8501/_stcore/health" >/dev/null 2>&1 && break
  sleep 1
done
curl -sf "http://localhost:8501/_stcore/health" >/dev/null 2>&1 \
  || die "Streamlit did not come up — see $OUT/streamlit.log"
sleep 2

# --- 4. start screen recording ----------------------------------------------
log "Recording screen -> demo/out/screen.mp4  (the UI driver runs now)"
ffmpeg -y -f avfoundation -capture_cursor 1 -framerate 30 -i "${SCR_IDX}:none" \
  -t 600 -pix_fmt yuv420p -vf "scale=1920:-2" "$OUT/screen.mp4" \
  </dev/null >"$OUT/ffmpeg_rec.log" 2>&1 &
FF_PID=$!
sleep 2   # let recording warm up

# --- 5. drive the visible UI -------------------------------------------------
"$PY" demo/drive_ui.py
DRIVE_RC=$?

# --- 6. stop recording cleanly ----------------------------------------------
log "Stopping screen recording"
kill -INT "$FF_PID" 2>/dev/null
wait "$FF_PID" 2>/dev/null
FF_PID=""

[ "$DRIVE_RC" = "0" ] || log "WARNING: UI driver exited non-zero ($DRIVE_RC) — video still saved; check it."

# --- 7. mux voiceover over the screen capture (pad to the longer track) ------
log "Muxing voiceover over screen capture -> demo/out/demo_final.mp4"
VD=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$OUT/screen.mp4")
AD=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$OUT/voice.wav")
# target = max(video, audio)+1; extend video by cloning its last frame to reach it
PADV=$(awk -v v="$VD" -v a="$AD" 'BEGIN{t=(a>v?a:v)+1; e=t-v; printf "%.3f", (e>0?e:0)}')
ffmpeg -y -i "$OUT/screen.mp4" -i "$OUT/voice.wav" \
  -filter_complex "[0:v]tpad=stop_mode=clone:stop_duration=${PADV}[v];[1:a]apad[a]" \
  -map "[v]" -map "[a]" -shortest \
  -c:v libx264 -pix_fmt yuv420p -c:a aac -movflags +faststart \
  "$OUT/demo_final.mp4" >"$OUT/ffmpeg_mux.log" 2>&1 \
  || die "mux failed — see $OUT/ffmpeg_mux.log"

log "DONE -> $OUT/demo_final.mp4"
echo "    (raw screen: $OUT/screen.mp4 | voiceover: $OUT/voice.wav)"
echo "    Review it, then trim/polish in Loom or iMovie if you like."
