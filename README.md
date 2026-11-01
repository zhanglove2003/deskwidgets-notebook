# deskwidgets-notebook

DeskWidgets（conky）桌面组件的自定义版本，重点是把原来的「相册」升级成 **图文笔记**：

- 章节 + 封面 + 正文自由图文混排（图片插在光标处，可粘贴截图、拖拽文件）
- 卡片显示封面 + 标题 + 第一段摘录；未设置封面时自动使用正文第一张图
- 滚轮翻页、章节菜单、条目跨章节移动
- 双击正文图片或封面打开应用内大图窗（滚轮缩放、拖动平移）

同时包含此前对 DeskWidgets 的汉化、HiDPI（200% 缩放）和鼠标/滚轮事件的补丁。

## 仓库结构

```
docs/            交接文档、实施计划、图文笔记 v2 设计
patches/         汉化（zh_patch*）与 DPI/滚轮/鼠标补丁（fix_*）
widgets/album/   图文笔记组件：widget.json / widget.lua / notebook.py / editor.py / topng.py
```

## 组件文件

| 文件 | 作用 |
|---|---|
| `widgets/album/widget.json` | 组件元数据与选项（首次导入目录、封面填充方式、自动轮播） |
| `widgets/album/widget.lua` | 卡片绘制与交互（翻页、章节菜单、尺寸手柄） |
| `widgets/album/notebook.py` | 笔记数据、v1→v2 迁移、快照生成（封面/摘录） |
| `widgets/album/editor.py` | GTK4 编辑器：图文混排、封面、章节移动、大图窗 |
| `widgets/album/topng.py` | 图片转 PNG 缓存（Pillow） |

## 环境

- Ubuntu 24.04 / GNOME / X11，2560×1440 @200%（Xft.dpi=192）
- DeskWidgets 2.0.0（conky 1.19 + Lua 5.3 + cairo）
- Python 3 + PyGObject 4.14（GTK4）+ Pillow

## 安装思路

1. 安装 DeskWidgets 2.0.0 及其依赖。
2. 把 `widgets/album/` 放到 `~/.config/deskwidgets/widgets/album/`。
3. 按需运行 `patches/` 下的补丁脚本（脚本内为幂等打补丁逻辑，执行前请先读一遍）。
4. `deskwidgets reload` 重载组件；首次打开笔记库时可用组件选项「首次导入目录」导入旧相册图片。

数据位置：

- 笔记库：`~/.local/share/deskwidgets/notebooks/<实例hex>/notebook.json` + `images/` + `view.json`
- 运行快照：`$XDG_RUNTIME_DIR/deskwidgets/album-<实例hex>/snapshot/`

## 文档

- [交接文档](docs/HANDOVER.md)：文件地图、数据格式、踩坑与回滚
- [图文笔记 v2 设计](docs/RICH_NOTES_DESIGN.md)
- [图文笔记 v2 实施计划](docs/RICH_NOTES_PLAN.md)
- [早期实施计划](docs/IMPLEMENTATION_PLAN.md)

## 说明

本仓库为个人桌面定制项目，代码按现状提供，未附带许可证文件；如需复用请先联系仓库所有者。
