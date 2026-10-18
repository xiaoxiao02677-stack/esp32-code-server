#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
管理后台 API 测试客户端
"""

import requests
import json
import time
from typing import Dict, Optional, Any, List, Tuple
from sm2_helper import login, get_sm2_helper


class AdminAPIClient:
    """管理后台 API 客户端"""

    BASE_URL = "https://sandyun.top:8001/yuhe"
    VERIFY_SSL = False

    def __init__(self, username: str = "demo", password: str = "P@ssword123"):
        self.session = requests.Session()
        self.session.verify = self.VERIFY_SSL
        self.session.headers.update({
            'Content-Type': 'application/json',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        self.token: Optional[str] = None
        self.username = username
        self.password = password
        self.test_results: List[Dict] = []
        self.issues: List[Dict] = []
        self.no_response_items: List[Dict] = []
        self.unexpected_items: List[Dict] = []

    def authenticate(self) -> bool:
        """登录获取 token"""
        try:
            self.token = login(self.username, self.password)
            self.session.headers['Authorization'] = f"Bearer {self.token}"
            print(f"登录成功! Token: {self.token[:20]}...")
            return True
        except Exception as e:
            print(f"登录失败: {e}")
            return False

    def request(self, method: str, path: str, **kwargs) -> Tuple[int, Dict]:
        """
        发送 API 请求

        Args:
            method: HTTP 方法
            path: API 路径
            **kwargs: 其他请求参数

        Returns:
            (status_code, response_data)
        """
        url = f"{self.BASE_URL}{path}"

        # 确保有 token
        if not self.token and path not in ['/user/login', '/user/captcha', '/user/pub-config']:
            if not self.authenticate():
                return 401, {"error": "未登录"}

        try:
            resp = self.session.request(method, url, timeout=30, **kwargs)
            try:
                data = resp.json()
            except:
                data = {"raw": resp.text[:500]}

            return resp.status_code, data
        except requests.exceptions.Timeout:
            return 408, {"error": "请求超时"}
        except requests.exceptions.ConnectionError:
            return 503, {"error": "连接失败"}
        except Exception as e:
            return 500, {"error": str(e)}

    def get(self, path: str, params: Optional[Dict] = None) -> Tuple[int, Dict]:
        """发送 GET 请求"""
        return self.request('GET', path, params=params)

    def post(self, path: str, data: Optional[Dict] = None) -> Tuple[int, Dict]:
        """发送 POST 请求"""
        return self.request('POST', path, json=data)

    def put(self, path: str, data: Optional[Dict] = None) -> Tuple[int, Dict]:
        """发送 PUT 请求"""
        return self.request('PUT', path, json=data)

    def delete(self, path: str) -> Tuple[int, Dict]:
        """发送 DELETE 请求"""
        return self.request('DELETE', path)

    def record_result(self, test_name: str, passed: bool, details: str = "", severity: str = "一般"):
        """记录测试结果"""
        result = {
            "name": test_name,
            "passed": passed,
            "details": details,
            "severity": severity,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        self.test_results.append(result)

        if not passed:
            if "无响应" in details or "超时" in details or "连接失败" in details:
                self.no_response_items.append(result)
            elif "不达预期" in details or "错误" in details:
                self.unexpected_items.append(result)
            else:
                self.issues.append(result)

    def get_test_summary(self) -> Dict:
        """获取测试摘要"""
        total = len(self.test_results)
        passed = sum(1 for r in self.test_results if r['passed'])
        failed = total - passed

        return {
            "total": total,
            "passed": passed,
            "failed": failed,
            "success_rate": f"{(passed/total*100):.1f}%" if total > 0 else "0%",
            "issues": len(self.issues),
            "no_response": len(self.no_response_items),
            "unexpected": len(self.unexpected_items)
        }


def test_api_client():
    """测试 API 客户端功能"""
    client = AdminAPIClient()

    # 登录
    if not client.authenticate():
        print("认证失败，退出测试")
        return None

    # 测试获取用户信息
    print("\n测试获取用户信息...")
    status, data = client.get('/user/info')
    print(f"状态码: {status}, 结果: {json.dumps(data, ensure_ascii=False)[:200]}")

    # 测试获取智能体列表
    print("\n测试获取智能体列表...")
    status, data = client.get('/agent/list')
    print(f"状态码: {status}, 结果: {json.dumps(data, ensure_ascii=False)[:200]}")

    return client


if __name__ == "__main__":
    test_api_client()
