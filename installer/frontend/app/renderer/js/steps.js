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
