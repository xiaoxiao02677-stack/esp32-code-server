#!/bin/bash
# ESP32-S3 配网快捷脚本
# 用法: ./provision.sh "你的WiFi名" "你的密码"

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROVISION_SCRIPT="${SCRIPT_DIR}/wifi_provision.py"

if [ $# -lt 2 ]; then
    echo "用法: $0 <WiFi名> <密码>"
    echo "示例: $0 MyWiFi 12345678"
    exit 1
fi

WIFI_SSID="$1"
WIFI_PASSWORD="$2"

echo "========================================"
echo "ESP32-S3 WiFi 配网工具"
echo "========================================"
echo "目标 WiFi: ${WIFI_SSID}"
echo "目标密码: ${WIFI_PASSWORD}"
echo ""
echo "请确保:"
echo "  1. ESP32 已通电并显示 XZS3-XXXX AP"
echo "  2. 手机/电脑已连上 XZS3-XXXX"
echo "  3. 按任意键继续..."
echo "========================================"
read -n 1 -s

python3 "${PROVISION_SCRIPT}" --ssid "${WIFI_SSID}" --password "${WIFI_PASSWORD}"
