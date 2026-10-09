import re
import sys

files = [
    'src/main/java/xiaozhi/modules/agent/entity/AgentEntity.java',
    'src/main/java/xiaozhi/modules/agent/dto/AgentUpdateDTO.java',
    'src/main/java/xiaozhi/modules/agent/dto/AgentCreateDTO.java',
    'src/main/java/xiaozhi/modules/agent/dto/AgentDTO.java',
    'src/main/java/xiaozhi/modules/agent/dto/AgentSnapshotDataDTO.java',
    'src/main/java/xiaozhi/modules/agent/Enums/AgentSnapshotField.java',
    'src/main/java/xiaozhi/modules/agent/service/impl/AgentServiceImpl.java',
    'src/main/java/xiaozhi/modules/agent/service/impl/AgentSnapshotServiceImpl.java',
    'src/main/java/xiaozhi/modules/config/service/impl/ConfigServiceImpl.java',
]

str_re = re.compile(r'"(?:\\.|[^"\\])*"')
char_re = re.compile(r"'(?:\\.|[^'\\])*'")
line_comment_re = re.compile(r'//.*')
block_comment_re = re.compile(r'/\*.*?\*/', re.S)

ok = True
for f in files:
    s = open(f, encoding='utf-8').read()
    s2 = str_re.sub('""', s)
    s2 = char_re.sub("''", s2)
    s2 = line_comment_re.sub('', s2)
    s2 = block_comment_re.sub('', s2)
    file_ok = True
    for open_c, close_c in [('{', '}'), ('(', ')'), ('[', ']')]:
        a, b = s2.count(open_c), s2.count(close_c)
        if a != b:
            print(f'{f}: {open_c}{a} vs {close_c}{b} MISMATCH')
            file_ok = False
            ok = False
    if file_ok:
        print(f'{f}: OK')

print('ALL OK' if ok else 'FAIL')
sys.exit(0 if ok else 1)
