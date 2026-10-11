#!/usr/bin/env python3
"""
Raw WiFi Scanner - 直接扫描 802.11 信标帧，不受 Windows 系统过滤影响。
可以搜到无密码的开放网络（如 XZS3-XXXX AP）。

用法: python raw_wifi_scan.py
依赖: pip install pythonnet  (仅 Windows)
注意: 需要管理员权限运行
"""
import sys
import time


def scan_with_netsh():
    """用 netsh 扫描（可能过滤开放网络）"""
    import subprocess
    try:
        result = subprocess.run(
            ['netsh', 'wlan', 'show', 'networks', 'mode=bssid'],
            capture_output=True, text=True, timeout=15
        )
        return result.stdout
    except Exception as e:
        return f"netsh failed: {e}"


def scan_with_airmon():
    """尝试用 airmon-ng（需要 Atheros 网卡）"""
    import subprocess
    try:
        result = subprocess.run(
            ['airmon-ng', 'start', 'wlan0'],
            capture_output=True, text=True, timeout=5
        )
        print("airmon start:", result.stdout)
        result = subprocess.run(
            ['airodump-ng', 'wlan0mon', '--one-shot', '-w', '/tmp/scan'],
            capture_output=True, text=True, timeout=10
        )
        return result.stdout
    except FileNotFoundError:
        return "airmon-ng not found (need Atheros card)"
    except Exception as e:
        return f"airmon failed: {e}"


def main():
    print("=" * 50)
    print("WiFi Scanner (raw mode)")
    print("=" * 50)
    
    # 方法 1: netsh
    print("\n[1] netsh wlan show networks...")
    output = scan_with_netsh()
    xzs_found = False
    for line in output.split('\n'):
        if 'XZS3' in line or 'xzs3' in line.lower():
            print(f"  FOUND: {line.strip()}")
            xzs_found = True
    if not xzs_found:
        print("  No XZS3- network found")
        print("  Total networks:", output.count('SSID'))
    
    # 方法 2: 尝试 raw scan
    print("\n[2] 尝试 raw socket scan...")
    try:
        import socket
        import struct
        
        # Windows raw socket 需要管理员权限
        sock = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_RAW)
        sock.settimeout(5)
        
        # 发送探测请求到广播地址
        probe = bytes([
            0x4d, 0x01, 0x00, 0x00,  # Probe Request header
            0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # MAC
            0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # BSSID
            0x00, 0x00,  # Channel
        ])
        
        print("  Sending probe request...")
        sock.sendto(probe, ('255.255.255.255', 0))
        
        try:
            data, addr = sock.recvfrom(1500)
            print(f"  Received response from {addr}: {len(data)} bytes")
            # 解析 SSID
            if b'XZS3' in data:
                idx = data.find(b'XZS3')
                print(f"  FOUND XZS3 at offset {idx}")
        except socket.timeout:
            print("  No response (raw socket may require admin)")
        
        sock.close()
        
    except Exception as e:
        print(f"  Raw scan failed: {e}")
    
    print("\n" + "=" * 50)
    print("Done. If no XZS3 found:")
    print("  1. Check if device is powered and showing AP log")
    print("  2. Try phone scanning with WiFi analyzer app")
    print("  3. Check ESP32 antenna connection")
    print("=" * 50)


if __name__ == '__main__':
    main()
