#!/usr/bin/env python3
"""One-shot: clip all cached entries to cognition_budget token tiers."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from auto_author import (build_entry, clip_field, clip_field_dual,
                         field_tokens, parse_fras, r_quota_for_c,
                         s_quota_for_c, s_runes_for_c)

cache_dir = sys.argv[1]
fixed = 0
total = 0
for fn in os.listdir(cache_dir):
    if not fn.endswith(".txt"):
        continue
    fp = os.path.join(cache_dir, fn)
    with open(fp, encoding="utf-8") as f:
        entry = f.read().strip()
    if not entry:
        continue
    total += 1
    try:
        name, tag, fields = parse_fras(entry)
    except Exception:
        print("unparseable:", fn)
        continue
    c = int(tag[2])
    changed = False
    if fields.get("F") and field_tokens(fields["F"]) > 160:
        fields["F"] = clip_field(fields["F"], 160)
        changed = True
    if fields.get("R") and field_tokens(fields["R"]) > r_quota_for_c(c):
        fields["R"] = clip_field(fields["R"], r_quota_for_c(c))
        changed = True
    if fields.get("A") and field_tokens(fields["A"]) > 400:
        fields["A"] = clip_field(fields["A"], 400)
        changed = True
    if fields.get("S"):
        fields["S"] = clip_field_dual(
            fields["S"], s_quota_for_c(c), s_runes_for_c(c))
        changed = True
    if changed:
        with open(fp, "w", encoding="utf-8") as f:
            f.write(build_entry(name, tag, fields))
        fixed += 1
print(f"clipped {fixed}/{total} entries in {cache_dir}")
