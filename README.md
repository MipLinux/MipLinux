<div align="center">

<img src="assets/mipl-logo.png" width="128" alt="MipLinux">

**MipLinux**

基于 Arch Linux 的滚动发行版 · 中文开箱即用 · NVIDIA 驱动预装

[![平台](https://img.shields.io/badge/平台-x86__64-4a5568?style=flat-square)](https://github.com/MipLinux/MipLinux)

</div>

MipLinux 解决两个 Arch 系发行版的常见麻烦：

- **NVIDIA 驱动开箱可用** —— 多数 Arch 系发行版不预装 N 卡驱动，装完还得自己折腾。
- **对中文用户友好** —— 国内镜像源、`zh_CN.UTF-8`、CJK 字体、`fcitx5` 输入法默认配好，装完不用手动折腾。

交付形态是装到硬盘的滚动发行版。ISO 采用**在线安装**：Live 环境极简、开机直进安装器，系统包在安装时从国内源拉取。

---

## 当前进度

> 截至 **2026-10-17**。正在做的工作在 [Issues](https://github.com/MipLinux/MipLinux/issues?q=label%3Atask)。

<!-- BEGIN:progress-table -->
| 阶段         | 状态          |
|------------|-------------|
| 构建环境与基线    | Bingo       |
| 自有 profile | Bingo       |
| 装系统链路      | Bingo       |
| 国内源与中文本地化  | Testing     |
| NVIDIA 驱动  | Testing     |
| 安装程序       | Testing     |
| 桌面环境 / 品牌化 | Making      |
<!-- END:progress-table -->

**Bingo** = 本机实测可用；**Testing** = 已有实现、还在验证；**Making** = 正在做；**Coming Soon** = 尚未开始。

---

## 上手

`mipl.sh` 需要 root，且不自己提权：非 root 运行时只打印该敲的命令，然后退出。

```bash
# 环境自检（换机器第一件事）
sudo ./scripts/mipl.sh doctor

# 用仓库里的 profile/ 构建 ISO
sudo ./scripts/mipl.sh build

# 建一块虚拟盘，再从 ISO 装到这块盘
sudo ./scripts/mipl.sh target
sudo ./scripts/mipl.sh qemu --disk target.qcow2

# 装完从盘启动
sudo ./scripts/mipl.sh qemu --disk target.qcow2 --boot c
```

`target` 遇到已存在的虚拟盘会拒绝覆盖；确实要重建时加 `--force`。构建容器用完用 `sudo ./scripts/mipl.sh stop` 关闭。完整用法见 `sudo ./scripts/mipl.sh --help`。

构建在纯净 Arch 容器里进行，测试在 QEMU 里做；NVIDIA 驱动与分区行为在真机上终验。

---

## 四条贯穿原则

- **构建是装配不是编译**：先把一个完整的 Arch 系统装出来，再把它压成只读镜像。
- **逻辑先于外壳**：装系统这条链先在无界面状态下跑通，界面只是它的第二个调用者。
- **不做无损 resize**：分区只在虚拟盘上测，真机用独立硬盘。
- **命令一律走脚本**：不手抄构建、装包与 QEMU 命令；安装器直到它装出来的系统能启动，才算被测过。

---

## 怎么参与

- **工作按 issue 布置**：一条工作 = 一个 issue。
- **改动怎么进**：`main` 受保护，PR 必须含 code owner 的审核，见 [CODEOWNERS](.github/CODEOWNERS)。
- **出界的改动先提 issue**：按 [Issue 模板](.github/ISSUE_TEMPLATE/) 写，不夹带进 PR。

---

## 许可

- **代码与配置**：**GPL-3.0-or-later**，全文见 [LICENSE](LICENSE)。
- **品牌素材**（logo 及派生尺寸）：单独按 **CC BY-SA 4.0** 授权；名称与商标不随素材授权，见 [assets/README.md](assets/README.md)。
- **Caelestia 桌面配置**：来自 MipLinux 维护的 [Caelestia-dotfiles](https://github.com/MipLinux/Caelestia-dotfiles)、[Caelestia-shell](https://github.com/MipLinux/Caelestia-shell)、[Caelestia-cli](https://github.com/MipLinux/Caelestia-cli) 三个 fork，以 **GPL-3.0-only** 分发（上游 Caelestia 的 LICENSE 为 GPLv3）；版权与修改声明见各仓库的 `NOTICE.md`。
- **第三方组件**：随仓库或随产物分发的第三方东西，各自保留原许可；许可分层、NVIDIA 专有组件与源码提供方式见 [THIRD-PARTY.md](THIRD-PARTY.md)。
- **专有组件**：发行版预装 NVIDIA 用户态驱动（`nvidia-utils`，NVIDIA Driver License Agreement）。它是独立专有组件，按聚合方式分发，再分发依据 EULA 1.1(d)：二进制不修改、EULA 随附；详见 [THIRD-PARTY.md](THIRD-PARTY.md)。它不是 GPL 代码，MipLinux 因此是“开源核心 + 专有驱动”，不是 100% 自由软件发行版。需要完全自由软件的用户不要安装 NVIDIA 组件。
