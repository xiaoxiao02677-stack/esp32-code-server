#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""校验生成的 changelog SQL：语句类型、列数、ID 唯一性、音色对照。"""
import io
import re

PATH = ("G:/demo/21_xiaozhi/code-server-mirror/manager-api/src/main/resources/"
        "db/changelog/202610071100.sql")


def split_statements(src):
    stmts = []
    buf = []
    in_q = False
    i = 0
    while i < len(src):
        ch = src[i]
        if ch == "'":
            if in_q and i + 1 < len(src) and src[i + 1] == "'":
                buf.append("''")
                i += 2
                continue
            in_q = not in_q
            buf.append(ch)
        elif ch == ";" and not in_q:
            stmts.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
        i += 1
    if "".join(buf).strip():
        stmts.append("".join(buf))
    # strip comment-only lines from each statement, keep real SQL
    cleaned = []
    for s in stmts:
        lines = [ln for ln in s.splitlines() if not ln.strip().startswith("--")]
        real = "\n".join(lines).strip()
        if real:
            cleaned.append(real)
    return cleaned


def split_values(body):
    depth = 0
    cur = ""
    vals = []
    in_q = False
    i = 0
    while i < len(body):
        ch = body[i]
        if ch == "'":
            if in_q and i + 1 < len(body) and body[i + 1] == "'":
                cur += "''"
                i += 2
                continue
            in_q = not in_q
            cur += ch
        elif not in_q and ch == "(":
            depth += 1
            if depth == 1:
                cur = ""
            else:
                cur += ch
        elif not in_q and ch == ")":
            depth -= 1
            if depth == 0:
                vals.append(cur)
                cur = ""
            else:
                cur += ch
        elif not in_q and ch == "," and depth == 1:
            vals.append(cur)
            cur = ""
        elif depth >= 1:
            cur += ch
        i += 1
    return [v.strip() for v in vals]


def main():
    src = io.open(PATH, encoding="utf-8").read()
    stmts = split_statements(src)
    updates = [s for s in stmts if s.upper().startswith("UPDATE")]
    deletes = [s for s in stmts if s.upper().startswith("DELETE")]
    inserts = [s for s in stmts if s.upper().startswith("INSERT")]
    print(f"statements={len(stmts)} updates={len(updates)} "
          f"deletes={len(deletes)} inserts={len(inserts)}")
    assert len(updates) == 5, "expect 5 UPDATE (1 provider + 4 model config)"
    assert len(deletes) == 4, "expect 4 DELETE"

    seen_ids = set()
    per_model = {}
    for s in inserts:
        m = re.match(r"INSERT INTO `ai_tts_voice` \([^)]*\) VALUES \((.*)\)$",
                     s, re.S)
        assert m, s[:100]
        vals = split_values("(" + m.group(1) + ")")
        assert len(vals) == 14, f"column count {len(vals)}: {s[:80]}"
        row_id, model_id, name, code, languages = vals[0], vals[1], vals[2], vals[3], vals[4]
        # unescape
        def unq(v):
            return v[1:-1].replace("''", "'") if v.startswith("'") else v
        row_id, model_id = unq(row_id), unq(model_id)
        assert row_id.startswith(model_id + "_V"), (row_id, model_id)
        assert row_id not in seen_ids, f"duplicate {row_id}"
        seen_ids.add(row_id)
        per_model.setdefault(model_id, []).append((unq(code), unq(languages)))

    for model_id, voices in per_model.items():
        print(f"  {model_id}: {len(voices)} voices")

    # 对照 Python/前端音色表
    flash = per_model["TTS_QwenTTS_Flash"]
    assert len(flash) == 48
    assert flash[0][0] == "Cherry" and flash[-1][0] == "Kiki"
    instruct = per_model["TTS_QwenTTS_Instruct"]
    assert len(instruct) == 24
    assert [v[0] for v in instruct] == [v[0] for v in flash[:24]]
    assert per_model["TTS_QwenAudio_Flash"][0][0] == "longanhuan_v3.6"
    assert len(per_model["TTS_QwenAudio_Plus"]) == 14
    # 检查语种非空
    for model_id, voices in per_model.items():
        for code, lang in voices:
            assert lang in ("普通话", "国际音色", "方言"), (model_id, code, lang)

    # UPDATE 幂等条件检查
    for s in updates:
        if s.startswith("UPDATE `ai_model_provider`"):
            assert "SYSTEM_TTS_qwen_tts" in s
            assert "NOT LIKE '%base_url%'" in s
            assert '"key":"base_url"' in s
        else:
            assert "JSON_EXTRACT(`config_json`, '$.base_url') IS NULL" in s
            assert "compatible-mode/v1" in s

    print("VALIDATION OK")


if __name__ == "__main__":
    main()
