/**
 * 进度页（7）—— 阶段、百分比、日志、耗时
 *
 * 数据来自后端事件流的替身：真接上以后，`core/events.py` 每推一个阶段，这里就把
 * 环形进度与阶段表往前拱一格。**界面层不做任何分区/装包逻辑**（M1 的纪律）。
 *
 * 这一页没有主动作：动作区只剩「取消安装」（二次确认在 app.js 的 `confirmCancel`）。
 */

import { h, mount, clear } from '../dom.js';
import { pageHead, panel, rings, meter, phaseList, callout } from '../components.js';
import { ring, fill } from '../motion.js';

/** 阶段边界（百分比）—— 与 tech/09 的 5 条 phase 文案一一对应。 */
const PHASES = [
  { key: 'progress.phase.start', until: 8 },
  { key: 'progress.phase.disk', until: 18 },
  { key: 'progress.phase.packages', until: 70 },
  { key: 'progress.phase.configure', until: 88 },
  { key: 'progress.phase.boot', until: 100 },
];

let timer = null;
let advanceTimer = null;
let startedAt = 0;

function stop() {
  if (timer) clearInterval(timer);
  if (advanceTimer) clearTimeout(advanceTimer);
  timer = null;
  advanceTimer = null;
}

function stamp() {
  const elapsed = Math.max(0, Math.floor((Date.now() - startedAt) / 1000));
  const mm = String(Math.floor(elapsed / 60)).padStart(2, '0');
  const ss = String(elapsed % 60).padStart(2, '0');
  return { clock: `${mm}:${ss}`, elapsed };
}

export default {
  id: 'progress',

  render(ctx) {
    const t = ctx.t;
    const { setup } = ctx;
    const progress = setup.data.progress || { percent: 0, phase: 0, done: false };

    // 取消之后回摘要页（remock：真实现里由后端的中止流程决定，界面不编造终态）
    if (progress.cancelled) {
      stop();
      queueMicrotask(() => ctx.goTo('summary'));
    }

    if (!progress.startedAt) {
      startedAt = Date.now();
      setup.data.progress = { ...progress, startedAt };
      start(ctx);
    } else {
      startedAt = progress.startedAt;
    }

    const { elapsed } = stamp();
    const phases = PHASES.map((phase, index) => ({
      id: `phase-${index}`,
      label: t(phase.key),
      state: progress.percent >= phase.until ? 'done' : index === progress.phase ? 'active' : 'todo',
    }));

    const ringEl = rings({
      id: 'progress-rings',
      percent: progress.percent,
      value: `${Math.round(progress.percent)}%`,
      label: t('progress.title'),
    });

    const logEl = h('div', { class: 'log', id: 'progress-log' }, []);
    for (const line of progress.lines || []) {
      logEl.append(h('div', { class: `log__line--${line.tone || 'info'}`, text: line.text }));
    }

    return h('div', { class: 'stack' }, [
      pageHead({ title: t('progress.title') }),
      panel(
        {},
        h('div', { class: 'progress-layout' }, [
          ringEl,
          h('div', { class: 'stack' }, [
            phaseList(phases),
            h('div', { class: 'row' }, [
              h('span', { class: 'label', id: 'progress-elapsed', text: t('progress.elapsed', `${Math.floor(elapsed / 60)}:${String(elapsed % 60).padStart(2, '0')}`) }),
              h('span', { class: 'panel__spacer' }),
              h('span', { class: 'caption', text: t('progress.cancelHint') }),
            ]),
            meter({ id: 'progress-meter', percent: progress.percent }),
          ]),
        ])
      ),
      logEl,
    ]);
  },

  isComplete() {
    return true;
  },

  /** 离开进度页 = 这一轮结束：停掉模拟事件流与自动跳转（否则会「遥控」别的页面）。 */
  onLeave() {
    stop();
  },
};

/** 模拟事件流：按阶段推进百分比，并把阶段切换写进日志。 */
function start(ctx) {
  stop();
  const { setup } = ctx;
  const t = ctx.t;
  const log = (text, tone = 'info') => {
    const current = setup.data.progress;
    const lines = [...(current.lines || []), { text: `${stamp().clock}  ${text}`, tone }];
    setup.data.progress = { ...current, lines: lines.slice(-40) };
  };

  log(t('progress.phase.start'));
  timer = setInterval(() => {
    const current = setup.data.progress;
    if (current.cancelled) {
      stop();
      return;
    }
    const next = Math.min(100, current.percent + Math.random() * 3.6 + 1.2);
    const phaseIndex = PHASES.findIndex((phase) => next <= phase.until);
    const phase = phaseIndex < 0 ? PHASES.length - 1 : phaseIndex;
    const changed = phase !== current.phase;
    setup.data.progress = { ...current, percent: next, phase };

    if (changed) {
      log(t(PHASES[phase].key));
    }

    // 只改这两个元素的属性，不重画整页 —— 进度页每 120ms 重画会闪
    const ringsEl = document.getElementById('progress-rings');
    if (ringsEl) ring(ringsEl, next);
    const valueEl = ringsEl && ringsEl.querySelector('.rings__value');
    if (valueEl) valueEl.textContent = `${Math.round(next)}%`;
    fill(document.querySelector('#progress-meter .meter__fill'), next);

    const elapsedEl = document.getElementById('progress-elapsed');
    if (elapsedEl) elapsedEl.textContent = ctx.t('progress.elapsed', `${Math.floor(stamp().elapsed / 60)}:${String(stamp().elapsed % 60).padStart(2, '0')}`);

    const logEl = document.getElementById('progress-log');
    if (logEl && changed) {
      logEl.append(h('div', { text: `${stamp().clock}  ${t(PHASES[phase].key)}` }));
      logEl.scrollTop = logEl.scrollHeight;
    }

    const phaseRow = document.getElementById(`phase-${phase}`);
    if (phaseRow && changed) {
      for (const row of document.querySelectorAll('.phase')) row.dataset.state = 'todo';
      for (let i = 0; i < phase; i += 1) {
        const done = document.getElementById(`phase-${i}`);
        if (done) done.dataset.state = 'done';
      }
      phaseRow.dataset.state = 'active';
    }

    if (next >= 100) {
      stop();
      log(t('progress.done'), 'ok');
      setup.data.progress = { ...setup.data.progress, percent: 100, done: true };
      const logNow = document.getElementById('progress-log');
      if (logNow) logNow.append(h('div', { class: 'log__line--ok', text: `${stamp().clock}  ${t('progress.done')}` }));
      advanceTimer = setTimeout(() => ctx.goNext(), 900);
    }
  }, 120);
}
