import re

BS = chr(92)
str_re = re.compile('"' + BS + '(?:' + BS + '.|[^"' + BS + '])*"')
char_re = re.compile("'" + BS + "(?:" + BS + ".|[^'" + BS + "])*'")
line_comment_re = re.compile('//.*')
block_comment_re = re.compile('/' + BS + '*.?' + BS + '*/', re.S)


def count(f):
    s = open(f, encoding='utf-8').read()
    s2 = str_re.sub('""', s)
    s2 = char_re.sub("''", s2)
    s2 = line_comment_re.sub('', s2)
    s2 = block_comment_re.sub('', s2)
    return {'{}': (s2.count('{'), s2.count('}')),
            '()': (s2.count('('), s2.count(')')),
            '[]': (s2.count('['), s2.count(']'))}


for f in ['/tmp/agentcheck/AgentSnapshotServiceImpl.java',
          'src/main/java/xiaozhi/modules/agent/service/impl/AgentSnapshotServiceImpl.java']:
    print(f, count(f))
