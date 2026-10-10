# 品牌资产 · logo

**这是安装器界面里唯一允许出现的图形标志。** 界面上的品牌位、欢迎页、完成页都用它；
不要另造近似图形，也不要用几何色块凑一个「mark」。

| 文件 | 用途 |
|---|---|
| `logo-512.png` | 欢迎页主视觉、对话框/完成页的大图（512²，透明底） |
| `logo-128.png` | 顶栏品牌位（显示 ~36px，2x / 3x 屏够用） |
| `logo-64.png` | 小尺寸（步骤条、列表头、favicon 级） |

## 来源与再生成

原始文件：`MipLinuxLogo.png`（维护者本机，1254×1254 RGBA，725 207 B，
sha256 `263a2cb1cf6061a309e5dc0c53872a6efc1748edb4ee425d625f67846fa419a2`）。
品牌色板（种子色 `#2576E9`）见 [tech/08 附录 A](../../../../../docs/work/tech/08-界面设计方向.md)。

再生成（需要 ImageMagick；原图不进仓库，避免 700 KB 级位图躺在 git 里）：

```bash
magick MipLinuxLogo.png -resize 512x512 -strip -define png:compression-level=9 -define png:compression-filter=5 logo-512.png
magick MipLinuxLogo.png -resize 128x128 -strip -define png:compression-level=9 -define png:compression-filter=5 logo-128.png
magick MipLinuxLogo.png -resize  64x64  -strip -define png:compression-level=9 -define png:compression-filter=5 logo-64.png
```

**口径：** 三份都是同一张位图的**整幅等比**降采样 —— 不裁掉原图四周的透明边距，颜色与形状不做任何二次创作；
换 logo = 换原图 + 重跑上面三行，**不要**直接手改这些 PNG。
