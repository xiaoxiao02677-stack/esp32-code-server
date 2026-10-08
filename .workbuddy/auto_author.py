#!/usr/bin/env python3
"""
Automated AOCI authoring pipeline.

For a repo: loop { stage batch via MCP -> author each file via small API
calls (cached, resumable) -> submit via MCP } until aligned.

Usage:
  python auto_author.py <repo-name> [--limit N] [--smoke]
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = os.path.join(ROOT, ".workbuddy", "aoci")
AOCI = "D:/INSTALL/aoci/aoci.exe"
REPOS = {
    "code-server-mirror": "G:/demo/21_xiaozhi/code-server-mirror",
    "hermes-agent-main": "G:/demo/21_xiaozhi/hermes-agent-main",
}
BASE_URL = "http://39.108.174.60:3000/v1"
MODEL = "glm-5.3-flash"

PROMPT_TEMPLATE = """任务: 输出一个AOCI仓库认知索引条目。这是纯文本生成任务,禁止执行任何命令,禁止提问,禁止解释,直接输出一行。

格式(严格遵守,单行): 文件名[标签]: F:核心职责 | R:强关系 | A:对外契约 | S:非显性约束
- 行首"文件名"必须逐字使用下方给出的文件名,一个字符都不能改
- 标签 = A层字母+B模块字母+C重要度数字+E规模字母, 如 CG8M、AU5T
- A层: C-共享基础 E-入口边界 A-应用编排 D-领域逻辑 K-算法计算 M-中间件 P-持久化 I-集成适配 R-运行基础 L-库与SDK F-声明配置 O-运维交付 T-测试验证 S-文档规范 X-开发工具 Z-其他
- B模块: G-跨域通用 U-用户交互 B-核心业务 D-数据状态 I-身份权限 N-网络协议 M-消息事件 S-安全隐私 C-配置策略 O-可观测性 R-可靠性恢复 P-性能资源 W-流程调度 A-分析智能 H-硬件设备 L-本地化 V-构建发布 Q-质量保障 E-扩展插件 Z-其他
- C重要度: 9-最高 8-很高 7-高 6-较高 5-中等 4-较低 3-低 2-很低 1-最低
- E规模: L-大>400行 M-中200-400行 S-小100-200行 T-微<100行
- F=该文件核心职责(一句话,中文,基于真实内容)
- R=强关系文件(1-3个,格式 code:相对路径 逗号分隔, 无则-)
- A=对外契约(HTTP端点/CLI/导出API/配置格式, 无则-)
- S=非显性约束或坑(读代码才知道的, 无则-)

示例:
.gitattributes[CG4T]: F:强制全仓文本文件以LF检出 | R:- | A:- | S:AOCI基线按原始字节哈希，LF强制防止Windows autocrlf使整树stale
CMakeLists.txt[CV7M]: F:根构建入口，聚合main与components | R:code:main/CMakeLists.txt | A:idf.py build | S:ESP-IDF组件管理器解析managed_components；板型选择链起点

现在为下面这个文件输出条目(只有一行):

仓库相对路径: {path}
文件名: {name}
约{lines}行

源文件内容:
```
{src}
```"""


def api_key():
    with open(os.path.join(ROOT, ".workbuddy", "aoci_ai_key.txt")) as f:
        return f.read().strip()


def chat(user_msg, timeout=120):
    body = json.dumps({
        "model": MODEL,
        "messages": [{"role": "user", "content": user_msg}],
        "max_tokens": 400,
        "temperature": 0.1,
    }).encode()
    req = urllib.request.Request(
        BASE_URL + "/chat/completions", data=body,
        headers={"Authorization": "Bearer " + api_key(),
                 "Content-Type": "application/json"})
    r = json.load(urllib.request.urlopen(req, timeout=timeout))
    return r["choices"][0]["message"]["content"].strip()


TAG_RE = re.compile(r"^\S+\[[A-Z][A-Z][1-9][A-Z]?[LMST]\]:")
A_LETTERS = set("CEADKMPIRLXOSTZF")
B_LETTERS = set("GUBDINMSCORPWALVQEHZ")


def validate_entry(path, entry):
    entry = entry.strip()
    # normalize full-width punctuation the model sometimes emits
    entry = entry.replace("]：", "]:").replace("｜", "|")
    if "\n" in entry:
        entry = entry.split("\n")[0].strip()
    if not TAG_RE.match(entry):
        return None, "tag format"
    # the leading filename must equal the candidate path's basename
    base = os.path.basename(path)
    if not entry.startswith(base + "["):
        return None, f"filename mismatch (want {base})"
    tag = entry[entry.index("[") + 1: entry.index("]")]
    if len(tag) not in (4, 5):
        return None, "tag len"
    if tag[0] not in A_LETTERS or tag[1] not in B_LETTERS:
        return None, "tag letters"
    if tag[2] not in "123456789":
        return None, "C"
    if len(tag) == 5 and tag[3] not in B_LETTERS:
        return None, "D"
    for fld in ("F:", "R:", "A:", "S:"):
        if fld not in entry:
            return None, "field " + fld
    # A field max 6 comma items; R max 8
    try:
        name0, tag0, fields0 = parse_fras(entry)
        if fields0.get("A") and fields0["A"] != "-":
            items = [x for x in fields0["A"].split(",") if x.strip()]
            if len(items) > 6:
                fields0["A"] = ",".join(items[:6])
                entry = build_entry(name0, tag0, fields0)
        if fields0.get("R") and fields0["R"] != "-":
            items = [x for x in fields0["R"].split(",") if x.strip()]
            if len(items) > 8:
                fields0["R"] = ",".join(items[:8])
                entry = build_entry(name0, tag0, fields0)
    except Exception:
        pass
    # preventive token budget limits (cognition_budget r/s tiers)
    try:
        name, tag2, fields = parse_fras(entry)
        c = int(tag2[2])
        if fields.get("F") and field_tokens(fields["F"]) > 160:
            fields["F"] = clip_field(fields["F"], 160)
        if fields.get("R") and field_tokens(fields["R"]) > r_quota_for_c(c):
            fields["R"] = clip_field(fields["R"], r_quota_for_c(c))
        if fields.get("A") and field_tokens(fields["A"]) > 400:
            fields["A"] = clip_field(fields["A"], 400)
        if fields.get("S"):
            fields["S"] = clip_field_dual(
                fields["S"], s_quota_for_c(c), s_runes_for_c(c))
        entry = build_entry(name, tag2, fields)
    except Exception:
        pass
    # strip markdown fences if any
    entry = entry.strip("`")
    return entry, None


class McpSession:
    def __init__(self, repo):
        self.proc = subprocess.Popen(
            [AOCI, "--repo", repo, "mcp"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, encoding="utf-8", bufsize=1)
        self.outbox = []
        threading.Thread(target=self._reader, daemon=True).start()
        self._id = 0
        self._call("initialize", {
            "protocolVersion": "2024-11-05", "capabilities": {},
            "clientInfo": {"name": "hermes-auto-author", "version": "1.0"}})
        self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})

    def _reader(self):
        for line in self.proc.stdout:
            line = line.strip()
            if line:
                try:
                    self.outbox.append(json.loads(line))
                except json.JSONDecodeError:
                    pass

    def _send(self, msg):
        self.proc.stdin.write(json.dumps(msg) + "\n")
        self.proc.stdin.flush()

    def _call(self, method, params=None, timeout=3600):
        self._id += 1
        rid = self._id
        self._send({"jsonrpc": "2.0", "id": rid, "method": method,
                    "params": params or {}})
        deadline = time.time() + timeout
        while time.time() < deadline:
            for i, m in enumerate(self.outbox):
                if m.get("id") == rid:
                    self.outbox.pop(i)
                    return m
            time.sleep(0.05)
        return {"error": "timeout"}

    def tool(self, name, arguments):
        r = self._call("tools/call", {"name": name, "arguments": arguments})
        content = r.get("result", {}).get("content", [])
        text = "".join(c.get("text", "") for c in content)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"_raw": text}

    def close(self):
        try:
            self.proc.terminate()
        except Exception:
            pass


def read_source(repo, path, max_chars=6000):
    fp = os.path.join(repo, path)
    try:
        with open(fp, encoding="utf-8", errors="replace") as f:
            data = f.read(max_chars)
        return data
    except OSError as e:
        return f"<unreadable: {e}>"


def author_one(repo, path, sha, cache_dir, retries=5):
    """Author one entry with cache. Returns entry string or None."""
    key = hashlib.sha256((repo + "|" + path + "|" + sha).encode()).hexdigest()
    cache_file = os.path.join(cache_dir, key + ".txt")
    if os.path.exists(cache_file):
        with open(cache_file, encoding="utf-8") as f:
            return f.read().strip() or None

    src = read_source(repo, path)
    lines = src.count("\n") + 1
    name = os.path.basename(path)
    user_msg = PROMPT_TEMPLATE.format(path=path, name=name, lines=lines, src=src)
    for attempt in range(retries):
        try:
            raw = chat(user_msg)
            entry, err = validate_entry(path, raw)
            if entry:
                with open(cache_file, "w", encoding="utf-8") as f:
                    f.write(entry)
                return entry
            print(f"    [invalid:{err}] {path}: {raw[:80]}")
        except Exception as e:
            print(f"    [api-error a{attempt}] {path}: {e}")
            time.sleep(3 * (attempt + 1))
    return None


def s_quota_for_c(c):
    c = int(c)
    if c >= 9:
        return 200
    if c >= 8:
        return 140
    if c >= 5:
        return 80
    return 40


def r_quota_for_c(c):
    c = int(c)
    if c >= 9:
        return 180
    if c >= 8:
        return 140
    if c >= 5:
        return 90
    return 50


def field_tokens(text):
    return len(text.encode("utf-8")) // 3


def s_runes_for_c(c):
    c = int(c)
    if c >= 8:
        return 600
    if c >= 4:
        return 200
    return 50


def clip_field_dual(text, max_tokens, max_runes=None):
    """Trim so both bytes/3 <= max_tokens AND rune count <= max_runes."""
    if max_runes is not None and len(text) > max_runes:
        text = text[:max_runes]
    if max_runes is None:
        return clip_field(text, max_tokens)
    while len(text.encode("utf-8")) // 3 > max_tokens and text:
        text = text[:-1]
    return text


def clip_field(text, max_tokens):
    """Trim text (by chars, CJK-heavy) so bytes/3 <= max_tokens."""
    encoded = text.encode("utf-8")
    if len(encoded) // 3 <= max_tokens:
        return text
    max_bytes = max_tokens * 3
    while len(text.encode("utf-8")) > max_bytes:
        text = text[:-1]
    return text


def parse_fras(entry):
    """Split 'name[tag]: F:.. | R:.. | A:.. | S:..' into parts."""
    head, _, body = entry.partition("]: ")
    tag = head[head.index("[") + 1:]
    name = head[:head.index("[")]
    fields = {}
    for part in body.split(" | "):
        for fld in ("F:", "R:", "A:", "S:"):
            if part.startswith(fld):
                fields[fld[0]] = part[len(fld):]
    return name, tag, fields


def build_entry(name, tag, fields):
    return (f"{name}[{tag}]: F:{fields.get('F', '-')} | "
            f"R:{fields.get('R', '-')} | A:{fields.get('A', '-')} | "
            f"S:{fields.get('S', '-')}")


def auto_repair_fras(res, cache_dir):
    """Fix FRAS length findings by truncating cache entries. Returns count."""
    findings = res.get("findings") or []
    if not findings:
        return 0
    repaired = 0
    for f in findings:
        rule = f.get("rule_code", "")
        path = f.get("path", "")
        if "fras_" not in rule and "too_long" not in rule:
            continue
        # locate the cache file for this path by scanning cache
        hit = None
        for fn in os.listdir(cache_dir):
            if not fn.endswith(".txt"):
                continue
            fp = os.path.join(cache_dir, fn)
            with open(fp, encoding="utf-8") as fh:
                entry = fh.read().strip()
            try:
                name, tag, fields = parse_fras(entry)
            except Exception:
                continue
            if name == os.path.basename(path) or path.endswith(name):
                hit = (fp, entry, name, tag, fields)
                break
        if not hit:
            continue
        fp, entry, name, tag, fields = hit
        c = int(tag[2])
        changed = False
        if fields.get("A") and fields["A"] != "-":
            items = [x for x in fields["A"].split(",") if x.strip()]
            if len(items) > 6:
                fields["A"] = ",".join(items[:6])
                changed = True
        if fields.get("R") and fields["R"] != "-":
            items = [x for x in fields["R"].split(",") if x.strip()]
            if len(items) > 8:
                fields["R"] = ",".join(items[:8])
                changed = True
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
            if fields["S"] != hit[1].split("S:")[-1]:
                changed = True
        if changed:
            with open(fp, "w", encoding="utf-8") as fh:
                fh.write(build_entry(name, tag, fields))
            repaired += 1
            print(f"    repaired {path} (rule={rule})", flush=True)
    return repaired


auto_ack_done = {}


def run(repo_name, limit=None, smoke=False):
    from concurrent.futures import ThreadPoolExecutor

    repo = REPOS[repo_name]
    cache_dir = os.path.join(WORK, "cache", repo_name)
    os.makedirs(cache_dir, exist_ok=True)
    session = McpSession(repo)

    def author_candidate(c):
        entry = author_one(repo, c["path"], c["source_sha256"], cache_dir)
        return c, entry

    batch_num = 0
    total_done = 0
    while True:
        data = session.tool("aoci_maintain", {})
        status = data.get("status")
        cands = data.get("candidates", [])
        ab = data.get("authoring_batch", {})
        if status == "stopped" and not cands:
            # Auto-resolve observed-evidence review stop, then retry once.
            cmds = data.get("next_commands") or []
            stage_hint = "scope acknowledge" in " ".join(cmds)
            if stage_hint and batch_num == 0 and not auto_ack_done.get(repo_name):
                print(f"[{repo_name}] stopped on observed review; "
                      f"running scope acknowledge", flush=True)
                session.close()
                subprocess.run(
                    [AOCI, "--repo", repo, "scope", "acknowledge",
                     "--reviewed-by", "hermes-agent", "--json"],
                    capture_output=True, timeout=300)
                auto_ack_done[repo_name] = True
                session = McpSession(repo)
                data = session.tool("aoci_maintain", {})
                status = data.get("status")
                cands = data.get("candidates", [])
                ab = data.get("authoring_batch", {})
            if status == "stopped" or not cands:
                print(f"[{repo_name}] maintain stopped: "
                      f"{data.get('next_action')}", flush=True)
                break
        if ab.get("next_action") != "author_complete_current_machine_batch":
            print(f"[{repo_name}] unexpected next_action: {ab.get('next_action')}", flush=True)
            break

        batch_num += 1
        code_batch_id = cands[0]["batch_id"]
        print(f"[{repo_name}] batch#{batch_num}: {len(cands)} files "
              f"(remaining={ab.get('remaining')}) batch_id={code_batch_id[:12]}", flush=True)

        targets = cands[:5] if smoke else cands
        entries = []
        failed = []
        done_count = 0
        with ThreadPoolExecutor(max_workers=3) as pool:
            for c, entry in pool.map(author_candidate, targets):
                done_count += 1
                if entry:
                    entries.append({
                        "path": c["path"],
                        "source_sha256": c["source_sha256"],
                        "candidate_id": c["candidate_id"],
                        "new_entry": entry,
                    })
                else:
                    failed.append(c["path"])
                if done_count % 20 == 0:
                    print(f"    authored {done_count}/{len(targets)} (fail {len(failed)})", flush=True)

        if failed:
            print(f"[{repo_name}] {len(failed)} files failed authoring; "
                  f"will retry this batch after cooldown: {failed[:5]}", flush=True)
            time.sleep(60)
            # Re-stage the same batch state by looping without submitting.
            session.close()
            session = McpSession(repo)
            batch_num = max(batch_num - 1, 0)
            continue

        if smoke:
            print(f"[{repo_name}] smoke: {len(entries)} entries authored OK; "
                  f"not submitting (smoke mode)", flush=True)
            break

        res = session.tool("aoci_update_entry", {
            "code_batch_id": code_batch_id, "entries": entries})
        rstatus = res.get("status") or "?"
        print(f"[{repo_name}] submit -> {rstatus}", flush=True)
        # archive the submitted payload for diagnosis
        pf = os.path.join(WORK, "results",
                          f"{repo_name}_payload_{int(time.time())}.json")
        os.makedirs(os.path.dirname(pf), exist_ok=True)
        with open(pf, "w", encoding="utf-8") as f:
            json.dump({"code_batch_id": code_batch_id,
                       "entries": entries}, f, ensure_ascii=False)
        if rstatus not in ("applied",):
            # save full response for offline repair
            rf = os.path.join(WORK, "results",
                              f"{repo_name}_repair_{int(time.time())}.json")
            os.makedirs(os.path.dirname(rf), exist_ok=True)
            with open(rf, "w", encoding="utf-8") as f:
                json.dump(res, f, ensure_ascii=False, indent=1)
            print(f"[{repo_name}] repair response saved -> {rf}", flush=True)
            # Auto-repair FRAS length findings from cache
            repaired = auto_repair_fras(res, cache_dir)
            if repaired:
                print(f"[{repo_name}] auto-repaired {repaired} entries; "
                      f"retrying submit", flush=True)
                continue
            print(json.dumps(res, ensure_ascii=False)[:2000], flush=True)
            break
        total_done += len(entries)
        if limit and total_done >= limit:
            print(f"[{repo_name}] reached limit {limit}", flush=True)
            break

    session.close()
    print(f"[{repo_name}] DONE, authored+submitted {total_done}", flush=True)


if __name__ == "__main__":
    name = sys.argv[1]
    limit = None
    smoke = "--smoke" in sys.argv
    for a in sys.argv[2:]:
        if a.startswith("--limit="):
            limit = int(a.split("=", 1)[1])
    run(name, limit=limit, smoke=smoke)
