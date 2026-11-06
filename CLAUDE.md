# Aeneas Align API — notes for Claude

- Small Flask API (gunicorn, systemd service `aeneas-align-api`, port from `.env`, default 3100) that returns
  word-level timestamps with Aeneas forced alignment. Read `README.md` first.
- Runs on the owner's Google Cloud VM (Ubuntu 22.04). Installed with `sudo bash install.sh`, updated with `aeneas-update`.
- **Keep the API contract stable**: `POST /align` with `audio_url` (or `audio` upload), `text`, `language`, `clean`;
  response `status, audio_duration, word_count, language, processing_seconds, fragments[{begin,end,text}]`
  with exactly one fragment per word, in order. Other systems call this API.
- Alignment logic in `app/align.py` mirrors the Mummy Video Editor (`backend/app/services/align.py`); keep them consistent.
- Aeneas install needs Python 3.11, numpy first, `setuptools<60` and `--no-build-isolation`; check that
  `aeneas.cdtw/cmfcc/cew` import (the fast C extensions).
- `install.sh` must stay safe to run again and must never overwrite `.env`.
- Never put the token or `.env` in the repo.
- Before pushing: `bash -n install.sh update.sh`, run the API locally and align a test file (English + Hindi).
- Deploy: commit to `main`, push, bump `VERSION`; the owner runs `aeneas-update`.
- Commit messages: one clear line per change; give the owner plain-language instructions (he is not a developer).
