#!/usr/bin/env python3
"""GTK4 editor for the album notebook widget.

Click the card -> this window opens on the current entry. One window per instance:
a second click activates the same window and switches the entry (asking first when
there are unsaved edits). Saving rebuilds the widget snapshot through a refresh marker.

Usage: editor.py --instance ID [--entry EID] [--chapter CHID]
"""
import argparse
import os
import re
import shutil
import sys
import time
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gi  # noqa: E402

gi.require_version('Gtk', '4.0')
gi.require_version('Gdk', '4.0')
gi.require_version('Pango', '1.0')
from gi.repository import Gdk, Gio, GLib, Gtk, Pango  # noqa: E402

import notebook as nb  # noqa: E402

def _sym(symbol, keywords):
    return (symbol, keywords, None)


def _pair(label, keywords):
    return (label, keywords, (label[0], label[1]))


def _group(symbols, keywords):
    return tuple(_sym(s, keywords) for s in symbols.split())


def _numbered(symbols, kind, start=1):
    return tuple(_sym(s, f'序号 圆形 数字 {i} {kind}')
                 for i, s in enumerate(symbols, start))


SYMBOL_GROUPS = (
    ('常用', (
        _sym('①', '常用 序号 圆形 数字 1'),
        _sym('②', '常用 序号 圆形 数字 2'),
        _sym('③', '常用 序号 圆形 数字 3'),
        _sym('④', '常用 序号 圆形 数字 4'),
        _sym('⑤', '常用 序号 圆形 数字 5'),
        _sym('⑥', '常用 序号 圆形 数字 6'),
        _sym('⑦', '常用 序号 圆形 数字 7'),
        _sym('⑧', '常用 序号 圆形 数字 8'),
        _sym('⑨', '常用 序号 圆形 数字 9'),
        _sym('⑩', '常用 序号 圆形 数字 10'),
        _sym('■', '常用 方框 黑色 方块'),
        _sym('□', '常用 方框 白色 方块'),
        _sym('☐', '常用 勾选 复选框 待办 空'),
        _sym('☑', '常用 勾选 复选框 待办 已选'),
        _sym('☒', '常用 勾选 复选框 取消'),
        _sym('✓', '常用 勾选 对勾 正确'),
        _sym('✗', '常用 勾选 叉 错误'),
        _sym('•', '常用 列表 项目符号 圆点'),
        _pair('“”', '常用 标点 引号 双引号'),
        _pair('【】', '常用 标点 括号 方括号'),
        _sym('—', '常用 标点 破折号'),
        _sym('…', '常用 标点 省略号'),
        _sym('→', '常用 箭头 右'),
        _sym('★', '常用 标记 星'),
    )),
    ('序号',
     _numbered('①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳', '带圈')
     + _numbered('❶❷❸❹❺❻❼❽❾❿', '黑底')
     + _numbered('⓵⓶⓷⓸⓹⓺⓻⓼⓽⓾', '双圈')),
    ('方框与勾选',
     _group('■ □ ▪ ▫ ▣ ▤ ▥ ▦ ▧ ▨ ▩ ◼ ◻ ◾ ◽', '方框 方块 方形')
     + (
         _sym('☐', '勾选 复选框 待办 空 未选'),
         _sym('☑', '勾选 复选框 待办 已选 对勾'),
         _sym('☒', '勾选 复选框 取消 叉'),
         _sym('✓', '勾选 对勾 正确'),
         _sym('✔', '勾选 对勾 正确 粗'),
         _sym('✗', '勾选 叉 错误'),
         _sym('✘', '勾选 叉 错误 粗'),
     )),
    ('标点与括号', (
        _sym('、', '标点 中文 顿号'),
        _sym('。', '标点 中文 句号'),
        _sym('，', '标点 中文 逗号'),
        _sym('；', '标点 中文 分号'),
        _sym('：', '标点 中文 冒号'),
        _sym('？', '标点 中文 问号'),
        _sym('！', '标点 中文 感叹号'),
        _sym('…', '标点 中文 省略号'),
        _sym('——', '标点 中文 破折号'),
        _sym('～', '标点 中文 波浪号'),
        _sym('·', '标点 中文 间隔号'),
        _pair('“”', '标点 中文 引号 双引号'),
        _pair('‘’', '标点 中文 引号 单引号'),
        _pair('「」', '标点 中文 引号 直角引号'),
        _pair('『』', '标点 中文 引号 双直角引号'),
        _pair('【】', '标点 中文 括号 方括号'),
        _pair('《》', '标点 中文 书名号'),
        _pair('〈〉', '标点 中文 括号 尖括号'),
        _pair('（）', '标点 中文 括号 圆括号'),
        _pair('〔〕', '标点 中文 括号 六角括号'),
        _pair('［］', '标点 中文 括号 全角方括号'),
        _pair('｛｝', '标点 中文 括号 花括号'),
    )),
    ('箭头与数学', (
        _sym('→', '箭头 方向 右'),
        _sym('←', '箭头 方向 左'),
        _sym('↑', '箭头 方向 上'),
        _sym('↓', '箭头 方向 下'),
        _sym('⇒', '箭头 双线 右'),
        _sym('⇐', '箭头 双线 左'),
        _sym('⇔', '箭头 双向'),
        _sym('➜', '箭头 实心 右'),
        _sym('×', '数学 乘号'),
        _sym('÷', '数学 除号'),
        _sym('±', '数学 正负号'),
        _sym('≈', '数学 约等号'),
        _sym('≠', '数学 不等号'),
        _sym('≤', '数学 小于等于'),
        _sym('≥', '数学 大于等于'),
        _sym('∞', '数学 无穷'),
    )),
    ('其他', (
        _sym('•', '列表 项目符号 圆点'),
        _sym('·', '列表 间隔点'),
        _sym('‣', '列表 三角点'),
        _sym('◦', '列表 空心点'),
        _sym('⁃', '列表 短横点'),
        _sym('∙', '列表 中点'),
        _sym('※', '标记 参考 注释'),
        _sym('§', '标记 章节'),
        _sym('¶', '标记 段落'),
        _sym('†', '标记 剑号'),
        _sym('‡', '标记 双剑号'),
        _sym('★', '标记 星 实心'),
        _sym('☆', '标记 星 空心'),
        _sym('✦', '标记 星 四角'),
        _sym('✧', '标记 星 四角空心'),
        _sym('♥', '标记 心 实心'),
        _sym('♡', '标记 心 空心'),
    )),
)


def widget_folder(instance):
    try:
        with open(os.path.join(nb.RUN, 'opts', instance), encoding='utf-8') as f:
            for line in f:
                if line.startswith('folder='):
                    return line.split('=', 1)[1].rstrip('\n')
    except OSError:
        pass
    return ''


class Editor(Gtk.Application):
    def __init__(self, instance):
        super().__init__(application_id='local.snow.notebook.n' + nb.inst_hex(instance),
                         flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        self.instance = instance
        self.root = nb.book_root(instance)
        self.run_root = nb.run_root(instance)
        self.book = None
        self.revision = None
        self.current_id = None
        self.chapter_id = None
        self.dirty = False
        self._loading = False
        self.requested_entry = None
        self.requested_chapter = None
        self.win = None
        self._quitting = False
        self.anchors = {}
        self._insert_mark = None
        self._cover_entry = None
        self.viewer = None
        self._viewer_pic = None
        self._viewer_tex = None
        self._viewer_scrolled = None
        self._viewer_zoom = 1.0
        self._viewer_zoom_label = None
        self._viewer_drag_start = None

    # application plumbing ---------------------------------------------------
    def do_command_line(self, command_line):
        p = argparse.ArgumentParser(add_help=False)
        p.add_argument('--instance')
        p.add_argument('--entry', default=None)
        p.add_argument('--chapter', default=None)
        ns, _ = p.parse_known_args(command_line.get_arguments()[1:])
        if ns.entry:
            self.requested_entry = ns.entry
        if ns.chapter:
            self.requested_chapter = ns.chapter
        self.activate()
        return 0

    def do_activate(self):
        if self.win is not None:
            self.win.present()
            self._apply_request()
            return
        self._build()
        self._load(None)
        self._apply_request()

    def _apply_request(self):
        entry = self.requested_entry
        chapter = self.requested_chapter
        self.requested_entry = self.requested_chapter = None
        if not (chapter or entry):
            return

        def apply():
            if chapter:
                self._select_chapter(chapter)
            if entry:
                self._request_entry(entry)

        if self.dirty:
            self._ask_unsaved(apply)
        else:
            apply()

    def _quit(self):
        if self._quitting:
            return
        self._quitting = True
        if self.win:
            self.win.destroy()
        self.release()
        self.quit()

    # UI ---------------------------------------------------------------------
    def _build(self):
        self._editor_style()
        self.win = Gtk.ApplicationWindow(application=self, title='图文笔记 · ' + self.instance)
        self.win.set_default_size(920, 640)
        self.win.connect('close-request', self._on_close)
        key = Gtk.EventControllerKey()
        key.connect('key-pressed', self._on_key)
        self.win.add_controller(key)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8,
                       margin_top=10, margin_bottom=10, margin_start=12, margin_end=12)
        self.rootbox = root

        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        top.append(Gtk.Label(label='章节'))
        self.chapter_dd = Gtk.DropDown(model=Gtk.StringList.new([]))
        self.chapter_dd.connect('notify::selected', self._on_chapter_selected)
        top.append(self.chapter_dd)
        self.chapter_entry = Gtk.Entry(placeholder_text='新章节名')
        self.chapter_entry.set_width_chars(14)
        top.append(self.chapter_entry)
        b = Gtk.Button(label='新建章节'); b.connect('clicked', self._on_new_chapter)
        top.append(b)
        b = Gtk.Button(label='重命名'); b.connect('clicked', self._on_rename_chapter)
        top.append(b)
        b = Gtk.Button(label='删除章节'); b.connect('clicked', self._on_delete_chapter)
        top.append(b)
        root.append(top)

        paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        paned.set_vexpand(True)
        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        b = Gtk.Button(label='新建条目'); b.connect('clicked', self._on_new_entry)
        left.append(b)
        scroll = Gtk.ScrolledWindow(vexpand=True)
        scroll.set_size_request(210, -1)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.listbox = Gtk.ListBox()
        self.listbox.set_activate_on_single_click(True)
        self.listbox.connect('row-activated', self._on_row_activated)
        scroll.set_child(self.listbox)
        left.append(scroll)
        paned.set_start_child(left)
        paned.set_resize_start_child(False)
        paned.set_shrink_start_child(False)

        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.title_entry = Gtk.Entry(placeholder_text='标题')
        self.title_entry.connect('changed', self._mark_dirty)
        right.append(self.title_entry)

        entry_chapter_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        entry_chapter_row.append(Gtk.Label(label='条目所属章节'))
        self.entry_chapter_dd = Gtk.DropDown(model=Gtk.StringList.new([]))
        self.entry_chapter_dd.connect('notify::selected', self._on_entry_chapter_changed)
        entry_chapter_row.append(self.entry_chapter_dd)
        right.append(entry_chapter_row)

        cover_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        cover_row.append(Gtk.Label(label='封面'))
        b = Gtk.Button(label='选择封面…'); b.connect('clicked', self._on_choose_cover)
        cover_row.append(b)
        b = Gtk.Button(label='清除封面'); b.connect('clicked', self._on_clear_cover)
        cover_row.append(b)
        self.cover_label = Gtk.Label(label='未设置时用正文第一张图', xalign=0)
        self.cover_label.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
        self.cover_label.set_max_width_chars(36)
        self.cover_label.set_hexpand(True)
        self.cover_label.add_css_class('dim-label')
        cover_row.append(self.cover_label)
        right.append(cover_row)

        self.cover_thumb = Gtk.Picture()
        self.cover_thumb.set_content_fit(Gtk.ContentFit.CONTAIN)
        cover_click = Gtk.GestureClick()
        cover_click.connect('pressed', self._on_cover_pressed)
        self.cover_thumb.add_controller(cover_click)
        thumb_view = Gtk.ScrolledWindow()
        thumb_view.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.NEVER)
        thumb_view.set_size_request(-1, 96)
        thumb_view.set_child(self.cover_thumb)
        cover_frame = Gtk.Frame()
        cover_frame.set_child(thumb_view)
        right.append(cover_frame)

        tools = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        tools.set_margin_top(2)

        def tool_btn(glyph, tip, cb):
            b = Gtk.Button(label=glyph)
            b.add_css_class('symbol-btn')
            b.add_css_class('flat')
            b.set_tooltip_text(tip)
            b.connect('clicked', lambda _b, fn=cb: fn(_b))
            tools.append(b)

        def sep():
            tools.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))

        tool_btn('↶', '撤销（Ctrl+Z）', self._undo)
        tool_btn('↷', '重做（Ctrl+Shift+Z）', self._redo)
        sep()
        tool_btn('图', '插入图片：插在光标处，也可以直接粘贴或拖入正文',
                 self._on_insert_image)
        sep()
        tool_btn('1.', '序号列表：给当前行或选中各行加编号，再点一次取消',
                 lambda _b: self._toggle_prefix('num'))
        tool_btn('•', '圆点列表：给当前行或选中各行加项目符号，再点一次取消',
                 lambda _b: self._toggle_prefix('bullet'))
        tool_btn('☐', '勾选清单：给当前行或选中各行加复选框，再点一次取消',
                 lambda _b: self._toggle_prefix('box'))
        tool_btn('❝', '引用：给当前行或选中各行加引用条，再点一次取消',
                 lambda _b: self._toggle_prefix('quote'))
        sep()
        tool_btn('─', '分隔线：在光标处插入一条横线', lambda _b: self._insert_divider())

        mb = Gtk.MenuButton(label='符号')
        mb.set_tooltip_text('编号、方框、勾选、标点和更多符号')
        mb.set_always_show_arrow(True)
        mb.set_popover(self._symbol_popover())
        tools.append(mb)

        right.append(tools)

        body_frame = Gtk.Frame(label='正文')
        body_frame.set_vexpand(True)
        body_scroll = Gtk.ScrolledWindow(vexpand=True)
        body_scroll.add_css_class('body-scroll')
        body_scroll.set_policy(Gtk.PolicyType.ALWAYS, Gtk.PolicyType.AUTOMATIC)
        body_scroll.set_overlay_scrolling(False)
        self.body = Gtk.TextView(wrap_mode=Gtk.WrapMode.NONE)
        self.body.set_left_margin(8)
        self.body.set_right_margin(8)
        self.body.set_top_margin(6)
        self.body.set_bottom_margin(6)
        self.body.get_buffer().connect('changed', self._mark_dirty)
        self._wire_history(self.body.get_buffer())
        key = Gtk.EventControllerKey()
        key.connect('key-pressed', self._on_body_key)
        self.body.add_controller(key)
        drop = Gtk.DropTarget.new(Gdk.FileList, Gdk.DragAction.COPY)
        drop.connect('drop', self._on_drop)
        self.body.add_controller(drop)
        body_scroll.set_child(self.body)
        body_frame.set_child(body_scroll)
        right.append(body_frame)

        bottom = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        b = Gtk.Button(label='保存'); b.connect('clicked', self._on_save)
        b.add_css_class('suggested-action')
        bottom.append(b)
        b = Gtk.Button(label='删除条目'); b.connect('clicked', self._on_delete_entry)
        bottom.append(b)
        self.status = Gtk.Label(label='', xalign=0, hexpand=True)
        self.status.add_css_class('dim-label')
        bottom.append(self.status)
        right.append(bottom)

        paned.set_end_child(right)
        root.append(paned)
        self.win.set_child(root)
        self.hold()
        self.win.present()

    def _on_key(self, _c, keyval, _code, _state):
        if keyval == Gdk.KEY_Escape:
            self.win.close()
            return True
        return False

    # data -------------------------------------------------------------------
    def _load(self, entry_id):
        self._loading = True
        self.status.set_text('')
        try:
            self.book = nb.load_book(self.root)
            if self.book is None:
                self.book = nb.ensure_book(self.root, widget_folder(self.instance), self.instance)
            self.revision = self.book['revision']
        except nb.NotebookError as e:
            self.status.set_text(str(e))
            if hasattr(self, 'rootbox'):
                self.rootbox.set_sensitive(False)
            self._loading = False
            return
        view = nb.load_view(self.root)
        chapter = self.requested_chapter or view.get('chapter_id') or self.book['chapters'][0]['id']
        if chapter not in {c['id'] for c in self.book['chapters']}:
            chapter = self.book['chapters'][0]['id']
        self._fill_chapters(chapter)
        self._fill_entries(chapter, entry_id or self.requested_entry or view.get('entry_id'))
        self._loading = False

    def _discard_edits(self):
        """Drop widget edits: re-read the book and rebuild the UI from disk.

        Returns False when the book cannot be re-read; the caller must then keep
        the unsaved edits and stop switching instead of silently forgetting them.
        """
        try:
            book = nb.load_book(self.root)
        except nb.NotebookError as e:
            self.status.set_text(str(e))
            return False
        if book is None:
            self.status.set_text('笔记库不存在，未放弃修改')
            return False
        self.book = book
        self.revision = book['revision']
        cid = self.chapter_id
        if cid not in {c['id'] for c in self.chapters()}:
            cid = self.chapters()[0]['id']
        self._loading = True
        self._fill_chapters(cid)
        self._loading = False
        ids = [e['id'] for e in self.chapter_entries(cid)]
        keep = self.current_id if self.current_id in ids else (ids[0] if ids else None)
        self._fill_entries(cid, keep)
        self.dirty = False
        return True

    def chapters(self):
        return self.book['chapters'] if self.book else []

    def chapter_title(self, cid):
        return next((c['title'] for c in self.chapters() if c['id'] == cid), '')

    def default_chapter(self):
        for c in self.chapters():
            if c['title'] == nb.DEFAULT_CHAPTER:
                return c
        c = {'id': nb.new_id('ch'), 'title': nb.DEFAULT_CHAPTER}
        self.book['chapters'].append(c)
        return c

    def entry(self, eid):
        return next((e for e in self.book['entries'] if e['id'] == eid), None)

    def chapter_entries(self, cid):
        return sorted([e for e in self.book['entries'] if e.get('chapter_id') == cid],
                      key=lambda e: (e.get('order', 0), e.get('title', '')))

    def _fill_chapters(self, chapter):
        prev = self._loading
        self._loading = True
        self.chapter_id = chapter
        titles = [c['title'] or '（无标题）' for c in self.chapters()]
        self.chapter_dd.set_model(Gtk.StringList.new(titles))
        idx = next((i for i, c in enumerate(self.chapters()) if c['id'] == chapter), 0)
        self.chapter_dd.set_selected(idx)
        self._loading = prev

    def _fill_entries(self, chapter, entry_id):
        self.chapter_id = chapter
        while (row := self.listbox.get_row_at_index(0)) is not None:
            self.listbox.remove(row)
        entries = self.chapter_entries(chapter)
        if not entries:
            self._show_entry(None)
            return
        target = next((e for e in entries if e['id'] == entry_id), entries[0])
        self._loading = True
        for e in entries:
            row = Gtk.ListBoxRow()
            row.entry_id = e['id']
            title = e['title'] or '（无标题）'
            label = Gtk.Label(label=title, xalign=0,
                              margin_top=6, margin_bottom=6, margin_start=8, margin_end=8)
            label.set_ellipsize(Pango.EllipsizeMode.END)
            label.set_hexpand(True)
            label.set_tooltip_text(title)
            row.set_child(label)
            self.listbox.append(row)
            if e['id'] == target['id']:
                self._loading = True
                self.listbox.select_row(row)
                self._loading = False
        self._show_entry(target)

    def _fill_entry_chapter(self, e):
        prev = self._loading
        self._loading = True
        chapters = self.chapters()
        self.entry_chapter_dd.set_model(Gtk.StringList.new([c['title'] or '（无标题）' for c in chapters]))
        idx = next((i for i, c in enumerate(chapters) if e and c['id'] == e.get('chapter_id')), 0)
        self.entry_chapter_dd.set_selected(idx)
        self.entry_chapter_dd.set_sensitive(e is not None)
        self._loading = prev

    def _on_entry_chapter_changed(self, dd, _pspec):
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
        self.status.set_text('条目已移动到「' + (chapters[idx]['title'] or '无标题') + '」，点保存生效')

    def _show_entry(self, e):
        self._loading = True
        self.current_id = e['id'] if e else None
        self.title_entry.set_text(e['title'] if e else '')
        self._fill_entry_chapter(e)
        self._fill_body(e.get('blocks') if e else [])
        self._show_cover(e)
        self.title_entry.set_sensitive(e is not None)
        self.body.set_sensitive(e is not None)
        self._loading = False

    def _picture_for(self, rel, width=360, height=210):
        path = os.path.join(self.root, rel)
        try:
            tex = Gdk.Texture.new_from_filename(path)
        except Exception:
            return None
        pic = Gtk.Picture(paintable=tex)
        pic.set_content_fit(Gtk.ContentFit.CONTAIN)
        pic.set_size_request(width, height)
        pic.set_can_shrink(True)
        pic.set_tooltip_text('双击放大')
        click = Gtk.GestureClick()
        click.connect('pressed', lambda g, n, x, y, r=rel: self._on_picture_pressed(n, r))
        pic.add_controller(click)
        return pic

    def _fill_body(self, blocks):
        buf = self.body.get_buffer()
        buf.set_text('')
        self.anchors.clear()
        self._undo_stack = []
        self._redo_stack = []
        self._pre_snap = None
        self._last_snap = self._snapshot()
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

    def _store_image(self, src, kind):
        ext = os.path.splitext(src)[1].lower() or '.png'
        name = f'{kind}-{self.current_id}-{uuid.uuid4().hex}{ext}'
        images = os.path.join(self.root, 'images')
        os.makedirs(images, exist_ok=True)
        shutil.copy2(src, os.path.join(images, name))
        return 'images/' + name

    def _show_cover(self, e):
        self.cover_thumb.set_paintable(None)
        if not e or not e.get('cover'):
            self.cover_label.set_text('未设置时用正文第一张图')
            self.cover_label.set_tooltip_text(None)
            return
        self.cover_label.set_text('已设置封面')
        self.cover_label.set_tooltip_text(e['cover'])
        try:
            self.cover_thumb.set_paintable(
                Gdk.Texture.new_from_filename(os.path.join(self.root, e['cover'])))
        except Exception:
            pass

    # text toolbar -----------------------------------------------------------
    _editor_css_done = False

    def _editor_style(self):
        if Editor._editor_css_done:
            return
        prov = Gtk.CssProvider()
        prov.load_from_data(b'''
button.symbol-btn {
  min-width: 30px;
  min-height: 30px;
  padding: 0 4px;
  font-size: 14pt;
}
.body-scroll scrollbar.vertical {
  min-width: 14px;
}
.body-scroll scrollbar.vertical slider {
  min-width: 10px;
  min-height: 44px;
  border-radius: 6px;
}
.body-scroll scrollbar.horizontal {
  min-height: 14px;
}
.body-scroll scrollbar.horizontal slider {
  min-height: 10px;
  min-width: 44px;
  border-radius: 6px;
}
.symbol-section {
  font-weight: bold;
  margin-top: 2px;
}
.symbol-popover scrollbar.vertical {
  min-width: 14px;
}
.symbol-popover scrollbar.vertical slider {
  min-width: 10px;
  min-height: 44px;
  border-radius: 6px;
}
''')
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), prov, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        Editor._editor_css_done = True

    def _symbol_popover(self):
        pop = Gtk.Popover()
        pop.add_css_class('symbol-popover')
        pop.set_has_arrow(False)
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8,
                        margin_top=10, margin_bottom=10, margin_start=10, margin_end=10)
        outer.set_size_request(560, -1)
        self._symbol_search = Gtk.SearchEntry(
            placeholder_text='搜索符号：序号、勾选、箭头…')
        self._symbol_search.connect('search-changed', self._filter_symbols)
        outer.append(self._symbol_search)

        self._symbol_scroll = Gtk.ScrolledWindow()
        self._symbol_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self._symbol_scroll.set_overlay_scrolling(False)
        self._symbol_scroll.set_max_content_height(300)
        self._symbol_scroll.set_propagate_natural_height(True)
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self._symbol_sections = []
        for title, items in SYMBOL_GROUPS:
            label = Gtk.Label(label=title, xalign=0)
            label.add_css_class('symbol-section')
            flow = Gtk.FlowBox()
            flow.set_selection_mode(Gtk.SelectionMode.NONE)
            flow.set_homogeneous(True)
            flow.set_max_children_per_line(8)
            flow.set_row_spacing(4)
            flow.set_column_spacing(4)
            flow.set_valign(Gtk.Align.START)
            entries = []
            for sym, keywords, pair in items:
                b = Gtk.Button(label=sym)
                b.add_css_class('symbol-btn')
                b.add_css_class('flat')
                b.set_tooltip_text(
                    ('包裹选中文字：' + sym) if pair else ('插入 ' + sym))
                if pair:
                    b.connect('clicked', lambda _b, p=pair: self._symbol_insert_pair(p, pop))
                else:
                    b.connect('clicked', lambda _b, s=sym: self._symbol_insert(s, pop))
                flow.append(b)
                entries.append((b, keywords))
            content.append(label)
            content.append(flow)
            self._symbol_sections.append((title, label, flow, entries))
        self._symbol_empty = Gtk.Label(label='没有找到匹配的符号', xalign=0)
        self._symbol_empty.add_css_class('dim-label')
        self._symbol_empty.set_visible(False)
        content.append(self._symbol_empty)
        self._symbol_scroll.set_child(content)
        outer.append(self._symbol_scroll)

        hint = Gtk.Label(label='引号/括号：选中文字时包裹，未选中时插入一对', xalign=0)
        hint.add_css_class('dim-label')
        outer.append(hint)
        pop.set_child(outer)
        pop.connect('map', self._symbol_opened)
        return pop

    def _symbol_opened(self, _pop):
        self._symbol_search.set_text('')
        self._filter_symbols(self._symbol_search)
        adj = self._symbol_scroll.get_vadjustment()
        if adj is not None:
            adj.set_value(0)
        GLib.idle_add(self._symbol_focus_search)

    def _symbol_focus_search(self):
        self._symbol_search.grab_focus()
        return False

    def _filter_symbols(self, entry):
        q = entry.get_text().strip().lower()
        any_visible = False
        for title, label, flow, entries in self._symbol_sections:
            common_hidden = bool(q) and title == '常用' and '常用' not in q
            matched = []
            if not common_hidden:
                for button, keywords in entries:
                    text = (keywords + ' ' + (button.get_label() or '')).lower()
                    if not q or q in text:
                        matched.append(button)
            child = flow.get_first_child()
            while child is not None:
                nxt = child.get_next_sibling()
                flow.remove(child)
                child = nxt
            for button in matched:
                flow.append(button)
            label.set_visible(bool(matched))
            flow.set_visible(bool(matched))
            any_visible = any_visible or bool(matched)
        self._symbol_empty.set_visible(not any_visible)
        adj = self._symbol_scroll.get_vadjustment()
        if adj is not None:
            adj.set_value(0)

    def _symbol_insert(self, sym, pop):
        pop.popdown()
        self._insert_text(sym)

    def _symbol_insert_pair(self, pair, pop):
        pop.popdown()
        self._surround(*pair)

    def _insert_text(self, text):
        if not self.current_id:
            self.status.set_text('先选择一条笔记')
            return
        buf = self.body.get_buffer()
        buf.begin_user_action()
        if buf.get_has_selection():
            start, end = buf.get_selection_bounds()
            buf.delete(start, end)
        buf.insert_at_cursor(text)
        buf.end_user_action()
        self._focus_body()

    def _surround(self, before, after):
        if not self.current_id:
            self.status.set_text('先选择一条笔记')
            return
        buf = self.body.get_buffer()
        buf.begin_user_action()
        if buf.get_has_selection():
            start, end = buf.get_selection_bounds()
            end_off = end.get_offset()
            start_off = start.get_offset()
            buf.insert(buf.get_iter_at_offset(end_off), after)
            buf.insert(buf.get_iter_at_offset(start_off), before)
        else:
            buf.insert_at_cursor(before + after)
            it = buf.get_iter_at_mark(buf.get_insert())
            it.backward_chars(len(after))
            buf.place_cursor(it)
        buf.end_user_action()
        self._focus_body()

    def _undo(self, _b=None):
        self._history_undo()

    def _redo(self, _b=None):
        self._history_redo()

    # GTK4's built-in undo keeps only the \ufffc placeholder when a child
    # anchor is deleted, and both irreversible actions and the enable-undo
    # toggle wipe the whole history, so the body buffer runs its own
    # snapshot-based undo stack instead.
    def _wire_history(self, buf):
        buf.set_enable_undo(False)
        self._undo_stack = []
        self._redo_stack = []
        self._pre_snap = None
        self._last_snap = None
        self._restoring = False
        self._micro_scheduled = False
        buf.connect('begin-user-action', self._on_hist_begin)
        buf.connect('end-user-action', self._on_hist_end)
        buf.connect('changed', self._on_hist_changed)

    def _snapshot(self):
        buf = self.body.get_buffer()
        text, imgs = [], []
        it = buf.get_start_iter()
        while not it.is_end():
            anchor = it.get_child_anchor()
            rel = self.anchors.get(anchor) if anchor is not None else None
            if rel:
                imgs.append((it.get_offset(), rel))
            elif anchor is None:
                text.append(it.get_char())
            it.forward_char()
        cur = buf.get_iter_at_mark(buf.get_insert()).get_offset()
        return (''.join(text), tuple(imgs), cur)

    def _same_snap(self, a, b):
        return a is not None and b is not None and a == b

    def _on_hist_begin(self, _buf):
        self._pre_snap = self._snapshot()

    def _on_hist_end(self, _buf):
        pre = self._pre_snap if self._pre_snap is not None else self._last_snap
        cur = self._snapshot()
        self._pre_snap = None
        self._last_snap = cur
        self._micro_scheduled = False
        if not self._same_snap(pre, cur):
            self._undo_stack.append(pre)
            self._redo_stack.clear()

    def _on_hist_changed(self, _buf):
        # Edits outside any user action (typing, IME, paste) become one
        # coalesced history entry via an idle callback.
        if self._restoring or self._pre_snap is not None or self._micro_scheduled:
            return
        self._micro_scheduled = True
        pre = self._last_snap if self._last_snap is not None else self._snapshot()
        GLib.idle_add(self._micro_commit, pre)

    def _micro_commit(self, pre):
        self._micro_scheduled = False
        if self._restoring or self._pre_snap is not None:
            return False
        cur = self._snapshot()
        self._last_snap = cur
        if not self._same_snap(pre, cur):
            self._undo_stack.append(pre)
            self._redo_stack.clear()
        return False

    def _history_undo(self):
        if self._restoring or not self._undo_stack:
            return
        self._redo_stack.append(self._snapshot())
        self._apply_snap(self._undo_stack.pop())
        self._focus_body()

    def _history_redo(self):
        if self._restoring or not self._redo_stack:
            return
        self._undo_stack.append(self._snapshot())
        self._apply_snap(self._redo_stack.pop())
        self._focus_body()

    def _apply_snap(self, snap):
        self._restoring = True
        buf = self.body.get_buffer()
        buf.set_text('')
        self.anchors.clear()
        text, imgs, cur = snap
        buf.insert(buf.get_start_iter(), text)
        for k, (off, rel) in enumerate(imgs):
            anchor = buf.create_child_anchor(buf.get_iter_at_offset(off - k))
            self.anchors[anchor] = rel
            pic = self._picture_for(rel)
            if pic is not None:
                self.body.add_child_at_anchor(pic, anchor)
        behind = sum(1 for off, _r in imgs if off < cur)
        buf.place_cursor(buf.get_iter_at_offset(cur - behind))
        self._last_snap = self._snapshot()
        self._micro_scheduled = False
        self._restoring = False

    _PREFIX_RE = re.compile(
        r'^(\s*)(?:[①-⑳❶-❿⓵-⓾]\s*|\d{1,3}[.、)]\s*|[•●]\s*|[☐☑☒]\s*|▎\s*)')
    _KIND_RES = {
        'num': re.compile(r'^\s*(?:[①-⑳❶-❿⓵-⓾]\s*|\d{1,3}[.、)]\s*)'),
        'bullet': re.compile(r'^\s*[•●]\s*'),
        'box': re.compile(r'^\s*[☐☑☒]\s*'),
        'quote': re.compile(r'^\s*▎\s*'),
    }
    _CIRCLED = '①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳'

    def _toggle_prefix(self, kind):
        if not self.current_id:
            self.status.set_text('先选择一条笔记')
            return
        buf = self.body.get_buffer()
        sel = buf.get_selection_bounds()
        if sel:
            first = sel[0].get_line()
            last = sel[1].get_line()
            if sel[1].starts_line() and last > first:
                last -= 1
        else:
            first = last = buf.get_iter_at_mark(buf.get_insert()).get_line()

        def line_text(ln):
            # get_text() skips anchor chars, which would shift every offset
            # on image lines; scan chars manually so positions stay aligned.
            s = buf.get_iter_at_line(ln)[1]
            e = s.copy()
            e.forward_to_line_end()
            chars = []
            it = s.copy()
            while it.compare(e) < 0:
                chars.append(it.get_char())
                it.forward_char()
            return s, e, ''.join(chars)

        has = False
        kind_re = self._KIND_RES[kind]
        for ln in range(first, last + 1):
            _s, _e, text = line_text(ln)
            if text.strip() and not kind_re.match(text):
                break
        else:
            has = True

        buf.begin_user_action()
        num = 0
        for ln in range(first, last + 1):
            s, _e, text = line_text(ln)
            if not text.strip():
                continue
            m = self._PREFIX_RE.match(text)
            indent = m.group(1) if m else ''
            if has:
                ps = s.copy()
                ps.forward_chars(len(indent))
                pe = s.copy()
                pe.forward_chars(m.end())
                buf.delete(ps, pe)
                continue
            if kind == 'num':
                num += 1
                prefix = (self._CIRCLED[num - 1] if num <= len(self._CIRCLED)
                          else f'{num}.')
            elif kind == 'bullet':
                prefix = '•'
            elif kind == 'box':
                prefix = '☐'
            else:
                prefix = '▎'
            if m and m.end() > 0:
                pe = s.copy()
                pe.forward_chars(m.end())
                buf.delete(s, pe)
            buf.insert(s, prefix + ' ' + indent)
        buf.end_user_action()
        self._focus_body()

    def _insert_divider(self):
        if not self.current_id:
            self.status.set_text('先选择一条笔记')
            return
        buf = self.body.get_buffer()
        it = buf.get_iter_at_mark(buf.get_insert())
        line_start = buf.get_iter_at_line(it.get_line())[1]
        before = buf.get_text(line_start, it, False).strip()
        text = ('\n' if before else '') + '─' * 20 + '\n'
        buf.begin_user_action()
        buf.insert(it, text)
        buf.end_user_action()
        self._focus_body()

    def _focus_body(self):
        GLib.idle_add(self._focus_body_idle)

    def _focus_body_idle(self):
        self.body.grab_focus()
        buf = self.body.get_buffer()
        it = buf.get_iter_at_mark(buf.get_insert())
        self.body.scroll_to_iter(it, 0.0, False, 0.0, 0.0)
        return False

    # picture viewer ---------------------------------------------------------
    _viewer_css_done = False

    def _on_picture_pressed(self, n_press, rel):
        if n_press == 2 and rel:
            self._open_viewer(rel)

    def _on_cover_pressed(self, _g, n_press, _x, _y):
        if n_press != 2:
            return
        e = self.entry(self.current_id) if self.current_id else None
        if e and e.get('cover'):
            self._open_viewer(e['cover'])

    def _viewer_style(self):
        if Editor._viewer_css_done:
            return
        prov = Gtk.CssProvider()
        prov.load_from_data(b'window.dw-viewer { background-color: #0b0b0d; }')
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), prov, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        Editor._viewer_css_done = True

    def _open_viewer(self, rel):
        path = os.path.join(self.root, rel)
        try:
            tex = Gdk.Texture.new_from_filename(path)
        except Exception:
            self.status.set_text('无法打开图片：' + rel)
            return
        self._close_viewer()
        self._viewer_style()
        self._viewer_tex = tex
        win = Gtk.Window(transient_for=self.win, modal=False,
                         title='查看图片 · ' + os.path.basename(rel))
        win.add_css_class('dw-viewer')
        win.connect('close-request', self._viewer_closed)
        mon = Gdk.Display.get_default().get_monitors().get_item(0).get_geometry()
        win.set_default_size(int(mon.width * 0.9), int(mon.height * 0.85))

        header = Gtk.HeaderBar()
        header.set_title_widget(Gtk.Label(label=os.path.basename(rel)))
        self._viewer_zoom_label = Gtk.Label(label='')
        header.pack_end(self._viewer_zoom_label)
        b = Gtk.Button(label='关闭')
        b.connect('clicked', lambda *_: win.close())
        header.pack_end(b)
        win.set_titlebar(header)

        self._viewer_pic = Gtk.Picture(paintable=tex)
        self._viewer_pic.set_content_fit(Gtk.ContentFit.CONTAIN)
        self._viewer_pic.set_can_shrink(True)
        self._viewer_pic.set_hexpand(True)
        self._viewer_pic.set_vexpand(True)
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_child(self._viewer_pic)
        win.set_child(scrolled)
        self._viewer_scrolled = scrolled

        click = Gtk.GestureClick()
        click.connect('pressed', self._viewer_pressed)
        self._viewer_pic.add_controller(click)
        drag = Gtk.GestureDrag()
        drag.connect('drag-begin', self._viewer_drag_begin)
        drag.connect('drag-update', self._viewer_drag_update)
        self._viewer_pic.add_controller(drag)
        scroll = Gtk.EventControllerScroll.new(Gtk.EventControllerScrollFlags.VERTICAL)
        scroll.connect('scroll', self._viewer_scroll)
        self._viewer_pic.add_controller(scroll)
        key = Gtk.EventControllerKey()
        key.connect('key-pressed', self._viewer_key)
        win.add_controller(key)

        boxw, boxh = mon.width * 0.9, mon.height * 0.85 - 60
        fit = min(boxw / tex.get_width(), boxh / tex.get_height())
        self._viewer_zoom = max(0.1, min(8.0, fit))
        self.viewer = win
        self._apply_viewer_zoom()
        win.present()

    def _apply_viewer_zoom(self):
        if not (self.viewer and self._viewer_tex and self._viewer_pic):
            return
        tw, th = self._viewer_tex.get_width(), self._viewer_tex.get_height()
        w = min(12000, max(1, int(tw * self._viewer_zoom)))
        h = min(12000, max(1, int(th * self._viewer_zoom)))
        self._viewer_pic.set_size_request(w, h)
        if self._viewer_zoom_label:
            self._viewer_zoom_label.set_text(f'{self._viewer_zoom * 100:.0f}%')
        GLib.idle_add(self._viewer_center)

    def _viewer_center(self):
        if not self._viewer_scrolled:
            return False
        hadj = self._viewer_scrolled.get_hadjustment()
        vadj = self._viewer_scrolled.get_vadjustment()
        hadj.set_value((hadj.get_upper() - hadj.get_page_size()) / 2)
        vadj.set_value((vadj.get_upper() - vadj.get_page_size()) / 2)
        return False

    def _viewer_scroll(self, _c, _dx, dy):
        if not dy:
            return False
        factor = 1.15 if dy < 0 else 1 / 1.15
        z = max(0.1, min(8.0, self._viewer_zoom * factor))
        if abs(z - self._viewer_zoom) < 1e-6:
            return True
        self._viewer_zoom = z
        self._apply_viewer_zoom()
        return True

    def _viewer_drag_begin(self, _g, _x, _y):
        s = self._viewer_scrolled
        self._viewer_drag_start = None
        if s:
            self._viewer_drag_start = (s.get_hadjustment().get_value(),
                                       s.get_vadjustment().get_value())

    def _viewer_drag_update(self, _g, ox, oy):
        if not (self._viewer_scrolled and self._viewer_drag_start):
            return
        sx, sy = self._viewer_drag_start
        self._viewer_scrolled.get_hadjustment().set_value(sx - ox)
        self._viewer_scrolled.get_vadjustment().set_value(sy - oy)

    def _viewer_pressed(self, _g, n_press, _x, _y):
        if n_press == 2:
            self._close_viewer()

    def _viewer_key(self, _c, keyval, _code, _state):
        if keyval == Gdk.KEY_Escape:
            self._close_viewer()
            return True
        return False

    def _viewer_closed(self, *_):
        self.viewer = None
        self._viewer_pic = None
        self._viewer_tex = None
        self._viewer_scrolled = None
        self._viewer_zoom_label = None
        return False

    def _close_viewer(self):
        win = self.viewer
        self.viewer = None
        self._viewer_pic = None
        self._viewer_tex = None
        self._viewer_scrolled = None
        self._viewer_zoom_label = None
        if win is not None:
            win.destroy()

    def _mark_dirty(self, *_):
        if self._loading:
            return
        self.dirty = True
        self.status.set_text('有未保存的修改')

    def _sync(self):
        if not self.current_id:
            return
        e = self.entry(self.current_id)
        if e is None:
            return
        e['title'] = self.title_entry.get_text()
        e['blocks'] = self._blocks()

    def _refresh_widget(self):
        os.makedirs(self.run_root, exist_ok=True)
        path = os.path.join(self.run_root, 'refresh')
        with open(path + '.tmp', 'w', encoding='utf-8') as f:
            f.write(str(time.time()))
        os.replace(path + '.tmp', path)

    # chapter actions --------------------------------------------------------
    def _on_chapter_selected(self, dd, _pspec):
        if self._loading:
            return
        idx = dd.get_selected()
        if idx >= len(self.chapters()):
            return
        cid = self.chapters()[idx]['id']
        if cid == self.chapter_id:
            return

        def switch():
            self.chapter_id = cid
            self._fill_entries(cid, None)

        def restore():
            self._loading = True
            self._fill_chapters(self.chapter_id)
            self._loading = False

        if self.dirty:
            self._ask_unsaved(switch, restore)
        else:
            switch()

    def _select_chapter(self, cid):
        if cid not in {c['id'] for c in self.chapters()}:
            return
        self._loading = True
        self._fill_chapters(cid)
        self._loading = False
        self._fill_entries(cid, None)

    def _on_new_chapter(self, _b):
        title = self.chapter_entry.get_text().strip()
        if not title:
            self.status.set_text('先输入新章节名')
            return

        def create():
            c = {'id': nb.new_id('ch'), 'title': title}
            self.book['chapters'].append(c)
            self.chapter_entry.set_text('')
            self._fill_chapters(c['id'])
            self._fill_entries(c['id'], None)
            self.dirty = True
            self.status.set_text('章节已添加，点保存生效')

        if self.dirty:
            self._ask_unsaved(create)
        else:
            create()

    def _on_rename_chapter(self, _b):
        title = self.chapter_entry.get_text().strip()
        if not title:
            self.status.set_text('先在输入框写新名称')
            return
        c = next((c for c in self.chapters() if c['id'] == self.chapter_id), None)
        if c:
            c['title'] = title
            self.chapter_entry.set_text('')
            self._fill_chapters(c['id'])
            self.dirty = True
            self.status.set_text('章节已重命名，点保存生效')

    def _on_delete_chapter(self, _b):
        if len(self.chapters()) <= 1:
            self.status.set_text('至少保留一个章节')
            return
        dlg = Gtk.AlertDialog(message='删除这个章节？', detail='章节里的条目会移动到「未分类」。')
        dlg.set_buttons(['取消', '删除'])
        dlg.set_cancel_button(0)

        def done(d, res):
            try:
                choice = d.choose_finish(res)
            except GLib.Error:
                return
            if choice != 1:
                return
            cid = self.chapter_id
            default = self.default_chapter()
            for e in self.book['entries']:
                if e.get('chapter_id') == cid:
                    e['chapter_id'] = default['id']
            self.book['chapters'] = [c for c in self.chapters() if c['id'] != cid]
            if not any(c['title'] == nb.DEFAULT_CHAPTER for c in self.chapters()):
                self.book['chapters'].append(default)
            self._sync()
            self._fill_chapters(default['id'])
            self._fill_entries(default['id'], None)
            self.dirty = True
            self.status.set_text('章节已删除，点保存生效')

        dlg.choose(self.win, None, done)

    # entry actions ----------------------------------------------------------
    def _on_row_activated(self, _lb, row):
        if self._loading:
            return
        self._request_entry(row.entry_id)

    def _request_entry(self, eid):
        if not eid or eid == self.current_id:
            return
        if self.dirty:
            self._ask_unsaved(lambda: self._open_entry(eid))
        else:
            self._open_entry(eid)

    def _open_entry(self, eid):
        e = self.entry(eid)
        if e is None:
            return
        self._sync()
        if e.get('chapter_id') != self.chapter_id:
            self._loading = True
            self._fill_chapters(e['chapter_id'])
            self._loading = False
            self._fill_entries(e['chapter_id'], eid)
        else:
            for i in range(len(self.chapter_entries(self.chapter_id))):
                row = self.listbox.get_row_at_index(i)
                if row and row.entry_id == eid:
                    self._loading = True
                    self.listbox.select_row(row)
                    self._loading = False
                    break
            self._show_entry(e)

    def _on_new_entry(self, _b):
        chapter = self.chapter_id or self.default_chapter()['id']
        e = {'id': nb.new_id('entry'), 'chapter_id': chapter, 'title': '', 'image': '',
             'body': '', 'order': len(self.chapter_entries(chapter))}
        self._sync()
        self.book['entries'].append(e)
        self.dirty = True
        self._fill_entries(chapter, e['id'])
        self.title_entry.grab_focus()
        self.status.set_text('新条目未保存')

    def _on_delete_entry(self, _b):
        e = self.entry(self.current_id) if self.current_id else None
        if e is None:
            return
        dlg = Gtk.AlertDialog(message='删除这条笔记？', detail='图片文件不会自动删除。')
        dlg.set_buttons(['取消', '删除'])
        dlg.set_cancel_button(0)

        def done(d, res):
            try:
                choice = d.choose_finish(res)
            except GLib.Error:
                return
            if choice != 1:
                return
            self.book['entries'] = [x for x in self.book['entries'] if x['id'] != e['id']]
            self.dirty = True
            self._fill_entries(self.chapter_id, None)
            self.status.set_text('条目已删除，点保存生效')

        dlg.choose(self.win, None, done)

    # cover and inline pictures ---------------------------------------------
    def _pick_image_dialog(self, title, callback):
        dialog = Gtk.FileDialog(title=title)
        filters = Gio.ListStore.new(Gtk.FileFilter)
        f = Gtk.FileFilter()
        f.set_name('图片')
        try:
            f.add_pixbuf_formats()
        except Exception:
            pass
        filters.append(f)
        dialog.set_filters(filters)
        dialog.open(self.win, None, callback)

    def _on_choose_cover(self, _b):
        e = self.entry(self.current_id) if self.current_id else None
        if e is None:
            self.status.set_text('先新建或选择一条笔记')
            return
        self._cover_entry = e['id']
        self._pick_image_dialog('选择封面', self._cover_chosen)

    def _cover_chosen(self, dialog, result):
        try:
            file = dialog.open_finish(result)
        except GLib.Error:
            return
        src = file.get_path()
        e = self.entry(getattr(self, '_cover_entry', None))
        if not src or e is None:
            return
        try:
            e['cover'] = self._store_image(src, 'cover')
        except OSError as ex:
            self.status.set_text(f'复制图片失败：{ex}')
            return
        self._show_cover(e)
        self.dirty = True
        self.status.set_text('封面已选择，点保存生效')

    def _on_clear_cover(self, _b):
        e = self.entry(self.current_id) if self.current_id else None
        if e is None:
            return
        e['cover'] = ''
        self._show_cover(e)
        self.dirty = True
        self.status.set_text('封面已清除，点保存生效')

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

    def _on_insert_image(self, _b=None):
        if not self.current_id:
            self.status.set_text('先选择一条笔记')
            return
        buf = self.body.get_buffer()
        self._insert_mark = buf.create_mark(None, buf.get_iter_at_mark(buf.get_insert()), True)
        self._pick_image_dialog('插入图片', self._insert_chosen)

    def _insert_chosen(self, dialog, result):
        try:
            file = dialog.open_finish(result)
        except GLib.Error:
            return
        src = file.get_path()
        mark = self._insert_mark
        if not src or mark is None:
            return
        try:
            rel = self._store_image(src, 'body')
        except OSError as ex:
            self.status.set_text(f'复制图片失败：{ex}')
            return
        it = self.body.get_buffer().get_iter_at_mark(mark)
        self._insert_rel(rel, it)

    def _on_body_key(self, _c, keyval, _code, state):
        ctrl = state & Gdk.ModifierType.CONTROL_MASK
        if keyval == Gdk.KEY_v and ctrl:
            self._paste()
            return True
        if ctrl and keyval in (Gdk.KEY_z, Gdk.KEY_Z):
            if state & Gdk.ModifierType.SHIFT_MASK:
                self._history_redo()
            else:
                self._history_undo()
            return True
        if ctrl and keyval == Gdk.KEY_y:
            self._history_redo()
            return True
        return False

    def _paste(self):
        if not self.current_id:
            return
        cb = self.body.get_clipboard()

        def got_texture(clip, res):
            try:
                tex = clip.read_texture_finish(res)
            except GLib.Error:
                tex = None
            if tex is not None:
                name = f'body-{self.current_id}-{uuid.uuid4().hex}.png'
                images = os.path.join(self.root, 'images')
                os.makedirs(images, exist_ok=True)
                try:
                    tex.save_to_png(os.path.join(images, name))
                except GLib.Error as ex:
                    self.status.set_text(f'粘贴图片失败：{ex}')
                    return
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
                self._focus_body()

        cb.read_text_async(None, got)

    def _on_drop(self, _target, value, x, y):
        if not self.current_id or value is None:
            return False
        try:
            ok, it = self.body.get_iter_at_location(int(x), int(y))
        except (TypeError, ValueError):
            ok, it = False, self.body.get_buffer().get_end_iter()
        if not ok:
            it = self.body.get_buffer().get_end_iter()
        first = True
        for gfile in value.get_files():
            src = gfile.get_path()
            if not src or os.path.splitext(src)[1].lower() not in nb.EXTS:
                continue
            try:
                rel = self._store_image(src, 'body')
            except OSError as ex:
                self.status.set_text(f'复制图片失败：{ex}')
                continue
            self._insert_rel(rel, it if first else None)
            first = False
        return True

    # save -------------------------------------------------------------------
    def _on_save(self, _b):
        self._sync()
        try:
            self.revision = nb.save_book(self.root, self.book, expected_revision=self.revision)
        except nb.RevisionConflict as e:
            self._conflict(str(e))
            return
        except nb.NotebookError as e:
            self.status.set_text(str(e))
            return
        self.book = nb.load_book(self.root) or self.book
        self.dirty = False
        self.status.set_text('已保存')
        self._refresh_widget()
        self._fill_chapters(self.chapter_id)
        ids = [x['id'] for x in self.chapter_entries(self.chapter_id)]
        keep = self.current_id if self.current_id in ids else (ids[0] if ids else None)
        self._fill_entries(self.chapter_id, keep)

    def _conflict(self, text):
        self.status.set_text(text)
        dlg = Gtk.AlertDialog(message='笔记已在别处修改', detail=text + '\n重新载入会放弃当前未保存的输入。')
        dlg.set_buttons(['取消', '重新载入'])
        dlg.set_cancel_button(0)

        def done(d, res):
            try:
                choice = d.choose_finish(res)
            except GLib.Error:
                return
            if choice == 1:
                self.dirty = False
                self._load(self.current_id)

        dlg.choose(self.win, None, done)

    # close ------------------------------------------------------------------
    def _on_close(self, *_):
        if self.dirty and not self._quitting:
            dlg = Gtk.AlertDialog(message='有未保存的修改', detail='保存后再关闭？')
            dlg.set_buttons(['取消', '放弃', '保存'])
            dlg.set_cancel_button(0)
            dlg.set_default_button(2)

            def done(d, res):
                try:
                    choice = d.choose_finish(res)
                except GLib.Error:
                    return
                if choice == 0:
                    return
                if choice == 2:
                    self._on_save(None)
                    if self.dirty:
                        return
                self.dirty = False
                self._quit()

            dlg.choose(self.win, None, done)
            return True
        self._quit()
        return True

    def _ask_unsaved(self, proceed, on_cancel=None):
        dlg = Gtk.AlertDialog(message='有未保存的修改', detail='离开当前编辑前要保存吗？')
        dlg.set_buttons(['取消', '放弃', '保存'])
        dlg.set_cancel_button(0)
        dlg.set_default_button(2)

        def done(d, res):
            try:
                choice = d.choose_finish(res)
            except GLib.Error:
                return
            if choice == 0:
                if on_cancel:
                    on_cancel()
                return
            if choice == 2:
                self._on_save(None)
                if self.dirty:
                    return
            else:
                # drop the edits for real: the in-memory book already has them
                if not self._discard_edits():
                    return
            self.dirty = False
            proceed()

        dlg.choose(self.win, None, done)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--instance', required=True)
    p.add_argument('--entry', default=None)
    p.add_argument('--chapter', default=None)
    ns, _ = p.parse_known_args()
    app = Editor(ns.instance)
    app.requested_entry = ns.entry
    app.requested_chapter = ns.chapter
    return app.run(None)


if __name__ == '__main__':
    sys.exit(main())
