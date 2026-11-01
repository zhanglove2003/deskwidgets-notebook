# DeskWidgets 定制化项目 · 交接文档

> 最后更新：2026-11-01 20:30 ｜ 主机：Ubuntu 24.04.5 / GNOME / X11 ｜ 屏幕：2560×1440 @200% 缩放（Xft.dpi=192，逻辑 1280×720）

---

## 一、项目是什么

在 Ubuntu GNOME 桌面上用 [DeskWidgets v2.0.0](https://github.com/T0ks1k24/DeskWidgets)（conky 1.19 + Lua 5.3 + cairo）搭仿 Apple 磁贴。

**本轮完成的两块工作：**

1. **相册升级为「图文笔记」**：章节 + 图片 + 正文，点击卡片打开 GTK4 编辑器；笔记持久化在 `~/.local/share/deskwidgets/notebooks/`。
2. **布局改为自由摆放**：去掉网格，绝对坐标 + 磁吸（屏幕边距、其他组件边/中线）；滚轮拖手柄可逐个调整卡片大小。

**当前桌面实例（`deskwidgets list`，逻辑坐标）：**

| 实例 | 类型 | 尺寸 | 位置 |
|---|---|---|---|
| weather | 天气 | 308×170 | (972, 44) |
| system | 系统监控 | 324×122 | (932, 230) |
| battery | 电池 | 120×138 | (90, 44) |
| album | 图文笔记 | 292×154 | (964, 368) |
| translator | 实时翻译 | 244×122 | (1036, 368) |

> 用户在本轮验收中自行移除了 note（便签）与 calendar（日历），并调整了各卡片尺寸/位置。**不要在未询问的情况下恢复这两个组件或改动尺寸。**

---

## 二、文件地图

| 路径 | 内容 |
|---|---|
| `~/Downloads/deskwidgets-pkg/` | 补丁脚本、实施计划、本交接文档、回滚备份 |
| `~/.config/deskwidgets/layout.json` | 布局 v4：每个实例的 `x/y/w/h`（逻辑像素）。⚠ 只能在服务停止时改 |
| `~/.config/deskwidgets/settings.json` | 全局设置（language=zh、字体、`margin_side=24`、`margin_top=44`、`margin_bottom=88`、`gap=16`） |
| `~/.config/deskwidgets/widgets/album/` | 图文笔记 widget：`widget.json`、`widget.lua`、`notebook.py`、`editor.py`、`topng.py` |
| `~/.config/deskwidgets/widgets/translator/` | 实时翻译 widget（未改动） |
| `~/.local/share/deskwidgets/notebooks/<实例hex>/` | **笔记主数据**：`notebook.json`、`view.json`、`images/` |
| `/run/user/1000/deskwidgets/album-<实例hex>/` | 运行时快照与状态：`snapshot/`、`size.txt`、`view-path.txt`、`refresh`、`error.txt` |
| `/run/user/1000/deskwidgets/opts/<id>` | 每个实例的 widget 选项（服务生成） |
| `/run/user/1000/deskwidgets/img/` | topng.py 的 PNG 转换缓存（可安全删除，会自动重建） |
| `/usr/share/deskwidgets/` | 系统文件（服务、引擎、扩展）。补丁备份为 `*.bak-*` |
| `~/Pictures/相册/` | 旧相册的图片来源，仅用于**首次导入** |

---

## 三、图文笔记（album）

### 3.1 卡片交互

- **滚轮**（鼠标悬停在图片/正文区域）：上/下翻页，只在**当前章节**内循环。
- **点击左上角章节名**：弹出章节菜单；在菜单上滚动可翻菜单。
- **点击底部 ‹ / ›**：上一页 / 下一页。
- **点击卡片其他区域**：打开该条目的编辑器（GTK4）。
- 自动播放（`autoplay>0` 时）也只在当前章节内。
- 右中 / 底中 / 右下三个隐藏手柄：把鼠标放在手柄上滚动，可改卡片宽 / 高 / 两者（16 逻辑像素一格）。

### 3.2 数据格式（持久数据）

`notebook.json`：

```json
{
  "version": 2,
  "revision": 5,
  "chapters": [{"id": "ch-…", "title": "未分类"}],
  "entries": [{
    "id": "entry-…", "chapter_id": "ch-…",
    "title": "01-山与月", "order": 0,
    "cover": "images/cover-….png",
    "blocks": [
      {"type": "text", "text": "第一段"},
      {"type": "image", "image": "images/body-….png"},
      {"type": "text", "text": "图片下方文字"}
    ]
  }]
}
```

- `blocks` 按阅读顺序保存正文：连续文字为一个 `text` 块，插图为一个 `image` 块；图片文件都在 `images/` 下。
- `cover` 是显式封面，可为空；**为空时卡片自动使用正文第一张图片**，正文无图才不显示图片区。
- `revision` 每次保存 +1，用于编辑冲突检测（`fcntl` 锁 + 原子替换）。
- `view.json` 只存 `{version, chapter_id, entry_id}`，即当前章节与条目；卡片翻页只写这个小文件。
- v1 数据（`image` + `body`）在首次读取时自动迁移：`image → cover`，`body → 一个 text 块`，revision +1。

### 3.3 快照协议（Python → Lua，只读）

每次准备（`prepare`）在 `RUN/album-<hex>/snapshot/g-<ms>-<pid>/` 生成一代快照，`snapshot/current` 写换代目录名；Lua 每秒最多读一次。

```
snapshot/<gen>/
  generation  chapter.txt  chapter_id  count  selected
  chapters/count, chapters/<n>/{id,title.txt}
  entries/<n>/{id,title.txt,excerpt.txt,has-cover,cover.png}
```

- `has-cover` = `1/0`，决定卡片是否显示封面区；无封面时摘录占满。
- `cover.png` 只转换封面这一张（显式封面或正文第一张图）：当前、下一条、上一条优先生成；`current` 切换后继续转换剩余条目。正文其他插图不转换，卡片不使用。
- 清理只保留当前代 + 上一代，避免运行目录膨胀。
- `size.txt` 记录上次准备的图片框物理尺寸；尺寸变化时 Lua 自动重新 `prepare`。
- `refresh`：编辑器保存后写入该标记，卡片看到后强制重新 `prepare`。
- 笔记库首次不存在时，`folder` 选项指向的目录会导入一次（按文件名排序，标题=去扩展名），之后库内数据为准。**以后新增图片请在编辑器里「选择图片…」**。

### 3.4 编辑器（GTK4）

- 每个实例单实例运行（`Gtk.Application` + `HANDLES_COMMAND_LINE`）；重复点击卡片会复用窗口并跳到对应条目。
- 功能：章节下拉 / 新建 / 重命名 / 删除（删除章节时条目移入「未分类」）；条目列表、标题、**条目所属章节下拉**（保存后条目移动到新章节）、封面选择/清除与缩略图、正文图文混排、保存、删除条目。
- 正文是所见即所得：工具栏「插入图片…」把图片插到光标处；在正文里 **Ctrl+V** 可粘贴截图或文字；从文件管理器**拖拽**图片到正文也会插到释放位置。图片可像字符一样删除。
- **双击图片或封面缩略图**：打开应用内大图窗（黑底、初始按屏幕 90% 等比显示）；滚轮缩放（原图 10%–800%），按住拖动平移；`Esc`、双击大图或「关闭」退出。大图直接读 `images/` 原图。
- 未保存修改：切换条目 / 关窗会提示；保存冲突（revision 不匹配）会提示重新载入。
- `Esc` = 关窗（有未保存提示）。
- 选封面/插图会把文件**复制**进 `notebooks/<hex>/images/`，不移动原文件；清除封面或删除插图只删引用，不删库内文件。

### 3.5 迁移记录

两层迁移，均不复制/删除用户图片：

1. **旧相册 → 笔记库**（首次 `prepare`）：扫描 `folder`（默认 `~/Pictures/相册`），复制图片进 `notebooks/<hex>/images/`，生成单章节「未分类」与条目（标题 = 文件名去扩展名）；尝试从旧 `RUN/selected.txt` 或 `album-<hex>.idx` 恢复当前条目。
2. **笔记 v1 → v2**（2026-11-01）：`image → cover`，`body → [{"type":"text","text":body}]`，revision +1。迁移前备份：
   - `notebooks/616c62756d/notebook.v1.json`
   - `notebooks/616c62756d/images.v1.list`
   - `widgets/album/editor.v1.py`

### 3.6 布局与缩放

- `layout.json` 版本 4，字段：`id/type/size/style/accent/options/x/y/w/h`（逻辑像素）。`grid.json` 已废弃，服务启动时会删除。
- 自由摆放：拖动后磁吸到「屏幕边距 24」「其他组件的左右/上下边 + gap 16」「组件中线」；`SNAP_PX=12` 逻辑像素内生效。
- 调整大小：Lua 在把手上滚动，按 16 逻辑像素/格写 `RUN/resize-<实例hex>` = `"w h"`；服务校验 `MIN_W=120 / MIN_H=100`、限制在屏幕内、重启该 conky 并写回 `layout.json`。
- 启动位置校正：WM 允许的误差 `OFFSET_LIMIT=4` 逻辑像素；超出则最多重试 `REPOSITION_TRIES=3` 次。仍失败时**采纳窗口实际位置**（回写 `layout.json`），避免「布局坐标」与屏幕显示长期不一致；不再有永久冻结。
- 位置边界按「窗口完整在屏内」限制：卡片四边至少离屏幕边 16 逻辑像素（即窗口的透明内边距），宽高上限为 `屏幕 - 32`。这样 WM 不会再把贴边窗口整体推开。
- 屏幕右边距由 `settings.margin_side=24`（逻辑）= 48 物理像素保证（拖动吸附）；卡片窗口自身另有 16 逻辑像素透明内边距。

---

## 四、实时翻译（translator，未改动，保留说明）

- **复制即翻译**：`fetch.py` 每 3s 读剪贴板（xclip），变化才翻译，写 `RUN/trans-<id>`。
- **模式**：normal（谷歌 gtx）/ camel / pascal / snake / upper / custom。
- **AI**：OpenAI 兼容 `/chat/completions`；模型名留空则 GET `/models` 自动选。
- **单击磁贴 → 快速输入窗**（GTK4）；复制结果有防回环哈希。
- 错误红字显示在磁贴上。

---

## 五、发布检查结果（2026-11-01）

- ✅ `notebook.py` / `editor.py` / `topng.py`：`python3 -m py_compile` 通过。
- ✅ `layout.json`、`notebook.json`、`view.json`：`python3 -m json.tool` 通过。
- ✅ Lua：本机无 `luac`，用离屏预览（conky 真实加载 `lib.lua` + `widget.lua`）验证；修复后无 Lua 报错。
- ✅ 离屏验证：有图卡片、无图长正文（CJK 逐字换行）、章节过滤（1/1）均正常。
- ✅ 编辑器实机打开验证：章节行、条目列表、标题、图片预览（限高 190）、正文编辑区、保存/删除按钮布局正常。
- ✅ 完整重启：`deskwidgets quit` → 5 个 conky 重新拉起，`deskwidgets list` 与 `layout.json` 一致；实际窗口坐标逐一对上（误差仅 WM 装饰 ≤4 逻辑像素），日志无「keeps placing」告警；相册复用当前快照，无需重复准备。
- ✅ 日志无 Python traceback；只有 conky 的 `k10temp/amdgpu` 设备解析提示。
- ✅ 编辑器保存链路：用户在编辑器里改了标题与正文并保存（revision 1→3），卡片在下一次刷新后显示新标题、正文和对应图片。
- ✅ 笔记 v2 迁移：v1→v2 后 revision 4，3 个条目的封面与正文均保留；`notebook.v1.json` 已备份。
- ✅ 卡面三形态离屏验证：显式封面、无封面自动取正文第一图、无图长正文，均正确。
- ✅ 编辑器 v2 实机：条目所属章节下拉、封面行与缩略图、插入图片工具栏、图文正文区均正常。
- ✅ 章节移动：用户实际操作并保存成功（revision 4→5，条目从「未分类」移动到新章节「FreeRTOS基础」）。
- ✅ 大图窗：用隔离实例打开查看窗并截图，图片正常显示、标题栏含文件名/缩放百分比/关闭按钮；黑底与初始 90% 适配正常。
- ⏳ 仍待实操验收：双击图片打开大图窗与滚轮缩放/拖动、Ctrl+V 粘贴截图、拖拽插图、滚轮翻页手感、章节菜单点击、保存冲突提示、重启后阅读位置。

---

## 六、常用命令

```bash
deskwidgets list          # 实例、尺寸、逻辑坐标
deskwidgets types         # 所有可用类型（"我的"= 自研）
deskwidgets reload        # 重读 widget 文件夹并重启所有 conky（改 lua 后用）
deskwidgets quit          # 停服务；确认进程退出后再改 layout.json
nohup deskwidgets run >/tmp/deskwidgets.log 2>&1 &   # 启动
deskwidgets gallery       # 图库（添加/删除/设置）
deskwidgets configure <id># 打开某实例的设置
deskwidgets preview album --lang zh -o /tmp/a.png    # 离屏预览
```

日志：`/tmp/deskwidgets.log`。注意：conky 的 **stdout 被重定向到 /dev/null**，`print` 出来的 Lua 错误看不到；排查时用离屏预览（手动起 conky 捕获 stdout），或临时改服务的重定向。

---

## 七、踩坑备忘（本轮新增）

1. **Lua 的 `gsub` 返回两个值**：`tonumber(trim(s))` 会把替换次数当成进制参数而报 `base out of range`。`trim()` 必须用括号包住返回值。
2. **中文没有空格**：原 `L.wrap` 只按空白断词，整段中文变成一个超长词后被省略号截断。`engine/lib.lua` 已加入「超宽词按 UTF-8 字符断行」，翻译/便签的中文同样受益。
3. **无图条目**：快照必须有 `has-image` 标记；否则 `e.image == nil` 与空字符串比较会误判为「有图待转换」。
4. **HiDPI 绘制**：`main.lua` 必须 `cairo_scale(SCALE * MAC_DPI)`；漏掉会得到半尺寸卡片（本轮已修）。
5. **GApplication ID**：`application_id` 每个段不能以数字开头；实例 hex 前要加字母（如 `n` + hex）。
6. **Gtk.Picture 会按原图比例索要高度**：放在纵向布局里要用限高容器（`ScrolledWindow` + `set_size_request(-1,190)`）夹住，否则正文区被挤没。
7. **conky 鼠标坐标是物理像素**：main.lua 里先除以 `SCALE*DPI`；widget 内区域用卡片相对坐标。
8. **root 操作**：本机 `sudo` 无 askpass、`pkexec` 在 no_new_privs 下直接失败；用 `systemd-run --user --unit=… --wait --collect pkexec …`（会弹一次图形授权）。
9. **截图**：`org.gnome.Shell.Screenshot` 被拒；用 `ffmpeg -f x11grab -video_size 2560x1440 -i :0.0` 抓合成后的桌面。`xwd -id` 抓 ARGB 窗口会拿到未合成像素，不可靠。
10. **改文件范围**：只改 widget → `deskwidgets reload`；改 `/usr/share/deskwidgets`（service/lib/main）→ `quit && run`。
11. **贴边卡片会被 WM 推开**：conky 窗口 = 卡片 + 16 逻辑像素透明边；卡片若贴到屏幕右缘，窗口越界 16px，mutter 会把整个窗口拉回屏内，视觉上卡片左移。服务现在按「窗口完整在屏内」限制 `x/y/w/h`（四边留 16）。
12. **WM 不听话时不要冻结组件**：旧实现失败三次后永久 `frozen`，用户之后拖拽也不会保存。现改为采纳实际位置并继续跟踪；排查位置问题时先看 `layout.json` 与实际窗口坐标是否一致。

---

## 八、历史补丁清单（重装系统后按序重放）

| 脚本 | 作用 | 改的文件 |
|---|---|---|
| `zh_patch.py` | UI 汉化（+语言选项"中文"） | i18n.py, settings.py, gallery.py, cli.py, note/widget.json |
| `zh_patch2.py` | widget 侧汉化 | engine/lib.lua |
| `zh_patch3.py` | 天气描述中文化 | widgets/weather/fetch.py |
| `fix_dpi.py` | HiDPI 逻辑像素修复 | x11.py, service.py |
| `fix_scroll.py` | 滚轮事件 | engine/main.lua |
| `fix_mouse2.py` | 鼠标事件全量透传 | engine/main.lua |

> 本轮对 `/usr/share/deskwidgets` 的改动（service/grid/engine/x11/cli、engine/main.lua、engine/lib.lua、extension.js）已直接写盘，旧文件保留为 `*.bak-*`。

---

## 九、回滚

完整备份：`/home/snow/Downloads/deskwidgets-pkg/backup-20261101-194321/`

```
config/config.tar.gz   # 备份时的 ~/.config/deskwidgets（旧版 album、旧 layout.json）
system/system.tar.gz   # 备份时的 /usr/share/deskwidgets（旧服务/引擎/扩展）
evidence/              # 备份时的 list/窗口/相册进度证据
```

步骤：

```bash
deskwidgets quit                       # 1. 停服务并确认退出
cd ~/Downloads/deskwidgets-pkg/backup-20261101-194321
tar -xzf config/config.tar.gz -C ~     # 2. 还原配置（旧相册、旧布局）
# 3. 还原系统文件需要 root：
#    systemd-run --user --unit=dw-restore --wait --collect \
#      pkexec tar -xzf "$PWD/system/system.tar.gz" -C /
nohup deskwidgets run >/tmp/deskwidgets.log 2>&1 &
```

注意：

- 还原 config 会把布局带回**网格时代**，并丢失本轮用户对尺寸/位置的调整（note/calendar 会回来）。若只想回滚笔记功能、保留当前布局，不要解压其中的 `layout.json`，只还原 `/usr/share` 与 `widgets/album`。
- **保留 `~/.local/share/deskwidgets/notebooks/`**：里面是用户写的笔记与图片副本，回滚旧相册不影响它们，也不会删除原图片。
- 只回滚 v2 图文功能：`cp notebook.v1.json notebook.json`（会丢失 v2 之后的新增/移动），`cp editor.v1.py editor.py`，再 `deskwidgets reload`。图片文件不删。
- 回滚后需在本文件记录：哪些功能已回滚、哪些持久数据仍在。

---

## 十、待用户验收 / 后续可做

用户实操清单（未反馈"通过"前不要标为完成）：

1. 滚轮向下/向上翻页，连续多次是否即时响应（重点：切换条目不再等数秒）。
2. 在正文中插入图片（按钮 / Ctrl+V / 拖拽），再删掉一张，保存后重开顺序与内容一致。
2b. 双击正文图片/封面缩略图：大图窗能打开、滚轮缩放、拖动平移，Esc/双击可关闭。
3. 给条目设置/清除封面；不设封面时卡片是否自动显示正文第一张图。
4. 用「条目所属章节」把条目移到另一章，保存后旧章节不再显示、新章节出现。
5. 中文长正文与多图文章保存后卡片有封面 + 摘录，重开编辑器能读完整内容。
6. 空章节、无图条目、文件名含空格；错误提示是否清楚。
7. `reload` 与完整退出重开后，位置/尺寸/章节/条目/正文块顺序保持。
8. 翻译、天气、系统、电池仍正常。

后续可选：章节菜单键盘导航、编辑器记住窗口大小、图片拖拽导入、笔记全文搜索。
