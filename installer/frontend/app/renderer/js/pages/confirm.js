/**
 * 擦除确认页（6）—— 不可逆动作的最后一道门
 *
 * `primaryError: true` → 外壳把它渲染成 danger 变体（P3：不可逆动作用错误色）。
 * 只有逐字输入所选磁盘名才放行。这里是**全流程唯一的危险按钮**。
 */

import { h } from '../dom.js';
import { pageHead, panel, field, textInput, callout, divider } from '../components.js';
import { icon } from '../icons.js';

export default {
  id: 'confirm',
  primaryError: true,

  render(ctx) {
    const t = ctx.t;
    const { setup, mock } = ctx;
    const disk = mock.diskById(setup.data.disk);
    const typed = setup.data.confirmText || '';
    const mismatch = typed.length > 0 && !setup.confirmTextMatches();

    const warn = callout({
      tone: 'danger',
      icon: 'warning',
      text: t('confirm.warn', disk ? disk.id : '—', disk ? disk.sizeLabel : '—'),
    });

    return h('div', { class: 'stack' }, [
      pageHead({ title: t('confirm.title') }),
      panel({ narrow: true }, [
        h('div', { class: 'danger-zone', id: 'confirm-danger', 'data-anim': '' }, [
          h('div', { class: 'danger-zone__title' }, [icon('warning'), h('span', { text: t('confirm.title') })]),
          h('p', { class: 'mono', text: disk ? `${disk.id} · ${disk.sizeLabel}` : '—' }),
          warn,
        ]),
        divider(),
        field({
          controlId: 'confirm-input',
          label: t('confirm.typePrompt'),
          error: mismatch ? t('confirm.err.mismatch') : '',
          control: textInput({
            id: 'confirm-input',
            value: typed,
            mono: true,
            invalid: mismatch,
            onInput: (value) => {
              setup.set('confirmText', value);
              ctx.refresh();
            },
          }),
        }),
      ]),
    ]);
  },

  isComplete(ctx) {
    return ctx.setup.confirmTextMatches();
  },

  primaryLabel(ctx) {
    return ctx.t('confirm.erase');
  },

  onPrimary(ctx) {
    ctx.goNext();
  },
};
