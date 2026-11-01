#!/usr/bin/env python3
"""DeskWidgets 汉化补丁第三部分：天气描述中文化 (widgets/weather/fetch.py)。

wttr.in 的 lang=zh 实际返回英文，此补丁在 LANG=zh 时用本地翻译表转换天气描述。
备份为 fetch.py.bak-zh3。
"""
import shutil
import sys

FETCH = '/usr/share/deskwidgets/widgets/weather/fetch.py'
BAK = '.bak-zh3'

# wttr.in 标准天气描述 → 中文
TABLE = '''ZH_DESC = {
    'Sunny': '晴', 'Clear': '晴', 'Partly cloudy': '多云', 'Cloudy': '多云',
    'Overcast': '阴', 'Mist': '薄雾', 'Fog': '雾', 'Haze': '霾',
    'Patchy rain nearby': '附近有零星降雨', 'Patchy rain possible': '可能零星降雨',
    'Light drizzle': '小雨', 'Patchy light drizzle': '零星小雨',
    'Drizzle': '毛毛雨', 'Heavy drizzle': '大雨', 'Freezing drizzle': '冻毛毛雨',
    'Light rain': '小雨', 'Moderate rain at times': '间歇中雨', 'Moderate rain': '中雨',
    'Heavy rain at times': '间歇大雨', 'Heavy rain': '大雨', 'Light freezing rain': '小雨夹冰',
    'Moderate or heavy freezing rain': '中到大冻雨', 'Light sleet': '小雨夹雪',
    'Moderate or heavy sleet': '中到大雨夹雪', 'Patchy light snow': '零星小雪',
    'Light snow': '小雪', 'Patchy moderate snow': '零星中雪', 'Moderate snow': '中雪',
    'Heavy snow': '大雪', 'Ice pellets': '冰粒', 'Light sleet showers': '小阵性雨夹雪',
    'Moderate or heavy sleet showers': '中到大阵性雨夹雪', 'Light snow showers': '小阵雪',
    'Moderate or heavy snow showers': '中到大阵雪', 'Blowing snow': '吹雪',
    'Blizzard': '暴风雪', 'Patchy snow nearby': '附近有零星降雪', 'Patchy snow possible': '可能零星降雪',
    'Thundery outbreaks possible': '可能有雷阵雨', 'Patchy light rain with thunder': '零星雷阵雨',
    'Moderate or heavy rain with thunder': '雷阵雨', 'Patchy light snow with thunder': '零星雷伴雪',
    'Moderate or heavy snow with thunder': '雷伴大雪', 'Light rain shower': '小阵雨',
    'Moderate or heavy rain shower': '中到大阵雨', 'Torrential rain shower': '暴雨',
    'Light showers of ice pellets': '小冰粒阵雨', 'Freezing fog': '冻雾',
    'Patchy freezing drizzle possible': '可能零星冻毛毛雨',
}

def zh_desc(text: str, lang: str) -> str:
    if lang == 'zh':
        return ZH_DESC.get(text, text)
    return text
'''

OLD = """    desc = (cur.get(f"lang_{LANG}") or [{}])[0].get("value") or cur["weatherDesc"][0]["value"]"""
NEW = """    desc = zh_desc(
        (cur.get(f"lang_{LANG}") or [{}])[0].get("value") or cur["weatherDesc"][0]["value"],
        LANG,
    )"""


def main():
    with open(FETCH, encoding='utf-8') as f:
        src = f.read()
    if 'ZH_DESC' in src:
        print('fetch.py 已打过补丁，跳过')
        return
    if OLD not in src:
        print('  ⚠ 未找到锚点，未做修改')
        sys.exit(1)
    # 翻译表插在 parse_clock 函数定义之前
    anchor = 'def parse_clock('
    if anchor not in src:
        print('  ⚠ 未找到插入点')
        sys.exit(1)
    src = src.replace(anchor, TABLE + '\n\n' + anchor, 1).replace(OLD, NEW, 1)
    shutil.copy2(FETCH, FETCH + BAK)
    with open(FETCH, 'w', encoding='utf-8') as f:
        f.write(src)
    print(f'✔ {FETCH} 天气描述中文化完成（备份 {FETCH}{BAK}）')


if __name__ == '__main__':
    main()
