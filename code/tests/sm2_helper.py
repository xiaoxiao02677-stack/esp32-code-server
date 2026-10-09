#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SM2 加密辅助模块 - 用于管理后台登录
"""

from gmssl import sm2, func
import base64


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
        
    def encrypt(self, plaintext: str) -> str:
        """
        使用 SM2 公钥加密明文
        
        Args:
            plaintext: 明文内容
            
        Returns:
            加密后的十六进制字符串
        """
        try:
            # SM2 加密
            sm2_crypt = sm2.CryptSM2(
                public_key=self.full_pub_key,
                private_key='0' * 64  # 只需公钥加密
            )
            encrypted = sm2_crypt.encrypt(plaintext.encode('utf-8'))
            return encrypted.hex()
        except Exception as e:
            raise Exception(f"SM2 加密失败: {e}")
    
    def encrypt_with_prefix(self, plaintext: str) -> str:
        """
        加密并添加 04 前缀（前端 sm-crypto 库的加密格式）
        
        Args:
            plaintext: 明文内容
            
        Returns:
            加密后的十六进制字符串（带 04 前缀）
        """
        encrypted = self.encrypt(plaintext)
        return '04' + encrypted


def test_sm2():
    """测试 SM2 加密功能"""
    # 使用项目中的公钥
    pub_key = "003312490a186fedb2b8dab3e848110f3fc5a967ea24b0ff2cc59bb5a5f9a60272b2dd4f222c9d6b0595dde84368e341795765fe6d35fa21f3cb3e5ee6851a4e"
    
    helper = SM2Helper(pub_key)
    
    # 测试加密
    test_plain = "test1234"
    encrypted = helper.encrypt(test_plain)
    print(f"明文: {test_plain}")
    print(f"密文: {encrypted}")
    print(f"密文长度: {len(encrypted)}")
    
    # 测试带前缀的加密
    encrypted_with_prefix = helper.encrypt_with_prefix(test_plain)
    print(f"带前缀密文: {encrypted_with_prefix}")
    print(f"密文长度: {len(encrypted_with_prefix)}")
    
    return True


if __name__ == "__main__":
    test_sm2()
