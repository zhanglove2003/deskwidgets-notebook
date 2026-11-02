#!/usr/bin/env python3
"""Notebook data for the album widget.

The book lives in ~/.local/share/deskwidgets/notebooks/<hex instance>/notebook.json;
the reading position in view.json next to it. The widget never parses JSON: prepare
writes a small versioned snapshot under $XDG_RUNTIME_DIR/deskwidgets/album-<hex>/
and switches a `current` pointer atomically.

Commands
  prepare --instance ID --folder PATH --width PX --height PX [--chapter all|CHID] [--entry EID]
  select  --instance ID [--chapter all|CHID] [--entry EID]
  refresh --instance ID
"""
import argparse
import fcntl
import json
import os
import shutil
import sys
import time
import uuid

import topng

HOME = os.path.expanduser('~')
RUN = os.path.join(os.environ.get('XDG_RUNTIME_DIR') or f'/tmp/deskwidgets-{os.getuid()}', 'deskwidgets')
DATA = os.path.join(os.environ.get('XDG_DATA_HOME') or os.path.join(HOME, '.local', 'share'),
                    'deskwidgets', 'notebooks')
EXTS = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.gif', '.tif', '.tiff'}
DEFAULT_CHAPTER = '未分类'
ALL_CHAPTERS = '全部章节'
VERSION = 2


class NotebookError(Exception):
    pass


class RevisionConflict(NotebookError):
    pass


def inst_hex(instance):
    return instance.encode('utf-8').hex()


def book_root(instance):
    return os.path.join(DATA, inst_hex(instance))


def run_root(instance):
    return os.path.join(RUN, 'album-' + inst_hex(instance))


def new_id(prefix):
    return f'{prefix}-{uuid.uuid4().hex}'


def _read_json(path):
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def _write_atomic(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f'{path}.{os.getpid()}.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        f.write(text)
    os.replace(tmp, path)


def _lock(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return open(path, 'a')


def _repair(data):
    """Never let a slightly old/hand-edited file lose the user's notes."""
    if not isinstance(data, dict):
        raise NotebookError('笔记库格式不正确（顶层不是对象）')
    chapters = [c for c in (data.get('chapters') or [])
                if isinstance(c, dict) and isinstance(c.get('id'), str) and c['id']]
    seen = {c['id'] for c in chapters}
    if not chapters:
        chapters = [{'id': new_id('ch'), 'title': DEFAULT_CHAPTER}]
    for c in chapters:
        c['title'] = str(c.get('title') or '')
    default = next((c for c in chapters if c['title'] == DEFAULT_CHAPTER), None)
    if default is None:
        default = {'id': new_id('ch'), 'title': DEFAULT_CHAPTER}
        chapters.append(default)
    entries = []
    for e in (data.get('entries') or []):
        if not isinstance(e, dict) or not isinstance(e.get('id'), str) or not e['id']:
            continue
        if e.get('chapter_id') not in seen:
            e['chapter_id'] = default['id']
        e['title'] = str(e.get('title') or '')
        image = e.pop('image', '')
        body = e.pop('body', '')
        if 'cover' not in e and image:
            e['cover'] = image
        e['cover'] = str(e.get('cover') or '')
        if 'blocks' not in e:
            e['blocks'] = [{'type': 'text', 'text': body}] if body else []
        blocks = []
        for b in e.get('blocks') if isinstance(e.get('blocks'), list) else []:
            if not isinstance(b, dict):
                continue
            if b.get('type') == 'text' and b.get('text'):
                blocks.append({'type': 'text', 'text': str(b['text'])})
            elif b.get('type') == 'image' and b.get('image'):
                blocks.append({'type': 'image', 'image': str(b['image'])})
        e['blocks'] = blocks
        try:
            e['order'] = int(e.get('order'))
        except (TypeError, ValueError):
            e['order'] = len(entries)
        entries.append(e)
    entries.sort(key=lambda e: (e['order'], e['title']))
    return {'version': VERSION, 'revision': int(data.get('revision') or 1),
            'chapters': chapters, 'entries': entries}


def load_book(root):
    """None when there is no book yet; NotebookError for a corrupt one (never overwritten)."""
    path = os.path.join(root, 'notebook.json')
    try:
        raw = _read_json(path)
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as e:
        raise NotebookError(f'笔记库无法读取：{path}（{e}）')
    old = int(raw.get('version') or 1) < VERSION or any(
        isinstance(e, dict) and ('image' in e or 'body' in e)
        for e in raw.get('entries') or [])
    book = _repair(raw)
    if old:
        try:
            book['revision'] = save_book(root, book, expected_revision=book['revision'])
        except RevisionConflict:
            book = _repair(_read_json(path))
    return book


def cover_of(entry):
    """Explicit cover, else the first inline picture (design: first picture is the cover)."""
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


def save_book(root, book, expected_revision=None):
    with _lock(os.path.join(root, '.lock')) as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        path = os.path.join(root, 'notebook.json')
        try:
            disk_rev = _repair(_read_json(path))['revision']
        except FileNotFoundError:
            disk_rev = 0
        except (OSError, ValueError) as e:
            raise NotebookError(f'笔记库无法读取：{path}（{e}）')
        if expected_revision is not None and disk_rev != expected_revision:
            raise RevisionConflict(f'笔记已在别处保存（磁盘 revision {disk_rev}，当前 {expected_revision}）')
        clean = _repair(book)
        clean['revision'] = disk_rev + 1
        _write_atomic(path, json.dumps(clean, ensure_ascii=False, indent=2) + '\n')
        return clean['revision']


def load_view(root):
    try:
        data = _read_json(os.path.join(root, 'view.json'))
    except (OSError, ValueError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    chapter = data.get('chapter_id')
    entry = data.get('entry_id')
    return {'version': VERSION,
            'chapter_id': chapter if isinstance(chapter, str) and chapter else None,
            'entry_id': entry if isinstance(entry, str) and entry else None}


def save_view(root, view):
    os.makedirs(root, exist_ok=True)
    with _lock(os.path.join(root, '.view.lock')) as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        out = {'version': VERSION,
               'chapter_id': view.get('chapter_id') or None,
               'entry_id': view.get('entry_id') or None}
        _write_atomic(os.path.join(root, 'view.json'), json.dumps(out) + '\n')
        return out


def _legacy_view(root, instance, entries):
    """Match the old album's saved page (RUN/selected.txt path or album-<hex>.idx)."""
    run = run_root(instance)
    selected = os.path.join(run, 'selected.txt')
    try:
        with open(selected, encoding='utf-8') as f:
            path = f.read().strip()
        stem = os.path.splitext(os.path.basename(path))[0]
        for e in entries:
            if e['title'] == stem:
                return e['id']
    except OSError:
        pass
    try:
        with open(os.path.join(RUN, 'album-' + inst_hex(instance) + '.idx'), encoding='utf-8') as f:
            n = int(f.read().strip())
        if 1 <= n <= len(entries):
            return entries[n - 1]['id']
    except (OSError, ValueError):
        pass
    return None


def ensure_book(root, folder, instance):
    book = load_book(root)
    if book is not None:
        return book
    images_dir = os.path.join(root, 'images')
    os.makedirs(images_dir, exist_ok=True)
    chapter = {'id': new_id('ch'), 'title': DEFAULT_CHAPTER}
    entries = []
    src_dir = os.path.expanduser(folder or '')
    if src_dir and os.path.isdir(src_dir):
        for name in sorted(os.listdir(src_dir)):
            src = os.path.join(src_dir, name)
            ext = os.path.splitext(name)[1]
            if ext.lower() not in EXTS or not os.path.isfile(src):
                continue
            eid = new_id('entry')
            dst_name = eid + ext.lower()
            shutil.copy2(src, os.path.join(images_dir, dst_name))
            entries.append({'id': eid, 'chapter_id': chapter['id'],
                            'title': os.path.splitext(name)[0], 'cover': 'images/' + dst_name,
                            'blocks': [], 'order': len(entries)})
    book = {'version': VERSION, 'revision': 1, 'chapters': [chapter], 'entries': entries}
    book['revision'] = save_book(root, book, expected_revision=None)
    legacy = _legacy_view(root, instance, entries)
    view = load_view(root)
    if legacy and not view.get('entry_id'):
        save_view(root, {'chapter_id': chapter['id'], 'entry_id': legacy})
    return _repair(book)


def _write(path, text):
    _write_atomic(path, text if text is not None else '')


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


def _cleanup(run, keep):
    snap = os.path.join(run, 'snapshot')
    try:
        gens = sorted(d for d in os.listdir(snap) if d.startswith('g-'))
    except OSError:
        return
    older = [g for g in gens if g < keep]
    keep_set = {keep} | ({older[-1]} if older else set())
    for g in gens:
        if g not in keep_set:
            shutil.rmtree(os.path.join(snap, g), ignore_errors=True)


def prepare(args):
    root = book_root(args.instance)
    run = run_root(args.instance)
    os.makedirs(run, exist_ok=True)
    with _lock(os.path.join(run, '.prepare.lock')) as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        book = ensure_book(root, args.folder, args.instance)
        view = load_view(root)
        chapters = book['chapters']
        ids = {c['id'] for c in chapters}
        chapter = args.chapter if args.chapter is not None else view.get('chapter_id')
        if chapter in ('', 'all', 'null') or chapter not in ids:
            chapter = None
        entries = sorted([e for e in book['entries'] if chapter is None or e.get('chapter_id') == chapter],
                         key=lambda e: (e.get('order', 0), e.get('title', '')))
        wanted = args.entry or view.get('entry_id')
        idx = next((i for i, e in enumerate(entries) if e['id'] == wanted), 0)
        entry_id = entries[idx]['id'] if entries else None
        save_view(root, {'chapter_id': chapter, 'entry_id': entry_id})
        _write(os.path.join(run, 'view-path.txt'), os.path.join(root, 'view.json') + '\n')
        _write(os.path.join(run, 'size.txt'), f'{args.width} {args.height}\n')
        try:
            os.unlink(os.path.join(run, 'error.txt'))
        except OSError:
            pass

        gen = f'g-{int(time.time() * 1000)}-{os.getpid()}'
        snap = os.path.join(run, 'snapshot')
        gen_dir = os.path.join(snap, gen)
        for n in range(1, len(entries) + 1):
            os.makedirs(os.path.join(gen_dir, 'entries', str(n)), exist_ok=True)
        os.makedirs(os.path.join(gen_dir, 'chapters'), exist_ok=True)
        title = next((c['title'] for c in chapters if c['id'] == chapter), ALL_CHAPTERS)
        _write(os.path.join(gen_dir, 'generation'), gen + '\n')
        _write(os.path.join(gen_dir, 'chapter.txt'), title + '\n')
        _write(os.path.join(gen_dir, 'chapter_id'), (chapter or '') + '\n')
        _write(os.path.join(gen_dir, 'count'), str(len(entries)) + '\n')
        _write(os.path.join(gen_dir, 'selected'), str(idx + 1) + '\n')
        _write(os.path.join(gen_dir, 'chapters', 'count'), str(len(chapters)) + '\n')
        for n, c in enumerate(chapters, 1):
            d = os.path.join(gen_dir, 'chapters', str(n))
            os.makedirs(d, exist_ok=True)
            _write(os.path.join(d, 'id'), c['id'] + '\n')
            _write(os.path.join(d, 'title.txt'), c['title'] + '\n')
        for n, e in enumerate(entries, 1):
            d = os.path.join(gen_dir, 'entries', str(n))
            src = cover_of(e)
            has_cover = bool(src) and os.path.isfile(
                os.path.normpath(os.path.join(root, src)))
            _write(os.path.join(d, 'id'), e['id'] + '\n')
            _write(os.path.join(d, 'title.txt'), (e.get('title') or '（无标题）') + '\n')
            _write(os.path.join(d, 'excerpt.txt'), excerpt_of(e) + '\n')
            _write(os.path.join(d, 'has-cover'), '1\n' if has_cover else '0\n')

        cache = {'run': run, 'book_root': root}
        order = [idx, idx + 1, idx - 1]
        done = set()
        for n in order:
            if 0 <= n < len(entries) and n not in done:
                _convert(entries[n], gen_dir, n + 1, args.width, args.height, cache)
                done.add(n)
        _write(os.path.join(snap, 'current'), gen + '\n')   # atomic enough: one rename
        for n in range(len(entries)):
            if n not in done:
                _convert(entries[n], gen_dir, n + 1, args.width, args.height, cache)
        _cleanup(run, gen)
        return 0


def select(args):
    root = book_root(args.instance)
    book = ensure_book(root, args.folder, args.instance)
    ids = {c['id'] for c in book['chapters']}
    view = load_view(root)
    chapter = args.chapter if args.chapter is not None else view.get('chapter_id')
    if chapter in ('', 'all', 'null') or chapter not in ids:
        chapter = None
    entries = [e for e in book['entries'] if chapter is None or e.get('chapter_id') == chapter]
    entry = args.entry or view.get('entry_id')
    if entry not in {e['id'] for e in entries}:
        entry = entries[0]['id'] if entries else None
    save_view(root, {'chapter_id': chapter, 'entry_id': entry})
    return 0


def refresh(args):
    run = run_root(args.instance)
    width, height = 712, 340
    try:
        with open(os.path.join(run, 'size.txt'), encoding='ascii') as f:
            width, height = (int(v) for v in f.read().split())
    except (OSError, ValueError):
        pass
    args.chapter = None
    args.entry = None
    args.width, args.height = width, height
    return prepare(args)


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest='command', required=True)
    for name in ('prepare', 'refresh', 'select'):
        s = sub.add_parser(name)
        s.add_argument('--instance', required=True)
        s.add_argument('--folder', default='')
        if name != 'select':
            s.add_argument('--width', type=int, default=712)
            s.add_argument('--height', type=int, default=340)
        s.add_argument('--chapter', default=None)
        s.add_argument('--entry', default=None)
    args = p.parse_args()
    run = run_root(args.instance)
    os.makedirs(run, exist_ok=True)
    try:
        return {'prepare': prepare, 'refresh': refresh, 'select': select}[args.command](args)
    except NotebookError as e:
        _write(os.path.join(run, 'error.txt'), str(e) + '\n')
        print(f'notebook: {e}', file=sys.stderr)
        return 1
    except Exception as e:
        _write(os.path.join(run, 'error.txt'), f'{type(e).__name__}: {e}\n')
        print(f'notebook: {type(e).__name__}: {e}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
