/**
 * motion.js —— 动效编排（anime.js v4，vendored / MIT）
 *
 * 纪律（tech/10 §5）：
 *   1. 只动 `transform` 与 `opacity`；
 *   2. 时长只用 tokens.css 的四档，缓动不用 linear / ease-in-out；
 *   3. `prefers-reduced-motion: reduce` 下**全部不做位移动画** —— 这是双保险里的 JS 那一层
 *      （CSS 那层在 tokens.css 里）。
 */

import { animate, createTimeline, stagger, utils } from '../../vendor/anime.esm.min.js';

/** 惰性拿 media query：Node（单测）里没有 window，此时一律当「不减动画」。 */
let reduceQuery = null;

function reduceRef() {
  if (reduceQuery) return reduceQuery;
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return null;
  reduceQuery = window.matchMedia('(prefers-reduced-motion: reduce)');
  return reduceQuery;
}

export function prefersReduced() {
  const query = reduceRef();
  return query ? query.matches : false;
}

export const DUR = { fast: 140, base: 240, slow: 420, page: 480 };

/** 读 tokens.css 里的时长，保证 JS 与 CSS 用同一套（改一处不会两边漂）。 */
function cssMs(name, fallback) {
  if (typeof document === 'undefined') return fallback;
  const raw = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  const value = Number.parseFloat(raw);
  if (!Number.isFinite(value)) return fallback;
  return raw.endsWith('ms') ? value : value * 1000;
}

export function durations() {
  return {
    fast: cssMs('--dur-fast', DUR.fast),
    base: cssMs('--dur-base', DUR.base),
    slow: cssMs('--dur-slow', DUR.slow),
    page: cssMs('--dur-page', DUR.page),
  };
}

/** 页面进场：容器淡入 + 子块 40ms 交错上浮。 */
export function pageEnter(root) {
  if (!root) return;
  const blocks = [...root.querySelectorAll('[data-anim]')];
  if (prefersReduced()) {
    utils.set(blocks, { opacity: 1, translateY: 0 });
    return;
  }
  const d = durations();
  animate(root, { opacity: [0, 1], duration: d.base, ease: 'out(3)' });
  if (!blocks.length) return;
  animate(blocks, {
    opacity: [0, 1],
    translateY: [14, 0],
    duration: d.slow,
    delay: stagger(40),
    ease: 'out(3)',
  });
}

/** 页面出场：给调用方一个 Promise（旧页先走，再挂新页）。 */
export function pageLeave(root) {
  if (!root || prefersReduced()) {
    if (root) utils.set(root, { opacity: 0 });
    return Promise.resolve();
  }
  const d = durations();
  return new Promise((resolve) => {
    animate(root, {
      opacity: [1, 0],
      translateY: [0, -8],
      duration: d.fast + 20,
      ease: 'in(2)',
      onComplete: resolve,
    });
  });
}

/** 对话框 / 遮罩进场。 */
export function popIn(el) {
  if (!el) return;
  if (prefersReduced()) {
    utils.set(el, { opacity: 1, scale: 1 });
    return;
  }
  const d = durations();
  animate(el, { opacity: [0, 1], duration: d.base, ease: 'out(3)' });
  const card = el.firstElementChild;
  if (card) {
    animate(card, { scale: [0.96, 1], translateY: [10, 0], duration: d.slow, ease: 'out(4)' });
  }
}

export function popOut(el) {
  if (!el) return Promise.resolve();
  if (prefersReduced()) {
    el.remove();
    return Promise.resolve();
  }
  const d = durations();
  return new Promise((resolve) => {
    animate(el, {
      opacity: [1, 0],
      duration: d.fast,
      ease: 'in(2)',
      onComplete: () => {
        el.remove();
        resolve();
      },
    });
  });
}

/** 主视觉的轻微漂浮（欢迎页 / 完成页）：幅度小、周期长，不抢注意力。 */
export function float(el) {
  if (!el || prefersReduced()) return;
  animate(el, {
    translateY: [-6, 6],
    duration: 5200,
    ease: 'inOutSine',
    loop: true,
    alternate: true,
  });
}

/** 步骤条 / 进度条填充。 */
export function fill(el, percent, instant = false) {
  if (!el) return;
  const value = Math.max(0, Math.min(100, percent));
  if (prefersReduced() || instant) {
    utils.set(el, { width: `${value}%` });
    return;
  }
  animate(el, { width: `${value}%`, duration: durations().slow, ease: 'out(3)' });
}

/** 环形的 `--p` 变量（MVP：CSS 过渡负责插值，这里只改值）。 */
export function ring(el, percent) {
  if (!el) return;
  el.style.setProperty('--p', String(Math.max(0, Math.min(100, percent))));
}

/** 数字滚动（容量 / 计时这类读数）。 */
export function countTo(el, from, to, format = (v) => String(Math.round(v))) {
  if (!el) return;
  if (prefersReduced()) {
    el.textContent = format(to);
    return;
  }
  const state = { value: from };
  animate(state, {
    value: to,
    duration: durations().slow,
    ease: 'out(2)',
    onUpdate: () => {
      el.textContent = format(state.value);
    },
  });
}

/** 列表项交错进场（网络列表、磁盘列表这种「一次出现一批」）。 */
export function staggerIn(items) {
  if (!items || !items.length) return;
  if (prefersReduced()) {
    utils.set(items, { opacity: 1, translateY: 0 });
    return;
  }
  animate(items, {
    opacity: [0, 1],
    translateY: [10, 0],
    duration: durations().base,
    delay: stagger(28),
    ease: 'out(3)',
  });
}

/** 危险动作的「重量感」：先轻微下压再回弹（减速曲线）。 */
export function weigh(el) {
  if (!el || prefersReduced()) return;
  const tl = createTimeline({ defaults: { ease: 'out(4)' } });
  tl.add(el, { scale: [1, 0.985], duration: 120 })
    .add(el, { scale: [0.985, 1], duration: 320 });
}
