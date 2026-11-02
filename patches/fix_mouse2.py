#!/usr/bin/env python3
"""DeskWidgets 引擎补丁 2：鼠标事件全量透传。

在 conky_mouse 入口处把原始事件先交给 widget.mouse(ev)（如果 widget 定义了它），
返回 true 则消费，false/nil 则继续走原有处理（左键/右键/滚轮）。
用于诊断 conky 1.19 的滚轮事件形态、以及 widget 侧自由适配。备份 *.bak-mouse2。
"""
import shutil
import sys

MAIN = '/usr/share/deskwidgets/engine/main.lua'

OLD = """function conky_mouse(ev)
    if ev.type ~= 'button_down' then return false end"""
NEW = """function conky_mouse(ev)
    if widget.mouse and widget.mouse(ev) then return true end   -- fix_mouse2: full event access
    if ev.type ~= 'button_down' then return false end"""


def main():
    with open(MAIN, encoding='utf-8') as f:
        src = f.read()
    if 'fix_mouse2' in src:
        print('main.lua 已打过此补丁，跳过')
        return
    if OLD not in src:
        print('  ⚠ 未找到锚点，未做修改')
        sys.exit(1)
    shutil.copy2(MAIN, MAIN + '.bak-mouse2')
    with open(MAIN, 'w', encoding='utf-8') as f:
        f.write(src.replace(OLD, NEW, 1))
    print(f'✔ {MAIN} 事件透传已添加（备份 {MAIN}.bak-mouse2）')
    print('运行 deskwidgets quit && deskwidgets run 生效。')


if __name__ == '__main__':
    main()
