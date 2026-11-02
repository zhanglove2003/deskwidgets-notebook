# 图文笔记 v2 设计（封面 + 图文混排 + 章节移动）

> 2026-11-01 ｜ 目标：把「单图 + 纯文本」的笔记改成类似 B 站笔记的自由图文文章，并支持条目跨章节移动。

---

## 1. 交互目标

1. 编辑器正文是**所见即所得**：文字和图片在同一篇文档里任意穿插，图片插在光标处，删除像删字符一样。
2. 条目可以**移动到其他章节**：编辑器内有「条目所属章节」下拉框，保存后条目出现在新章节。
3. 卡片（292×154）显示**封面 + 标题 + 正文第一段摘录**；封面未设置时自动使用正文第一张图；正文无图才不显示图片区。
4. 插入图片支持三种方式：工具栏选文件、Ctrl+V 粘贴截图、从文件管理器拖拽到正文。

---

## 2. 数据模型（notebook.json version 2）

```json
{
  "version": 2,
  "revision": 4,
  "chapters": [{"id": "ch-...", "title": "未分类"}],
  "entries": [{
    "id": "entry-...",
    "chapter_id": "ch-...",
    "title": "01-山与月",
    "order": 0,
    "cover": "images/cover-...png",
    "blocks": [
      {"type": "text", "text": "第一段"},
      {"type": "image", "image": "images/body-...png"},
      {"type": "text", "text": "图片下方文字"}
    ]
  }]
}
```

- `cover`：显式封面，可为空字符串。
- `blocks`：按阅读顺序保存的文本/图片块，是正文的唯一真源。
- 所有图片文件仍放在 `notebooks/<hex>/images/`，不移动、不删除用户原图。
- 内文插图文件名：`<entry-id>-<时间戳><扩展名>`，避免与封面/其他条目重名。

### 迁移（version 1 → 2）

- `entry.image` → `entry.cover`（为空则保持空）。
- `entry.body` → `blocks = [{"type":"text","text": body}]`；body 为空则 `blocks = []`。
- 迁移在 `load_book` 内一次性完成并 `save_book`（revision +1）；迁移前先备份当前 notebook.json 与 images 清单。
- 迁移不复制、不删除任何图片文件。

---

## 3. 编辑器（editor.py）

### 3.1 布局

- 顶部：章节管理（下拉、新建、重命名、删除）——不变。
- 左侧：当前章节的条目列表。
- 右侧自上而下：
  1. 标题输入框。
  2. 「条目所属章节」下拉框（新）。
  3. 「封面」行：选择封面… / 清除封面 + 小预览（原「选择图片」改为封面）。
  4. 工具栏：插入图片…（新）。
  5. 正文 TextView（图文混排，占用剩余高度，外框标题「正文」）。
  6. 保存 / 删除条目 / 状态文字。

### 3.2 图文混排实现

- 使用 `Gtk.TextBuffer.insert_child_anchor()` + `Gtk.TextView.add_child_at_anchor()` 把 `Gtk.Picture` 嵌入正文。
- 图片显示：按正文宽度等比缩放，最大高度约 260px；用库内图片文件，不产生二次副本。
- 序列化：保存时从头到尾扫描缓冲区，把连续文字收集为 text 块，把锚点收集为 image 块，保持屏幕顺序。
- 反序列化：打开条目时清空缓冲区，按 blocks 依次插入文字和图片锚点。
- 删除图片 = 删除锚点；保存后该图片块消失，磁盘文件保留（不做自动清理）。

### 3.3 插图方式

- **选文件**：`Gtk.FileDialog`，复制进 `images/`，插到当前光标处。
- **粘贴**：拦截 TextView 的 Ctrl+V；剪贴板有图像时保存为 PNG 并插入，没有图像时走普通文字粘贴。
- **拖拽**：TextView 注册 `Gtk.DropTarget`（文件列表），在释放位置插入图片；非图片文件忽略。

### 3.4 章节移动

- 「条目所属章节」下拉框显示全部章节；切换即修改 `entry.chapter_id` 并标记未保存。
- 保存后刷新条目列表：条目从旧章节消失、出现在新章节；写 `refresh` 标记让卡片重新准备。
- 编辑器顶部原有的章节下拉仅作为「浏览哪一章」，与条目的所属章节分开。

### 3.5 保存与冲突

- 沿用 `save_book(expected_revision=...)`、revision 冲突提示、未保存提示、单实例、Esc 关闭。
- 保存内容：title、chapter_id、cover、blocks。

---

## 4. 快照与卡片（notebook.py / widget.lua）

### 4.1 快照（entries/<n>/）

- `id`、`title.txt`、`has-cover`、`cover.png`、`excerpt.txt`。
- 封面来源：`entry.cover`；为空时取 `blocks` 中第一张图片。
- `cover.png` 只转换这一张，尺寸沿用卡片图片框（当前 544×144 物理左右）；正文其他图片不转换，卡片不用。
- `excerpt.txt`：第一个非空 text 块，空白折叠为单空格，最多约 200 字符。
- 删除旧的 `body.txt`、`has-image` 语义（迁移期可短暂保留，发布前清理）。

### 4.2 卡片

- 有封面：封面图 + 标题 + 摘录。
- 无封面（正文无图）：标题 + 摘录，正文占满图片区。
- 翻页、章节菜单、自动播放、点击打开编辑器逻辑不变。
- 内文插图不出现在卡片上（卡面太小，按「封面为主」方案）。

---

## 5. 涉及文件

| 文件 | 改动 |
|---|---|
| `~/.config/deskwidgets/widgets/album/notebook.py` | version 2 模型、迁移、快照 cover/excerpt、章节移动后的 prepare |
| `~/.config/deskwidgets/widgets/album/editor.py` | 图文混排 TextView、封面、插图三方式、所属章节下拉、序列化 |
| `~/.config/deskwidgets/widgets/album/widget.lua` | 读取 cover/excerpt，无图布局，移除 body/has-image |
| `~/.config/deskwidgets/widgets/album/widget.json` | 选项说明更新（folder 仅首次导入、封面/插图在编辑器） |
| `~/Downloads/deskwidgets-pkg/HANDOVER.md` | 数据格式、导入规则、操作说明更新 |
| 备份 | 迁移前的 notebook.json、images 清单、editor.py/widget.lua 副本 |

---

## 6. 验证

1. 数据层：v1 notebook 自动迁移后 revision+1，条目数、封面、正文不变；旧图片仍在。
2. 离屏渲染：有封面卡、无封面但有内文图（自动取第一张）、完全无图卡三种形态。
3. 编辑器实机截图：封面行、所属章节下拉、工具栏、正文内图片顺序正确。
4. 保存后 refresh → 卡片标题/摘录/封面更新；移动章节后旧章节不再显示该条目。
5. 粘贴截图与拖拽文件插入到指定位置；删除图片后保存不再出现。
6. 不做鼠标模拟；滚轮翻页与真实拖拽手感由用户验收。
7. 回滚：恢复备份 notebook.json 与旧 editor.py/widget.lua；图片与笔记不删除。

---

## 7. 风险与边界

- GTK TextView 的 child anchor 在撤销/重做上的行为不保证；先不启用 undo manager，避免图文错位。
- 超大图片（如 4K 截图）在编辑器里需按显示尺寸缩放，避免一次载入过多显存。
- 粘贴的剪贴板图像统一存为 PNG；其他格式在导入时经现有 topng 转换。
- 不做图片说明文字（caption）、图床、富文本样式（粗体/标题层级），本轮范围外。
