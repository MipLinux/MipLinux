/**
 * 欢迎页（0）—— 主视觉 + 高级安装开关
 *
 * 这里**不加**审核稿之外的文案：欢迎页的身份感来自 logo、字号与留白，不靠副标题堆。
 */

import { h } from '../dom.js';
import { lead, panel, checkbox } from '../components.js';
import { float } from '../motion.js';

export default {
  id: 'welcome',

  render(ctx) {
    const t = ctx.t;
    const { setup } = ctx;

    const logo = h('img', {
      class: 'welcome__logo',
      src: new URL('../../assets/logo/logo-512.png', import.meta.url).href,
      alt: '',
      decoding: 'async',
    });
    // 主视觉轻微漂浮：幅度 6px、周期 5.2s —— 让 kiosk 看起来「活着」但不抢注意力
    queueMicrotask(() => float(logo));

    const advancedToggle = checkbox({
      id: 'advanced-toggle',
      checked: setup.advanced,
      label: t('advanced.toggle'),
      hint: setup.advanced ? t('advanced.hint') : '',
      onChange: (checked) => {
        setup.setAdvanced(checked);
        ctx.rerender();
      },
    });

    return h('div', { class: 'welcome' }, [
      h('div', { class: 'welcome__copy' }, [
        h('p', { class: 'lead', 'data-anim': '', text: t('welcome.title') }),
        h('p', { class: 'page-desc', 'data-anim': '', text: t('welcome.body') }),
        h('div', { class: 'welcome__toggle', 'data-anim': '' }, panel({ quiet: true }, advancedToggle)),
      ]),
      h('div', { class: 'welcome__art', 'data-anim': '' }, [
        h('span', { class: 'welcome__glow' }),
        h('span', { class: 'welcome__ring' }),
        logo,
      ]),
    ]);
  },

  isComplete() {
    return true;
  },

  primaryLabel(ctx) {
    return ctx.t('welcome.begin');
  },
};
