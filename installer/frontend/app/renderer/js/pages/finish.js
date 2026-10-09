/**
 * 完成页（8）—— 重启
 *
 * 「重启」由**后端**执行（`--reboot` → `systemctl reboot`）；前端只发请求
 * （`window.mipl.reboot()`），自己不执行任何系统动作。请求失败必须说出来 ——
 * 点一下什么都没发生，人只会以为按钮坏了（v0.1 它确实只是个空壳，实机反馈）。
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

  async onPrimary(ctx) {
    if (!window.mipl || !window.mipl.reboot) return;
    const result = await window.mipl.reboot();
    // 后端那句失败原文是中文，只进 journal（main.js 打的），界面按自己的文案说话 ——
    // 英文模式下把后端的句子摆上来就是露馅（app/README.md §7.2）。
    if (result && result.ok === false) ctx.snackbar(ctx.t('finish.rebootFailed'));
  },
};

