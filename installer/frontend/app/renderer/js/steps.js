/**
 * steps.js —— 两套流程的步骤表
 *
 * 普通 8 步 / 高级 12 步（docs/work/tech/09 §二 · 流程）；`setup.advanced` 决定用哪张表，
 * 欢迎页那个开关一拨即时生效。页面模块与步骤 id 一一对应（`pages/<id>.js`）。
 */

export const FLOWS = {
  normal: ['welcome', 'network', 'disk', 'account', 'summary', 'confirm', 'progress', 'finish'],
  advanced: [
    'welcome',
    'locale',
    'keymap',
    'timezone',
    'network',
    'disk',
    'account',
    'hostname',
    'summary',
    'confirm',
    'progress',
    'finish',
  ],
};

/** 步骤的标题键（左侧轨道与窄屏步骤条用；页面标题另有自己的 title）。 */
export const STEP_TITLE_KEY = {
  welcome: 'welcome.title',
  locale: 'locale.title',
  keymap: 'keymap.title',
  timezone: 'timezone.title',
  network: 'network.title',
  disk: 'disk.title',
  account: 'account.title',
  hostname: 'hostname.title',
  summary: 'summary.title',
  confirm: 'confirm.title',
  progress: 'progress.title',
  finish: 'finish.title',
};

export function flowFor(advanced) {
  return advanced ? FLOWS.advanced : FLOWS.normal;
}

/** 走完之后不该再退回去的页面（进度与完成）。 */
export const NO_BACK = new Set(['progress', 'finish']);

/**
 * 进进度页时要不要把上一轮的终态清掉（= 重跑一轮安装）。
 *
 * **`cameFromProgress` 是这条判据的全部要点。** 进度页自己也会 `ctx.rerender()`
 * ——装失败时要把后端那句话摆出来就得重画。把那种重画也当成「重新进入」的话：
 *
 *     失败 → 重画 → 状态被清空（`startedAt` 没了）→ 进度页又 `startRun()`
 *          → 又失败 → …… 无限循环
 *
 * 而那正是这个项目明令禁止的事：**不许在残骸上接着装**（`pipeline.run` 的失败收尾
 * 把目标卸干净，就是不想让「再试一次」变成「接着装」）。所以只有**从别的页走过来**
 * 才算重跑；页面自己的重画一律不动状态。
 *
 * 抽成纯函数是为了能钉住它：`app.js` 在 Node 里 import 不了（模块顶层就读 `window`），
 * 而这条判据是「一个手滑就变成死循环」的那种。
 */
export function shouldRestartRun(progress, { cameFromProgress = false } = {}) {
  if (cameFromProgress) return false;
  return Boolean(progress && (progress.done || progress.cancelled || progress.failed));
}
