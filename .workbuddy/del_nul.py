#!/usr/bin/env python3
"""Delete the Windows reserved-name file 'nul' in workspace root."""
import os

target = r"\\.\G:\demo\21_xiaozhi\nul"
try:
    os.remove(target)
    print("deleted via \\\\.\\ prefix")
except Exception as e:
    print("fail:", e)
    # fallback: git bash rm with the device path
    os.system('rm -f "\\\\\\\\.\\\\G:\\\\demo\\\\21_xiaozhi\\\\nul"')

print("exists after:", os.path.exists(r"\\.\G:\demo\21_xiaozhi\nul"))
