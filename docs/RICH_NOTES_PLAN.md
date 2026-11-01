# 图文笔记 v2 实施计划（封面 + 图文混排 + 章节移动）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把相册笔记从「单图 + 纯文本」升级为「封面 + 正文自由图文混排」，并支持条目跨章节移动。

**Architecture:** 数据层（notebook.py）升级到 version 2：`cover` + `blocks[]`；编辑器用 GTK4 TextView 子控件锚点实现所见即所得，序列化回 blocks；卡片只读快照里的封面与第一段摘录。

**Tech Stack:** Python 3 / PyGObject 4.14（GTK4）/ Lua 5.3 / cairo / conky 1.19 / Pillow。

**Spec:** `~/Downloads/deskwidgets-pkg/RICH_NOTES_DESIGN.md`

## Global Constraints

- 不添加自动化测试、探针或鼠标模拟；只做语法/加载检查、离屏渲染和用户实操验收。
- 迁移前必须备份 `notebook.json` 与 `images/` 清单；迁移只加字段，不复制/删除用户图片。
- 保持中文 UI 与 200% 缩放（Xft.dpi=192）；卡片坐标是逻辑像素。
- 只改 `~/.config/deskwidgets/widgets/album/` 下的文件；本轮不改 `/usr/share`。
- 持久数据只写 `~/.local/share/deskwidgets/notebooks/<hex>/`；运行缓存只写 `/run/user/1000/deskwidgets/`。
- 项目目录不是 git 仓库，任务末尾用「备份 + 校验」代替 commit。

---

## 文件结构

| 文件 | 职责 |
|---|---|
| `~/.config/deskwidgets/widgets/album/notebook.py` | v2 数据模型、迁移、封面/摘录快照、prepare/select/refresh |
| `~/.config/deskwidgets/widgets/album/editor.py` | 图文混排编辑器、封面、所属章节、选图/粘贴/拖拽 |
| `~/.config/deskwidgets/widgets/album/widget.lua` | 读快照、绘制封面 + 标题 + 摘录 |
| `~/.config/deskwidgets/widgets/album/widget.json` | 选项与说明文案 |
| `~/Downloads/deskwidgets-pkg/HANDOVER.md` | 数据格式、操作、回滚说明 |

---

### Task 1: notebook.py v2 数据模型与迁移

**Files:**
- Modify: `~/.config/deskwidgets/widgets/album/notebook.py`
- Backup: `~/.local/share/deskwidgets/notebooks/616c62756d/notebook.json` → `notebook.v1.json`，并列出 `images/`

**Interfaces:**
- Produces:
  - `VERSION = 2`
  - `migrate_book(book) -> book`
  - `normalize_book(book) -> book`
  - `cover_of(entry) -> str`
  - `excerpt_of(entry, limit=200) -> str`
  - `load_book(root)` 返回已迁移、已规范化的 v2 book
  - entry 字段：`id/chapter_id/title/order/cover/blocks`，block 为 `{"type":"text","text":str}` 或 `{"type":"image","image":str}`

- [ ] **Step 1: 备份用户笔记**

```bash
cd ~/.local/share/deskwidgets/notebooks/616c62756d
cp -a notebook.json notebook.v1.json
ls -l images > images.v1.list
```

- [ ] **Step 2: 在 notebook.py 顶部升级版本并新增迁移/规范化函数**

```python
VERSION = 2
IMAGE_EXTS = {'.png', '.jpg', '.jpeg', '.webp', '.bmp', '.gif', '.tif', '.tiff'}


def migrate_book(book):
    if int(book.get('version') or 1) >= VERSION:
        return book
    for e in book.get('entries', []):
        image = e.pop('image', '')
        body = e.pop('body', '')
        e['cover'] = image or ''
        e['blocks'] = [{'type': 'text', 'text': body}] if body else []
    book['version'] = VERSION
    return book


def normalize_book(book):
    for e in book.get('entries', []):
        e['cover'] = str(e.get('cover') or '')
        blocks = e.get('blocks')
        clean = []
        for b in blocks if isinstance(blocks, list) else []:
            if not isinstance(b, dict):
                continue
            if b.get('type') == 'text' and b.get('text'):
                clean.append({'type': 'text', 'text': str(b['text'])})
            elif b.get('type') == 'image' and b.get('image'):
                clean.append({'type': 'image', 'image': str(b['image'])})
        e['blocks'] = clean
    return book


def cover_of(entry):
    if entry.get('cover'):
        return entry['cover']
    for b in entry.get('blocks') or []:
        if b.get('type') == 'image' and b.get('image'):
            return b['image']
    return ''


def excerpt_of(entry, limit=200):
    for b in entry.get('blocks') or []:
        if b.get('type') == 'text':
            text = ' '.join((b.get('text') or '').split())
            if text:
                return text[:limit]
    return ''
```

- [ ] **Step 3: load_book 内执行迁移并容错**

把 `load_book` 的返回改成：

```python
def load_book(root):
    try:
        with open(os.path.join(root, 'notebook.json'), encoding='utf-8') as f:
            book = json.load(f)
    except (OSError, ValueError):
        return None
    if int(book.get('version') or 1) < VERSION:
        migrate_book(book)
        try:
            book['revision'] = save_book(root, book, expected_revision=book.get('revision'))
        except RevisionConflict:
            book = load_book(root) or book
    return normalize_book(book)
```

- [ ] **Step 4: 用临时实例验证迁移（不动用户数据）**

```bash
cd ~/.config/deskwidgets/widgets/album
python3 - <<'EOF'
import json, os, shutil, sys
sys.path.insert(0, '.')
import notebook as nb
root = nb.book_root('mig-test')
os.makedirs(root, exist_ok=True)
shutil.copy2(os.path.expanduser('~/.local/share/deskwidgets/notebooks/616c62756d/notebook.v1.json'),
             os.path.join(root, 'notebook.json'))
book = nb.load_book(root)
print('version', book['version'], 'rev', book['revision'])
for e in book['entries']:
    print(e['title'][:16], 'cover=', bool(e['cover']), 'blocks=', [b['type'] for b in e['blocks']])
print('excerpt1', nb.excerpt_of(book['entries'][0])[:30])
EOF
```

预期：`version 2`，每个条目有 `cover`，原先有正文的条目含 1 个 `text` 块。验证完删除临时目录：

```bash
rm -rf ~/.local/share/deskwidgets/notebooks/$(python3 -c "print('mig-test'.encode().hex())")
```

- [ ] **Step 5: 语法检查**

```bash
python3 -m py_compile notebook.py && echo OK
```

---

### Task 2: 快照写入封面与摘录

**Files:**
- Modify: `~/.config/deskwidgets/widgets/album/notebook.py`（`_convert` 与 `prepare` 的元数据循环）

**Interfaces:**
- Consumes: `cover_of(entry)`, `excerpt_of(entry)`
- Produces: 每个条目目录含 `id/title.txt/excerpt.txt/has-cover/cover.png`；不再写 `body.txt`

- [ ] **Step 1: 改写 _convert，只转换封面**

```python
def _convert(entry, gen_dir, n, width, height, cache):
    src = cover_of(entry)
    if not src:
        return
    src = os.path.normpath(os.path.join(cache['book_root'], src))
    if not os.path.isfile(src):
        return
    dst = os.path.join(gen_dir, 'entries', str(n), 'cover.png')
    if os.path.exists(dst):
        return
    made = topng.convert(src, os.path.join(cache['run'], 'img'), width, height)
    if not made:
        return
    tmp = dst + f'.{os.getpid()}.tmp'
    shutil.copyfile(made, tmp)
    os.replace(tmp, dst)
```

- [ ] **Step 2: 元数据循环改为封面/摘录**

```python
        for n, e in enumerate(entries, 1):
            d = os.path.join(gen_dir, 'entries', str(n))
            src = cover_of(e)
            has_cover = bool(src) and os.path.isfile(
                os.path.normpath(os.path.join(root, src)))
            _write(os.path.join(d, 'id'), e['id'] + '\n')
            _write(os.path.join(d, 'title.txt'), (e.get('title') or '（无标题）') + '\n')
            _write(os.path.join(d, 'excerpt.txt'), excerpt_of(e) + '\n')
            _write(os.path.join(d, 'has-cover'), '1\n' if has_cover else '0\n')
```

删除原来写 `body.txt` 和 `has-image` 的两行。

- [ ] **Step 3: 在真实实例上生成 v2 快照（Task 1 已备份）**

```bash
cd ~/.config/deskwidgets/widgets/album
python3 notebook.py prepare --instance album --folder '~/Pictures/相册' --width 544 --height 144
G=$(cat /run/user/1000/deskwidgets/album-616c62756d/snapshot/current)
ls /run/user/1000/deskwidgets/album-616c62756d/snapshot/$G/entries/1/
cat /run/user/1000/deskwidgets/album-616c62756d/snapshot/$G/entries/1/excerpt.txt
```

预期：出现 `cover.png`、`excerpt.txt`、`has-cover`，没有 `body.txt`；`notebook.json` 已是 version 2，revision 增加 1。

- [ ] **Step 4: 语法与 JSON 检查**

```bash
python3 -m py_compile notebook.py && python3 -m json.tool \
  ~/.local/share/deskwidgets/notebooks/616c62756d/notebook.json >/dev/null && echo OK
```

---

### Task 3: 卡片绘制封面 + 摘录

**Files:**
- Modify: `~/.config/deskwidgets/widgets/album/widget.lua`
- Modify: `~/.config/deskwidgets/widgets/album/widget.json`

**Interfaces:**
- Consumes: 快照条目字段 `has-cover`、`cover.png`、`excerpt.txt`
- Produces: 卡片无图/有封面两种布局；不再读取 `body.txt`、`has-image`

- [ ] **Step 1: 替换 load_snapshot 的条目字段**

```lua
local has_cover = trim(read_file(d .. '/entries/' .. i .. '/has-cover')) == '1'
es[i] = {id = id,
         title = trim(read_file(d .. '/entries/' .. i .. '/title.txt')),
         cover = has_cover and 'cover.png' or '',
         excerpt = trim(read_file(d .. '/entries/' .. i .. '/excerpt.txt')),
         dir = d .. '/entries/' .. i}
```

- [ ] **Step 2: 删除 body_of/bodies，改用 excerpt**

删掉 `body_of` 与 `bodies` 缓存；`draw_content` 中：

```lua
    if e and surf_draw then
        ...
        zones.open = {x = pad, y = rel_y, w = iw, h = image_h}
    elseif e and e.cover ~= '' then
        L.rrect(cr, x + pad, iy, iw, image_h, 10)
        cairo_set_source_rgba(cr, 1, 1, 1, 0.05); cairo_fill(cr)
        L.font(cr, F.regular, 10); L.set(cr, C.text3)
        L.text(cr, '正在准备封面…', x + pad + iw / 2, iy + image_h / 2, 'c')
        zones.open = {x = pad, y = rel_y, w = iw, h = image_h}
    end

    local ty = iy + ((e and e.cover ~= '') and image_h + 13 or 14)
    if e then
        L.font(cr, F.semibold, 11); L.set(cr, C.text)
        L.text(cr, L.fit(cr, e.title ~= '' and e.title or '（无标题）', iw), x + pad, ty)
        local by = ty + 13
        local lines = body_lines
        if e.cover == '' then
            lines = math.max(1, math.floor((y + h - pad - footer_h - by) / line_h))
        end
        L.font(cr, F.regular, 9.5); L.set(cr, C.text2)
        for i, line in ipairs(L.wrap(cr, e.excerpt or '', iw, lines)) do
            L.text(cr, line, x + pad, by + (i - 1) * line_h)
        end
        zones.open = zones.open or {x = pad, y = rel_y, w = iw, h = math.max(1, ty + 40 - iy)}
    else
        ...
```

`image_surface(e)` 改成：

```lua
local function image_surface(e)
    if not e or e.cover == '' then return nil end
    local path = e.dir .. '/' .. e.cover
    if surf_key ~= path then
        if surf then cairo_surface_destroy(surf) end
        surf, surf_key = nil, path
    end
    if surf then return surf end
    local f = io.open(path, 'r')
    if not f then return nil end
    f:close()
    local s = cairo_image_surface_create_from_png(path)
    if cairo_image_surface_get_width(s) > 0 then surf = s
    else cairo_surface_destroy(s) end
    return surf
end
```

- [ ] **Step 3: 更新 widget.json 文案**

把 description 改为「章节、封面与图文笔记：滚轮翻页，点击编辑」，并在 `fit` 提示里写明「封面按 cover/contain 显示」。

- [ ] **Step 4: 三种卡面离屏验证**

用与之前相同的沙盒方法：创建 `alb-render` 实例，写入 3 个条目（有封面、无封面但有内文图、完全无图），`prepare --width 544 --height 144`，再用 conky 的 `MAC_PREVIEW` + `MAC_DPI=1` 渲染，检查：

```bash
python3 -c "from PIL import Image; im=Image.open('/tmp/alb-render.png'); im.resize((648,372)).save('/tmp/alb-render-v.png')"
```

预期：有封面显示图片 + 标题 + 摘录；无封面但有内文图自动显示第一张图；无图时标题 + 多行摘录占满。验证后删除沙盒实例与目录。

---

### Task 4: 编辑器图文混排 + 封面 + 所属章节

**Files:**
- Modify: `~/.config/deskwidgets/widgets/album/editor.py`
- Backup: `cp editor.py editor.v1.py`

**Interfaces:**
- Consumes: v2 entry（`cover/blocks`）、`nb.new_id`
- Produces:
  - `self.anchors: dict[Gtk.TextChildAnchor, str]`（图片相对路径）
  - `_fill_body(blocks)`、`_blocks() -> list`
  - `_store_image(src, kind) -> str`
  - `_insert_rel(rel, at_iter=None)`
  - 所属章节下拉 `self.entry_chapter_dd`

- [ ] **Step 1: 备份旧编辑器**

```bash
cd ~/.config/deskwidgets/widgets/album && cp -a editor.py editor.v1.py
```

- [ ] **Step 2: 初始化 anchors，并在 _load 中填充封面/正文**

```python
        self.anchors = {}
        self._cover_entry = None
```

`_load`（或现有 `_show_entry`）改为：

```python
        self.current_id = e['id'] if e else None
        self.title_entry.set_text(e['title'] if e else '')
        self._loading = True
        self._fill_entry_chapter(e)
        self._fill_body(e.get('blocks') if e else [])
        self._loading = False
        self._show_cover(e)
        self.title_entry.set_sensitive(e is not None)
        self.body.set_sensitive(e is not None)
```

- [ ] **Step 3: 正文反序列化与序列化**

```python
    def _picture_for(self, rel):
        path = os.path.join(self.root, rel)
        try:
            tex = Gdk.Texture.new_from_filename(path)
        except Exception:
            return None
        pic = Gtk.Picture(paintable=tex)
        pic.set_content_fit(Gtk.ContentFit.CONTAIN)
        pic.set_size_request(360, 200)
        pic.set_can_shrink(True)
        return pic

    def _fill_body(self, blocks):
        buf = self.body.get_buffer()
        buf.set_text('')
        self.anchors.clear()
        for b in blocks or []:
            if b.get('type') == 'text':
                buf.insert(buf.get_end_iter(), b.get('text') or '')
            elif b.get('type') == 'image' and b.get('image'):
                it = buf.get_end_iter()
                anchor = buf.create_child_anchor(it)
                pic = self._picture_for(b['image'])
                if pic is not None:
                    self.body.add_child_at_anchor(pic, anchor)
                    self.anchors[anchor] = b['image']

    def _blocks(self):
        buf = self.body.get_buffer()
        out, text = [], []

        def flush():
            if not text:
                return
            s = ''.join(text)
            text.clear()
            if not s.strip():
                return
            if out and out[-1]['type'] == 'text':
                out[-1]['text'] += s
            else:
                out.append({'type': 'text', 'text': s})

        it = buf.get_start_iter()
        while not it.is_end():
            anchor = it.get_child_anchor()
            if anchor is not None:
                flush()
                rel = self.anchors.get(anchor)
                if rel:
                    out.append({'type': 'image', 'image': rel})
                it.forward_char()
                continue
            ch = it.get_char()
            if ch != '\ufffc':
                text.append(ch)
            it.forward_char()
        flush()
        return out
```

`_sync` 里把 `e['body'] = ...` 换成：

```python
        e['blocks'] = self._blocks()
```

- [ ] **Step 4: 封面行替换原来的单图行**

新增：

```python
        self.cover_label = Gtk.Label(label='', xalign=0)
        self.cover_label.add_css_class('dim-label')
        self.cover_thumb = Gtk.Picture()
        self.cover_thumb.set_content_fit(Gtk.ContentFit.CONTAIN)
        self.cover_thumb.set_size_request(-1, 90)
```

`_on_choose_cover`：捕获 `self._cover_entry = e['id']`，选完复制为 `images/cover-<entryid>-<ms><ext>`，设置 `e['cover']`、刷新缩略图、脏标记。
`_on_clear_cover`：`e['cover'] = ''`，清空缩略图，脏标记。
`_show_cover(e)`：加载 `os.path.join(self.root, e['cover'])` 到 `Gdk.Texture`，失败则清空。

同时删除旧的单图逻辑：`_on_choose_image`、`_image_chosen`、`_show_image`、`self.preview`、`self.image_label` 及其在布局里的两行。

- [ ] **Step 5: 所属章节下拉**

构建行：

```python
        self.entry_chapter_dd = Gtk.DropDown(model=Gtk.StringList.new([]))
        self.entry_chapter_dd.connect('notify::selected', self._on_entry_chapter_changed)
```

```python
    def _fill_entry_chapter(self, e):
        self._loading = True
        chapters = self.chapters()
        self.entry_chapter_dd.set_model(Gtk.StringList.new([c['title'] for c in chapters]))
        idx = next((i for i, c in enumerate(chapters) if e and c['id'] == e.get('chapter_id')), 0)
        self.entry_chapter_dd.set_selected(idx)
        self.entry_chapter_dd.set_sensitive(e is not None)
        self._loading = False

    def _on_entry_chapter_changed(self, dd, _):
        if self._loading:
            return
        e = self.entry(self.current_id)
        chapters = self.chapters()
        idx = dd.get_selected()
        if e is None or idx >= len(chapters):
            return
        cid = chapters[idx]['id']
        if e['chapter_id'] == cid:
            return
        self._sync()
        e['chapter_id'] = cid
        self.dirty = True
        self.status.set_text('条目已移动，点保存生效')
```

- [ ] **Step 6: 保存后刷新列表，处理条目移出当前章节**

`_on_save` 末尾：

```python
        self._fill_chapters(self.chapter_id)
        ids = [x['id'] for x in self.chapter_entries(self.chapter_id)]
        keep = self.current_id if self.current_id in ids else (ids[0] if ids else None)
        self._fill_entries(self.chapter_id, keep)
```

- [ ] **Step 7: 语法检查与实机打开**

```bash
python3 -m py_compile editor.py && echo OK
cd ~/.config/deskwidgets/widgets/album && python3 editor.py --instance album --entry <现有条目id>
```

用 ffmpeg 截图核对：标题、所属章节下拉、封面行、正文区；插入一张图（选文件）后保存，检查 notebook.json 的 blocks 顺序为 `text → image → text`（可先输入 A、插图、输入 B）。

---

### Task 5: 粘贴截图与拖拽插图

**Files:**
- Modify: `~/.config/deskwidgets/widgets/album/editor.py`

**Interfaces:**
- Consumes: `_store_image`、`_insert_rel`
- Produces: Ctrl+V 图片/文字粘贴；文件拖入正文

- [ ] **Step 1: 通用入库函数**

```python
    def _store_image(self, src, kind):
        ext = os.path.splitext(src)[1].lower() or '.png'
        name = f'{kind}-{self.current_id}-{int(time.time() * 1000)}{ext}'
        images = os.path.join(self.root, 'images')
        os.makedirs(images, exist_ok=True)
        dst = os.path.join(images, name)
        shutil.copy2(src, dst)
        return 'images/' + name

    def _insert_rel(self, rel, at_iter=None):
        buf = self.body.get_buffer()
        it = at_iter or buf.get_iter_at_mark(buf.get_insert())
        anchor = buf.create_child_anchor(it)
        pic = self._picture_for(rel)
        if pic is None:
            return False
        self.body.add_child_at_anchor(pic, anchor)
        self.anchors[anchor] = rel
        self._mark_dirty()
        return True
```

- [ ] **Step 2: 工具栏「插入图片…」**

```python
    def _on_insert_image(self, _b):
        if not self.current_id:
            self.status.set_text('先选择一条笔记')
            return
        buf = self.body.get_buffer()
        self._insert_mark = buf.create_mark(None, buf.get_iter_at_mark(buf.get_insert()), True)
        dlg = Gtk.FileDialog(title='插入图片')
        filters = Gio.ListStore.new(Gtk.FileFilter)
        f = Gtk.FileFilter()
        f.set_name('图片')
        f.add_pixbuf_formats()
        filters.append(f)
        dlg.set_filters(filters)
        dlg.open(self.win, None, self._insert_chosen)

    def _insert_chosen(self, dialog, result):
        try:
            gfile = dialog.open_finish(result)
        except GLib.Error:
            return
        src = gfile.get_path()
        mark = getattr(self, '_insert_mark', None)
        if not src or mark is None:
            return
        rel = self._store_image(src, 'body')
        it = self.body.get_buffer().get_iter_at_mark(mark)
        self._insert_rel(rel, it)
```

- [ ] **Step 3: Ctrl+V 粘贴**

```python
        key = Gtk.EventControllerKey()
        key.connect('key-pressed', self._on_body_key)
        self.body.add_controller(key)
```

```python
    def _on_body_key(self, _c, keyval, _code, state):
        if keyval == Gdk.KEY_v and state & Gdk.ModifierType.CONTROL_MASK:
            self._paste()
            return True
        return False

    def _paste(self):
        cb = self.body.get_clipboard()

        def got_texture(clip, res):
            try:
                tex = clip.read_texture_finish(res)
            except GLib.Error:
                tex = None
            if tex is not None:
                name = f'body-{self.current_id}-{int(time.time() * 1000)}.png'
                images = os.path.join(self.root, 'images')
                os.makedirs(images, exist_ok=True)
                dst = os.path.join(images, name)
                tex.save_to_png(dst)
                self._insert_rel('images/' + name)
            else:
                self._paste_text()

        cb.read_texture_async(None, got_texture)

    def _paste_text(self):
        cb = self.body.get_clipboard()

        def got(clip, res):
            try:
                text = clip.read_text_finish(res)
            except GLib.Error:
                return
            if text:
                self.body.get_buffer().insert_at_cursor(text)
                self._mark_dirty()

        cb.read_text_async(None, got)
```

- [ ] **Step 4: 拖拽文件**

```python
        drop = Gtk.DropTarget.new(Gdk.FileList, Gdk.DragAction.COPY)
        drop.connect('drop', self._on_drop)
        self.body.add_controller(drop)
```

```python
    def _on_drop(self, _target, value, x, y):
        ok, it = self.body.get_iter_at_location(int(x), int(y))
        if not ok:
            it = self.body.get_buffer().get_end_iter()
        first = True
        for gfile in value.get_files():
            src = gfile.get_path()
            if not src or os.path.splitext(src)[1].lower() not in nb.EXTS:
                continue
            rel = self._store_image(src, 'body')
            self._insert_rel(rel, it if first else None)
            first = False
        return True
```

- [ ] **Step 5: 实机验证三种方式**

打开编辑器，分别：按钮插图、Ctrl+V 粘贴截图、从文件管理器拖图；保存后检查 `notebook.json` 中对应条目的 `blocks` 顺序与图片路径；重新打开编辑器确认顺序一致。

---

### Task 6: 卡片刷新、章节移动与端到端联调

**Files:**
- Modify: `~/.config/deskwidgets/widgets/album/widget.lua`（如需）
- Modify: `~/Downloads/deskwidgets-pkg/HANDOVER.md`

**Interfaces:**
- Consumes: Task 2 快照、Task 4/5 编辑器
- Produces: 保存 → refresh → 卡片更新；移动章节后列表/卡片同步

- [ ] **Step 1: 确认保存写 refresh**

```bash
grep -n "_refresh_widget" ~/.config/deskwidgets/widgets/album/editor.py
```

预期：`_on_save` 内调用 `self._refresh_widget()`（定义在保存章节动作之前）。若不存在，在 `self.status.set_text('已保存')` 后补上。

- [ ] **Step 2: 移动章节的端到端检查（交互步骤留给用户；数据核对在此执行）**

用户在编辑器里把条目从「未分类」切到新章节并保存，然后：

```bash
G=$(cat /run/user/1000/deskwidgets/album-616c62756d/snapshot/current)
cat /run/user/1000/deskwidgets/album-616c62756d/snapshot/$G/chapter.txt
cat /run/user/1000/deskwidgets/album-616c62756d/snapshot/$G/count
```

预期：卡片章节标题变化，旧章节列表不再含该条目，count 对应当前章节。

- [ ] **Step 3: 保存后卡片即时刷新**

在编辑器改标题/封面后保存，等待 ≤1s，截图卡片区域确认标题与封面更新。

- [ ] **Step 4: 更新 HANDOVER.md**

修改「3.2 数据格式」「3.3 快照协议」「3.4 编辑器」：version 2、cover/blocks、has-cover/excerpt、封面回退规则、所属章节下拉、三种插图方式、迁移说明（notebook.v1.json 备份位置）。

---

### Task 7: 发布检查与完整重启

**Files:**
- Modify: `~/Downloads/deskwidgets-pkg/HANDOVER.md`（检查结果）

- [ ] **Step 1: 语法与 JSON**

```bash
cd ~/.config/deskwidgets/widgets/album
python3 -m py_compile notebook.py editor.py topng.py
python3 -m json.tool notebook.json >/dev/null 2>&1 || true
python3 -m json.tool ~/.local/share/deskwidgets/notebooks/616c62756d/notebook.json >/dev/null
python3 -m json.tool ~/.local/share/deskwidgets/notebooks/616c62756d/view.json >/dev/null
```

- [ ] **Step 2: reload 与完整重启**

```bash
deskwidgets reload          # Lua 改动
deskwidgets quit
nohup deskwidgets run >>/tmp/deskwidgets.log 2>&1 &
```

预期：5 个 conky 拉起，`deskwidgets list` 坐标不变，日志无 Lua/Python 异常（忽略 k10temp/amdgpu）。

- [ ] **Step 3: 重启后数据保持**

确认章节、条目、封面、阅读位置、正文块顺序都还在；卡片显示封面 + 摘录。

- [ ] **Step 4: 更新 HANDOVER 的检查结果与未验收项**

记录：迁移后的 revision、备份路径 `notebook.v1.json`、三种卡面验证结果、编辑器截图结论；未验收项留给用户（粘贴/拖拽手感、移动章节交互、翻页）。

- [ ] **Step 5: 回滚说明**

```
恢复 notebook.json：cp notebook.v1.json notebook.json
恢复编辑器：cp editor.v1.py editor.py
图片目录不动（迁移不删图片）
旧版 widget.lua/ widget.json 从 backup-20261101-194321 取
```
