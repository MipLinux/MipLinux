/**
 * 进度页（7）—— 阶段、百分比、日志、耗时
 *
 * **进度不再由界面编。** 这一页只做两件事：把 `backend.onInstallEvent()` 推来的
 * 记录翻成画面，和把用户的取消请求送到 `backend.cancelInstall()`。
 * 「装到哪一步了」的答案在 `events.JsonReporter` 的事件流里，
 * 界面自己跑一个定时器往前拱百分比，是界面在描述它没做的事（M1 的纪律）。
 *
 * ## 三条口径
 *
 * 1. **百分比按阶段落格**：后端只在 `done` 那一条给 100，其余阶段不带百分比
 *    （它也不知道 `pacstrap` 装了百分之几）。所以进度条的推进单位是**阶段**：
 *    `start → 8% → disk → 18% → packages → 70% → configure → 88% → boot → 96%`。
 *    这是「到哪一步了」的诚实画法，比一个匀速爬动的假进度条更敢让人看。
 *    **100% 只留给 `done`**：boot 那一格里还有「装引导 + 校验 + 卸载目标落盘」，
 *    实机上卸载那一步等写缓存落盘能以分钟计 —— boot 落 100% 会让圆环在机器
 *    还在写盘时就报「装完了」（Issue #97 实机教训：「到 100% 后还卡很久」）。
 * 2. **日志里的话是后端说的**：阶段那几行走翻译键（`progress.phase.*`，中英都有）；
 *    `note` 是后端的旁白（目标盘、dry-run 之类），**原样显示不翻译** ——
 *    它是诊断信息，和 `journalctl` 里那行是同一句话，翻译它反而对不上。
 * 3. **取消只发生在阶段之间**：按下的那一刻只是「举手」（`SIGUSR1`），
 *    页面上那句提示就是这么写的（`progress.cancelHint`）。真的停下来之后
 *    后端给一条退出码 130，那时才回摘要页 —— 提前跳走会让人以为已经停了。
 */

import { h } from '../dom.js';
import { pageHead, panel, rings, meter, phaseList, callout } from '../components.js';
import { ring, fill } from '../motion.js';
import { buildPlan, buildSecrets } from '../backend.js';

/**
 * 阶段边界 —— 与 `mipl_installer/events.py` 的 `PHASES` 一一对应。
 *
 * 抄一份在这里是**有意的**：界面要知道「这个阶段在第几格」，就得有边界值，
 * 而边界值是产品决定（跑完 8% 算进了第一步），不是后端事实。
 * 名字对不上的话，下面 `phaseIndex()` 找不到就退回「不动」——不会画错，
 * 只会慢一格，那比一个错位的进度条好查。
 */
const PHASES = [
  { phase: 'start', key: 'progress.phase.start', until: 8 },
  { phase: 'disk', key: 'progress.phase.disk', until: 18 },
  { phase: 'packages', key: 'progress.phase.packages', until: 70 },
  { phase: 'configure', key: 'progress.phase.configure', until: 88 },
  { phase: 'boot', key: 'progress.phase.boot', until: 96 },
];

/** 界面侧的一次订阅与一个时钟。装完/离开时都要收掉，否则会「遥控」别的页面。 */
let subscription = null;
let clock = null;
let advanceTimer = null;
let startedAt = 0;

function stop() {
  if (subscription) subscription();
  subscription = null;
  if (clock) clearInterval(clock);
  clock = null;
  if (advanceTimer) clearTimeout(advanceTimer);
  advanceTimer = null;
}

function stamp() {
  const elapsed = Math.max(0, Math.floor((Date.now() - startedAt) / 1000));
  const mm = String(Math.floor(elapsed / 60)).padStart(2, '0');
  const ss = String(elapsed % 60).padStart(2, '0');
  return { clock: `${mm}:${ss}`, elapsed };
}

function phaseIndex(phase) {
  const index = PHASES.findIndex((item) => item.phase === phase);
  return index < 0 ? null : index;
}

/** 进度写进 `setup.data`（探针与重进页面都读它）。 */
function patch(ctx, changes) {
  ctx.setup.data.progress = { ...ctx.setup.data.progress, ...changes };
}

function appendLog(ctx, text, tone = 'info') {
  const current = ctx.setup.data.progress;
  const line = { text: `${stamp().clock}  ${text}`, tone };
  patch(ctx, { lines: [...(current.lines || []), line].slice(-40) });
  const logEl = document.getElementById('progress-log');
  if (logEl) {
    logEl.append(h('div', { class: `log__line--${tone}`, text: line.text }));
    logEl.scrollTop = logEl.scrollHeight;
  }
}

/** 只改元素属性，不重画整页 —— 事件流每来一条就重画一次，页面会闪。 */
function paint(ctx, percent, index) {
  const ringsEl = document.getElementById('progress-rings');
  if (ringsEl) ring(ringsEl, percent);
  const valueEl = ringsEl && ringsEl.querySelector('.rings__value');
  if (valueEl) valueEl.textContent = `${Math.round(percent)}%`;
  fill(document.querySelector('#progress-meter .meter__fill'), percent);
  for (const row of document.querySelectorAll('.phase')) row.dataset.state = 'todo';
  for (let i = 0; i < index; i += 1) {
    const done = document.getElementById(`phase-${i}`);
    if (done) done.dataset.state = 'done';
  }
  const active = document.getElementById(`phase-${index}`);
  if (active) active.dataset.state = 'active';
  const elapsedEl = document.getElementById('progress-elapsed');
  if (elapsedEl) {
    elapsedEl.textContent = ctx.t('progress.elapsed', `${Math.floor(stamp().elapsed / 60)}:${stamp().elapsed % 60}`);
  }
}

function finish(ctx, { failed, message }) {
  stop();
  patch(ctx, { done: !failed, failed: Boolean(failed), failure: message || '' });
  if (failed) {
    // 失败就停在原地，把后端那句话摆出来。**不自动跳走** ——
    // 装到一半的现场是个需要人做决定的状态，替人翻页等于替他决定。
    ctx.rerender();
    return;
  }
  advanceTimer = setTimeout(() => {
    // 期间可能已经被别的原因带走了（比如用户点了取消）：不在这一页就别推
    if (ctx.setup.stepId === 'progress') ctx.goNext();
  }, 900);
}

function onRecord(ctx, record) {
  if (!record || typeof record !== 'object') return;
  const current = ctx.setup.data.progress;

  switch (record.kind) {
    case 'event': {
      if (record.phase === 'done') {
        appendLog(ctx, ctx.t('progress.done'), 'ok');
        // phase 推过最后一格：五格全亮「完成」，也不留一格「进行中」在跳完成页
        // 前的那九百毫秒里骗人
        paint(ctx, 100, PHASES.length);
        patch(ctx, { percent: 100, phase: PHASES.length });
        break;
      }
      const index = phaseIndex(record.phase);
      if (index === null) break;
      if (index !== current.phase) appendLog(ctx, ctx.t(PHASES[index].key));
      const percent = record.percent === null || record.percent === undefined
        ? PHASES[index].until
        : record.percent;
      patch(ctx, { percent, phase: index });
      paint(ctx, percent, index);
      break;
    }
    case 'note':
      // 后端的旁白：原样显示（见文件头第 2 条）
      if (record.message) appendLog(ctx, String(record.message));
      break;
    case 'command':
      // 命令行不进日志：`pacstrap` 一次会刷出几十条，把有用的那几行冲走。
      // 要看它们有 journalctl（子进程的 stderr 也在那儿）。
      break;
    case 'error':
      patch(ctx, { failed: true, failure: [record.message, record.hint].filter(Boolean).join('\n') });
      break;
    case 'end':
      patch(ctx, { exitCode: record.code });
      break;
    case 'exit': {
      const cancelled = Boolean(record.cancelled) || record.code === 130;
      if (cancelled) {
        patch(ctx, { cancelled: true, cancelRequested: false });
        stop();
        ctx.goTo('summary');
        return;
      }
      if (record.code === 0) {
        finish(ctx, { failed: false });
        return;
      }
      // stderr 尾巴里可能带着子进程的控制字符（\b / \r）：摆进 <pre> 之前洗掉，
      // 否则失败现场又是一屏豆腐块
      const why = current.failure
        || (record.stderr || '').replace(/[\x00-\x08\x0b-\x1f\x7f]/g, ' ').trim().split('\n').slice(-3).join('\n')
        || ctx.t('common.error');
      finish(ctx, { failed: true, message: why });
      break;
    }
    default:
      break;
  }
}

function startRun(ctx) {
  stop();
  startedAt = Date.now();
  ctx.setup.data.progress = {
    percent: 0,
    phase: 0,
    lines: [],
    startedAt,
    done: false,
    cancelled: false,
    cancelRequested: false,
    failed: false,
    failure: '',
  };
  appendLog(ctx, ctx.t(PHASES[0].key));
  subscription = ctx.backend.onInstallEvent((record) => onRecord(ctx, record));
  clock = setInterval(() => {
    const elapsedEl = document.getElementById('progress-elapsed');
    if (elapsedEl) {
      elapsedEl.textContent = ctx.t('progress.elapsed', `${Math.floor(stamp().elapsed / 60)}:${stamp().elapsed % 60}`);
    }
  }, 1000);

  ctx.backend.startInstall(buildPlan(ctx.setup), buildSecrets(ctx.setup)).then((result) => {
    if (result && result.ok === false) {
      finish(ctx, { failed: true, message: result.error || ctx.t('common.error') });
    }
  });
}

export default {
  id: 'progress',

  render(ctx) {
    const t = ctx.t;
    const setup = ctx.setup;
    const progress = setup.data.progress || {};

    if (progress.cancelled) {
      stop();
      queueMicrotask(() => ctx.goTo('summary'));
      return h('div', { class: 'stack' }, [pageHead({ title: t('progress.title') })]);
    }

    // 进入这一页 = 开一轮安装。重进（重画）时若已经跑过，就不重开一次。
    if (!progress.startedAt) {
      startRun(ctx);
    } else {
      startedAt = progress.startedAt;
    }

    // 用户在对话框里按了「取消安装」：这里才把请求送出去（见文件头第 3 条）
    if (progress.cancelRequested && !progress.cancelSent) {
      patch(ctx, { cancelSent: true });
      ctx.backend.cancelInstall();
      appendLog(ctx, t('progress.cancelHint'), 'warn');
    }

    const current = setup.data.progress;
    const phases = PHASES.map((phase, index) => ({
      id: `phase-${index}`,
      label: t(phase.key),
        // 「进行中」优先于「百分比到格」：否则阶段刚点亮（百分比落到本格上限）
        // 就会被画成「已完成」，而它其实还在跑
        state: index === current.phase ? 'active' : current.percent >= phase.until ? 'done' : 'todo',
    }));
    const { elapsed } = stamp();

    const logEl = h('div', { class: 'log', id: 'progress-log' }, []);
    for (const line of current.lines || []) {
      logEl.append(h('div', { class: `log__line--${line.tone || 'info'}`, text: line.text }));
    }

    return h('div', { class: 'stack' }, [
      pageHead({ title: t('progress.title') }),
      current.failed
        ? callout({
            id: 'progress-error',
            tone: 'danger',
            icon: 'warning',
            text: t('common.error'),
            extra: current.failure ? h('pre', { class: 'log log--inline', text: current.failure }) : null,
          })
        : null,
      panel(
        {},
        h('div', { class: 'progress-layout' }, [
          rings({
            id: 'progress-rings',
            percent: current.percent || 0,
            value: `${Math.round(current.percent || 0)}%`,
            label: t('progress.title'),
          }),
          h('div', { class: 'stack' }, [
            phaseList(phases),
            h('div', { class: 'row' }, [
              h('span', {
                class: 'label',
                id: 'progress-elapsed',
                text: t('progress.elapsed', `${Math.floor(elapsed / 60)}:${String(elapsed % 60).padStart(2, '0')}`),
              }),
              h('span', { class: 'panel__spacer' }),
              h('span', {
                class: 'caption',
                text: current.failed ? '' : t('progress.cancelHint'),
              }),
            ]),
            meter({ id: 'progress-meter', percent: current.percent || 0 }),
          ]),
        ])
      ),
      logEl,
    ]);
  },

  isComplete() {
    return true;
  },

  /** 离开进度页 = 这一轮结束：退订事件流、停时钟（否则会在别的页面上继续画）。 */
  onLeave() {
    stop();
  },
};
