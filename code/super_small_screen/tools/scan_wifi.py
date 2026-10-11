#!/usr/bin/env python3
"""WiFi Scanner - bypass Windows filtering to find open networks like XZS3-DIAG"""
import subprocess
import time
import sys

def scan_wifi():
    print("Scanning WiFi networks...")
    print("=" * 50)

    # Method 1: netsh
    result = subprocess.run(
        ['netsh', 'wlan', 'show', 'networks', 'mode=bssid'],
        capture_output=True, text=True, encoding='utf-8', errors='ignore', timeout=15
    )

    found_xzs = False
    all_networks = []

    for line in result.stdout.split('\n'):
        line = line.strip()
        if 'SSID' in line and ':' in line:
            parts = line.split(':')
            if len(parts) >= 2:
                ssid = parts[1].strip()
                if ssid:
                    all_networks.append(ssid)
                    if 'XZS3' in ssid.upper():
                        found_xzs = True
                        print(f"FOUND: {ssid}")

    print(f"\nTotal networks found: {len(all_networks)}")
    for ssid in all_networks[:20]:
        print(f"  - {ssid}")

    if not found_xzs:
        print("\nXZS3-DIAG NOT FOUND!")
        print("This confirms RF hardware issue on the ESP32-S3 board.")
        print("\nPlease check:")
        print("1. Board power supply (should be 3.3V stable)")
        print("2. Antenna connection (PCB trace or IPEX)")
        print("3. Try different board if available")
    else:
        print("\nSUCCESS! XZS3-DIAG is broadcasting.")

    return found_xzs

if __name__ == '__main__':
    success = scan_wifi()
    sys.exit(0 if success else 1)
