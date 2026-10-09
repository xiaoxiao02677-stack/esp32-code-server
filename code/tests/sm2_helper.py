#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SM2 加密辅助模块 - 用于管理后台登录
"""

from gmssl import sm2
import time


class SM2Helper:
    """SM2 加密工具类"""

    def __init__(self, public_key_hex: str):
        """
        初始化 SM2 加密器

        Args:
            public_key_hex: SM2 公钥（十六进制字符串，不带 04 前缀）
        """
        # 公钥去掉开头的 04
        if public_key_hex.startswith('04'):
            self.pub_key = public_key_hex[2:]
        else:
            self.pub_key = public_key_hex
        # SM2 公钥格式：04 + 64字节 (X:32字节 + Y:32字节)
        self.full_pub_key = '04' + self.pub_key
        # 初始化 C1C3C2 模式（与后端 BouncyCastle 一致）
        self.crypt = sm2.CryptSM2(
            public_key=self.pub_key,
            private_key='0' * 64,
            mode=True  # C1C3C2 模式
        )

    def encrypt(self, plaintext: str) -> str:
        """
        使用 SM2 公钥加密明文

        Args:
            plaintext: 明文内容

        Returns:
            加密后的十六进制字符串（带 04 前缀）
        """
        encrypted = self.crypt.encrypt(plaintext.encode('utf-8'))
        return '04' + encrypted.hex()


def get_sm2_helper():
    """获取 SM2 加密器实例"""
    import requests
    BASE_URL = "https://sandyun.top:8001/xiaozhi"

    resp = requests.get(f"{BASE_URL}/user/pub-config", verify=False)
    config = resp.json()
    pub_key = config['data']['sm2PublicKey']

    return SM2Helper(pub_key)


def login(username: str, password: str, captcha_text: str = "") -> str:
    """
    登录获取 token

    Args:
        username: 用户名
        password: 密码
        captcha_text: 验证码文本（可选，如果不提供则自动获取并识别）

    Returns:
        token 字符串
    """
    import requests
    import ddddocr
    from io import BytesIO
    from PIL import Image

    BASE_URL = "https://sandyun.top:8001/xiaozhi"
    sm2_helper = get_sm2_helper()

    # 获取验证码
    captcha_uuid = f"test-{int(time.time() * 1000)}"
    resp = requests.get(f"{BASE_URL}/user/captcha?uuid={captcha_uuid}", verify=False)

    # OCR 识别验证码
    ocr = ddddocr.DdddOcr(show_ad=False)
    captcha_text = ocr.classification(resp.content)
    print(f"识别验证码: {captcha_text}")

    # 加密密码（captcha + password）
    encrypted_password = sm2_helper.encrypt(captcha_text + password)

    # 发送登录请求
    login_data = {
        "username": username,
        "password": encrypted_password,
        "captchaId": captcha_uuid
    }

    resp = requests.post(f"{BASE_URL}/user/login", json=login_data, verify=False)
    result = resp.json()

    if result.get('code') == 0 and result.get('data', {}).get('token'):
        return result['data']['token']
    else:
        raise Exception(f"登录失败: {result.get('msg')}")


if __name__ == "__main__":
    token = login("demo", "P@ssword123")
    print(f"登录成功! Token: {token[:30]}...")
