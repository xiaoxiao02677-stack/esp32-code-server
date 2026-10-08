#!/usr/bin/env python3
"""
屿禾工坊 (YH) 固件串口日志监听 —— 用户自用工具

用途：烧录完成后，插着 USB 跑这个脚本，实时看 ESP32-S3 启动日志 / YH 协议心跳。
用法：
    python yh_monitor.py              # 自动探测串口
    python yh_monitor.py COM5         # 指定串口
    python yh_monitor.py COM5 115200  # 指定串口+波特率

依赖（首次）：pip install pyserial
退出：Ctrl+C

关键看点：
    [YH] started (server=...:3333)   -> YH协议启动
    [YH] ... connected               -> TCP连上服务器
    HELLO / ADVERTISEMENT / HEARTBEAT -> 协议正常
    YhWs2812Led ready on GPIO 48      -> WS2812初始化
    Set output volume: 50 / AUDIO    -> 音量
    I (main): Application started     -> 系统就绪
"""
import sys
import time
import serial
import serial.tools.list_ports


def find_port():
    """自动探测 CP210x / CH340 / USB Serial / JTAG 串口"""
    targets = ("Silicon Labs", "CH340", "USB Serial", "JTAG", "CP210", "FTDI")
    for p in serial.tools.list_ports.comports():
        desc = f"{p.description} {p.manufacturer or ''}"
        if any(t.lower() in desc.lower() for t in targets):
            return p.device
    # 兜底：列出所有 COM 让用户挑
    ports = [p.device for p in serial.tools.list_ports.comports()]
    if ports:
        print("[?] 未识别到常见串口芯片，探测到:", ", ".join(ports))
        return ports[0]
    return None


def main():
    port = sys.argv[1] if len(sys.argv) > 1 else find_port()
    baud = int(sys.argv[2]) if len(sys.argv) > 2 else 115200

    if not port:
        print("[ERR] 没找到串口。请检查 USB 连接，或手动指定：python yh_monitor.py COM5")
        sys.exit(1)

    print(f"[YH-MON] port={port} baud={baud}")
    print("[YH-MON] 开始监听 (Ctrl+C 退出) —— 日志关键行高亮显示")
    print("-" * 70)

    try:
        ser = serial.Serial(port, baud, timeout=0.5)
    except serial.SerialException as e:
        print(f"[ERR] 打不开 {port}: {e}")
        print("       提示：串口可能被 idf.py monitor / 另一个终端占着，先关掉")
        sys.exit(1)

    # 高亮关键字
    hi = ("[YH]", "YhWs2812Led", "HELLO", "HEARTBEAT", "ADVERTISEMENT",
          "SET_LED", "Application started", "volume", "Application",
          "error", "E (", "W (")

    try:
        with ser:
            print(f"[YH-MON] 已连接 {port}，等待设备启动日志...\n")
            while True:
                try:
                    n = ser.in_waiting
                    if n:
                        chunk = ser.read(n)
                        try:
                            text = chunk.decode("utf-8", errors="replace")
                        except Exception:
                            text = chunk.decode("latin-1", errors="replace")
                        for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
                            if not line.strip():
                                continue
                            if any(k in line for k in hi):
                                # 关键行加前缀标记
                                print(f">> {line}", flush=True)
                            else:
                                print(f"   {line}", flush=True)
                    else:
                        time.sleep(0.05)
                except serial.SerialException as e:
                    print(f"[WARN] 串口读取异常: {e}")
                    time.sleep(1)
    except KeyboardInterrupt:
        print("\n[YH-MON] 已退出监听。")
    finally:
        try:
            ser.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
