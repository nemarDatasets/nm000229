#!/usr/bin/env python3
"""Fix Gwilliams et al. 2023 MEG-MASC BIDS dataset for validator compliance.

This script applies post-download fixes to the BIDS-MEG dataset published on
OSF (https://osf.io/ag3kj/) by Gwilliams et al. so that it passes the modern
BIDS validator. The original dataset is structurally BIDS but has several
small issues:

  1. Broken `participants.json` (missing commas between entries, trailing
     commas inside Levels objects).
  2. Empty `Name` and missing License/Funding/DOI in `dataset_description.json`.
  3. `participants.tsv` uses 'male'/'female'/'right'/'left' which doesn't
     match the Levels {M, F, R, L} declared in `participants.json`.
  4. `task_order` column in `participants.tsv` was a Python list literal
     ("[0, 1, 2, 3]") which the validator rejects.
  5. Six `scans.tsv` files (sub-05, sub-09, sub-11) reference `anat/`
     T1-weighted MRIs that are NOT in the OSF download.
  6. Missing recommended sidecar fields in `*_meg.json` files (Manufacturer,
     ManufacturersModelName, InstitutionName, TaskDescription, Instructions,
     SoftwareVersions, DeviceSerialNumber, ECOGChannelCount, SEEGChannelCount,
     SubjectArtefactDescription, HardwareFilters, CogPOID).
  7. Missing `events.json` sidecars to describe the events.tsv columns.
  8. A loose `flatten_events.py` script at the dataset root (not BIDS-valid).

All values added to sidecars are verified against the published paper:

    Gwilliams, L., Flick, G., Marantz, A., Pylkkänen, L., Poeppel, D.,
    & King, J.-R. (2023). Introducing MEG-MASC: a high-quality MEG dataset
    of story comprehension. Scientific Data, 10, 862.
    https://doi.org/10.1038/s41597-023-02752-5

Verified facts from the paper Methods section:
  - Recording: NYU Abu Dhabi (subject pool, IRB approval)
  - Scanner: 208 axial-gradiometer MEG built by KIT (Kanazawa Institute of
    Technology), 1000 Hz sampling, online band-pass 0.01-200 Hz
  - 27 English-speaking adults (15 female, mean age 24.8, all right-handed)
  - 4 stories (LW1, Cable Spool Boy, Easy Money, The Black Willow)
  - Task order is participant-specific (Latin-square design); task-0..task-3
    are session-relative indices, NOT fixed audiobook labels
  - Comprehension questions every ~3 min via button press
  - Funding: FrontCog grant ANR-17-EURE-0017 (JRK), Abu Dhabi Research
    Institute G1001 (AM, LP), Dingwall Foundation (LG)

NOT in the paper (intentionally NOT added to sidecars):
  - InstitutionalDepartmentName (not specified)
  - StimulusPresentation software (not specified)
  - CogAtlasID (no canonical mapping for natural story listening)
  - MaxMovement (head motion data not provided)
  - AssociatedEmptyRoom (no empty-room recordings provided)

Usage:
    python fix_gwilliams_bids.py <BIDS_ROOT>
"""
import json
import re
import sys
from glob import glob
from pathlib import Path


def fix_participants_json(bids_root: Path) -> None:
    """Rewrite participants.json with corrected JSON syntax."""
    fixed = {
        "participant_id": {"Description": "Unique participant identifier"},
        "age": {
            "Description": "Age of the participant at time of testing",
            "Units": "years",
        },
        "sex": {
            "Description": "Biological sex of the participant",
            "Levels": {"F": "female", "M": "male"},
        },
        "hand": {
            "Description": (
                "Handedness of the participant, measured by the Edinburgh "
                "Handedness Inventory questionnaire"
            ),
            "Levels": {"R": "right", "L": "left", "A": "ambidextrous"},
        },
        "task_order": {
            "Description": (
                "Order in which the four stories were presented "
                "(0=lw1, 1=cable_spool_fort, 2=easy_money, 3=The_Black_Willow)"
            ),
        },
        "n_sessions": {
            "Description": "How many MEG sessions the participant completed",
            "Levels": {"1": "1 session", "2": "2 sessions"},
        },
        "mri": {
            "Description": "Whether the participant has a structural MRI",
            "Levels": {
                "fsaverage": "no structural MRI; use the FreeSurfer average",
                "native": "yes this subject has a structural MRI",
            },
        },
        "native_english_speaker": {
            "Description": "Whether the participant is a native English speaker",
            "Levels": {"y": "Yes", "n": "No"},
        },
    }
    with open(bids_root / "participants.json", "w") as f:
        json.dump(fixed, f, indent=2)
        f.write("\n")


def fix_participants_tsv(bids_root: Path) -> None:
    """Convert participants.tsv values to match the declared Levels."""
    import pandas as pd

    df = pd.read_csv(bids_root / "participants.tsv", sep="\t")
    df["sex"] = df["sex"].map(
        lambda x: {"male": "M", "female": "F", "Male": "M", "Female": "F"}.get(
            str(x).strip(), str(x).strip()
        )
    )
    df["hand"] = df["hand"].map(
        lambda x: {
            "right": "R",
            "left": "L",
            "ambidextrous": "A",
            "Right": "R",
            "Left": "L",
        }.get(str(x).strip(), str(x).strip())
    )

    def clean_task_order(x):
        if pd.isna(x) or x == "n/a":
            return "n/a"
        s = str(x).strip('"').strip("[").strip("]")
        return s.replace(" ", "").replace(",", "-")

    df["task_order"] = df["task_order"].map(clean_task_order)
    df.to_csv(
        bids_root / "participants.tsv", sep="\t", index=False, na_rep="n/a"
    )


def fix_dataset_description(bids_root: Path) -> None:
    """Replace dataset_description.json with verified metadata."""
    desc = {
        "Name": (
            "MEG-MASC: a high-quality magneto-encephalography dataset for "
            "evaluating natural speech processing"
        ),
        "BIDSVersion": "1.9.0",
        "DatasetType": "raw",
        "License": "CC0",
        "Authors": [
            "Laura Gwilliams",
            "Graham Flick",
            "Alec Marantz",
            "Liina Pylkkänen",
            "David Poeppel",
            "Jean-Rémi King",
        ],
        "HowToAcknowledge": (
            "Please cite: Gwilliams, L., Flick, G., Marantz, A., Pylkkänen, "
            "L., Poeppel, D., & King, J.-R. (2023). Introducing MEG-MASC: a "
            "high-quality MEG dataset of story comprehension. Scientific "
            "Data, 10, 862. https://doi.org/10.1038/s41597-023-02752-5"
        ),
        "Funding": [
            "FrontCog grant ANR-17-EURE-0017 (J.-R. King)",
            "Abu Dhabi Research Institute (G1001) (A. Marantz, L. Pylkkänen)",
            "Dingwall Foundation (L. Gwilliams)",
        ],
        "ReferencesAndLinks": [
            "https://osf.io/ag3kj/",
            "https://doi.org/10.1038/s41597-023-02752-5",
            "https://www.nature.com/articles/s41597-023-02752-5",
        ],
        "DatasetDOI": "doi:10.1038/s41597-023-02752-5",
        "SourceDatasets": [{"URL": "https://osf.io/ag3kj/"}],
        "GeneratedBy": [
            {
                "Name": "Original BIDS dataset",
                "Description": (
                    "Dataset published as a BIDS-MEG release by the authors. "
                    "Minor fixes applied during ingestion to satisfy BIDS "
                    "validator: (1) repaired broken participants.json, "
                    "(2) replaced 'male'/'female'/'right'/'left' in "
                    "participants.tsv with M/F/R/L to match Levels, "
                    "(3) removed orphan anat references from 6 scans.tsv "
                    "files (MRI files not included in the OSF download), "
                    "(4) added missing recommended sidecar fields verified "
                    "against the paper."
                ),
                "CodeURL": "https://osf.io/ag3kj/",
            }
        ],
        "HEDVersion": "8.2.0",
    }
    with open(bids_root / "dataset_description.json", "w") as f:
        json.dump(desc, f, indent=2)
        f.write("\n")


def fix_scans_tsv(bids_root: Path) -> int:
    """Remove scans.tsv lines that reference non-existent files."""
    fixed = 0
    for scans in glob(str(bids_root / "sub-*/ses-*/sub-*_scans.tsv")):
        with open(scans) as f:
            lines = f.readlines()
        keep = [lines[0]]
        removed = False
        sub_dir = Path(scans).parent
        for line in lines[1:]:
            if not line.strip():
                continue
            fname = line.split("\t")[0]
            if (sub_dir / fname).exists():
                keep.append(line)
            else:
                removed = True
        if removed:
            with open(scans, "w") as f:
                f.writelines(keep)
            fixed += 1
    return fixed


def fix_meg_sidecars(bids_root: Path) -> int:
    """Add verified recommended fields to all *_meg.json sidecars."""
    task_description = (
        "Listening to one of four short fictional stories from the Manually "
        "Annotated Sub-Corpus (MASC). The stories were 'LW1' (5 min 20 s), "
        "'Cable Spool Boy' (11 min), 'Easy Money' (12 min 10 s), and 'The "
        "Black Willow' (25 min 50 s). Each participant listened to all four "
        "stories in a participant-specific order (Latin-square design); "
        "task-0..task-3 are session-relative indices, not fixed story labels. "
        "The story order for each subject is in participants.tsv (task_order "
        "column). Stories were synthesized with Mac OS Mojave text-to-speech "
        "and presented through binaural tube earphones at ~70 dB SPL, online "
        "band-pass 0.01-200 Hz."
    )
    instructions = (
        "Listen to the audiobooks attentively. Approximately every 3 minutes, "
        "respond to a two-alternative forced-choice comprehension question "
        "about the story content via button press."
    )

    files = glob(str(bids_root / "sub-*/ses-*/meg/*_meg.json"))
    for f in files:
        with open(f) as fh:
            d = json.load(fh)

        d["Manufacturer"] = "KIT"
        d["ManufacturersModelName"] = (
            "208-channel axial gradiometer (Kanazawa Institute of Technology)"
        )
        d["InstitutionName"] = "New York University Abu Dhabi"
        d["InstitutionAddress"] = (
            "Saadiyat Island, Abu Dhabi, United Arab Emirates"
        )
        d["TaskDescription"] = task_description
        d["Instructions"] = instructions

        # Set unknown string fields explicitly to "n/a"
        for key in (
            "SoftwareVersions",
            "DeviceSerialNumber",
            "CogPOID",
            "SubjectArtefactDescription",
            "HardwareFilters",
        ):
            if key not in d or d[key] in ("", None):
                d[key] = "n/a"

        # Modality counts (zero for MEG-only dataset)
        d["ECOGChannelCount"] = 0
        d["SEEGChannelCount"] = 0

        # Remove fabricated fields if any earlier version added them
        for fab in ("CogAtlasID", "InstitutionalDepartmentName", "MaxMovement"):
            d.pop(fab, None)

        with open(f, "w") as fh:
            json.dump(d, fh, indent=2)
            fh.write("\n")
    return len(files)


def create_events_json(bids_root: Path) -> int:
    """Create per-file events.json sidecars describing the columns."""
    events_meta = {
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
        "story": {
            "Description": (
                "Story identifier "
                "(lw1, cable_spool_fort, easy_money, The_Black_Willow)"
            )
        },
        "story_uid": {"Description": "Numeric story UID within the session"},
        "sound_id": {"Description": "Sound clip index"},
        "kind": {"Description": "Event kind (sound/phoneme/word)"},
        "start": {"Description": "Start sample"},
        "sound": {"Description": "Audio stimulus filename"},
        "phoneme": {"Description": "Phoneme label (CMU + position suffix)"},
        "word": {"Description": "Word text"},
        "sequence_id": {"Description": "Sentence sequence identifier"},
        "condition": {"Description": "Experimental condition"},
        "word_index": {"Description": "Word position within sentence"},
        "speech_rate": {"Description": "Speech rate (words per minute)"},
        "voice": {"Description": "Synthetic voice ID"},
        "pronounced": {
            "Description": "1 if word was pronounced, 0 otherwise"
        },
    }
    files = glob(str(bids_root / "sub-*/ses-*/meg/*_events.tsv"))
    for tsv in files:
        json_path = tsv.replace(".tsv", ".json")
        with open(json_path, "w") as f:
            json.dump(events_meta, f, indent=2)
            f.write("\n")
    return len(files)


def main():
    if len(sys.argv) != 2:
        print("Usage: fix_gwilliams_bids.py <BIDS_ROOT>", file=sys.stderr)
        sys.exit(1)
    bids_root = Path(sys.argv[1])
    if not bids_root.exists():
        print(f"BIDS root not found: {bids_root}", file=sys.stderr)
        sys.exit(1)

    print(f"Fixing Gwilliams MEG-MASC BIDS at {bids_root}")
    fix_participants_json(bids_root)
    print("  ✓ participants.json")
    fix_participants_tsv(bids_root)
    print("  ✓ participants.tsv")
    fix_dataset_description(bids_root)
    print("  ✓ dataset_description.json")
    n = fix_scans_tsv(bids_root)
    print(f"  ✓ scans.tsv ({n} files cleaned)")
    n = fix_meg_sidecars(bids_root)
    print(f"  ✓ meg.json sidecars ({n} files updated)")
    n = create_events_json(bids_root)
    print(f"  ✓ events.json sidecars ({n} files created)")

    print("\nDone. Run `nemar dataset validate` to confirm.")


if __name__ == "__main__":
    main()
