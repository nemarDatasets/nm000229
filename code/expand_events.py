"""nm000229 events.tsv: expand the OSF dict-string layout (trial_type = "{'story': ..., 'kind': ...}") into the
column layout of code/flatten_events.py (used for sub-01..11 in the initial upload). Used for sub-12..27 in version 1.0.2.
Pure Python, byte level: onset/duration/value/sample are copied as the original strings.

Output layout:
  * no UTF-8 BOM; CRLF line terminator on every line, including the last;
  * columns: onset duration trial_type value sample + the dict keys in KEYS order;
  * trial_type = the dict's 'kind' ('sound' / 'phoneme' / 'word');
  * dict values: whole-number floats as integers ('0.0' -> '0'), other floats as Python repr (exact), strings
    verbatim, absent key -> 'n/a'.
expand(raw, g=True) formats floats as flatten_events.py does (f"{v:g}", 6 significant digits); with g=True the output
is byte-identical to the 84 sub-01..11 files of 1.0.1. Version 1.0.2 wrote sub-12..27 with g=False (exact values).
"""
import ast, math, re

BOM = b"\xef\xbb\xbf"
KEYS = ["story", "story_uid", "sound_id", "kind", "start", "sound", "phoneme", "word", "sequence_id", "condition",
        "word_index", "speech_rate", "voice", "pronounced"]
HEAD = ["onset", "duration", "trial_type", "value", "sample"]
NAN = re.compile(r"(?<=: )nan(?=[,}])")


def parse_dict(s):
    d = ast.literal_eval(NAN.sub("None", s))
    assert isinstance(d, dict), s
    return d


def fmt(v, g=False):
    """g=True reproduces v1.0.1's code/flatten_events.py (f"{v:g}", 6 significant digits) for floats."""
    if v is None:
        return "n/a"
    if isinstance(v, float):
        if math.isnan(v):
            return "n/a"
        if g:
            return f"{v:g}"
        return str(int(v)) if v.is_integer() else repr(v)
    if isinstance(v, bool):
        raise TypeError(v)
    return str(v)


def read_dict_layout(raw):
    """-> list of (onset, duration, dict, value, sample) strings/dict from an OSF-layout file (bytes)."""
    if raw.startswith(BOM):
        raw = raw[3:]
    text = raw.decode("utf-8")
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines = lines[:-1]
    lines = [l[:-1] if l.endswith("\r") else l for l in lines]
    hdr = lines[0].split("\t")
    assert hdr == HEAD, hdr
    rows = []
    for l in lines[1:]:
        p = l.split("\t")
        assert len(p) == 5, (len(p), l[:200])
        rows.append((p[0], p[1], parse_dict(p[2]), p[3], p[4]))
    return rows


def expand(raw, g=False):
    """g=False: exact values (repr; integral floats as int). g=True: v1.0.1 flatten_events.py float formatting."""
    rows = read_dict_layout(raw)
    extra = sorted({k for r in rows for k in r[2]} - set(KEYS))
    assert not extra, extra
    out = ["\t".join(HEAD + KEYS)]
    for on, du, d, va, sa in rows:
        out.append("\t".join([on, du, fmt(d["kind"]), va, sa] + [fmt(d.get(k), g) for k in KEYS]))
    return ("\r\n".join(out) + "\r\n").encode("utf-8"), len(rows)
