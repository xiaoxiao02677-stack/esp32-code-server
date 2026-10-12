# 屿禾 Web 环境迁移包 (yh.tar.gz)

打包时间: 2026-10-13 00:05 (源服务器: sandyun.top)

## 内容结构
- db/xiaozhi_esp32_server.sql.gz   MySQL 业务库热备(--single-transaction, 含routines/triggers/events/hex-blob)
- db/redis_dump.rdb                Redis 快照(BGSAVE)
- app/xiaozhi-server/              Python 服务(WS:8000/API:8003, 含models本地ASR模型929MB, 排除.venv/tmp/日志)
- app/manager-api/                 Java 服务源码(排除target, 需mvn package)
- deploy/opt-xiaozhi/              已编译最新 jar + uploadfile (目标放 /opt/xiaozhi/)
- web/console-v2/                  前端构建产物(管理端admin/顾客端app)
- config/                          nginx站点配置 + systemd服务文件
- scripts/requirements-freeze.txt  Python依赖精确版本
- scripts/config.yaml.reference    Python参考配置(实际配置以 data/.config.yaml 为准,由Java下发)

## 目标服务器部署步骤
1. 基础软件: MySQL8 + Redis + Nginx + Python3.12 + JDK17 + Maven
2. MySQL: CREATE DATABASE xiaozhi_esp32_server; 
   gunzip < db/xiaozhi_esp32_server.sql.gz | mysql -uroot -p xiaozhi_esp32_server
   业务账号: 见 app/manager-api/src/main/resources/application-dev.yml
3. Redis: 停服务后用 redis_dump.rdb 覆盖 /var/lib/redis/dump.rdb 再启动
4. Python: cd app/xiaozhi-server && python -m venv .venv && .venv/bin/pip install -r ../scripts/requirements-freeze.txt
5. Java: cp deploy/opt-xiaozhi/xiaozhi-esp32-api.jar /opt/xiaozhi/ (或 mvn package 后部署)
6. 拷贝 config/ 下的 nginx 配置到 /etc/nginx/sites-available/ 并建软链, systemd 服务文件到 /etc/systemd/system/
7. systemctl daemon-reload && systemctl enable --now xiaozhi-server xiaozhi-manager-api && nginx -t && systemctl reload nginx

## 关键提醒
- Python 服务端口: 8000(WS)/8003(HTTP)  Java: 8002  Nginx 对外: 8001(ws+web)/9444(https)
- MySQL root密码(源): 123456  —— 测试服务器请务必修改
- config 里 server.secret / auth_key 与 Java sys_params 的 server.secret 必须一致
- manager-api 的 WebSocket 地址下发依赖部署域名, 若域名不同需改 application-dev.yml 或参数表
