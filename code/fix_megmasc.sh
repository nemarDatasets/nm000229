#!/bin/bash
# fix_megmasc.sh — Pre-upload BIDS validator fixes for MEG-MASC
# (Gwilliams et al. 2023, OSF ag3kj+h2tzn+u5327+dr4wy)
#
# Fixes:
#   1. Delete stray .DS_Store (macOS leftovers from OSF)
#   2. Rename/ignore sub-XX_ses-Y-T1_defaced.nii.gz (non-BIDS name)
#   3. Fix /participants.json (JSON_INVALID)
#   4. Regenerate *_scans.tsv for subjects with mismatched file lists
#   5. Add .bidsignore for anything else non-standard
#
# Run idempotently. Archives self into code/ on completion.
#
# Usage: bash fix_megmasc.sh [path-to-dataset]
set -euo pipefail

DS="${1:-$HOME/mne_data/MEG-MASC}"
[[ -d "$DS" ]] || { echo "Not found: $DS"; exit 1; }
cd "$DS"

echo "=== Fix MEG-MASC at $DS ==="

# -------------------------------------------------------------------
# 1. Delete .DS_Store files
# -------------------------------------------------------------------
echo "--- 1. Removing .DS_Store files ---"
count=$(find . -name ".DS_Store" 2>/dev/null | wc -l)
find . -name ".DS_Store" -delete 2>/dev/null || true
echo "  Removed $count .DS_Store"

# -------------------------------------------------------------------
# 2. The defaced T1 filenames have a non-BIDS dash:
#    sub-09_ses-1-T1_defaced.nii.gz instead of sub-09_ses-1_T1w.nii.gz
#    Move them under sourcedata/ to exclude from validation but keep
#    them for provenance (they're anatomical references).
# -------------------------------------------------------------------
echo "--- 2. Moving defaced T1s to sourcedata/ ---"
mkdir -p sourcedata
count=0
for f in $(find . -path "./sourcedata" -prune -o -name "*_defaced.nii.gz" -print 2>/dev/null); do
  rel="${f#./}"
  dest="sourcedata/$rel"
  mkdir -p "$(dirname "$dest")"
  mv -n "$f" "$dest"
  count=$((count + 1))
done
echo "  Moved $count defaced T1s to sourcedata/"

# Remove now-empty anat/ dirs
find . -path "./sourcedata" -prune -o -type d -name "anat" -empty -print -delete 2>/dev/null || true

# -------------------------------------------------------------------
# 2b. Normalize participants.tsv sex / hand to BIDS-compliant values
#     BIDS requires sex in {M, F, O, n/a}; hand in {R, L, A, n/a}
# -------------------------------------------------------------------
echo "--- 2b. Normalizing participants.tsv ---"
if [[ -f participants.tsv ]]; then
  awk -F'\t' -v OFS='\t' '
    NR == 1 {
      for (i=1; i<=NF; i++) {
        if ($i == "sex")  sex_col = i
        if ($i == "hand") hand_col = i
      }
      print; next
    }
    {
      if (sex_col) {
        v = tolower($sex_col)
        if      (v == "male")   $sex_col = "M"
        else if (v == "female") $sex_col = "F"
        else if (v == "other")  $sex_col = "O"
        else if (v == ""  || v == "n/a") $sex_col = "n/a"
      }
      if (hand_col) {
        v = tolower($hand_col)
        if      (v == "right" || v == "r") $hand_col = "R"
        else if (v == "left"  || v == "l") $hand_col = "L"
        else if (v == "ambidextrous" || v == "both") $hand_col = "A"
        else if (v == ""  || v == "n/a") $hand_col = "n/a"
      }
      print
    }
  ' participants.tsv > participants.tsv.tmp
  mv participants.tsv.tmp participants.tsv
  echo "  participants.tsv normalized (sex: male→M, female→F; hand: right→R, left→L)"
fi

# -------------------------------------------------------------------
# 3. Fix /participants.json (JSON_INVALID)
# -------------------------------------------------------------------
echo "--- 3. Validating /participants.json ---"
if [[ -f participants.json ]]; then
  if ! python3 -c "import json; json.load(open('participants.json'))" 2>/dev/null; then
    echo "  participants.json is invalid — attempting fix"
    # Common case: trailing comma, unquoted strings, etc.
    # Replace with a minimal valid sidecar based on participants.tsv headers
    if [[ -f participants.tsv ]]; then
      headers=$(head -1 participants.tsv)
      python3 <<PYEOF
import json, re
with open('participants.tsv') as f:
    headers = f.readline().strip().split('\t')
sidecar = {
    "participant_id": {
        "Description": "Unique participant identifier"
    }
}
for h in headers:
    if h == "participant_id": continue
    sidecar[h] = {"Description": f"{h} (see paper for details)"}
with open('participants.json', 'w') as f:
    json.dump(sidecar, f, indent=2)
    f.write('\n')
print("  Regenerated participants.json")
PYEOF
    fi
  else
    echo "  participants.json OK"
  fi
fi

# -------------------------------------------------------------------
# 4. Regenerate *_scans.tsv with files actually present
# -------------------------------------------------------------------
echo "--- 4. Regenerating *_scans.tsv per session ---"
count=0
for scans in $(find . -name "*_scans.tsv"); do
  dir=$(dirname "$scans")
  sub_ses=$(basename "$scans" _scans.tsv)
  # sub_ses = sub-09_ses-1 (usual BIDS)
  # List all data files belonging to this session
  actual_files=$(find "$dir" -type f \( -name "*.fif" -o -name "*.con" -o -name "*.set" -o -name "*.vhdr" -o -name "*.edf" -o -name "*.nii.gz" \) 2>/dev/null | sed "s|^$dir/||" | sort)
  # Rewrite scans.tsv with just filename column (BIDS minimum)
  {
    echo -e "filename\tacq_time"
    echo "$actual_files" | while read -r f; do
      [[ -n "$f" ]] && echo -e "${f}\tn/a"
    done
  } > "${scans}.tmp"
  mv "${scans}.tmp" "$scans"
  count=$((count + 1))
done
echo "  Regenerated $count scans.tsv files"

# -------------------------------------------------------------------
# 5. Validate all JSONs + create .bidsignore if needed
# -------------------------------------------------------------------
echo "--- 5. Validating all JSONs ---"
bad_json=()
for j in $(find . -path "./sourcedata" -prune -o -name "*.json" -print); do
  if ! python3 -c "import json; json.load(open('$j'))" 2>/dev/null; then
    bad_json+=("$j")
    echo "  INVALID: $j"
  fi
done
echo "  ${#bad_json[@]} bad JSONs (manual review needed if > 0)"

# -------------------------------------------------------------------
# 6. Write .bidsignore for sourcedata/ and anything else
# -------------------------------------------------------------------
echo "--- 6. Writing .bidsignore ---"
cat > .bidsignore <<'EOF'
# Defaced T1 anatomicals with non-BIDS naming moved here for provenance
sourcedata/
EOF
echo "  .bidsignore written"

# -------------------------------------------------------------------
# 7. Archive script into code/
# -------------------------------------------------------------------
echo "--- 7. Archiving fix script into code/ ---"
mkdir -p code
SELF="$(readlink -f "$0" 2>/dev/null || realpath "$0")"
[[ -f "$SELF" ]] && cp -f "$SELF" code/fix_megmasc.sh
chmod +x code/fix_megmasc.sh 2>/dev/null || true
echo "  archived → code/fix_megmasc.sh"

echo ""
echo "=== Done ==="
echo "Re-run validator with:"
echo "  nemar dataset validate --prune --ignore-warnings $DS"
