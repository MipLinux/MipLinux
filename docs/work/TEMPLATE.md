---
description: 工作 issue 的正文骨架：一条工作 = 一个 issue；复制骨架到 out/issue-drafts/ 填好，给人过目后再发布。
tags: [work, template, issue]
---

<!--
  用法：**只复制「正文骨架」那一节**（从 `### 目标` 到文件末尾），存成 `out/issue-drafts/<主题>.md`
  （`out/` 已 gitignore，草案不是仓库资产）。填好 → 给人过目 → 发布。
  `out/` 不可写时（如 `mipl.sh` 以 root 跑过后目录归 root，见 Issue #93）**不必用 root 写普通文本**：
  草案存进任何可写的目录，校验改用 `MIPL_WORK_DRAFTS=<目录> ./scripts/check-work-issue.sh`（整个目录）
  或 `./scripts/check-work-issue.sh <草案路径>`（只查一份）；发布时 `--body-file` 指向草案实际路径。

  别把本文件的 frontmatter 与这段注释抄进草案：issue 不是仓库文档，不接受 YAML frontmatter 与 HTML
  注释，`./scripts/check-work-issue.sh` 会把它们判成错。骨架里的 `### <字段>` 小节标题**不能改名** ——
  GitHub 表单 `.github/ISSUE_TEMPLATE/task.yml` 的 `label:` 与它们逐字相同，守卫会比对两边是否漂移。

  发布两条路（产出的正文同一份；**发布前先问维护者** —— 会以维护者账号公开）：
    1. 网页：New issue →「工作分配」表单，逐字段填（不依赖 gh，任何环境都能走）
    2. gh（本机已装并登录维护者账号）：gh issue create --title "[工作] <主题>" \
         --body-file out/issue-drafts/<主题>.md --label task

  字段为什么这么切、验收口径、角色到人的对应，见 docs/work/README.md 的「工作 issue 规范」——
  **本节不重述规范**，判据冲突时以规范为准。
-->

## 正文骨架（从下一行开始复制）

### 目标

<一句话：让什么从「不能」变成「能」，或从「错」变成「对」。不写做法。>

### 实现

<做什么、改哪些文件（逐个写路径）、明确**不**做什么。>

### 验收

<能在本机跑出来的判据：命令 + 期望结果。
没有实测证据不许写「已验证」，只能写 未实测 / 仅静态检查 / 仅 dry-run。>

### 回报

<交什么（命令输出 / 文件路径 / 截图）、给谁。>

### 依赖

<被哪个 issue / P 编号 / 里程碑卡住；没有就写「无」。>

---

**开工前请执行：**

```bash
git switch main && git pull origin main
git switch -c feat/<主题>   # 只改文档用 docs/<主题>
```

> 🤔 本 issue 由 AI 起草，不同发行版可能有差异，AI 可能出错；如有错误，请直接在本 issue 下回复。
> 分支不在 `main` 上、或拉取不是快进 → 停下来问维护者，**不要**自行 `merge` / `rebase` / `reset --hard`。
