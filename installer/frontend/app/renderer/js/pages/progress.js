/**
 * 进度页（7）—— 阶段、当前步骤、真计数、日志、耗时
 *
 * **进度不由界面编。** 这一页只做两件事：把 `backend.onInstallEvent()` 推来的
 * 记录翻成画面，和把用户的取消请求送到 `backend.cancelInstall()`。
 *
 * ## 两层进度，两层都只说真话（2026-10-06 实机反馈后重做）
 *
 * 旧版是「一进阶段就把这一段的百分比先领了」：`start→8% / disk→18% /
 * packages→70% / configure→88% / boot→96%`。实机上它的代价很直观 —— 第一个包还没
 * 下完，环上就写着 70%（维护者：「安装系统实际上是很前期的事情，这里不应该给
 * 70% 这么大的进度」）。**全局百分比是对整次安装的预测，而界面没有依据做这个预测**：
 * 四个阶段的耗时差着量级（分区几十秒、下载看网速、initramfs 看 CPU）。
 *
 * 现在：
 *   1. **环 = 第几个阶段 / 共几个阶段**（`PHASES.length`）。真的，永不倒退，
 *      也永不提前领功；
 *   2. **meter = 当前阶段内真的数得出来的进度**（`record.step / record.total`，
 *      例如 pacman 的 `(14/345)`）。数不出来就画不确定态 —— 不编百分比；
 *   3. **子步骤列表**：当前阶段报过的 `step_id`，名字走 `progress.step.<id>` ——
 *      id 是后端事件里的稳定标识，界面不猜、也不自己排一份步骤表；
 *   4. **时间**：`已用时` 是真的；不可细分的长步骤给一句「这一步以分钟计」；
 *      packages 那一步按**本阶段**实测速率给一条局部估算，绝不外推到整次安装。
 *
 * ## 另外两条口径
 *
 * - **日志里的话是后端说的**：阶段那几行走翻译键（`progress.phase.*`）；
 *   `note` 是后端的旁白（子进程的真实输出、耗时），**原样显示不翻译** ——
 *   它是诊断信息，和 `journalctl` 里那行是同一句话。
 * - **取消只发生在阶段之间**：按下的那一刻只是「举手」（`SIGUSR1`），页面上那句
 *   提示就是这么写的（`progress.cancelHint`）。真停下来之后后端给 130，才回摘要页。
 */

import { h, clear } from '../dom.js';
import { pageHead, panel, rings, meter, phaseList, button } from '../components.js';
import { icon } from '../icons.js';
import { ring, fill } from '../motion.js';
import { buildPlan, buildSecrets } from '../backend.js';

/**
 * 阶段的显示顺序与文案键 —— 与 `mipl_installer/events.py` 的 `PHASES` 一一对应。
 *
 * 这里**只认 id 与文案**，不再有百分比：全局百分比是界面替后端做的预测，
 * 而依据在后端手里（它才知道每一步真的走到哪了）。
 */
const PHASES = [
  { phase: 'start', key: 'progress.phase.start' },
  { phase: 'disk', key: 'progress.phase.disk' },
  { phase: 'packages', key: 'progress.phase.packages' },
  { phase: 'configure', key: 'progress.phase.configure' },
  { phase: 'boot', key: 'progress.phase.boot' },
];

/**
 * 「这一步以分钟计」的那几步：它们输出少、耗时长（gpg 等熵、导入几百个键、
 * mkinitcpio 压缩），而界面又数不出子进度。说一句预期，比一个假百分比有用。
 */
const SLOW_STEPS = new Set(['keyring-init', 'keyring-populate', 'keyring-refresh', 'initramfs']);

/**
 * 失败码 → 界面自己的句子与补救动作。
 *
 * 认得的用本地化文案（英文模式才不会冒出中文），**认不出的照实摆后端那句** ——
 * 编一句「安装失败」比原文更没用（同 `network.err.other` 的道理）。
 * `action` 是能一键补救的那几条：目前只有「`/mnt` 被占用」（守卫拒绝时盘一个
 * 字节都没动，卸掉挂载就能重来）。
 */
const KNOWN_FAILURES = {
  targetMounted: {
    title: 'progress.err.targetMounted',
    hint: 'progress.err.targetMountedHint',
    action: 'unmountTarget',
  },
};

/** 一键卸载目标挂载点。**动作在后端**（`umount -R`），界面只发请求与报结果。 */
async function unmountTarget(ctx) {
  const result = await ctx.backend.unmountTarget();
  if (result.ok) {
    patch(ctx, { unmounted: true });
    ctx.snackbar(ctx.t('progress.unmounted'));
  } else {
    ctx.snackbar(ctx.t('progress.unmountFailed'));
  }
  ctx.rerender();
}

/**
 * 失败那一块：**什么坏了 / 下一步怎么办 / 能点什么 / 技术细节**。
 *
 * 不用 `.callout`：那里只放得下一句话，而失败要把这四件事分开说，还得塞得下一个
 * 按钮。技术细节走原生 `<details>` 收起 —— 摆给要排查的人，不占别人的眼睛。
 */
function failureBlock(ctx, current) {
  const t = ctx.t;
  const known = current.failureReason ? KNOWN_FAILURES[current.failureReason] : null;
  const title = known ? t(known.title) : (current.failure || t('common.error'));
  const hint = known ? t(known.hint) : (current.failureHint || '');

  const actions = [];
  if (known && known.action === 'unmountTarget') {
    actions.push(current.unmounted
      ? h('span', { class: 'failure__done', text: t('progress.unmounted') })
      : button({
        id: 'failure-unmount',
        label: t('progress.unmount'),
        variant: 'primary',
        onClick: () => unmountTarget(ctx),
      }));
  }

  // **没有「技术细节」那一块。** 它曾经把后端那句原文与 hint 折起来摆在下面，
  // 而那两句要么已经被上面的本地化文案说过了、要么就是标题本身 —— 一个只会重复
  // 上一行的折叠块（实机反馈：「技术细节删除，没有用处」）。
  // 认不出的失败码仍然照实把后端那句当标题摆出来，信息一个字没少；
  // 要原文有 `journalctl -u mipl-installer` 与安装日志（后端的 stderr 都在那儿）。
  return h('div', { class: 'failure', id: 'progress-error' }, [
    h('div', { class: 'failure__head' }, [
      icon('warning'),
      h('div', { class: 'failure__body' }, [
        h('div', { class: 'failure__title', text: title }),
        hint ? h('div', { class: 'failure__hint', text: hint }) : null,
      ]),
    ]),
    actions.length ? h('div', { class: 'failure__actions' }, actions) : null,
  ]);
}

/** 界面侧的一次订阅与一个时钟。装完/离开时都要收掉，否则会「遥控」别的页面。 */
let subscription = null;
let clock = null;
let advanceTimer = null;
let startedAt = 0;
/** packages 那一步的速率样本：`{at, step}`，只用来算**本阶段**的局部估算。 */
let rateSample = null;

function stop() {
  if (subscription) subscription();
  subscription = null;
  if (clock) clearInterval(clock);
  clock = null;
  if (advanceTimer) clearTimeout(advanceTimer);
  advanceTimer = null;
  rateSample = null;
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

/**
 * 「按当前速度还需约 N 分钟」—— **只在本阶段内成立**，也只用本阶段实测到的样本。
 *
 * 不外推到整次安装：后面还有几步、各要多久，界面不知道。样本不够（刚装第一个包）
 * 或算出来不到一分钟就不显示 —— 一句估不准的话比没有更糟。
 */
function localEta(progress) {
  if (progress.stepId !== 'install' || !progress.total || !rateSample) return '';
  const seconds = (Date.now() - rateSample.at) / 1000;
  const done = progress.step - rateSample.step;
  if (seconds < 5 || done < 1) return '';
  const remaining = progress.total - progress.step;
  const minutes = Math.round(remaining / (done / seconds) / 60);
  return minutes >= 1 ? String(minutes) : '';
}

/** 环、阶段、meter、计数、提示 —— 每条事件都更新这几样（都是廉价的属性赋值）。 */
function paint(ctx) {
  const t = ctx.t;
  const progress = ctx.setup.data.progress;
  const completed = Math.min(progress.phaseIndex || 0, PHASES.length);

  const ringsEl = document.getElementById('progress-rings');
  ring(ringsEl, (completed / PHASES.length) * 100);
  const valueEl = ringsEl && ringsEl.querySelector('.rings__value');
  if (valueEl) valueEl.textContent = `${completed} / ${PHASES.length}`;

  for (const [index, item] of PHASES.entries()) {
    const row = document.getElementById(item.phase);
    if (!row) continue;
    row.dataset.state = index < (progress.phaseIndex || 0) ? 'done'
      : index === progress.phaseIndex ? 'active' : 'todo';
  }

  const hasCounter = Boolean(progress.total) && Number.isFinite(progress.step);
  const counterEl = document.getElementById('progress-counter');
  if (counterEl) {
    counterEl.textContent = hasCounter
      ? (progress.stepId === 'install'
        ? t('progress.packages', progress.step, progress.total)
        : `${progress.step} / ${progress.total}`)
      : '';
  }
  fill(document.querySelector('#progress-meter .meter__fill'),
    hasCounter ? (progress.step / progress.total) * 100 : 0);
  const meterEl = document.getElementById('progress-meter');
  if (meterEl) meterEl.classList.toggle('meter--indeterminate', !hasCounter && !progress.done);

  const hintEl = document.getElementById('progress-hint');
  if (hintEl) {
    const minutes = localEta(progress);
    hintEl.textContent = minutes ? t('progress.eta', minutes)
      : SLOW_STEPS.has(progress.stepId) ? t('progress.slow') : '';
  }

  const elapsedEl = document.getElementById('progress-elapsed');
  if (elapsedEl) {
    elapsedEl.textContent = t('progress.elapsed', `${Math.floor(stamp().elapsed / 60)}:${stamp().elapsed % 60}`);
  }
}

/**
 * 子步骤列表：**只画后端已经报过的那几步**，名字查 `progress.step.<id>`。
 *
 * 不预先排一份「这个阶段有哪几步」的表：那会成为第二份真相（后端加一步、
 * 界面这里忘了加，表现是这一步永远不出现）。已经报过的按顺序列出来，
 * 当前那一步高亮 —— 下一个阶段一开，这一块就整个换掉。
 */
function renderSteps(ctx) {
  const host = document.getElementById('progress-steps');
  if (!host) return;
  const progress = ctx.setup.data.progress;
  const steps = progress.steps || [];
  const currentIndex = steps.indexOf(progress.stepId);
  const signature = `${progress.phaseIndex}|${progress.stepId}|${steps.join(',')}`;
  if (host.dataset.signature === signature) return;
  host.dataset.signature = signature;
  clear(host);
  if (!steps.length) return;
  host.append(
    phaseList(
      steps.map((id, index) => ({
        id: `substep-${index}`,
        state: id === progress.stepId ? 'active' : currentIndex >= 0 && index < currentIndex ? 'done' : 'todo',
        label: ctx.t(`progress.step.${id}`),
      })),
      { className: 'phase-list--sub' }
    )
  );
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
        patch(ctx, { phaseIndex: PHASES.length, stepId: null, step: null, total: null });
        renderSteps(ctx);
        paint(ctx);
        break;
      }
      const index = phaseIndex(record.phase);
      if (index === null) break;
      const changes = {};
      if (index !== current.phaseIndex) {
        // 阶段切换才在日志里记一行；细进度不进日志（它每装一个包就变一次）
        appendLog(ctx, ctx.t(PHASES[index].key));
        changes.phaseIndex = index;
        changes.steps = [];
        changes.stepId = null;
        changes.step = null;
        changes.total = null;
        rateSample = null;
      }
      if (record.step_id) {
        const steps = changes.steps || current.steps || [];
        if (!steps.includes(record.step_id)) changes.steps = [...steps, record.step_id];
        if (record.step_id !== current.stepId) rateSample = null;
        changes.stepId = record.step_id;
        changes.step = Number.isFinite(record.step) ? record.step : null;
        changes.total = Number.isFinite(record.total) ? record.total : null;
        if (record.step_id === 'install' && changes.step && !rateSample) {
          rateSample = { at: Date.now(), step: changes.step };
        }
      }
      patch(ctx, changes);
      renderSteps(ctx);
      paint(ctx);
      break;
    }
    case 'note':
      // 后端的旁白：原样显示（见文件头最后一条）
      if (record.message) appendLog(ctx, String(record.message));
      break;
    case 'command':
      // 命令行不进日志：`pacstrap` 一次会刷出几十条，把有用的那几行冲走。
      // 要看它们有 journalctl（子进程的 stderr 也在那儿）。
      break;
    case 'error':
      // 后端那句原文与 `hint` 都留着（`failureBlock` 用它们当原始记录）；
      // `reason` 是机器可读的失败码，界面拿它挑自己的句子与补救动作。
      patch(ctx, {
        failed: true,
        failure: record.message || '',
        failureHint: record.hint || '',
        failureReason: record.reason || '',
      });
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

/**
 * 订阅事件流 + 起一个走秒的钟。**两个入口共用**：新开一轮（`startRun`）与
 * 中途回到这一页（`render` 的 resume 分支）。
 */
function attach(ctx) {
  if (!subscription) {
    subscription = ctx.backend.onInstallEvent((record) => onRecord(ctx, record));
  }
  if (!clock) {
    clock = setInterval(() => {
      const elapsedEl = document.getElementById('progress-elapsed');
      if (elapsedEl) {
        elapsedEl.textContent = ctx.t('progress.elapsed',
          `${Math.floor(stamp().elapsed / 60)}:${stamp().elapsed % 60}`);
      }
    }, 1000);
  }
}

function startRun(ctx) {
  stop();
  startedAt = Date.now();
  ctx.setup.data.progress = {
    phaseIndex: 0,
    stepId: null,
    step: null,
    total: null,
    steps: [],
    lines: [],
    startedAt,
    done: false,
    cancelled: false,
    cancelRequested: false,
    failed: false,
    failure: '',
  };
  appendLog(ctx, ctx.t(PHASES[0].key));
  attach(ctx);

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

    // 进入这一页 = 开一轮安装；一轮还没结束就回到这一页 = **接回去**，不是再开一轮。
    if (!progress.startedAt) {
      startRun(ctx);
    } else {
      startedAt = progress.startedAt;
      // `onLeave` 会把订阅退掉（不退的话它会在别的页面上继续画），所以回到这一页
      // 必须重新接上 —— 否则页面停在离开那一刻，看着像卡死。产品路径走不到这里
      // （进度页没有返回），但这是一条**会静默冻住**的路，留着比修它危险。
      attach(ctx);
      renderSteps(ctx);
      paint(ctx);
    }

    // 用户在对话框里按了「取消安装」：这里才把请求送出去（见文件头最后一条）
    if (progress.cancelRequested && !progress.cancelSent) {
      patch(ctx, { cancelSent: true });
      ctx.backend.cancelInstall();
      appendLog(ctx, t('progress.cancelHint'), 'warn');
    }

    const current = setup.data.progress;
    const completed = Math.min(current.phaseIndex || 0, PHASES.length);
    const phases = PHASES.map((phase, index) => ({
      id: phase.phase,
      label: t(phase.key),
      // 「进行中」优先于「已完成」：阶段刚点亮时不该被画成已完成
      state: index === current.phaseIndex ? 'active' : index < completed ? 'done' : 'todo',
    }));
    const { elapsed } = stamp();

    const logEl = h('div', { class: 'log', id: 'progress-log' }, []);
    for (const line of current.lines || []) {
      logEl.append(h('div', { class: `log__line--${line.tone || 'info'}`, text: line.text }));
    }

    return h('div', { class: 'stack' }, [
      pageHead({ title: t('progress.title') }),
      current.failed ? failureBlock(ctx, current) : null,
      panel(
        {},
        h('div', { class: 'progress-layout' }, [
          rings({
            id: 'progress-rings',
            percent: (completed / PHASES.length) * 100,
            value: `${completed} / ${PHASES.length}`,
            label: t('progress.stage'),
          }),
          h('div', { class: 'stack' }, [
            phaseList(phases),
            h('div', { id: 'progress-steps' }),
            h('div', { class: 'row' }, [
              h('span', {
                class: 'label',
                id: 'progress-elapsed',
                text: t('progress.elapsed', `${Math.floor(elapsed / 60)}:${String(elapsed % 60).padStart(2, '0')}`),
              }),
              h('span', { class: 'panel__spacer' }),
              h('span', { class: 'caption', id: 'progress-hint', text: '' }),
              h('span', { class: 'panel__spacer' }),
              h('span', {
                class: 'caption',
                text: current.failed ? '' : t('progress.cancelHint'),
              }),
            ]),
            h('div', { class: 'row progress-meter' }, [
              meter({ id: 'progress-meter', percent: 0 }),
              h('span', { class: 'caption mono', id: 'progress-counter', text: '' }),
            ]),
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