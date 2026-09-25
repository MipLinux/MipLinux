# installer/frontend/assets · LOGO 资产

这里的 `*.png` 是**生成物，但进仓库**。这条与 `out/`、`*.iso` 的纪律不同，
是刻意区分的，理由写清楚，免得后来的人以为是漏了 gitignore。

## 为什么进仓库

| | `out/`、`*.iso` | 这两个 PNG |
|---|---|---|
| 大小 | GiB 级 | 220 KB |
| 改动频率 | 每次构建都变 | 换 LOGO 才变 |
| 提交的代价 | 仓库爆炸 | 无感 |
| **不提交的代价** | 无 —— 随时能重建 | **ISO 构建会缺文件**：构建脚本以 root 跑、只读挂载 `profile/`，仓库由普通用户持有，所以构建期**不能**替人往仓库里写图 |

最后一行是决定性的：既然构建期生成不了，就必须有一份已生成的在仓库里，
否则「谁 clone 谁构建失败」。`tools/build-assets.sh` 保留，用于**换 LOGO**，
不是用于构建期兜底。

> **branding 资产的归属：** 这是品牌化资产第一次进仓库。
> [06 §五](../../../docs/knowledge/06-待定事项.md) 把品牌化（logo / 壁纸 / 主题）
> 排在功能之后且受 P5 阻塞 —— 安装器首屏没有 LOGO 说不过去，所以这两个文件
> 随 G3 进来；**再往仓库里加别的品牌资产（壁纸、图标、字体）要先问维护者。**

## 怎么重新生成

```bash
bash installer/frontend/tools/build-assets.sh --force
```

换一台机器、换一份 clone 时不需要跑 —— 图已经在仓库里了。
源图不在原位时脚本会明确报出该放哪，也可以用环境变量指过去：

```bash
MIPL_LOGO_SRC=/path/to/MipLinuxLogo.png \
  bash installer/frontend/tools/build-assets.sh --force
```

## 产出

| 文件 | 尺寸 | 大小 | 用在哪 |
|---|---|---|---|
| `mipl-logo-hero.png` | 512×508 | 约 200 KB | 欢迎页主视觉（显示 180 / 128 px，留 HiDPI 余量） |
| `mipl-logo-mark.png` | 96×95 | 约 13 KB | 欢迎页页头小标（显示 26 px） |

生成时做两件事：**裁掉透明边**（源图内容只占 1112×973，画布是 1254×1254，
不裁会在界面里小一大圈）、**只在更大时缩小**（`512x512>`，放大只会糊）。

## 界面里怎么用

`qml/pages/WelcomePage.qml` 里用 `Qt.resolvedUrl("../../assets/…")` 引用；
`HeroMark.qml` 是显示 LOGO 的组件。

**LOGO 不做装饰**（2026-09-25 定）：外面不套环、不加星光、不做描线动画。
它自己已经是一枚完整的图形（蓝色渐变圆 + 海豹 + 山形 M + 星光），
再叠一层是替它说话。这里只保留一次很短的淡入。

