-- 图文笔记: chapter header, picture, note preview and page bar.
-- Data lives in Python (notebook.py writes a small versioned snapshot); this file only
-- reads the snapshot and writes the reading position, so a page turn never waits on disk.
local L = require 'lib'
local C, F, PAD, ICON = L.C, L.F, L.PAD, L.ICON
local DPI = L.DPI or 1
local SCALE = L.SCALE or 1

local W = {}
local FOLDER = L.trim(L.opt('folder', ''))
local FIT = L.opt('fit', 'cover')
local AUTO = L.opt_num('autoplay', 0)

local function full_hex(s)
    return (tostring(s):gsub('.', function(c) return string.format('%02x', c:byte()) end))
end

local RUN = L.RUN .. '/album-' .. full_hex(L.ID)
local SNAP = RUN .. '/snapshot'
local CURRENT = SNAP .. '/current'
local VIEWPATH = RUN .. '/view-path.txt'
local REFRESH = RUN .. '/refresh'
local ERROR = RUN .. '/error.txt'
local SIZEFILE = RUN .. '/size.txt'

L.spawn('/bin/mkdir -p ' .. L.quote(RUN))

local gen, chapter_id, chapter_title = nil, '', ''
local entries, chapters = {}, {}
local count, idx = 0, 0
local menu_open, menu_scroll = false, 0
local surf, surf_key
local zones = {}
local last_tw, last_th = -1, -1
local prepared_at, prepared_size = 0, ''
local pending_chapter = nil

local function read_file(path)
    local f = io.open(path, 'r')
    if not f then return nil end
    local s = f:read('*a')
    f:close()
    return s
end

local function write_atomic(path, text)
    local f = io.open(path .. '.tmp', 'w')
    if not f then return false end
    f:write(text)
    f:close()
    return os.rename(path .. '.tmp', path)
end

local function trim(s) return ((s or ''):gsub('^%s+', ''):gsub('%s+$', '')) end

-- snapshot ------------------------------------------------------------------
local function load_snapshot()
    local g = trim(read_file(CURRENT))
    if g == '' then return false end
    if g == gen then return true end
    local d = SNAP .. '/' .. g
    local n = tonumber(trim(read_file(d .. '/count'))) or 0
    local es = {}
    for i = 1, n do
        local id = trim(read_file(d .. '/entries/' .. i .. '/id'))
        if id ~= '' then
            local has_cover = trim(read_file(d .. '/entries/' .. i .. '/has-cover')) == '1'
            es[i] = {id = id, title = trim(read_file(d .. '/entries/' .. i .. '/title.txt')),
                     cover = has_cover and 'cover.png' or '',
                     excerpt = trim(read_file(d .. '/entries/' .. i .. '/excerpt.txt')),
                     dir = d .. '/entries/' .. i}
        end
    end
    local cn = tonumber(trim(read_file(d .. '/chapters/count'))) or 0
    local cs = {}
    for i = 1, cn do
        local id = trim(read_file(d .. '/chapters/' .. i .. '/id'))
        if id ~= '' then cs[#cs + 1] = {id = id, title = trim(read_file(d .. '/chapters/' .. i .. '/title.txt'))} end
    end
    entries, chapters, count = es, cs, n
    chapter_id = trim(read_file(d .. '/chapter_id'))
    chapter_title = trim(read_file(d .. '/chapter.txt'))
    idx = tonumber(trim(read_file(d .. '/selected'))) or 1
    if count == 0 then idx = 0 end
    if idx > count then idx = count end
    gen = g
    return true
end

local function save_view()
    local vp = trim(read_file(VIEWPATH))
    if vp == '' then return end
    local e = entries[idx]
    local cid = chapter_id ~= '' and ('"' .. chapter_id .. '"') or 'null'
    local eid = e and ('"' .. e.id .. '"') or 'null'
    write_atomic(vp, string.format('{"version": 1, "chapter_id": %s, "entry_id": %s}\n', cid, eid))
end

local function page(d)
    if count == 0 then return false end
    idx = idx + d
    if idx < 1 then idx = count end
    if idx > count then idx = 1 end
    save_view()
    return true
end

local function prepare(width, height, chapter, entry, force)
    local key = width .. 'x' .. height .. '|' .. tostring(chapter or '') .. '|' .. tostring(entry or '')
    local now = os.time()
    if not force and (key == prepared_size or now - prepared_at < 2) then return end
    prepared_at, prepared_size = now, key
    local args = {'prepare', '--instance', L.ID, '--folder', FOLDER,
                  '--width', tostring(width), '--height', tostring(height)}
    if chapter == 'all' then
        args[#args + 1] = '--chapter'; args[#args + 1] = 'all'
    elseif chapter and chapter ~= '' then
        args[#args + 1] = '--chapter'; args[#args + 1] = chapter
    end
    if entry then args[#args + 1] = '--entry'; args[#args + 1] = entry end
    L.python('notebook.py', table.unpack(args))
end

local function open_editor()
    local e = entries[idx]
    if e then
        L.python('editor.py', '--instance', L.ID, '--entry', e.id)
    else
        L.python('editor.py', '--instance', L.ID)
    end
end

local function switch_chapter(cid)
    menu_open = false
    pending_chapter = cid or 'all'
    prepare(last_tw, last_th, pending_chapter, nil, true)
end

-- layout --------------------------------------------------------------------
local function metrics(w, h)
    local pad = math.min(12, math.max(8, math.floor(h * 0.07)))
    local header_h = 16
    local footer_h = 14
    local title_h = 13
    local line_h = 11
    local max_body = (h >= 280) and 8 or ((h >= 160) and 2 or 1)
    local inner_h = h - 2 * pad
    local body_lines = max_body
    local image_h = inner_h - header_h - footer_h - title_h - body_lines * line_h - 8
    while body_lines > 0 and image_h < 34 do
        body_lines = body_lines - 1
        image_h = inner_h - header_h - footer_h - title_h - body_lines * line_h - 8
    end
    if image_h < 0 then image_h = 0 end
    return pad, header_h, footer_h, title_h, line_h, body_lines, image_h
end

local function inside(z, x, y)
    return z and x >= z.x and x <= z.x + z.w and y >= z.y and y <= z.y + z.h
end

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
    if cairo_image_surface_get_width(s) > 0 then
        surf = s
    else
        cairo_surface_destroy(s)
    end
    return surf
end

-- menu ----------------------------------------------------------------------
local function menu_items()
    local items = {{id = 'all', title = '全部章节'}}
    for _, c in ipairs(chapters) do items[#items + 1] = c end
    return items
end

local menu_visible = 4

-- drawing -------------------------------------------------------------------
local function draw_menu(cr, x, y, w, h, pad)
    local items = menu_items()
    local px, py = x + pad - 4, y + pad - 4
    local pw, ph = w - 2 * pad + 8, h - 2 * pad + 8
    L.rrect(cr, px, py, pw, ph, 12)
    cairo_set_source_rgba(cr, 0.07, 0.07, 0.09, 0.96)
    cairo_fill(cr)
    local row_h = 19
    local first = y + pad + 6 + 18
    local visible = math.floor((ph - 30) / row_h)
    menu_visible = visible
    local maxs = math.max(0, #items - visible)
    if menu_scroll > maxs then menu_scroll = maxs end
    local row_zones = {}
    L.font(cr, F.semibold, 9.5); L.set(cr, C.text3)
    L.text(cr, '选择章节', x + pad + 4, y + pad + 12)
    for i = 1, visible do
        local n = menu_scroll + i
        local item = items[n]
        if not item then break end
        local ry = first + (i - 1) * row_h
        local active = (item.id == 'all' and chapter_id == '') or item.id == chapter_id
        if active then
            L.rrect(cr, x + pad, ry - 12, w - 2 * pad, row_h - 3, 6)
            cairo_set_source_rgba(cr, 1, 1, 1, 0.10); cairo_fill(cr)
        end
        L.font(cr, active and F.semibold or F.regular, 10.5)
        L.set(cr, active and C.text or C.text2)
        L.text(cr, L.fit(cr, item.title, w - 2 * pad - 26), x + pad + 8, ry)
        row_zones[i] = {id = item.id, x = pad, y = ry - y - 14, w = w - 2 * pad, h = row_h}
    end
    zones.menu = row_zones
    zones.menu_box = {x = pad - 4, y = pad - 4, w = pw, h = ph}
    if #items > visible then
        L.font(cr, F.regular, 9); L.set(cr, C.text3)
        L.text(cr, (menu_scroll + 1) .. '–' .. math.min(menu_scroll + visible, #items) .. ' / ' .. #items,
               x + w - pad - 4, y + pad + 12, 'r')
    end
end

local function draw_content(cr, x, y, w, h)
    local pad, header_h, footer_h, title_h, line_h, body_lines, image_h = metrics(w, h)
    zones = {}
    local e = entries[idx]
    -- header: chapter name + position
    L.font(cr, F.semibold, 10.5); L.set(cr, C.text2)
    L.text(cr, L.fit(cr, chapter_title ~= '' and chapter_title or '全部章节', w - 2 * pad - 44), x + pad, y + pad + 10)
    L.font(cr, F.regular, 9); L.set(cr, C.text3)
    L.text(cr, '›', x + pad + L.width(cr, L.fit(cr, chapter_title ~= '' and chapter_title or '全部章节', w - 2 * pad - 44)) + 5,
           y + pad + 10)
    if count > 0 then L.text(cr, idx .. ' / ' .. count, x + w - pad, y + pad + 10, 'r') end
    zones.chapter = {x = pad, y = pad, w = math.max(40, w - 2 * pad - 44), h = header_h}
    local iy = y + pad + header_h + 2
    local rel_y = iy - y
    local iw = w - 2 * pad
    local surf_draw = nil
    if e then surf_draw = image_surface(e) end
    if e and surf_draw then
        if FIT == 'contain' then
            local sw, sh = cairo_image_surface_get_width(surf_draw), cairo_image_surface_get_height(surf_draw)
            local k = math.min(iw / sw, image_h / sh)
            local dw, dh = sw * k, sh * k
            L.cover(cr, surf_draw, x + pad + (iw - dw) / 2, iy + (image_h - dh) / 2, dw, dh, 10)
        else
            L.cover(cr, surf_draw, x + pad, iy, iw, image_h, 10)
        end
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
        if e.cover == '' then lines = math.max(1, math.floor((y + h - pad - footer_h - by) / line_h)) end
        L.font(cr, F.regular, 9.5); L.set(cr, C.text2)
        for i, line in ipairs(L.wrap(cr, e.excerpt or '', iw, lines)) do
            L.text(cr, line, x + pad, by + (i - 1) * line_h)
        end
        zones.open = zones.open or {x = pad, y = rel_y, w = iw, h = math.max(1, ty + 40 - iy)}
    else
        L.font(cr, F.medium, 11); L.set(cr, C.text2)
        L.text(cr, '还没有笔记', x + w / 2, y + h / 2 - 8, 'c')
        L.font(cr, F.regular, 10); L.set(cr, C.text3)
        L.text(cr, '点击这里新建第一条', x + w / 2, y + h / 2 + 10, 'c')
        zones.open = {x = pad, y = pad, w = w - 2 * pad, h = h - 2 * pad}
    end

    -- footer: previous / next
    local fy = y + h - pad - 2
    L.font(cr, F.semibold, 14); L.set(cr, count > 1 and C.text2 or C.text3)
    L.text(cr, '‹', x + pad + 2, fy)
    L.text(cr, '›', x + w - pad - 8, fy)
    zones.prev = {x = pad - 4, y = fy - y - 14, w = 26, h = 20}
    zones.next = {x = w - pad - 26, y = fy - y - 14, w = 26, h = 20}
end

local function draw_error(cr, x, y, w, h, text)
    L.font(cr, F.regular, 9.5); L.set(cr, L.SYS.red)
    for i, line in ipairs(L.wrap(cr, text, w - 2 * PAD, 5)) do
        L.text(cr, line, x + PAD, y + PAD + 14 + (i - 1) * 12)
    end
end

function W.mouse(ev)
    if ev.type == 'mouse_scroll' and ev.direction then
        if menu_open then
            local items = menu_items()
            local maxs = math.max(0, #items - menu_visible)
            menu_scroll = menu_scroll + (ev.direction == 'down' and 1 or -1)
            if menu_scroll < 0 then menu_scroll = 0 end
            if menu_scroll > maxs then menu_scroll = maxs end
            return true
        end
        if ev.x and ev.y then
            local mx, my = ev.x - L.M, ev.y - L.M
            if inside(zones.open, mx, my) then
                return page(ev.direction == 'down' and 1 or -1)
            end
        end
    end
    return false
end

function W.click(mx, my, w, h)
    if menu_open then
        if zones.menu then
            for _, z in ipairs(zones.menu) do
                if inside(z, mx, my) then
                    switch_chapter(z.id == 'all' and 'all' or z.id)
                    return true
                end
            end
        end
        if not inside(zones.menu_box, mx, my) then menu_open = false end
        return true
    end
    if inside(zones.chapter, mx, my) then
        menu_open, menu_scroll = true, 0
        return true
    end
    if inside(zones.prev, mx, my) then return page(-1) end
    if inside(zones.next, mx, my) then return page(1) end
    if inside(zones.open, mx, my) then
        open_editor()
        return true
    end
    return false
end

function W.draw(cr, x, y, w, h)
    local pad, header_h, footer_h, title_h, line_h, body_lines, image_h = metrics(w, h)
    local iw_phys = math.max(1, math.floor((w - 2 * pad) * SCALE * DPI + 0.5))
    local ih_phys = math.max(1, math.floor(image_h * SCALE * DPI + 0.5))
    local resized = iw_phys ~= last_tw or ih_phys ~= last_th
    if resized then last_tw, last_th = iw_phys, ih_phys end

    if L.due('album_read', 1) or gen == nil then load_snapshot() end
    local size_now = trim(read_file(SIZEFILE))
    if gen == nil or size_now ~= (iw_phys .. ' ' .. ih_phys) then
        prepare(iw_phys, ih_phys, nil, nil, false)
    end
    if L.due('album_refresh', 1) then
        local f = io.open(REFRESH, 'r')
        if f then
            f:close()
            os.remove(REFRESH)
            prepare(iw_phys, ih_phys, nil, nil, true)
        end
        load_snapshot()
    end
    if AUTO > 0 and count > 1 and L.due('album_auto', AUTO) then page(1) end

    L.card(cr, x, y, w, h)
    local err = read_file(ERROR)
    if gen == nil then
        if err and trim(err) ~= '' then
            draw_error(cr, x, y, w, h, trim(err))
        else
            L.font(cr, F.regular, 10.5); L.set(cr, C.text3)
            L.text(cr, '正在加载笔记…', x + w / 2, y + h / 2, 'c')
        end
    elseif menu_open then
        draw_menu(cr, x, y, w, h, pad)
    else
        draw_content(cr, x, y, w, h)
    end
end

return W
