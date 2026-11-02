#!/usr/bin/env python3
"""DeskWidgets v2.0.0 中文汉化补丁。

修改 /usr/share/deskwidgets/deskwidgets/ 下的四个文件 + note 小组件的默认文本。
所有被修改的文件都会先备份为 *.bak-zh，可随时还原。
"""
import re
import shutil
import sys

BASE = '/usr/share/deskwidgets/deskwidgets'
WIDGETS = '/usr/share/deskwidgets/widgets'
BAK = '.bak-zh'

ZH = {
    # --- 图库 / 通用 ---
    'Add': '添加',
    'Add to the desktop': '添加到桌面',
    'Already exists: ': '已存在：',
    'About': '关于',
    'Anime': '动漫',
    'Appearance': '外观',
    'Arrange on the grid': '按网格排列',
    'pack widgets onto the grid': '将小组件排列到网格',
    'batteries': '电池',
    'Blue': '蓝色',
    'built-in': '内置',
    'Cancel': '取消',
    'Check dependencies': '检查依赖',
    'check dependencies': '检查依赖',
    'Choose…': '选择…',
    'Clear': '清除',
    'Colour': '颜色',
    'Create': '创建',
    'Create a widget…': '创建小组件…',
    'create your own widget': '创建自己的小组件',
    'Default': '默认',
    'Desktop widgets': '桌面小组件',
    'DeskWidgets': 'DeskWidgets',
    'Each widget’s own': '各小组件自定',
    'Font': '字体',
    'font ': '字体 ',
    'Glass': '毛玻璃',
    'Graphite': '石墨',
    'Green': '绿色',
    'Grid': '网格',
    'Hotkey Super+Alt+W': '快捷键 Super+Alt+W',
    'Icons are built in': '图标已内置',
    'Images': '图片',
    'Indigo': '靛蓝',
    'Information': '信息',
    'Language': '语言',
    'Large': '大',
    'LAN watch': '局域网监视',
    'Light': '浅色',
    'Look': '外观',
    'Medium': '中',
    'Menu': '菜单',
    'Mint': '薄荷',
    'My widgets': '我的小组件',
    'My widgets folder': '我的小组件文件夹',
    'No card · dark text': '无卡片 · 深色文字',
    'No card · light text': '无卡片 · 浅色文字',
    'none': '无',
    'no access — the udev rule is needed': '无权限 — 需要 udev 规则',
    'no answer': '无响应',
    'No such widget: ': '没有这个小组件：',
    'No widgets yet': '还没有小组件',
    'New widget': '新建小组件',
    'On the desktop': '在桌面上',
    'Open the "Add" tab.': '请打开「添加」标签页。',
    'Opens this window': '打开此窗口',
    'optional': '可选',
    'Options': '选项',
    'Orange': '橙色',
    'Other': '其他',
    'Personal': '个人',
    'Pink': '粉色',
    'Purple': '紫色',
    'Red': '红色',
    'Refresh thumbnails': '刷新缩略图',
    'refresh gallery thumbnails': '刷新图库缩略图',
    'Reload widgets': '重载小组件',
    're-read widget folders and restart': '重新读取小组件文件夹并重启',
    'Remove': '移除',
    'remove a widget': '移除小组件',
    'Remove from the desktop': '从桌面移除',
    'Rendering failed': '渲染失败',
    'Run the service (default)': '运行服务（默认）',
    'run the service (default)': '运行服务（默认）',
    'Sakura': '樱花',
    'Settings': '设置',
    'settings of a widget': '小组件设置',
    'Size': '尺寸',
    'Small': '小',
    'Sides': '两侧',
    'Start at login': '登录时启动',
    'start it': '启动它',
    'stop the service': '停止服务',
    'Style': '风格',
    'Style for new widgets': '新小组件的默认风格',
    'System': '系统',
    'Teal': '青色',
    'That widget already exists': '该小组件已存在',
    'The DeskWidgets service did not start': 'DeskWidgets 服务未能启动',
    'Time & date': '时间与日期',
    'Widget size': '小组件大小',
    'Widgets': '小组件',
    'widgets on the desktop': '桌面上的小组件',
    'Your own widgets': '自制小组件',
    'conky with Lua/Cairo': 'conky with Lua/Cairo',
    'a fallback sans-serif will be used': '将使用备用无衬线字体',
    'GNOME grid helper': 'GNOME 网格助手',
    'GNOME only': '仅限 GNOME',
    'only for "Up next"': '仅用于「接下来」',
    'Between widgets': '小组件间距',
    'mouse battery ': '鼠标电量 ',
    ', charging': '，充电中',
    'battery of wireless gaming mice': '无线游戏鼠标电量',
    'asleep or not linked': '休眠或未连接',
    'install conky-all': '请安装 conky-all',
    'needs conky-all': '需要 conky-all',
    'needs the udev rule, run: ': '需要 udev 规则，请运行：',
    'nothing selected': '未选择任何项',
    'open the gallery': '打开图库',
    'render a widget to PNG': '将小组件渲染为 PNG',
    'real data instead of sample data': '使用真实数据而非示例数据',
    'service running': '服务运行中',
    'updates: ': '更新：',
    'add a widget to the desktop': '添加小组件到桌面',
    'all available widgets': '所有可用小组件',
    'autostart, hotkey, grid helper': '自启动、快捷键、网格助手',
    'The GNOME grid helper starts working after you log out and back in.':
        'GNOME 网格助手将在注销并重新登录后生效。',
    'mine': '我的',
    '  · mine': '  · 我的',
    # --- doctor 输出 ---
    'Japanese font (anime widgets)': '日文字体（动漫小组件）',
}

I18N_NEW = '''"""Two-language UI + zh patch: every string is written as tr('Ukrainian', 'English')."""
from . import settings

_lang = None

ZH = ''' + repr(ZH) + '''


def lang():
    global _lang
    if _lang is None:
        _lang = settings.language()
    return _lang


def set_lang(value):
    global _lang
    _lang = value


def tr(uk, en):
    l = lang()
    if l == 'zh':
        return ZH.get(en, en)
    return en if l == 'en' else uk


def loc(value, language=None):
    """A manifest value: plain string, or {"uk": ..., "en": ...}."""
    if isinstance(value, dict):
        l = language or lang()
        return value.get(l) or value.get('en') or value.get('uk') or next(iter(value.values()), '')
    return value
'''


def patch(path, subs, rewrite=None):
    if rewrite is not None:
        shutil.copy2(path, path + BAK)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(rewrite)
        print(f'  ✔ 重写 {path}（备份 {path}{BAK}）')
        return
    with open(path, encoding='utf-8') as f:
        src = f.read()
    if 'zh_patch applied' in src or all(new in src for _, new in subs):
        print(f'  – {path} 已打过补丁，跳过')
        return
    orig = src
    for old, new in subs:
        if old not in src:
            print(f'  ⚠ {path} 中未找到: {old[:60]!r}')
            continue
        src = src.replace(old, new)
    if src != orig:
        shutil.copy2(path, path + BAK)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(src)
        print(f'  ✔ 修改 {path}（备份 {path}{BAK}）')


def main():
    print('开始汉化 DeskWidgets…')

    # 1. i18n.py — 核心：加 zh 分支和翻译表
    patch(f'{BASE}/i18n.py', None, rewrite=I18N_NEW + '\n# zh_patch applied\n')

    # 2. settings.py — 允许语言值 'zh'
    patch(f'{BASE}/settings.py', [
        ("if lang in ('uk', 'en'):", "if lang in ('uk', 'en', 'zh'):  # zh_patch"),
        ("'language': 'auto',        # auto | uk | en",
         "'language': 'auto',        # auto | uk | en | zh  (zh_patch)"),
    ])

    # 3. gallery.py — 语言下拉框加中文
    patch(f'{BASE}/gallery.py', [
        ("langs = [('auto', tr('Як у системі', 'System')), ('uk', 'Українська'), ('en', 'English')]",
         "langs = [('auto', tr('Як у системі', 'System')), ('zh', '中文'), ('uk', 'Українська'), ('en', 'English')]  # zh_patch"),
        ("in ('auto', 'uk', 'en')", "in ('auto', 'zh', 'uk', 'en')  # zh_patch"),
    ])

    # 4. cli.py — --lang 参数允许 zh
    patch(f'{BASE}/cli.py', [
        ("choices=['uk', 'en']", "choices=['uk', 'en', 'zh']  # zh_patch"),
    ])

    # 5. note 小组件的默认文本加中文
    try:
        patch(f'{WIDGETS}/note/widget.json', [
            ('"default": {"uk": "Нотатка", "en": "Note"}',
             '"default": {"uk": "Нотатка", "en": "Note", "zh": "便签"}'),
            ('"en": "Right-click to change the text of this note."',
             '"en": "Right-click to change the text of this note.", "zh": "右键点击便签，即可修改文字。"'),
        ])
    except FileNotFoundError as e:
        print(f'  ⚠ note widget: {e}')

    print('完成！现在运行: deskwidgets reload 让改动生效。')


if __name__ == '__main__':
    sys.exit(main())
