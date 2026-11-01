#!/usr/bin/env python3
"""DeskWidgets 汉化补丁第二部分：widget 侧 (engine/lib.lua)。

- 让 MAC_LANG=zh 能传到 widget
- 星期/月份表加中文
- L.tr 加中文翻译表（约 120 条 widget 文本）
所有修改先备份为 *.bak-zh2。
"""
import shutil
import sys

LIB = '/usr/share/deskwidgets/engine/lib.lua'
BAK = '.bak-zh2'

ZH_LANG_FIX = """local _ml = env('MAC_LANG')
L.LANG = (_ml == 'en' or _ml == 'zh') and _ml or 'uk'"""

ZH_TR_FIX = """local ZHW = {
    ['~1h'] = '约 1 小时', ['~1m'] = '约 1 分钟',
    ['%dh %dm'] = '%d小时%d分', ['%dd %dh'] = '%d天%d小时', ['%dm'] = '%d分钟',
    ['in %dd %dh'] = '%d天%d小时后', ['in %dh %dm'] = '%d小时%d分后', ['in %dm'] = '%d分钟后',
    [' d'] = ' 天', ['h'] = '小时', [' min'] = ' 分钟', [' wk '] = ' 周 ', ['wk '] = '周 ',
    ['ago'] = '前', [' left'] = ' 剩余', ['until '] = '直到 ', ['for '] = '持续 ',
    ['in '] = '还有 ', ['of '] = ' / ', [' · all day'] = ' · 全天', [' · asleep'] = ' · 休眠',
    [' · seen '] = ' · 看过 ',
    ['All devices known'] = '已识别所有设备', ['Anime'] = '动漫',
    ['Battery'] = '电池', ['cache '] = '缓存 ', ['Charged'] = '已充满', ['Charging'] = '充电中',
    ['Choose a picture'] = '选择一张图片', ['date unknown'] = '日期未知',
    ['Disk'] = '磁盘', ['Disks'] = '磁盘', ['Docker is not available'] = 'Docker 不可用',
    ['Ep. '] = '第 ',
    ['Events from GNOME calendars (Google, local)'] = '来自 GNOME 日历的事件（Google、本地）',
    ['feels '] = '体感 ', ['Full in '] = '约 ',
    ['Good afternoon'] = '下午好', ['Good evening'] = '晚上好', ['Good morning'] = '早上好',
    ['Headphones'] = '耳机', ['Home'] = '主目录',
    ['H:'] = '最高:', ['°  L:'] = '°  最低:',
    ['Install nmap to watch the network'] = '安装 nmap 以监控网络',
    ['load '] = '负载 ', ['Loading…'] = '加载中…',
    ['Loading from AniList…'] = '正在从 AniList 加载…', ['Loading weather…'] = '正在加载天气…',
    ['Memory'] = '内存', ['Mouse'] = '鼠标',
    ['Mouse: needs access — deskwidgets doctor'] = '鼠标：需要权限 — 请运行 deskwidgets doctor',
    ['NBU rates'] = 'NBU 汇率', ['Network'] = '网络', ['New Year'] = '新年',
    ['No battery found'] = '未找到电池', ['No containers'] = '没有容器',
    ['no data'] = '无数据', ['Note'] = '便签', ['Nothing this week'] = '本周没有日程',
    ['Not playing'] = '未在播放', ['now'] = '现在', ['Now'] = '现在',
    ['offline'] = '离线', ['Olivia’s birthday'] = 'Olivia 的生日',
    ['On battery'] = '使用电池', ['online: '] = '在线: ', ['out now'] = '已播出',
    ['Partly cloudy'] = '多云', ['Paused'] = '已暂停', ['peak '] = '峰值 ',
    ['Playing'] = '正在播放', ['Play some music'] = '播放点音乐吧', ['Plugged in'] = '已接通电源',
    [' processes'] = ' 个进程', ['Processor'] = '处理器', ['Project meeting'] = '项目会议',
    ['RAM'] = '内存', ['Received: '] = '接收: ', ['right-click for settings'] = '右键打开设置',
    [' running'] = ' 运行中', ['Scanning the local network…'] = '正在扫描局域网…',
    ['Sent: '] = '发送: ', ['Spanish class'] = '西班牙语课',
    ['swap'] = '交换', ['Swap'] = '交换分区', ['System'] = '系统',
    ['Team stand-up'] = '团队站会', ['Temperature'] = '温度', ['Time to sleep'] = '该睡觉了',
    ['Today'] = '今天', ['Today!'] = '今天！', ['Tomorrow'] = '明天',
    ['Unknown device'] = '未知设备', ['Unknown devices: '] = '未知设备: ',
    ['Untitled'] = '无标题', ['Up next'] = '接下来', ['week '] = '本周 ',
    ['World clock'] = '世界时钟', ['Yesterday'] = '昨天',
}

function L.tr(uk, en)
    if L.LANG == 'zh' then return ZHW[en] or en end
    return (L.LANG == 'en' and en) or uk
end"""

ZH_WD = """    zh = { caps = { '星期日', '星期一', '星期二', '星期三', '星期四', '星期五', '星期六' },
           cap = { '星期日', '星期一', '星期二', '星期三', '星期四', '星期五', '星期六' },
           short = { '日', '一', '二', '三', '四', '五', '六' },
           head = { '一', '二', '三', '四', '五', '六', '日' },
           month_gen = { '1月', '2月', '3月', '4月', '5月', '6月', '7月',
                         '8月', '9月', '10月', '11月', '12月' },
           month = { '一月', '二月', '三月', '四月', '五月', '六月', '七月',
                     '八月', '九月', '十月', '十一月', '十二月' } },
}
local wd = WD[L.LANG] or WD.uk"""

DAY_MONTH_OLD = """function L.day_month(t)
    if L.LANG == 'en' then return L.MONTH[t.month] .. ' ' .. t.day end
    return t.day .. ' ' .. L.MONTH_GEN[t.month]
end"""

DAY_MONTH_NEW = """function L.day_month(t)
    if L.LANG == 'zh' then return t.month .. '月' .. t.day .. '日' end
    if L.LANG == 'en' then return L.MONTH[t.month] .. ' ' .. t.day end
    return t.day .. ' ' .. L.MONTH_GEN[t.month]
end"""


def main():
    with open(LIB, encoding='utf-8') as f:
        src = f.read()

    if "ZHW" in src:
        print('lib.lua 已打过补丁，跳过')
        return

    subs = [
        # 1. 语言透传：zh 不再被强制变成 uk
        ("L.LANG = env('MAC_LANG') == 'en' and 'en' or 'uk'", ZH_LANG_FIX),
        # 2. L.tr 支持中文
        ("function L.tr(uk, en) return (L.LANG == 'en' and en) or uk end", ZH_TR_FIX),
        # 3. 星期/月份表：加 zh，并兜底防 nil 崩溃
        ("}\nlocal wd = WD[L.LANG]", ZH_WD),
        # 4. 日期格式：11月1日
        (DAY_MONTH_OLD, DAY_MONTH_NEW),
    ]

    ok = True
    for old, new in subs:
        if old not in src:
            print(f'  ⚠ 未找到锚点: {old[:50]!r}')
            ok = False
            continue
        src = src.replace(old, new, 1)

    if not ok:
        print('有锚点未命中，未写入任何修改')
        sys.exit(1)

    shutil.copy2(LIB, LIB + BAK)
    with open(LIB, 'w', encoding='utf-8') as f:
        f.write(src)
    print(f'✔ {LIB} 汉化完成（备份 {LIB}{BAK}）')


if __name__ == '__main__':
    main()
