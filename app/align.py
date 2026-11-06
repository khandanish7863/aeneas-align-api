"""Word-level forced alignment with Aeneas (deterministic: same audio + text -> same timings).

Reused from the Mummy Video Editor (backend/app/services/align.py), which runs this in production:
  * punctuation-only tokens ("-", "।", "...") are glued to the previous word, never timed on their own
  * punctuation is stripped for the speech synthesiser but kept in the returned text
  * silence at the start / end of the file and long pauses are cut out of word boundaries
  * zero-length words and words that swallowed a long pause are repaired
  * no length limit on long audio or long text
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

PUNCT_ONLY = re.compile(r"^[\s\.\,\!\?\-–—।॥:;\"'()\[\]…]+$")
PUNCT_STRIP = re.compile(r"[\.\,\!\?।॥:;\"'()\[\]…]")

# Word timing repair limits (seconds). Can be overridden per request.
MIN_WORD = 0.08
MAX_WORD = 1.4


class AlignError(RuntimeError):
    pass


def tokenize(text: str) -> list:
    """Split text into words; punctuation-only pieces are attached to the previous word."""
    tokens = []
    for raw in text.split():
        if PUNCT_ONLY.match(raw):
            if tokens:
                tokens[-1] += raw
            continue
        tokens.append(raw)
    return tokens


def audio_duration(path: Path):
    """Audio length in seconds (ffprobe), or None if the file is not readable audio."""
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True,
    )
    try:
        return round(float(proc.stdout.strip()), 3)
    except ValueError:
        return None


def to_wav(src: Path, dst: Path) -> None:
    """Convert any audio/video file to 16 kHz mono WAV (what Aeneas works on internally)."""
    proc = subprocess.run(
        ["ffmpeg", "-nostdin", "-y", "-v", "error", "-i", str(src), "-vn", "-ac", "1", "-ar", "16000",
         "-c:a", "pcm_s16le", str(dst)],
        capture_output=True, text=True,
    )
    if proc.returncode != 0 or not dst.exists():
        raise AlignError("Could not read the audio file: " + (proc.stderr or "")[-500:])


def align(audio: Path, text: str, work_dir: Path, language: str = "eng", clean: bool = True,
          timeout: int = 1800) -> list:
    """Return [{"begin", "end", "text"}, ...] — one entry per word of `text`, in order."""
    tokens = tokenize(text)
    if not tokens:
        raise AlignError("The text has no words")

    wav = work_dir / "audio16k.wav"
    to_wav(audio, wav)

    words_txt = work_dir / "words.txt"
    out_json = work_dir / "out.json"
    synth = [PUNCT_STRIP.sub("", t) or t for t in tokens]
    words_txt.write_text("\n".join(synth), encoding="utf-8")

    config = [
        f"task_language={language}",
        "is_text_type=plain",
        "os_task_file_format=json",
    ]
    if clean:
        # Silence before the first / after the last word is not part of a word.
        config += ["is_audio_file_detect_head_max=10",
                   "is_audio_file_detect_tail_max=10"]
        # Do not let words stretch over pauses / background noise.
        config += ["task_adjust_boundary_nonspeech_min=0.4",
                   "task_adjust_boundary_nonspeech_string=REMOVE"]

    env = dict(os.environ, PYTHONIOENCODING="UTF-8")
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "aeneas.tools.execute_task", str(wav), str(words_txt),
             "|".join(config), str(out_json),
             "-r=task_max_audio_length=0|task_max_text_length=0|dtw_margin=60"],
            capture_output=True, text=True, env=env, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        raise AlignError(f"Alignment took longer than {timeout} s and was stopped")
    if proc.returncode != 0 or not out_json.exists():
        raise AlignError("Aeneas failed: " + (proc.stderr or proc.stdout or "")[-1500:])

    frags = json.loads(out_json.read_text(encoding="utf-8")).get("fragments", [])
    # Keep only the text fragments (one per word, same order as words.txt).
    frags = [f for f in frags if f.get("lines")]
    if len(frags) != len(tokens):
        raise AlignError(f"Aeneas returned {len(frags)} timings for {len(tokens)} words")

    words = [{"begin": float(f["begin"]), "end": float(f["end"]), "text": tok}
             for tok, f in zip(tokens, frags)]
    if clean:
        words = fix_timings(words)
    for w in words:
        w["begin"] = round(w["begin"], 3)
        w["end"] = round(w["end"], 3)
    return words


def fix_timings(words: list, min_word: float = MIN_WORD, max_word: float = MAX_WORD) -> list:
    """Repair zero-length words and words that swallowed a long pause."""
    for w in words:
        if w["end"] - w["begin"] > max_word:
            w["end"] = w["begin"] + max_word
    for i, w in enumerate(words):
        if w["end"] - w["begin"] < min_word:
            prev = words[i - 1] if i > 0 else None
            if prev and prev["end"] - prev["begin"] > 2 * min_word and abs(prev["end"] - w["begin"]) < 0.05:
                mid = max(prev["begin"] + min_word, w["begin"] - min_word)
                prev["end"] = mid
                w["begin"] = mid
            w["end"] = max(w["end"], w["begin"] + min_word)
    # Never overlap the next word.
    for i in range(len(words) - 1):
        if words[i]["end"] > words[i + 1]["begin"]:
            words[i]["end"] = max(words[i]["begin"], words[i + 1]["begin"])
    return words
