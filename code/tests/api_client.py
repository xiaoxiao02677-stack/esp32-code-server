#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
管理后台 API 测试客户端
"""

import requests
import json
import time
from typing import Dict, Optional, Any
from sm2_helper import SM2Helper


class AdminAPIClient:
    """管理后台 API 客户端"""
    
    BASE_URL = "https://sandyun.top:8001/xiaozhi"
    VERIFY_SSL = False  # 跳过 SSL 验证
    
    def __init__(self):
        self.session = requests.Session()
        self.session.verify = self.VERIFY_SSL
        self.session.headers.update({
            'Content-Type': 'application/json',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        self.token: Optional[str] = None
        self.sm2_helper: Optional[SM2Helper] = None
        self.pub_config: Optional[Dict] = None
        
    def get_pub_config(self) -> Dict:
        """获取公共配置（包含 SM2 公钥）"""
        resp = self.session.get(f"{self.BASE_URL}/user/pub-config")
        if resp.status_code == 200:
            data = resp.json()
            if data.get('code') == 0:
                self.pub_config = data.get('data', {})
                pub_key = self.pub_config.get('sm2PublicKey', '')
                if pub_key:
                    self.sm2_helper = SM2Helper(pub_key)
                return data
        raise Exception(f"获取公共配置失败: {resp.status_code} {resp.text[:200]}")
    
    def login(self, username: str, password: str, captcha: str = "") -> Dict:
        """
        登录获取 token
        
        Args:
            username: 用户名
            password: 密码
            captcha: 验证码
            
        Returns:
            登录响应数据
        """
        if not self.sm2_helper:
            self.get_pub_config()
        
        if not self.sm2_helper:
            raise Exception("无法初始化 SM2 加密器")
        
        # 获取验证码 UUID
        captcha_uuid = f"test-{int(time.time() * 1000)}"
        
        # 加密密码（密码 + 验证码）
        encrypted_password = self.sm2_helper.encrypt_with_prefix(captcha + password)
        
        # 发送登录请求
        login_data = {
            "username": username,
            "password": encrypted_password,
            "captchaId": captcha_uuid
        }
        
        resp = self.session.post(
            f"{self.BASE_URL}/user/login",
            json=login_data
        )
        
        if resp.status_code == 200:
            data = resp.json()
            if data.get('code') == 0 and data.get('data', {}).get('token'):
                self.token = data['data']['token']
                self.session.headers['Authorization'] = f"Bearer {self.token}"
                return data
            else:
                # 可能返回错误码，记录详细信息
                return data
        else:
            raise Exception(f"登录失败: HTTP {resp.status_code}")
    
    def get_token(self) -> str:
        """获取登录 token"""
        return self.token
    
    def request(self, method: str, path: str, **kwargs) -> Dict:
        """
        发送 API 请求
        
        Args:
            method: HTTP 方法 (GET/POST/PUT/DELETE)
            path: API 路径
            **kwargs: 其他请求参数
            
        Returns:
            API 响应数据
        """
        url = f"{self.BASE_URL}{path}"
        
        # 确保有 token
        if not self.token and path not in ['/user/login', '/user/captcha', '/user/pub-config']:
            raise Exception("未登录，请先调用 login()")
        
        resp = self.session.request(method, url, **kwargs)
        
        if resp.status_code == 200:
            return resp.json()
        elif resp.status_code == 401:
            raise Exception(f"未授权访问: {path}")
        else:
            raise Exception(f"API 请求失败: {method} {path} -> HTTP {resp.status_code} {resp.text[:200]}")
    
    def get(self, path: str, params: Optional[Dict] = None) -> Dict:
        """发送 GET 请求"""
        return self.request('GET', path, params=params)
    
    def post(self, path: str, data: Optional[Dict] = None) -> Dict:
        """发送 POST 请求"""
        return self.request('POST', path, json=data)
    
    def put(self, path: str, data: Optional[Dict] = None) -> Dict:
        """发送 PUT 请求"""
        return self.request('PUT', path, json=data)
    
    def delete(self, path: str) -> Dict:
        """发送 DELETE 请求"""
        return self.request('DELETE', path)


def test_client():
    """测试客户端功能"""
    client = AdminAPIClient()
    
    # 测试获取公共配置
    print("测试获取公共配置...")
    config = client.get_pub_config()
    print(f"配置获取成功: {list(config.get('data', {}).keys())}")
    
    # 测试登录
    print("\n测试登录...")
    try:
        login_result = client.login('demo', 'P@ssword123', '')
        print(f"登录结果: {login_result}")
        if login_result.get('code') == 0:
            print(f"登录成功! Token: {client.token[:20]}...")
        else:
            print(f"登录失败: {login_result.get('msg')}")
    except Exception as e:
        print(f"登录异常: {e}")
    
    return client


if __name__ == "__main__":
    test_client()
