#!/usr/bin/env python3
"""Insert Memory_mem_hybrid model config on server."""
import subprocess

SQL = (
    "INSERT INTO ai_model_config (id, model_type, model_name, config_json, is_default, "
    "is_enabled, sort, create_date) VALUES ('Memory_mem_hybrid', 'Memory', "
    "'混合记忆（短期总结+长期事实+LLM沉淀）', "
    "'{\"type\": \"mem_hybrid\", \"llm\": \"LLM_DeepSeek\", \"db_dir\": \"data/memory/\", "
    "\"auto_extract\": true, \"distill_facts\": true, \"distill_max_facts\": 5, "
    "\"default_trust\": 0.5, \"min_trust_threshold\": 0.3, \"temporal_decay_half_life\": 0}', "
    "0, 1, 6, now()) "
    "ON DUPLICATE KEY UPDATE config_json=VALUES(config_json), model_name=VALUES(model_name)"
)

r = subprocess.run(
    ["mysql", "-uroot", "-p123456", "xiaozhi_esp32_server", "-N", "-e", SQL],
    capture_output=True, text=True, timeout=60)
print("insert rc:", r.returncode, r.stderr.strip()[:100] if r.returncode else "OK")

r = subprocess.run(
    ["mysql", "-uroot", "-p123456", "xiaozhi_esp32_server", "-N", "-B", "-e",
     "SELECT id, model_name, is_enabled FROM ai_model_config WHERE model_type='Memory'"],
    capture_output=True, text=True, timeout=60)
print(r.stdout)
