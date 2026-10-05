# vendor/ —— 随仓库走的第三方前端资源（vendored）

为什么要 vendored，而不是包管理器
----------------------------------
Live 与构建容器里**没有 npm**，也不该为了装界面去拉 `node_modules` ——
安装器只需要两个单文件资源，把它们钉死版本、随源码进仓库，构建就永远可复现，
ISO 也不必付第二份运行时的体积。

**纪律：**
- 新增任何 vendored 文件 → 本文件加一条（版本 / 来源 URL / sha256 / 许可），并把 LICENSE 原件一起放进来。
- **不提交** `node_modules/`、不打 bundle、不在构建里跑 `npm install`。
- 升级 = 换文件 + 换版本号 + 换 sha256 + 把 LICENSE 一起换，四件事同一笔提交。

## 清单

| 文件 | 版本 | 许可 | 来源 |
|---|---|---|---|
| `anime.esm.min.js` | anime.js **v4.5.0** | MIT（`LICENSE.anime.js.md`） | `https://cdn.jsdelivr.net/npm/animejs@4.5.0/dist/bundles/anime.esm.min.js` |
| `fonts/geist-latin-wght-normal.woff2` | Geist Variable（`@fontsource-variable/geist@5.3.0` 打包） | SIL OFL 1.1（`fonts/LICENSE.geist.txt`） | `https://cdn.jsdelivr.net/npm/@fontsource-variable/geist@5.3.0/files/geist-latin-wght-normal.woff2` |
| `fonts/geist-latin-wght-italic.woff2` | 同上（斜体） | 同上 | `…/files/geist-latin-wght-italic.woff2` |
| `icons/*.svg` | Phosphor Icons **v2.1.1**（regular，17 个） | MIT（`icons/LICENSE.txt`） | `https://cdn.jsdelivr.net/npm/@phosphor-icons/core@2.1.1/assets/regular/<name>.svg` |

sha256（2026-10-04 记录）：

```
a19015a1a92d52025a2fb6703b6d67eadd1cc2aeaf880770e96e04cf6aa07be1  anime.esm.min.js
19f9c92546aa300c312235e3125af1b81394d8db9a4bc4a425cd5b641d2d54e1  fonts/geist-latin-wght-normal.woff2
9b10496762af92659f3b05d2b084b0c8f962c3ecdf637aa764e3b7fd17f5acaf  fonts/geist-latin-wght-italic.woff2
```

## 为什么是这两个

- **anime.js**：动效编排（页面切换、步骤条、微交互）。纯 DOM/CSS 变换与不透明度，
  在 QEMU 的 SwiftShader 软渲染下也不会像 WebGL 那样拖垮首帧；MIT，单文件 116 KiB。
- **Geist（仅拉丁子集）**：界面里中文由 Live 自带的 `noto-fonts-cjk` 渲染，拉丁/数字需要一个
  更有性格的字面 —— Geist 是 OFL，两个 woff2 加起来只有 60 KiB，且带可变字重。
- **Phosphor 图标**：只用 `regular` 一档（统一线宽、同一 256 网格）。**不混家族、不手画路径**；
  增删图标 = 往 `vendor/icons/` 放/删 SVG → `python3 tools/gen-icons.py --write`（`renderer/js/icons.js` 是生成物）。
- **没有引入 three.js**：Live 在 QEMU 里无 GPU、Chromium 走软件渲染，WebGL 场景会吃掉首帧预算；
  氛围感改用 CSS 分层渐变 + 噪声 + canvas 2D 轻粒子，代价近乎为零。**结论记录在此，避免以后重复讨论。**
