import json, re, os

REPOS = {
    "BIG": r"G:/demo/21_xiaozhi/code/big_secreen/yuhe-esp32",
    "SMALL": r"G:/demo/21_xiaozhi/code/small_secreen/yuhe-esp32",
}
SRC_EXT = (".cc", ".cpp", ".cxx", ".h", ".hpp", ".hh")

for label, REPO in REPOS.items():
    base = json.load(open(os.path.join(REPO, ".aoci", "baseline.json")))
    files = base["files"]
    entries = open(os.path.join(REPO, "aoci.code.txt"), encoding="utf-8").read()
    entry_basenames = set()
    for m in re.finditer(r'^([^\s\[]+)\[', entries, re.M):
        entry_basenames.add(m.group(1))

    index_files = [p for p, m in files.items() if m.get("role") == "index"]
    # first-party source only (in main/ or components/), exclude generated/asset .c
    candidates = []
    for p in index_files:
        base_name = p.split("/")[-1]
        if not base_name.endswith(SRC_EXT):
            continue
        if base_name not in entry_basenames:
            candidates.append(p)
    print(f"[{label}] index source files w/o entry: {len(candidates)}")
    for p in sorted(candidates):
        print("   -", p)
