#!/usr/bin/env python3
"""Fix nginx.conf: append proper stream block for dual-protocol 8001."""
import re

ng = open('/etc/nginx/nginx.conf').read()

# remove empty/broken stream blocks
ng = re.sub(r'\nstream\s*\{[^}]*\}\n?', '\n', ng)

block = '''
# ===== 8001 同端口双协议（TLS 探测分流，stream 层）=====
# 浏览器 https://sandyun.top:8001 -> 127.0.0.1:9443（SSL web）
# 设备   ws://sandyun.top:8001   -> 127.0.0.1:9001（明文 HTTP + WS 反代）
stream {
    map $ssl_preread_protocol $upstream_8001 {
        ""        127.0.0.1:9001;
        default   127.0.0.1:9443;
    }
    server {
        listen 8001;
        ssl_preread on;
        proxy_pass $upstream_8001;
        proxy_timeout 3600s;
    }
}
'''

ng = ng.rstrip() + '\n' + block
open('/etc/nginx/nginx.conf', 'w').write(ng)
print('stream block written')
