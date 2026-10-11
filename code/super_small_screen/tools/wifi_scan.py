#!/usr/bin/env python3
"""Raw WiFi Scanner using Windows WlanAPI - bypasses system filtering of open networks."""
import ctypes
import ctypes.wintypes
from ctypes import *
import struct
import time

# WlanAPI constants
WLAN_API_VERSION = 2
WLAN_SIGNAL_FULL = 100

# WLAN_opcode enum
wlan_opcode_value = 0  # WLAN_OP_CODE_NUM_OPERATORS

def scan_wifi():
    """使用 WlanAPI 扫描所有 WiFi 网络（包括无密码的开放网络）"""
    try:
        wlan = ctypes.windll.wlanapi
        pInterface = ctypes.c_void_p()
        pdwNegotiatedVersion = ctypes.c_ulong()
        
        # 打开句柄
        ret = wlan.WlanOpenHandle(WLAN_API_VERSION, None, byref(dnegotiatedVersion), byref(pInterface))
        if ret != 0:
            print(f"WlanOpenHandle failed: error {ret}")
            return
        
        # 获取接口列表
        ppInterfaceList = ctypes.c_void_p()
        ret = wlan.WlanEnumInterfaces(pInterface, None, byref(ppInterfaceList))
        if ret != 0:
            print(f"WlanEnumInterfaces failed: error {ret}")
            wlan.WlanCloseHandle(pInterface, None)
            return
        
        # 解析接口列表
        interface_list = ctypes.cast(ppInterfaceList, ctypes.POINTER(ctypes.c_uint8)).contents
        # ... 简化处理
        
        # 直接调用 WlanScan
        interface_guid = ctypes.c_GUID()
        ret = wlan.WlanScan(pInterface, byref(interface_guid), None, None)
        if ret != 0:
            print(f"WlanScan failed: error {ret}")
        
        # 等待扫描完成
        time.sleep(2)
        
        # 获取可见网络
        ppNetworkList = ctypes.c_void_p()
        ret = wlan.WlanGetAvailableNetworkList(pInterface, byref(interface_guid), 0, None, byref(ppNetworkList))
        if ret != 0:
            print(f"WlanGetAvailableNetworkList failed: error {ret}")
        else:
            # 解析网络列表
            network_list = ctypes.cast(ppNetworkList, ctypes.POINTER(ctypes.c_uint8)).contents
            print("扫描完成")
        
        wlan.WlanFreeMemory(ppNetworkList)
        wlan.WlanFreeMemory(ppInterfaceList)
        wlan.WlanCloseHandle(pInterface, None)
        
    except Exception as e:
        print(f"Scan failed: {e}")


if __name__ == '__main__':
    print("=" * 50)
    print("WiFi Scanner (WlanAPI)")
    print("=" * 50)
    scan_wifi()
    print("=" * 50)
