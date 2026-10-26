#!/usr/bin/env python3
"""Fix qxtest password: generate proper BCrypt hash and UPDATE sys_user."""
import subprocess
import sys

try:
    import bcrypt
except ImportError:
    subprocess.run([sys.executable, '-m', 'pip', 'install', 'bcrypt', '-q',
                    '--disable-pip-version-check', '-i', 'https://mirrors.aliyun.com/pypi/simple'],
                   check=True)
    import bcrypt

PWD = 'QxTest#2026'
h = bcrypt.hashpw(PWD.encode('utf-8'), bcrypt.gensalt(10)).decode('ascii')
print('new hash:', h)

sql = "UPDATE sys_user SET password='{}' WHERE username='qxtest';".format(h)
r = subprocess.run(['mysql', '-uroot', '-pa43fafe4e20126d9', 'xiaozhi_esp32_server',
                    '-e', sql], capture_output=True, text=True)
if r.returncode != 0:
    print('mysql err:', r.stderr)
    sys.exit(1)

r2 = subprocess.run(['mysql', '-uroot', '-pa43fafe4e20126d9', 'xiaozhi_esp32_server',
                     '-e', "SELECT username, LENGTH(password), LEFT(password,7) FROM sys_user WHERE username='qxtest';"],
                    capture_output=True, text=True)
print(r2.stdout)
