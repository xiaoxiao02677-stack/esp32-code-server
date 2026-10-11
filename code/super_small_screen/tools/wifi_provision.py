#!/usr/bin/env python3
"""
ESP32-S3 UDP 配网工具
用于连接 XZS3-XXXX AP 并发送 WiFi 凭证到 192.168.4.1:5555

用法:
    python wifi_provision.py --ssid "YourWiFi" --password "12345678"
    
依赖:
    pip install pythonnet
"""
import argparse
import socket
import sys
import time


def send_provision(udp_ip, udp_port, ssid, password):
    """发送配网 JSON 到 ESP32"""
    payload = f'{{"ssid":"{ssid}","password":"{password}"}}'
    payload_bytes = payload.encode('utf-8')
    
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(5.0)
        
        print(f"发送配网数据到 {udp_ip}:{udp_port}")
        print(f"内容: {payload}")
        
        bytes_sent = sock.sendto(payload_bytes, (udp_ip, udp_port))
        print(f"已发送 {bytes_sent} 字节")
        
        # 尝试接收响应
        try:
            data, addr = sock.recvfrom(1024)
            response = data.decode('utf-8', errors='replace')
            print(f"收到响应: {response}")
        except socket.timeout:
            print("未收到响应（可能设备正在处理）")
        
        sock.close()
        return True
        
    except Exception as e:
        print(f"发送失败: {e}", file=sys.stderr)
        return False


def scan_ap_ssid():
    """扫描附近的 XZS3- 热点"""
    import subprocess
    
    # Windows: netsh wlan show networks
    # Linux/Mac: `airport -s` or `iwlist scan`
    try:
        result = subprocess.run(
            ['netsh', 'wlan', 'show', 'networks', 'mode=Bssid'],
            capture_output=True, text=True, timeout=10
        )
        
        # 简单解析 SSID
        lines = result.stdout.split('\n')
        xzs_networks = []
        for i, line in enumerate(lines):
            if 'XZS3-' in line or 'SSID' in line:
                # 向前找 SSID
                for j in range(max(0, i-5), i+1):
                    if 'SSID' in lines[j] and ':' in lines[j]:
                        ssid = lines[j].split(':')[-1].strip()
                        if ssid.startswith('XZS3-'):
                            xzs_networks.append(ssid)
        
        return list(set(xzs_networks))
        
    except Exception as e:
        print(f"扫描失败（请手动输入 AP SSID）: {e}", file=sys.stderr)
        return []


def main():
    parser = argparse.ArgumentParser(description='ESP32-S3 WiFi 配网工具')
    parser.add_argument('--ssid', '-s', required=True, help='目标 WiFi 名称')
    parser.add_argument('--password', '-p', required=True, help='目标 WiFi 密码')
    parser.add_argument('--target-ip', default='192.168.4.1', help='ESP32 AP 地址（默认 192.168.4.1）')
    parser.add_argument('--target-port', type=int, default=5555, help='UDP 端口（默认 5555）')
    parser.add_argument('--scan', action='store_true', help='扫描附近的 XZS3- AP')
    
    args = parser.parse_args()
    
    # 扫描 AP
    if args.scan:
        print("扫描 XZS3- 热点...")
        networks = scan_ap_ssid()
        if networks:
            print(f"找到: {networks}")
            selected = input(f"选择 AP (默认 {networks[0]}): ").strip() or networks[0]
            args.target_ip = selected.replace('XZS3-', '').lower()  # 简化处理
            print(f"使用 AP: {selected}")
        else:
            print("未找到 XZS3- 热点，请手动输入 AP IP")
            args.target_ip = input(f"ESP32 AP IP ({args.target_ip}): ").strip() or args.target_ip
    
    # 发送配网
    print(f"\n目标 ESP32: {args.target_ip}:{args.target_port}")
    print(f"目标 WiFi: {args.ssid}")
    
    if send_provision(args.target_ip, args.target_port, args.ssid, args.password):
        print("\n✅ 配网命令已发送")
        print("等待设备重启（约 3-5 秒）...")
        time.sleep(5)
        print("\n设备应已重启并连接到你指定的 WiFi")
        print("可用串口监视器确认连接状态")
    else:
        print("\n❌ 配网失败，请检查:")
        print("   1. 手机是否连上 XZS3-XXXX AP")
        print("   2. ESP32 的 UDP server 是否在运行")
        print("   3. IP 地址是否正确（默认 192.168.4.1）")
        sys.exit(1)


if __name__ == '__main__':
    main()
