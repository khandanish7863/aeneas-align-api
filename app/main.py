"""Aeneas Align API — word-level timestamps for an audio file and its transcript.

    GET  /health   public, no token
    POST /align    needs  Authorization: Bearer <API_TOKEN>

/align accepts either
    JSON      {"audio_url": "...", "text": "...", "language": "eng", "clean": true}
    or a form upload (multipart/form-data) with fields  audio=<file>, text, language, clean
"""
import hmac
import logging
import os
import re
import tempfile
import time
from functools import wraps
from pathlib import Path

import requests
from flask import Flask, jsonify, request

from .align import AlignError, align, audio_duration

APP_DIR = Path(__file__).resolve().parent.parent
VERSION = (APP_DIR / "VERSION").read_text(encoding="utf-8").strip() if (APP_DIR / "VERSION").exists() else "dev"

# Settings come from .env (loaded by systemd). Several tokens may be given, separated by commas.
API_TOKENS = [t.strip() for t in os.environ.get("API_TOKEN", "").split(",") if t.strip()]
MAX_AUDIO_MB = int(os.environ.get("MAX_AUDIO_MB", "1024"))
ALIGN_TIMEOUT = int(os.environ.get("ALIGN_TIMEOUT", "1800"))
DOWNLOAD_TIMEOUT = int(os.environ.get("DOWNLOAD_TIMEOUT", "300"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("aeneas-align-api")

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_AUDIO_MB * 1024 * 1024
app.json.sort_keys = False


def error(message: str, code: int):
    return jsonify({"status": "error", "message": message}), code


def require_token(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not API_TOKENS:
            return error("Server has no API_TOKEN set in .env", 500)
        header = request.headers.get("Authorization", "")
        given = header[7:].strip() if header.lower().startswith("bearer ") else ""
        if not given or not any(hmac.compare_digest(given, t) for t in API_TOKENS):
            return error("Unauthorized. Provide a valid Bearer token.", 401)
        return f(*args, **kwargs)
    return wrapper


# ---------------------------------------------------------------- download

DRIVE_ID = re.compile(r"(?:/file/d/|[?&]id=)([A-Za-z0-9_-]{10,})")


def drive_direct_url(url: str):
    """Google Drive share/download links -> a direct download link (skips the 'virus scan' page)."""
    if "drive.google.com" not in url and "drive.usercontent.google.com" not in url:
        return None
    m = DRIVE_ID.search(url)
    if not m:
        return None
    return f"https://drive.usercontent.google.com/download?id={m.group(1)}&export=download&confirm=t"


def download(url: str, dest: Path) -> None:
    url = drive_direct_url(url) or url
    limit = MAX_AUDIO_MB * 1024 * 1024
    with requests.get(url, stream=True, timeout=(15, DOWNLOAD_TIMEOUT), allow_redirects=True) as r:
        r.raise_for_status()
        ctype = r.headers.get("Content-Type", "")
        size = 0
        with open(dest, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 16):
                size += len(chunk)
                if size > limit:
                    raise ValueError(f"Audio is larger than {MAX_AUDIO_MB} MB")
                f.write(chunk)
    if size == 0:
        raise ValueError("The audio link returned an empty file")
    if ctype.startswith("text/html"):
        raise ValueError("The link returned a web page, not an audio file. "
                         "Check the file is shared publicly ('Anyone with the link').")


def to_bool(v, default=True) -> bool:
    if v is None:
        return default
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() not in ("0", "false", "no", "off")


# ---------------------------------------------------------------- routes

@app.get("/health")
def health():
    return jsonify({"status": "ok", "service": "aeneas-alignment-api", "version": VERSION})


@app.post("/align")
@require_token
def align_route():
    started = time.time()
    upload = request.files.get("audio")
    if upload:
        data = request.form
    else:
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return error("Send JSON (audio_url, text) or a form upload (audio, text)", 400)

    text = (data.get("text") or "").strip()
    language = (data.get("language") or "eng").strip()
    clean = to_bool(data.get("clean"), True)
    audio_url = (data.get("audio_url") or "").strip()

    if not upload and not audio_url:
        return error("Missing 'audio_url'", 400)
    if not text:
        return error("Missing 'text'", 400)
    if not re.fullmatch(r"[a-z]{2,3}(-[a-z0-9]+)?", language):
        return error("Invalid 'language' (use a code like eng, hin, urd)", 400)

    with tempfile.TemporaryDirectory(prefix="aeneas_") as tmp:
        work = Path(tmp)
        src = work / "input_audio"
        try:
            if upload:
                upload.save(src)
            else:
                download(audio_url, src)
        except requests.RequestException as e:
            return error(f"Failed to download audio: {e}", 400)
        except ValueError as e:
            return error(str(e), 400)

        duration = audio_duration(src)
        if duration is None:
            return error("The file is not a readable audio file", 400)

        try:
            fragments = align(src, text, work, language=language, clean=clean, timeout=ALIGN_TIMEOUT)
        except AlignError as e:
            log.warning("align failed: %s", e)
            return error(str(e), 500)

    took = round(time.time() - started, 2)
    log.info("aligned %d words, %.1f s audio, lang=%s, %.2f s", len(fragments), duration, language, took)
    return jsonify({
        "status": "success",
        "audio_duration": duration,
        "word_count": len(fragments),
        "language": language,
        "processing_seconds": took,
        "fragments": fragments,
    })


@app.errorhandler(413)
def too_large(_):
    return error(f"Upload is larger than {MAX_AUDIO_MB} MB", 413)


if __name__ == "__main__":  # local testing only; the service runs under gunicorn
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "3100")))
