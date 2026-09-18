<!--
main 受保护：PR 需要至少 1 个 approving review，且必须包含 code owner（@LaT-SKY）的审核。
本文件里的 HTML 注释不会显示在渲染后的正文中，但下面的标题请保留。
填不出来的项请写「未验证」或「N/A」，不要留空。
-->

## 改了什么

<!-- 一两句话。若对应当日任务，请写明是哪条线，例如：9.19 线C。 -->

## 为什么

<!-- 解决什么问题、依据哪条已有结论。已写进 docs/knowledge/ 的结论请直接引用，不要重述。 -->

## 验证方式

<!-- 只写真实跑过的命令与结果。纯文档改动可整段写 N/A。 -->

| 项 | 结果 |
|---|---|
| 构建 `sudo ./scripts/mipl.sh build` | 产物与大小：`out/…` |
| QEMU `sudo ./scripts/mipl.sh qemu` | 验到检查点 __ / 6（见 `docs/knowledge/05-测试方法.md` §5） |
| 静态检查 | 如 `isoinfo`、挂载目标盘（§6）： |

## 检查项

- [ ] 本次 PR 只做一件事（例如没有把「搬 profile」和「改 profile」混在一起）
- [ ] 命令都走 `scripts/mipl.sh`，没有手抄长命令（Issue #7、#8 的教训）
- [ ] 没有提交 `out/` 产物、`*.iso`、`OVMF_VARS*.fd` 或任何密钥
- [ ] 改了行为或结论时，相关文档已同步（`docs/knowledge/` 或 `docs/work/`）

<!-- 关联 Issue 写 Closes #编号，合并后会自动关闭。 -->
