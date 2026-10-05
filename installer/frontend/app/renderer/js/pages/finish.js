/**
 * 完成页（8）—— 重启
 *
 * 「重启」在 v0.1 由后端接管（`systemctl reboot`）；前端只发请求（`window.mipl.reboot()`），
 * 自己**不执行**任何系统动作。
 */

import { h } from '../dom.js';
import { float } from '../motion.js';
import { icon } from '../icons.js';

export default {
  id: 'finish',

  render(ctx) {
    const t = ctx.t;
    const logo = h('img', {
      class: 'finish__logo',
      src: new URL('../../assets/logo/logo-512.png', import.meta.url).href,
      alt: '',
      draggable: 'false',
      decoding: 'async',
    });
    queueMicrotask(() => float(logo));

    return h('div', { class: 'finish' }, [
      h('div', { class: 'finish__check', 'data-anim': '' }, icon('check')),
      h('h1', { class: 'lead', 'data-anim': '', text: t('finish.title') }),
      h('p', { class: 'page-desc', 'data-anim': '', text: t('finish.body') }),
      h('div', { class: 'finish__art', 'data-anim': '' }, [h('span', { class: 'welcome__glow' }), logo]),
    ]);
  },

  isComplete() {
    return true;
  },

  primaryLabel(ctx) {
    return ctx.t('finish.reboot');
  },

  onPrimary() {
    if (window.mipl && window.mipl.reboot) window.mipl.reboot();
  },
};

