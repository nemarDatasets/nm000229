#!/usr/bin/env python3
"""
Flatten Gwilliams MEG-MASC events.tsv trial_type dict column into proper BIDS columns.

Original schema:
  onset  duration  trial_type (dict literal)  value  sample

New schema:
  onset  duration  trial_type  value  sample  story  story_uid  sound_id
  kind  start  sound  phoneme  word  sequence_id  condition  word_index
  speech_rate  voice  pronounced

trial_type is set to the 'kind' value (sound/phoneme/word), which is a proper
BIDS short label. All other dict keys are promoted to separate columns.
"""
import ast
import csv
import json
from pathlib import Path
import sys

ROOT = Path("/tmp/gwilliams2022")

# Union of all keys observed across kinds
FLAT_COLS = [
    "onset", "duration", "trial_type", "value", "sample",
    "story", "story_uid", "sound_id", "kind", "start", "sound",
    "phoneme", "word", "sequence_id", "condition", "word_index",
    "speech_rate", "voice", "pronounced",
]

EVENTS_JSON = {
    "onset": {"Description": "Event onset in seconds", "Units": "s"},
    "duration": {"Description": "Event duration in seconds", "Units": "s"},
    "trial_type": {
        "Description": "Type of event (short BIDS label)",
        "Levels": {
            "sound": "Start of a sound stimulus",
            "phoneme": "Onset of a phoneme",
            "word": "Onset of a word",
        },
    },
    "value": {"Description": "Numerical event code"},
    "sample": {"Description": "Sample index of event onset (0-based)"},
    "story": {"Description": "Story identifier (lw1, cable_spool_fort, easy_money, The_Black_Willow)"},
    "story_uid": {"Description": "Numeric story UID within the session"},
    "sound_id": {"Description": "Index of the 3-minute audio chunk within the story"},
    "kind": {
        "Description": "Type of linguistic unit",
        "Levels": {
            "sound": "Start of sound file",
            "phoneme": "Phoneme onset",
            "word": "Word onset",
        },
    },
    "start": {"Description": "Time within the sound file at which the event begins", "Units": "s"},
    "sound": {"Description": "Relative path to the stimulus audio file"},
    "phoneme": {"Description": "Phoneme label with position suffix (_B beginning, _I internal, _E end)"},
    "word": {"Description": "Orthographic form of the word"},
    "sequence_id": {"Description": "Sentence/sequence index within the story"},
    "condition": {
        "Description": "Linguistic context",
        "Levels": {
            "sentence": "Word appeared inside a story sentence",
            "word_list": "Word appeared inside a random word list",
        },
    },
    "word_index": {"Description": "Position of the word within its sentence/sequence (0-based)"},
    "speech_rate": {"Description": "Speech rate of the synthesized audio", "Units": "words_per_minute"},
    "voice": {
        "Description": "Mac OS Mojave TTS voice used to synthesize audio",
        "Levels": {"Ava": "Ava", "Samantha": "Samantha", "Allison": "Allison"},
    },
    "pronounced": {
        "Description": "Whether the word/phoneme was pronounced (1) or silent/non-word (0)",
    },
}


def flatten_row(row):
    """Flatten one row dict (with trial_type as Python dict literal) to new schema."""
    raw = row["trial_type"]
    try:
        meta = ast.literal_eval(raw) if raw and raw != "n/a" else {}
    except (ValueError, SyntaxError):
        meta = {}

    new_row = {c: "n/a" for c in FLAT_COLS}
    new_row["onset"] = row.get("onset", "n/a")
    new_row["duration"] = row.get("duration", "n/a")
    new_row["value"] = row.get("value", "n/a")
    new_row["sample"] = row.get("sample", "n/a")

    kind = meta.get("kind", "n/a")
    new_row["trial_type"] = kind  # short label per BIDS
    for k in ("story", "story_uid", "sound_id", "kind", "start", "sound",
              "phoneme", "word", "sequence_id", "condition", "word_index",
              "speech_rate", "voice", "pronounced"):
        if k in meta:
            v = meta[k]
            if isinstance(v, float):
                # Preserve precision but avoid trailing .0 noise
                v = f"{v:g}"
            new_row[k] = str(v)
    return new_row


def process_file(events_path: Path, dry_run: bool = False):
    with events_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter="\t")
        rows = [flatten_row(r) for r in reader]

    if dry_run:
        print(f"[dry] {events_path.relative_to(ROOT)}: {len(rows)} rows")
        if rows:
            print(f"  first: {rows[0]}")
        return

    tmp = events_path.with_suffix(".tsv.tmp")
    with tmp.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f, fieldnames=FLAT_COLS, delimiter="\t", extrasaction="ignore"
        )
        writer.writeheader()
        writer.writerows(rows)
    tmp.replace(events_path)

    # Write events.json sidecar alongside
    json_path = events_path.with_suffix(".json")
    with json_path.open("w", encoding="utf-8") as f:
        json.dump(EVENTS_JSON, f, indent=2)

    print(f"[write] {events_path.relative_to(ROOT)}: {len(rows)} rows")


def main():
    dry_run = "--dry" in sys.argv
    count = 0
    for events in sorted(ROOT.rglob("sub-*_task-*_events.tsv")):
        process_file(events, dry_run=dry_run)
        count += 1
    print(f"\nProcessed {count} events files")


if __name__ == "__main__":
    main()
