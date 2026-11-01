#!/usr/bin/env python3
"""DeskWidgets 引擎补丁：把鼠标滚轮事件转发给 widget。

main.lua 的 conky_mouse 原本只处理左键(1)和右键(3)。
X11 滚轮 = 按钮 4(上)/5(下)，此补丁把它们转发给 widget.scroll(±1)，
供"相册"磁贴切换图片。备份 *.bak-scroll。
"""
import shutil
import sys

MAIN = '/usr/share/deskwidgets/engine/main.lua'

OLD = """        return widget.click(x, y, BASE_W - 2 * L.M, BASE_H - 2 * L.M) and true or false
    end
    return false
end"""

NEW = """        return widget.click(x, y, BASE_W - 2 * L.M, BASE_H - 2 * L.M) and true or false
    end
    -- fix_scroll: forward the mouse wheel (X11 buttons 4/5) to widget.scroll(±1)
    if widget.scroll and (button_is(ev, 4, 'up') or button_is(ev, 5, 'down')) then
        return widget.scroll(button_is(ev, 4, 'up') and -1 or 1) and true or false
    end
    return false
end"""


def main():
    with open(MAIN, encoding='utf-8') as f:
        src = f.read()
    if 'fix_scroll' in src:
        print('main.lua 已打过补丁，跳过')
        return
    if OLD not in src:
        print('  ⚠ 未找到锚点，未做修改')
        sys.exit(1)
    shutil.copy2(MAIN, MAIN + '.bak-scroll')
    with open(MAIN, 'w', encoding='utf-8') as f:
        f.write(src.replace(OLD, NEW, 1))
    print(f'✔ {MAIN} 滚轮支持已添加（备份 {MAIN}.bak-scroll）')
    print('运行 deskwidgets quit && deskwidgets run 生效。')


if __name__ == '__main__':
    main()
