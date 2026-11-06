# 🎯 Aeneas Align API

A small self-hosted API that gives **word-by-word timestamps** for an audio file and its transcript.
It uses [Aeneas](https://github.com/readbeyond/aeneas) forced alignment — **not AI**: no GPU, no guessing,
no hallucination. The same audio + text always gives exactly the same result.

Full documentation (Word): **`docs/Aeneas_Align_API_Documentation.docx`** · GitHub workflow: **`docs/GITHUB.md`**

```
audio link (or upload) + transcript  ──►  POST /align  ──►  {"audio_duration": 63.36, "fragments": [{"begin":0.48,"end":1.16,"text":"Saudi"}, …]}
```

## Install on a new VM (Ubuntu 20.04 / 22.04 / 24.04) — one command

Log in as your normal user (not root) and paste this **one line** into the VM's terminal:

```bash
sudo apt-get update -y && sudo apt-get install -y git openssh-client && mkdir -p ~/.ssh && chmod 700 ~/.ssh && { [ -f ~/.ssh/aeneas_deploy ] || ssh-keygen -q -t ed25519 -N "" -f ~/.ssh/aeneas_deploy -C aeneas-vm-deploy; } && { grep -q "Host github-aeneas" ~/.ssh/config 2>/dev/null || printf 'Host github-aeneas\n  HostName github.com\n  User git\n  IdentityFile ~/.ssh/aeneas_deploy\n  IdentitiesOnly yes\n' >> ~/.ssh/config; } && chmod 600 ~/.ssh/config && ssh-keyscan -t ed25519 github.com >> ~/.ssh/known_hosts 2>/dev/null && echo && echo "=== ADD THIS KEY ON GITHUB: aeneas-align-api > Settings > Deploy keys > Add deploy key (leave write access OFF) ===" && cat ~/.ssh/aeneas_deploy.pub && echo "=== Waiting until the key is added on GitHub (checks every 5 s)... ===" && until ssh -o BatchMode=yes -T git@github-aeneas 2>&1 | grep -q successfully; do sleep 5; done && echo "=== Key OK, installing ===" && { [ -d ~/aeneas-align-api/.git ] || git clone -q git@github-aeneas:khandanish7863/aeneas-align-api.git ~/aeneas-align-api; } && cd ~/aeneas-align-api && sudo bash install.sh
```

1. It prints a key (`ssh-ed25519 …`) and waits.
2. On GitHub: this repo → **Settings → Deploy keys → Add deploy key** → title e.g. `Aeneas VM`,
   paste the key, leave **Allow write access** off → **Add key**.
3. The command notices the key by itself within 5 seconds, downloads the code and installs everything
   (about 3–5 minutes).
4. At the end it prints your API address and **token**.
5. Allow the port (default **3100**) in your cloud firewall
   (GCP: **VPC network → Firewall → Create rule**, TCP 3100). Done.

**Coming from the old hand-made setup (`~/aeneas_api.py`)?** Same command. The installer stops the old
`aeneas-api` service and **re-uses your old token**, so everything that already calls the API keeps working.

**Already installed? Don't install again — just update:** `aeneas-update`

## Use the API

### Health check (no token)
```bash
curl http://YOUR_VM_IP:3100/health
# {"status":"ok","service":"aeneas-alignment-api","version":"1.0.0"}
```

### Align — audio link + text (JSON)
```bash
curl -X POST http://YOUR_VM_IP:3100/align \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "audio_url": "https://drive.google.com/uc?export=download&id=YOUR_FILE_ID",
    "text": "Picture two major Asian powers choosing to strengthen their military bonds even further.",
    "language": "eng"
  }'
```

### Align — upload the audio file instead of a link
```bash
curl -X POST http://YOUR_VM_IP:3100/align \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F "audio=@my_audio.mp3" \
  -F "text=Picture two major Asian powers choosing to strengthen their military bonds even further." \
  -F "language=eng"
```

### Request fields

| Field       | Required | Default | Meaning |
|-------------|----------|---------|---------|
| `audio_url` | yes*     |         | Direct download link to the audio. Any format ffmpeg reads (wav, mp3, m4a, flac, ogg, even mp4 video). Google Drive links work, also big files (file must be shared "Anyone with the link"). |
| `audio`     | yes*     |         | The audio file itself (form upload) — use instead of `audio_url`. |
| `text`      | yes      |         | The exact words spoken in the audio. |
| `language`  | no       | `eng`   | Language code: `eng`, `hin`, `urd`, `ara`, `ben`, `tam`, … (see below). |
| `clean`     | no       | `true`  | `true` = trims silence/pauses out of word boundaries and repairs zero-length words. `false` = raw Aeneas timings (like the old API). |

\* give either `audio_url` or `audio`.

### Response
```json
{
  "status": "success",
  "audio_duration": 63.36,
  "word_count": 11,
  "language": "eng",
  "processing_seconds": 0.65,
  "fragments": [
    {"begin": 0.48, "end": 1.16, "text": "Picture"},
    {"begin": 1.16, "end": 1.56, "text": "two"},
    {"begin": 1.56, "end": 2.2,  "text": "major"}
  ]
}
```
Times are in seconds. There is exactly one fragment per word of `text`, in the same order.
Punctuation stays attached to its word (`"further."`).

### Errors
| HTTP | When |
|------|------|
| 400  | missing `audio_url`/`text`, link could not be downloaded, file is not audio |
| 401  | missing or wrong token |
| 413  | audio larger than `MAX_AUDIO_MB` |
| 500  | alignment failed (message says why) |

All errors look like `{"status": "error", "message": "..."}`.

### Python example
```python
import requests
r = requests.post("http://YOUR_VM_IP:3100/align",
                  headers={"Authorization": "Bearer YOUR_TOKEN"},
                  json={"audio_url": "https://…/audio.wav", "text": "…", "language": "hin"},
                  timeout=1800)
for w in r.json()["fragments"]:
    print(w["begin"], w["end"], w["text"])
```

## Languages
`eng` English · `hin` Hindi · `urd` Urdu · `ara` Arabic · `ben` Bengali · `tam` Tamil · `tel` Telugu ·
`mar` Marathi · `guj` Gujarati · `kan` Kannada · `mal` Malayalam · `pan` Punjabi · `fra` French ·
`deu` German · `spa` Spanish · `ita` Italian · `por` Portuguese · `rus` Russian · `tur` Turkish ·
`nld` Dutch · `pol` Polish · `ind` Indonesian · `vie` Vietnamese · `fas` Persian · `zho` Chinese ·
`jpn` Japanese · `kor` Korean · `tha` Thai

## Important: the text must match the audio
Aeneas trusts the text completely. If words are missing or extra, you still get a result, but the timings
around those words are wrong — there is no error. Fix the transcript first, then align.

## Settings (`.env` on the VM — never in git)
```
API_TOKEN=…            # secret token; several allowed, separated by commas
PORT=3100
# WORKERS=2            # requests processed at the same time (default = CPUs, min 2)
MAX_AUDIO_MB=1024
ALIGN_TIMEOUT=1800     # seconds
DOWNLOAD_TIMEOUT=300   # seconds
```
After changing it: `sudo systemctl restart aeneas-align-api`

**Change the token:** edit `API_TOKEN` in `~/aeneas-align-api/.env`, then restart.

## Update
```bash
aeneas-update            # download latest from GitHub, show changes, reinstall, restart
aeneas-update --force    # reinstall even if nothing changed
```

## Useful commands
```bash
sudo systemctl status aeneas-align-api      # running?
sudo systemctl restart aeneas-align-api     # restart
sudo journalctl -u aeneas-align-api -f      # live logs (every request is logged)
cat ~/aeneas-align-api/.env                 # see your token / port
curl -s -4 ifconfig.me; echo                # the VM's public IP
```

## VM size
Runs on CPU only. 1 vCPU / 1 GB RAM works; 2 vCPU / 2 GB is comfortable. A 1-minute audio takes about 1–3 seconds.

## Where things are
```
app/main.py        the API: /health, /align, token check, downloads (incl. Google Drive), uploads
app/align.py       Aeneas alignment + timing clean-up (same logic as the Mummy Video Editor)
install.sh         one-command installer (safe to run again)
update.sh          aeneas-update: git pull + install.sh
.env.example       settings template (the real .env is created by install.sh)
docs/              Word documentation, GitHub workflow
```

## Development (run locally)
```bash
uv venv -p 3.11 .venv && uv pip install -r requirements.txt 'setuptools<60' wheel \
  && uv pip install --no-build-isolation aeneas==1.7.3.0
API_TOKEN=test .venv/bin/python -m app.main          # http://localhost:3100
```
Needs `ffmpeg`, `espeak` and `libespeak-dev` installed (`sudo apt-get install ffmpeg espeak libespeak-dev`).
