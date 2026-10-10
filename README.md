<div align="center">

**MipLinux**

基于 Arch Linux 的滚动发行版 · 中文开箱即用 · NVIDIA 驱动预装

[![平台](https://img.shields.io/badge/平台-x86__64-4a5568?style=flat-square)](https://github.com/MipLinux/MipLinux)

</div>

MipLinux 解决两个 Arch 系发行版的常见麻烦：

- **NVIDIA 驱动开箱可用** —— 多数 Arch 系发行版不预装 N 卡驱动，装完还得自己折腾。
- **对中文用户友好** —— 目标是国内镜像源、`zh_CN.UTF-8`、CJK 字体、`fcitx5` 输入法全部默认配好，装完不用手动折腾（做到哪一步见下面的进度表）。

交付形态是装到硬盘的滚动发行版（D7）。ISO 采用**在线安装**：Live 环境极简、开机直进安装器，包在安装时从国内源拉取（D11 / D12）。

---

## 当前进度

> 截至 **2026-10-10**。
> 
> 正在做的工作在 [Issues](https://github.com/MipLinux/MipLinux/issues?q=label%3Atask)

<!-- BEGIN:progress-table -->
| 阶段         | 状态          |
|------------|-------------|
| 构建环境与基线    | Bingo       |
| 自有 profile | Bingo       |
| 装系统链路      | Bingo       |
| 国内源与中文本地化  | Testing     |
| NVIDIA 驱动  | Testing     |
| 安装程序       | Testing     |
| 桌面环境 / 品牌化 | Coming Soon |
<!-- END:progress-table -->

---

## 上手

命令一律需要 root；`mipl.sh` 不自己提权，非 root 时只打印该敲的命令然后退出。

```bash
# 环境自检
sudo ./scripts/mipl.sh doctor 

# 用仓库里的 profile/ 构建 ISO
sudo ./scripts/mipl.sh build 

# 创建虚拟磁盘
sudo ./scripts/mipl.sh target --force

# 启动 QEMU
sudo ./scripts/mipl.sh qemu 
# 如果 QEMU 提示被占用
sudo ./scripts/mipl.sh stop 

# 开启串口
sudo ./scripts/mipl.sh qemu --serial console 
```

完整使用方式见 `sudo ./scripts/mipl.sh --help`；命令表、脚本清单与文档入口见 [docs/README.md](docs/README.md)。

### 构建与测试环境

| 环节 | 是什么 | 为什么是它 |
|---|---|---|
| 源码 | `profile/` —— 发行版的「源代码」就是配置文件 | 构建是**装配**不是编译，改配置即改行为 |
| 构建 | `systemd-nspawn` 容器里的纯 Arch，跑 `mkarchiso` | 需要 `pacman` / `pacstrap` / `mkinitcpio` |
| 测试 | 宿主机的 QEMU（KVM），终验真机 | nspawn 不能引导；NVIDIA 驱动与分区行为只能在真机终验 |

宿主发行版与项目无关（维护者用的宿主发行版各不相同），容器只读挂载仓库里的 `profile/`，唯一必须保持一致的接口是包清单 [`profile/packages.x86_64`](profile/packages.x86_64)。

## 四条贯穿原则

- **构建是装配不是编译**：`mkarchiso` 先装出一个完整的 Arch 系统，再把系统压扁成只读镜像。
- **逻辑先于外壳**：安装链先在无界面状态下跑通，界面只是它的第二个调用者。
- **不做无损 resize**：分区只在虚拟盘 `out/target.qcow2` 上测，真机用独立硬盘。
- **命令一律走脚本**，不手抄 `mkarchiso` / `pacstrap` / `qemu`；**安装器直到它装出来的系统能启动，才算被测过**。

---

## 怎么参与

- **分工在 [Issues](https://github.com/MipLinux/MipLinux/issues?q=label%3Atask) 里**，怎么写见[工作 issue 规范](docs/work/README.md)。
- `main` 受保护，PR 必须含 code owner（[@LaT-SKY](https://github.com/LaT-SKY)）的审核，见 [CODEOWNERS](.github/CODEOWNERS)。
- 一个 PR 只做一件事；出界的改动先按 [Issue 模板](.github/ISSUE_TEMPLATE/) 提 issue，不夹带进 PR。