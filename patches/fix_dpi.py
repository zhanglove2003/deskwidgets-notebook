#!/usr/bin/env python3
"""DeskWidgets HiDPI 修复补丁。

问题：conky 会按 Xft.dpi（200% 缩放屏 = 192）把窗口内容放大 2 倍渲染，
但 DeskWidgets 服务端按物理像素（2560）规划网格，两边坐标系差了 2 倍——
网格实际渲染宽度超出屏幕，右侧约一半的格子永远放不进去，拖过去就被弹回。

修复：服务端全部改用"逻辑像素"（物理 ÷ DPI 倍数）：
  1. x11.py    新增 dpi_factor()，从 RESOURCE_MANAGER 读 Xft.dpi
  2. service.py 网格按逻辑屏幕尺寸计算
  3. service.py 位置读取 ÷ dpi，窗口移动 × dpi
备份：*.bak-dpi
"""
import shutil
import sys

X11 = '/usr/share/deskwidgets/deskwidgets/x11.py'
SVC = '/usr/share/deskwidgets/deskwidgets/service.py'

DPI_METHOD = '''
    def dpi_factor(self):
        """conky scales its window by Xft.dpi / 96; return that factor (1.0 at 96 dpi)."""
        try:
            import subprocess
            out = subprocess.run(['xrdb', '-q'], capture_output=True, text=True, timeout=5).stdout
            for line in out.splitlines():
                if line.strip().startswith('Xft.dpi'):
                    dpi = float(line.split(':', 1)[1].strip() or 96)
                    if dpi > 0:
                        return dpi / 96.0
        except Exception:
            pass
        return 1.0
'''

SVC_DPI_INIT = '''        self.screen = self.x.screen_size()
        self.dpi = self.x.dpi_factor()   # fix_dpi: conky renders at Xft.dpi/96 ×
        self.load_settings()'''

SVC_GRID = '''        self.grid = Grid(*(round(v / self.dpi) for v in self.screen), self.settings)   # fix_dpi: logical screen'''

SVC_POLL_OLD = '''            pos = self.x.position(r.window)
            if pos is None:
                r.window = None
                continue'''
SVC_POLL_NEW = '''            pos = self.x.position(r.window)
            if pos is None:
                r.window = None
                continue
            if self.dpi != 1:   # fix_dpi: X reports physical px, grid works in logical px
                pos = (pos[0] / self.dpi, pos[1] / self.dpi)'''

SVC_MOVE_OLD = '''        if r.window is not None and r.offset is not None:
            self.x.move(r.window, x + r.offset[0], y + r.offset[1])'''
SVC_MOVE_NEW = '''        if r.window is not None and r.offset is not None:
            self.x.move(r.window, round((x + r.offset[0]) * self.dpi), round((y + r.offset[1]) * self.dpi))   # fix_dpi'''


def patch(path, subs, marker='fix_dpi'):
    with open(path, encoding='utf-8') as f:
        src = f.read()
    if marker in src:
        print(f'– {path} 已打过补丁，跳过')
        return True
    ok = True
    for old, new in subs:
        if old not in src:
            print(f'  ⚠ {path} 未找到锚点: {old[:50]!r}')
            ok = False
            continue
        src = src.replace(old, new, 1)
    if not ok:
        return False
    shutil.copy2(path, path + '.bak-dpi')
    with open(path, 'w', encoding='utf-8') as f:
        f.write(src)
    print(f'✔ {path} 已修复（备份 {path}.bak-dpi）')
    return True


def main():
    ok1 = patch(X11, [
        ("    def screen_size(self):", DPI_METHOD + '\n    def screen_size(self):'),
    ])
    ok2 = patch(SVC, [
        ('        self.screen = self.x.screen_size()\n        self.load_settings()',
         SVC_DPI_INIT + '\n        self.load_settings()'),
        ('        self.grid = Grid(*self.screen, self.settings)', SVC_GRID),
        (SVC_POLL_OLD, SVC_POLL_NEW),
        (SVC_MOVE_OLD, SVC_MOVE_NEW),
    ])
    if not (ok1 and ok2):
        print('有锚点未命中，请把本输出发给助手')
        sys.exit(1)
    print('完成！运行 deskwidgets quit && deskwidgets run 重启服务。')


if __name__ == '__main__':
    main()
