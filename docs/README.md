# docs · 文档入口

这里是 MipLinux 的全部文档。`docs/` 分四层，各有明确的读者与职责 —— 放错层比写错更麻烦，
因为下一个来找结论的人会翻到一份「说过但不算数」的东西。

| 层 | 是什么 | 从哪读起 |
|---|---|---|
| [knowledge/](knowledge/) | **当前状态的结论**：概念、环境、结构、决策、测试方法 | [01-概念模型.md](knowledge/01-概念模型.md) —— 给第一次接触这个项目的人 |
| [work/](work/) | 工作 issue 的规范与骨架、ROADMAP、可复现的实测步骤 | [work/README.md](work/README.md) |
| [archive/](archive/) | 已解决或已分流问题的记录：症状 / 证据 / 根因 / 修法 | [archive/README.md](archive/README.md) |
| [AGENTS.md](AGENTS.md) | 上面三层的**写法规矩**（给在仓库里干活的人与 AI） | 动手改文档前先读 |

## 想找什么，去哪看

| 想知道什么 | 去哪看 |
|---|---|
| 怎么构建出一个发行版（新手先读） | [01-概念模型](knowledge/01-概念模型.md) → [02-环境与工具链](knowledge/02-环境与工具链.md) → [03-项目结构](knowledge/03-项目结构.md) |
| 架构决策（D 编号） | [04-架构决策.md](knowledge/04-架构决策.md)：驱动与中文相关的那几条成篇展开 |
| 怎么验证 ISO 和装后系统 | [05-测试方法.md](knowledge/05-测试方法.md)：六个检查点 |
| 还没定的事、已否决的选项 | [06-待定事项.md](knowledge/06-待定事项.md)：P 表与排除表 |
| 安装器接下来做什么 | [installer-roadmap.md](work/installer-roadmap.md)：里程碑 M0–M5、验收标准、失败模式 |
| 正在做的工作（唯一来源） | [Issues](https://github.com/MipLinux/MipLinux/issues?q=label%3Atask)：一条工作 = 一个 issue |
| 一条工作要写成什么样 | [work/README.md](work/README.md) 的「工作 issue 规范」· [work/TEMPLATE.md](work/TEMPLATE.md) |
| 已经踩过的坑 | [archive/](archive/) |

## 仓库里的脚本

命令一律走脚本（手抄 `mkarchiso` / `pacstrap` / `qemu` 出过事故）。需要 root 的只有 `mipl.sh` 一族，
它自己不提权；非 root 运行只会打印该敲的命令。完整命令表见 [work/README.md](work/README.md)。

| 脚本 | 作用 |
|---|---|
| [mipl.sh](../scripts/mipl.sh) | 项目操作台：环境自检、构建、QEMU 测试、进出构建容器（需要 root） |
| [mipl.fish](../scripts/mipl.fish) | 同一操作台的 fish 入口，薄封装 |
| [mipl-lib.sh](../scripts/mipl-lib.sh) | `mipl.sh` 与 `baseline-build.sh` 共用的判断库（容器健康检查等「两个入口必须给出同一个答案」的东西） |
| [baseline-build.sh](../scripts/baseline-build.sh) | 构建本体，由 `mipl build` 调用；`--baseline` 改用原版 `releng` 做对照 |
| [check-identity.sh](../scripts/check-identity.sh) | 品牌一致性检查（**不需要 root**）；`--iso` 扫产物 |
| [check-readme-links.sh](../scripts/check-readme-links.sh) | README 可点性检查：仓库内死链、跨仓库死链、死锚点、进度表标记（**不需要 root**） |
| [check-doc-sync.sh](../scripts/check-doc-sync.sh) | 文档同步守卫：仓库 README 的进度口径与组织主页是否一致，并挡住已被推翻的旧口径（清单在 `check-doc-sync.facts`；**不需要 root、只读**） |
| [sync-profile-progress.sh](../scripts/sync-profile-progress.sh) | 把 README 的进度表同步进组织主页，写完自跑守卫，不通过就回滚 |
| [check-doc-sync.test.sh](../scripts/check-doc-sync.test.sh) | 上面两个脚本的回归测试：塞进各种漂移，验证抓得住也不误报 |
| [check-work-issue.sh](../scripts/check-work-issue.sh) | 工作 issue 草案守卫：草案是否符合[工作 issue 规范](work/README.md)（字段齐备、验收含命令与期望、≤60 行），并比对骨架与表单是否漂移（**不需要 root、只读**） |
| [check-work-issue.test.sh](../scripts/check-work-issue.test.sh) | 上面那个守卫的回归测试：九个用例塞进字段缺失 / 过时的受理人正文段 / 验收没命令 / 超行数 / 骨架或表单漂移，验证抓得住也不误报（**不需要 root**） |
| [ai-review-context.sh](../scripts/ai-review-context.sh) | issue 受理前质检的上下文生成器（脚本只算集合，语义判给模型，判据见 [ai-review-rubric](work/ai-review-rubric.md)）；由 [ai-summary.yml](../.github/workflows/ai-summary.yml) 调用 |
| [pr-acceptance-context.sh](../scripts/pr-acceptance-context.sh) | PR 验收对账的上下文生成器：把 PR 声称与 issue 验收摊平成一张表，不判定真伪；由 [pr-acceptance.yml](../.github/workflows/pr-acceptance.yml) 调用 |
| [mipl-out-ownership.test.sh](../scripts/mipl-out-ownership.test.sh) | `out/` 属主归还逻辑的回归测试（Issue #93）：身份解析、归还、不递归、身份缺失不猜属主 |

## 在仓库里干活

- **行为契约**：根 [AGENTS.md](../AGENTS.md)；`profile/`、`installer/`、`scripts/`、`docs/` 各有自己的 `AGENTS.md`，进目录先读它。
- **工作怎么布置**：一条工作 = 一个 issue（label `task`），assignee 就是受理人；规范见 [work/README.md](work/README.md)，当前在做的工作看 [Issues](https://github.com/MipLinux/MipLinux/issues?q=label%3Atask)。
- **改动怎么进**：`main` 受保护，PR 必须含 code owner 的审核；一个 PR 只做一件事，出界的改动先提 issue，不夹带。