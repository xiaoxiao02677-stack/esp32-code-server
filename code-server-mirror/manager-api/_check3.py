def count(f):
    s = open(f, encoding='utf-8').read()
    return {'{}': (s.count('{'), s.count('}')),
            '()': (s.count('('), s.count(')')),
            '[]': (s.count('['), s.count(']'))}


for f in ['/tmp/agentcheck/AgentSnapshotServiceImpl.java',
          'src/main/java/xiaozhi/modules/agent/service/impl/AgentSnapshotServiceImpl.java']:
    print(f, count(f))
