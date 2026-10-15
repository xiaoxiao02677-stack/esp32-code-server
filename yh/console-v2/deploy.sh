#!/bin/bash
set -e

echo "=== 构建前端 ==="
cd "$(dirname "$0")"
npm run build

echo "=== 部署到服务器 ==="
scp -P 22222 -r dist/* root@sandyun.top:/var/www/console-v2/admin/

echo "=== 清理旧文件 ==="
ssh -p 22222 root@sandyun.top "cd /var/www/console-v2/admin && find . -name '*.js' -o -name '*.css' | grep -v 'index-' | xargs rm -f 2>/dev/null; true"

echo "=== 验证部署 ==="
ssh -p 22222 root@sandyun.top "ls -la /var/www/console-v2/admin/assets/"
ssh -p 22222 root@sandyun.top "curl -s http://127.0.0.1:8001/admin/ | grep title"

echo "=== 完成 ==="
