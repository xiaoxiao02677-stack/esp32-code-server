# -*- coding: utf-8 -*-
"""console-v2 UI 审查修复批处理：
A. chip div -> button（键盘可达）
B. StatCard icon="emoji" -> icon="图标名"（StatCard 内部走 YhIcon）
C. 空态 <div class="empty-icon">emoji</div> -> <div class="empty-icon"><YhIcon .../></div> + 自动补 import
D. 含 loading ref 且用了 <DataTable> 的页面自动接 :loading="loading"
E. 清理单行本地 .chip / .chip.active / .chip.sm 规则（已收敛到 global.css）
幂等：重复运行不会二次替换。
"""
import io, os, re

ROOT = r"G:\demo\21_xiaozhi\yh\console-v2\src\views"

EMOJI_MAP = {
    '🤖': 'bot', '📡': 'device', '🎙': 'mic', '💎': 'gem', '👤': 'user', '🧩': 'grid',
    '👥': 'users', '📦': 'package', '💬': 'chat', '🧠': 'memory', '📚': 'book',
    '⚙': 'sliders', '🎭': 'badge', '📜': 'scroll', '🖼': 'image', '🎯': 'target',
    '✅': 'check-circle', '📖': 'book-open', '🖥': 'server', '🔗': 'link', '🧪': 'flask',
    '🔊': 'volume', '📮': 'send', '📤': 'send', '🛠': 'wrench', '📈': 'trend-up',
    '📉': 'trend-down', '🔌': 'plug', '🔑': 'key', '🛡': 'shield', '📄': 'file',
    '🧱': 'grid', '🔢': 'hash', '⏳': 'clock', '🟢': 'dot', '⚡': 'zap', '🌐': 'globe',
    '👁': 'eye', '🎨': 'image', '📱': 'phone', '📊': 'chart', '🕓': 'clock', '⬆': 'upload',
}

def norm(s):
    return s.replace('\ufe0f', '')

def map_emoji(e):
    return EMOJI_MAP.get(norm(e.strip()))

CHIP_OPEN = re.compile(r'<div(\s[^>]*class="chip(?: [^"]*)?"[^>]*)>')

def process(path):
    with io.open(path, 'r', encoding='utf-8') as f:
        src = f.read()
    orig = src
    rel = os.path.relpath(path, ROOT).replace('\\', '/')
    stats = {'icon': 0, 'empty': 0, 'chip': 0, 'loading': 0, 'css': 0, 'import': 0}

    # B. StatCard icon="emoji" -> icon="name"
    def repl_icon(m):
        name = map_emoji(m.group(1))
        if name:
            stats['icon'] += 1
            return 'icon="%s"' % name
        return m.group(0)
    src = re.sub(r'icon="([^"]+)"', repl_icon, src)

    # C. 空态 emoji -> YhIcon
    def repl_empty(m):
        name = map_emoji(m.group(1))
        if name:
            stats['empty'] += 1
            return '<div class="empty-icon"><YhIcon name="%s" /></div>' % name
        return m.group(0)
    src = re.sub(r'<div class="empty-icon">([^<]*)</div>', repl_empty, src)

    # C-2. 补 YhIcon import（只对发生空态转换的文件）
    if stats['empty'] > 0 and 'YhIcon.vue' not in src:
        depth = rel.count('/')  # views/admin/X.vue -> 2 -> ../../
        prefix = '../' * (depth + 1)
        src = src.replace(
            '<script setup>\n',
            "<script setup>\nimport YhIcon from '%scomponents/YhIcon.vue'\n" % prefix,
            1)
        stats['import'] += 1

    # A. chip div -> button
    out, pos = [], 0
    while True:
        m = CHIP_OPEN.search(src, pos)
        if not m:
            out.append(src[pos:])
            break
        close = src.find('</div>', m.end())
        if close == -1:
            out.append(src[pos:])
            break
        out.append(src[pos:m.start()])
        out.append('<button type="button"%s>' % m.group(1))
        out.append(src[m.end():close])
        out.append('</button>')
        pos = close + 6
        stats['chip'] += 1
    src = ''.join(out)

    # E. 清理单行本地 .chip 规则
    def drop_css(line):
        if re.match(r'^\.chip(\.(active|sm))? \{[^}]*\}\s*$', line.rstrip('\n')):
            stats['css'] += 1
            return '/* .chip 已收敛到 global.css */\n'
        return line
    src = '\n'.join(drop_css(l) for l in src.split('\n'))

    # D. DataTable 接 :loading
    if '<DataTable' in src and re.search(r'const loading = ref\(', src):
        def repl_dt(m):
            tag = m.group(0)
            if ':loading' in tag:
                return tag
            stats['loading'] += 1
            return tag[:-1] + ' :loading="loading">'
        src = re.sub(r'<DataTable[^>]*>', repl_dt, src)

    if src != orig:
        with io.open(path, 'w', encoding='utf-8', newline='') as f:
            f.write(src)
        print('%-34s icon=%-3d empty=%-3d chip=%-3d loading=%-3d css=%-2d import=%d'
              % (rel, stats['icon'], stats['empty'], stats['chip'],
                 stats['loading'], stats['css'], stats['import']))
        return True
    return False

total = changed = 0
sums = {}
for dirpath, _dirnames, filenames in os.walk(ROOT):
    for fn in filenames:
        if fn.endswith('.vue'):
            total += 1
            if process(os.path.join(dirpath, fn)):
                changed += 1
print('---- files: %d scanned, %d changed ----' % (total, changed))
