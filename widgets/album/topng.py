#!/usr/bin/env python3
"""Thumbnail cache for the album widget.

  topng.py --manifest --dir DIR --width PX --height PX
      prints "path<TAB>sha256-key" for every image in DIR, sorted by file name.
  topng.py --src PATH --cache DIR --width PX --height PX
      converts PATH to a PNG thumbnail in CACHE/<key>.png.

The key hashes the canonical path, the source mtime_ns, its size, the requested
pixel box and the converter version, so a moved, edited or replaced picture never
reuses a stale image. Original files are never modified; writes are atomic and a
lock keeps concurrent runs from converting the same key twice.
"""
import argparse
import fcntl
import hashlib
import os
import sys

from PIL import Image, ImageOps

VERSION = '2'
EXTS = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.gif', '.tif', '.tiff'}


def canonical(path):
    return os.path.realpath(os.path.expanduser(path))


def key_for(src, width, height):
    st = os.stat(src)
    raw = '\0'.join((src, str(st.st_mtime_ns), str(st.st_size), f'{width}x{height}', VERSION))
    return hashlib.sha256(raw.encode('utf-8', 'surrogateescape')).hexdigest()


def manifest(directory, width, height):
    directory = os.path.expanduser(directory)
    try:
        names = sorted(os.listdir(directory))
    except OSError:
        return
    for name in names:
        src = os.path.join(directory, name)
        if os.path.splitext(name)[1].lower() not in EXTS or not os.path.isfile(src):
            continue
        try:
            print(f'{src}\t{key_for(canonical(src), width, height)}')
        except OSError:
            continue


def write_atomic(path, text):
    tmp = f'{path}.{os.getpid()}.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        f.write(text)
    os.replace(tmp, path)


def convert(src, cache, width, height):
    """Returns the cached PNG path, or None when the image cannot be read."""
    src = canonical(src)
    os.makedirs(cache, exist_ok=True)
    key = key_for(src, width, height)
    dst = os.path.join(cache, key + '.png')
    err = os.path.join(cache, key + '.err')
    if os.path.exists(dst):
        try:
            os.unlink(err)
        except OSError:
            pass
        return dst
    with open(os.path.join(cache, '.lock'), 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if os.path.exists(dst):          # another run finished while we waited
            try:
                os.unlink(err)
            except OSError:
                pass
            return dst
        tmp = os.path.join(cache, f'.{key}.{os.getpid()}.tmp')
        try:
            with Image.open(src) as im:
                im = ImageOps.exif_transpose(im)
                im.thumbnail((max(1, width), max(1, height)), Image.LANCZOS)
                im = im.convert('RGBA')
                im.save(tmp, 'PNG')
            os.replace(tmp, dst)
            try:
                os.unlink(err)
            except OSError:
                pass
            return dst
        except Exception as e:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            write_atomic(err, f'{type(e).__name__}: {e}\n')
            return None
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--manifest', action='store_true')
    p.add_argument('--dir')
    p.add_argument('--src')
    p.add_argument('--cache')
    p.add_argument('--width', type=int, required=True)
    p.add_argument('--height', type=int, required=True)
    a = p.parse_args()
    if a.manifest:
        if not a.dir:
            p.error('--manifest needs --dir')
        manifest(a.dir, a.width, a.height)
        return 0
    if not (a.src and a.cache):
        p.error('conversion needs --src and --cache')
    return 0 if convert(a.src, a.cache, a.width, a.height) else 1


if __name__ == '__main__':
    sys.exit(main())
