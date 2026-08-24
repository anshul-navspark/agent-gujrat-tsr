#!/usr/bin/env python3
"""Generate the demo voiceover with Gemini TTS (voice: Charon, en-IN).

Reads narration segments from demo/narration.md (one per top-level "- " bullet),
synthesizes each with the Gemini TTS REST API, and concatenates them (with a
short gap) into demo/out/voice.wav.

Key: read from env GEMINI_TTS_API_KEY, falling back to GEMINI_API_KEY.
NOTE: Gemini TTS preview models require a *billing-enabled* project. A free-tier
key will fail with "project has been denied access" — set GEMINI_TTS_API_KEY to a
TTS-capable key. Cost is a fraction of a cent for this ~5-sentence script.

Usage:
    GEMINI_TTS_API_KEY=AIza... python demo/generate_voiceover.py
"""
import base64
import json
import os
import sys
import urllib.request
import urllib.error
import wave
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
OUT.mkdir(exist_ok=True)

MODEL = os.getenv("GEMINI_TTS_MODEL", "gemini-2.5-flash-preview-tts")
VOICE = os.getenv("GEMINI_TTS_VOICE", "Charon")
LANG = os.getenv("GEMINI_TTS_LANG", "en-IN")
STYLE = os.getenv(
    "GEMINI_TTS_STYLE",
    "Read aloud slowly in a warm, natural Indian English accent, "
    "like a friendly Indian product narrator:",
)
GAP_SECONDS = float(os.getenv("GEMINI_TTS_GAP", "0.45"))
RATE = 24000  # Gemini TTS returns 24kHz, 16-bit, mono PCM

KEY = os.getenv("GEMINI_TTS_API_KEY") or os.getenv("GEMINI_API_KEY")
if not KEY:
    sys.exit("ERROR: set GEMINI_TTS_API_KEY (or GEMINI_API_KEY) to a TTS-capable key.")


def parse_segments(md_path: Path):
    segs = []
    for line in md_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("- "):
            segs.append(line[2:].strip())
    return [s for s in segs if s]


def synth(text: str) -> bytes:
    body = json.dumps({
        "contents": [{"parts": [{"text": f"{STYLE}\n\n{text}"}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {
                "languageCode": LANG,
                "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": VOICE}},
            },
        },
    }).encode()
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{MODEL}:generateContent?key={KEY}"
    )
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    last_err = None
    for attempt in range(3):  # TTS preview occasionally returns 503/timeout
        try:
            r = json.load(urllib.request.urlopen(req, timeout=120))
            part = r["candidates"][0]["content"]["parts"][0]
            return base64.b64decode(part["inlineData"]["data"])
        except urllib.error.HTTPError as e:
            last_err = e.read().decode()[:200]
            if e.code == 429 or e.code >= 500:
                continue
            raise SystemExit(f"ERROR from Gemini TTS (HTTP {e.code}): {last_err}")
        except Exception as e:  # noqa: BLE001 - transient timeouts
            last_err = str(e)
    raise SystemExit(f"ERROR: TTS failed after retries: {last_err}")


def main():
    segments = parse_segments(HERE / "narration.md")
    if not segments:
        sys.exit("ERROR: no '- ' segments found in demo/narration.md")
    print(f"Synthesizing {len(segments)} segment(s) with {MODEL} / {VOICE} / {LANG}...")

    pcm = bytearray()
    silence = b"\x00\x00" * int(RATE * GAP_SECONDS)
    for i, seg in enumerate(segments, 1):
        data = synth(seg)
        pcm += data
        if i < len(segments):
            pcm += silence
        print(f"  [{i}/{len(segments)}] {len(data)//2/RATE:.1f}s  —  {seg[:60]}...")

    out = OUT / "voice.wav"
    with wave.open(str(out), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(bytes(pcm))
    print(f"\nWrote {out}  (~{len(pcm)//2/RATE:.1f}s total)")


if __name__ == "__main__":
    main()
