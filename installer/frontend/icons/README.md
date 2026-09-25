# installer/frontend/icons · 图标

图标集是 **Lucide**（ISC；其中一批派生自 Feather，MIT）。许可原文在
`lucide/LICENSE` —— 两个许可都要求**随分发保留版权声明**，所以这份文件
不能删，也不能挪出这个目录。

## 只放用到的（2026-09-25 评审）

**仓库里只有界面真正引用到的那些 SVG。** 当前 20 个，合计 84 KB。

Lucide 全量是 **1854 个、7.3 MB**。全量入库的代价不是磁盘（那点体积无所谓），
而是三件事：

1. 把一整份图标主题背在发行版的源码里，**每次上游增删图标都跟我们无关**，
   却让我们多了一份要跟着走的东西；
2. 评审时「这个图标哪来的」变成一阵 `ls | grep`，而不是「谁在用」；
3. 图标主题本该由桌面环境提供（装后系统那半段是 M3 的事），安装器只需要
   自己用到的那几个。

## 怎么加一个图标

```bash
# 1. 从 https://lucide.dev/icons 找名字（例如 user-round）
# 2. 把那一个 .svg 放进来
curl -o installer/frontend/icons/lucide/user-round.svg \
  https://raw.githubusercontent.com/lucide-icons/lucide/main/icons/user-round.svg

# 3. QML 里直接用名字
#    Icon { name: "user-round"; size: 52; color: Tokens.accentDecor }
```

**少一个图标不会静默**：`bridge/icons.py` 在取不到源文件时会打
`[icons] 找不到图标：X（在 …）` 并画一张透明空图 —— 取图脚本一跑就能看见。

## 怎么核对「有没有多放」

在 `qml/` 与 `bridge/` 里出现的、且与文件名同名的字符串，就是被引用的图标：

```bash
cd installer/frontend
ls icons/lucide/*.svg | xargs -n1 basename | sed 's/\.svg$//' | sort > /tmp/iconfiles
grep -rhoE '"[^"]+"' qml bridge | tr -d '"' | sort -u > /tmp/strings
comm -12 /tmp/strings /tmp/iconfiles     # 交集＝在用（少数误报无害）
```

运行时是最终判据：把 `qml/pages/*.qml` 全取一遍图，输出里不该出现
`找不到图标`（`tools/shots.py` 会把 provider 的提示原样打出来）。

## 为什么图标不能直接 `Image { source: "…/lock.svg" }`

Lucide 的 SVG 全写 `stroke="currentColor"`，**Qt 的 SVG 渲染器不认这个关键字** ——
实测渲染出来是纯黑，`Image.color` 也染不了它。所以由 `bridge/icons.py` 在渲染前
把 `currentColor` 换成真实色值，顺带按 (图标, 颜色, 尺寸) 缓存。
