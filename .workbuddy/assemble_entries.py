#!/usr/bin/env python3
"""
Validate and assemble authored entries into an aoci_update_entry payload.

Input: a stage JSON (from aoci_loop --stage) + a lines file with entries:
  <repo-relative-path>\t<single-line entry: name[AB(C)DE]: F:... | R:... | A:... | S:...>
Output: submit-ready JSON {code_batch_id, entries:[...]}
"""
import json
import re
import sys

TAG_RE = re.compile(r"^\S+\[[A-Z][A-Z][1-9][A-Z]?[LMST]\]:")

# valid A layer letters (code) and B module letters
A_LETTERS = set("CEADKMPIRLXOSTZ")
B_LETTERS = set("GUBDINMSCORPWALVQEHZ")
E_LETTERS = set("LMST")


def validate_line(line):
    """Return (ok, error). Line: path<TAB>entry"""
    if "\t" not in line:
        return False, "missing TAB separator"
    path, entry = line.split("\t", 1)
    entry = entry.strip()
    m = TAG_RE.match(entry)
    if not m:
        return False, "entry does not start with name[AB(C)(D)E]: format"
    tag = entry[entry.index("[") + 1 : entry.index("]")]
    if len(tag) not in (4, 5):
        return False, f"tag length {len(tag)} not 4 or 5"
    a, b, c = tag[0], tag[1], tag[2]
    if a not in A_LETTERS:
        return False, f"A layer '{a}' invalid"
    if b not in B_LETTERS:
        return False, f"B module '{b}' invalid"
    if c not in "123456789":
        return False, f"C importance '{c}' invalid"
    if len(tag) == 5 and tag[3] not in B_LETTERS:
        return False, f"D module '{tag[3]}' invalid"
    # FRAS fields
    for f in ("F:", "R:", "A:", "S:"):
        if f not in entry:
            return False, f"missing {f} field"
    return True, ""


def main():
    stage_path, lines_path, out_path = sys.argv[1], sys.argv[2], sys.argv[3]
    with open(stage_path, encoding="utf-8") as f:
        stage = json.load(f)
    candidates = {c["path"]: c for c in stage["candidates"]}
    code_batch_id = stage["candidates"][0]["batch_id"]

    entries = []
    errors = []
    seen = set()
    with open(lines_path, encoding="utf-8") as f:
        for ln, raw in enumerate(f, 1):
            line = raw.rstrip("\n")
            if not line.strip():
                continue
            ok, err = validate_line(line)
            if not ok:
                errors.append(f"line {ln}: {err}")
                continue
            path, entry = line.split("\t", 1)
            if path not in candidates:
                errors.append(f"line {ln}: path {path} not in current batch")
                continue
            if path in seen:
                errors.append(f"line {ln}: duplicate path {path}")
                continue
            seen.add(path)
            c = candidates[path]
            entries.append({
                "path": c["path"],
                "source_sha256": c["source_sha256"],
                "candidate_id": c["candidate_id"],
                "new_entry": entry.strip(),
            })

    missing = [p for p in candidates if p not in seen]
    if missing:
        errors.append(f"missing entries for {len(missing)} paths: {missing[:8]}")
    if errors:
        print("VALIDATION FAILED:")
        for e in errors[:30]:
            print(" ", e)
        sys.exit(1)
    payload = {"code_batch_id": code_batch_id, "entries": entries}
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    print(f"OK: {len(entries)} entries -> {out_path}")


if __name__ == "__main__":
    main()
