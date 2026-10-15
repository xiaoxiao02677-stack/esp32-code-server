#!/bin/bash
# 话题源推送接口探测（在目标机执行，参数=项目根目录）
cd "$1" || exit 1
KEY=$(.venv/bin/python -c "import yaml;print(yaml.safe_load(open('config.yaml'))['server'].get('auth_key',''))")
BASE=http://127.0.0.1:8003
echo "--- 1) 双空 content (期望 400) ---"
curl -s -o /dev/null -w '%{http_code}\n' -X POST "$BASE/api/push/schedule" -H "Authorization: Bearer $KEY" -H 'Content-Type: application/json' -d '{"device_ids":["d1"],"content":{}}'
echo "--- 2) audio_url+topic_sources 双填 (期望 400) ---"
curl -s -o /dev/null -w '%{http_code}\n' -X POST "$BASE/api/push/schedule" -H "Authorization: Bearer $KEY" -H 'Content-Type: application/json' -d '{"device_ids":["d1"],"content":{"audio_url":"http://x/a.mp3","topic_sources":["memory"]}}'
echo "--- 3) 非法 topic_sources (期望 400) ---"
curl -s -o /dev/null -w '%{http_code}\n' -X POST "$BASE/api/push/schedule" -H "Authorization: Bearer $KEY" -H 'Content-Type: application/json' -d '{"device_ids":["d1"],"content":{"topic_sources":["bogus"]}}'
echo "--- 4) 无鉴权 (期望 401) ---"
curl -s -o /dev/null -w '%{http_code}\n' -X POST "$BASE/api/push/schedule" -H 'Content-Type: application/json' -d '{"device_ids":["d1"],"content":{"topic_sources":["memory"]}}'
echo "--- 5) 合法 topic_sources (期望 200 + push_id) ---"
curl -s -X POST "$BASE/api/push/schedule" -H "Authorization: Bearer $KEY" -H 'Content-Type: application/json' -d '{"device_ids":["d1"],"content":{"topic_sources":["memory","weather"],"location":"杭州"},"schedule":{"type":"immediate"}}'
echo
echo "--- 6) 列出任务 (期望 200) ---"
curl -s "$BASE/api/push/tasks" -H "Authorization: Bearer $KEY"
echo
