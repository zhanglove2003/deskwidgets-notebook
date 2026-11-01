#!/usr/bin/env python3
"""GTK4 editor for the album notebook widget.

Click the card -> this window opens on the current entry. One window per instance:
a second click activates the same window and switches the entry (asking first when
there are unsaved edits). Saving rebuilds the widget snapshot through a refresh marker.

Usage: editor.py --instance ID [--entry EID] [--chapter CHID]
"""
import argparse
import os
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gi  # noqa: E402

gi.require_version('Gtk', '4.0')
gi.require_version('Gdk', '4.0')
from gi.repository import Gdk, Gio, GLib, Gtk  # noqa: E402

import notebook as nb  # noqa: E402


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

        tools = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        b = Gtk.Button(label='插入图片…'); b.connect('clicked', self._on_insert_image)
        tools.append(b)
        hint = Gtk.Label(label='图片插在光标处，也可以直接粘贴或拖入正文', xalign=0)
        hint.add_css_class('dim-label')
        tools.append(hint)
        right.append(tools)

        body_frame = Gtk.Frame(label='正文')
        body_frame.set_vexpand(True)
        body_scroll = Gtk.ScrolledWindow(vexpand=True)
        self.body = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR)
        self.body.set_left_margin(8)
        self.body.set_right_margin(8)
        self.body.set_top_margin(6)
        self.body.get_buffer().connect('changed', self._mark_dirty)
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
        """Drop widget edits: re-read the book and rebuild the UI from disk."""
        self.dirty = False
        try:
            book = nb.load_book(self.root)
        except nb.NotebookError as e:
            self.status.set_text(str(e))
            return
        if book is None:
            return
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
            label = Gtk.Label(label=e['title'] or '（无标题）', xalign=0,
                              margin_top=6, margin_bottom=6, margin_start=8, margin_end=8)
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
        name = f'{kind}-{self.current_id}-{int(time.time() * 1000)}{ext}'
        images = os.path.join(self.root, 'images')
        os.makedirs(images, exist_ok=True)
        shutil.copy2(src, os.path.join(images, name))
        return 'images/' + name

    def _show_cover(self, e):
        self.cover_thumb.set_paintable(None)
        if not e or not e.get('cover'):
            self.cover_label.set_text('未设置时用正文第一张图')
            return
        self.cover_label.set_text(e['cover'])
        try:
            self.cover_thumb.set_paintable(
                Gdk.Texture.new_from_filename(os.path.join(self.root, e['cover'])))
        except Exception:
            pass

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

    def _on_insert_image(self, _b):
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
        if keyval == Gdk.KEY_v and state & Gdk.ModifierType.CONTROL_MASK:
            self._paste()
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
                name = f'body-{self.current_id}-{int(time.time() * 1000)}.png'
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
                self._discard_edits()
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
