#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
公共测试工具：登录态获取 + 注入 + 浏览器操作记录
供 10 个 Agent Worker 复用
"""
import os
import sys
import json
import time
import csv
import datetime
import requests
import ddddocr
from gmssl import sm2

BASE_URL = "https://sandyun.top:8001/yuhe"
FRONT_URL = "https://sandyun.top:8001/admincc/#/"
REPORTS_DIR = "G:/demo/21_xiaozhi/code/reports"
ARTIFACTS_DIR = "G:/demo/21_xiaozhi/code/artifacts"
LOGS_DIR = "G:/demo/21_xiaozhi/code/logs"

os.makedirs(REPORTS_DIR, exist_ok=True)
os.makedirs(ARTIFACTS_DIR, exist_ok=True)
os.makedirs(LOGS_DIR, exist_ok=True)


def get_sm2_public_key():
    resp = requests.get(f"{BASE_URL}/user/pub-config", verify=False, timeout=20)
    return resp.json()["data"]["sm2PublicKey"]


def sm2_encrypt_c1c3c2(plaintext: str, pub_key_full: str) -> str:
    """SM2 C1C3C2 加密，与后端 BouncyCastle 兼容"""
    pub_no04 = pub_key_full[2:] if pub_key_full.startswith("04") else pub_key_full
    crypt = sm2.CryptSM2(public_key=pub_no04, private_key="0" * 64, mode=True)
    return "04" + crypt.encrypt(plaintext.encode("utf-8")).hex()


def ocr_captcha(image_bytes: bytes) -> str:
    ocr = ddddocr.DdddOcr(show_ad=False)
    return ocr.classification(image_bytes)


def get_login_token(username="demo", password="P@ssword123", max_retry=5):
    """直调登录 API 获取 token（OCR 验证码）"""
    pub_key = get_sm2_public_key()
    for attempt in range(max_retry):
        try:
            captcha_uuid = f"auto-{int(time.time()*1000)}-{attempt}"
            captcha_resp = requests.get(
                f"{BASE_URL}/user/captcha?uuid={captcha_uuid}", verify=False, timeout=20
            )
            captcha_text = ocr_captcha(captcha_resp.content)
            encrypted = sm2_encrypt_c1c3c2(captcha_text + password, pub_key)
            resp = requests.post(
                f"{BASE_URL}/user/login",
                json={"username": username, "password": encrypted, "captchaId": captcha_uuid},
                verify=False, timeout=20,
            )
            data = resp.json()
            if data.get("code") == 0 and data.get("data", {}).get("token"):
                return data["data"]
            print(f"  登录尝试 {attempt+1} 失败: {data.get('msg')}")
        except Exception as e:
            print(f"  登录尝试 {attempt+1} 异常: {e}")
        time.sleep(1)
    raise Exception("登录失败：无法获取 token")


def make_token_artifact(token_data: dict, worker_id: str = "main"):
    """将 token 保存为 worker 可注入的文件"""
    path = os.path.join(ARTIFACTS_DIR, f"token_{worker_id}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(token_data, f, ensure_ascii=False)
    return path


def load_token_data(worker_id: str = "main"):
    path = os.path.join(ARTIFACTS_DIR, f"token_{worker_id}.json")
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


class ButtonRecorder:
    """按钮测试记录器：写 CSV + 截图 + 网络日志"""

    def __init__(self, worker_id: str):
        self.worker_id = worker_id
        self.dir = os.path.join(ARTIFACTS_DIR, f"agent-{worker_id}")
        os.makedirs(self.dir, exist_ok=True)
        self.rows = []
        self.api_calls = []
        self.console_errors = []
        self.request_failures = []
        self.timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")

    def log(self, msg: str):
        line = f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {msg}"
        print(line)
        with open(os.path.join(self.dir, f"agent-{self.worker_id}.log"), "a", encoding="utf-8") as f:
            f.write(line + "\n")

    def record_button(self, page_key: str, btn_text: str, btn_selector: str, btn_type: str,
                      status: str, expected: str, actual: str, api_requests: list, screenshot: str = ""):
        row = {
            "worker": self.worker_id,
            "page": page_key,
            "button_text": btn_text,
            "selector": btn_selector,
            "type": btn_type,
            "status": status,  # PASS/FAIL/无反应/跳过-禁用/跳过-危险/跳过-外部依赖
            "expected": expected,
            "actual": actual,
            "api_requests": "|".join(api_requests),
            "screenshot": screenshot,
            "time": datetime.datetime.now().isoformat(),
        }
        self.rows.append(row)

    def save_csv(self):
        path = os.path.join(self.dir, f"buttons_{self.worker_id}.csv")
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=list(self.rows[0].keys()) if self.rows else [
                "worker", "page", "button_text", "selector", "type", "status",
                "expected", "actual", "api_requests", "screenshot", "time"])
            w.writeheader()
            for r in self.rows:
                w.writerow(r)
        return path

    def save_api_calls(self):
        path = os.path.join(self.dir, f"api_calls_{self.worker_id}.csv")
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["time", "method", "url", "status", "success", "duration_ms", "page", "trigger"])
            for c in self.api_calls:
                w.writerow([c["time"], c["method"], c["url"], c["status"], c["success"],
                            c["duration_ms"], c.get("page", ""), c.get("trigger", "")])
        return path

    def save_console_errors(self):
        path = os.path.join(self.dir, f"console_errors_{self.worker_id}.csv")
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["time", "type", "message", "page", "url"])
            for e in self.console_errors:
                w.writerow([e["time"], e["type"], e["message"], e.get("page", ""), e.get("url", "")])
        return path


def summary_json(results):
    """将 worker 结果汇总到 reports/all_results.json"""
    path = os.path.join(REPORTS_DIR, "all_results.json")
    all_results = []
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                all_results = json.load(f)
        except Exception:
            all_results = []
    all_results.append(results)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=1)
    return path
