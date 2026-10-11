import paramiko, os, posixpath

HOST, PORT, USER, PWD = "sandyun.top", 22222, "root", "Ymm6088."
LOCAL_BASE = "G:/demo/21_xiaozhi/code-server-mirror/manager-api/src/main"
REMOTE_BASE = "/root/xiaozhi-server/main/manager-api/src/main"

# 12 new files (missing on server) + 5 changed + 4 DTOs + AgentDao.xml
NEW_FILES = [
    "java/xiaozhi/modules/agent/controller/WakeWordController.java",
    "java/xiaozhi/modules/agent/controller/AgentMcpConfigController.java",
    "java/xiaozhi/modules/agent/dao/AgentWakeWordDao.java",
    "java/xiaozhi/modules/agent/dao/AgentMcpConfigDao.java",
    "java/xiaozhi/modules/agent/entity/AgentWakeWordEntity.java",
    "java/xiaozhi/modules/agent/entity/AgentMcpConfigEntity.java",
    "java/xiaozhi/modules/agent/service/AgentWakeWordService.java",
    "java/xiaozhi/modules/agent/service/AgentMcpConfigService.java",
    "java/xiaozhi/modules/agent/service/impl/AgentWakeWordServiceImpl.java",
    "java/xiaozhi/modules/agent/service/impl/AgentMcpConfigServiceImpl.java",
    "java/xiaozhi/modules/memory/service/AgentMemorySummarizeService.java",
    "java/xiaozhi/modules/memory/service/impl/AgentMemorySummarizeServiceImpl.java",
]
CHANGED_FILES = [
    "java/xiaozhi/common/exception/ErrorCode.java",
    "java/xiaozhi/modules/agent/Enums/AgentSnapshotField.java",
    "java/xiaozhi/modules/agent/dto/AgentCreateDTO.java",
    "java/xiaozhi/modules/agent/dto/AgentDTO.java",
    "java/xiaozhi/modules/agent/dto/AgentUpdateDTO.java",
    "java/xiaozhi/modules/agent/dto/AgentSnapshotDataDTO.java",
    "java/xiaozhi/modules/agent/service/AgentService.java",
    "java/xiaozhi/modules/agent/service/impl/AgentServiceImpl.java",
    "java/xiaozhi/modules/agent/service/impl/AgentSnapshotServiceImpl.java",
]
XML_FILES = [
    "resources/mapper/agent/AgentDao.xml",
]

cli = paramiko.SSHClient(); cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
cli.connect(HOST, port=PORT, username=USER, password=PWD, timeout=15,
            banner_timeout=15, auth_timeout=15, look_for_keys=False, allow_agent=False)
sftp = cli.open_sftp()

def run(cmd):
    stdin, stdout, stderr = cli.exec_command(cmd, timeout=30)
    rc = stdout.channel.recv_exit_status()
    out = stdout.read().decode("utf-8", "replace").strip()
    err = stderr.read().decode("utf-8", "replace").strip()
    return rc, out, err

# backup changed files (new files don't exist yet)
for rel in CHANGED_FILES + XML_FILES:
    rpath = REMOTE_BASE + "/" + rel
    rc, out, err = run(f"test -f {rpath} && cp -n {rpath} {rpath}.bak-wc; echo done")
    print("BAK", rel, err or out)

# upload
all_files = NEW_FILES + CHANGED_FILES + XML_FILES
for rel in all_files:
    lpath = os.path.join(LOCAL_BASE, rel)
    rpath = REMOTE_BASE + "/" + rel
    # ensure remote dir
    rdir = posixpath.dirname(rpath)
    rc, out, err = run(f"mkdir -p {rdir}")
    sftp.put(lpath, rpath)
    print("UP ", rel)

# verify md5 match
import hashlib
mismatches = []
for rel in all_files:
    lpath = os.path.join(LOCAL_BASE, rel)
    with open(lpath, "rb") as f:
        lmd5 = hashlib.md5(f.read().replace(b"\r\n", b"\n")).hexdigest()
    rc, out, err = run(f"md5sum <(tr -d '\r' < {REMOTE_BASE}/{rel}) | awk '{{print $1}}'")
    if out != lmd5:
        mismatches.append((rel, lmd5, out))
        print("MISMATCH", rel, "local=", lmd5, "remote=", out)
if not mismatches:
    print("ALL_MD5_MATCH")
sftp.close(); cli.close()
