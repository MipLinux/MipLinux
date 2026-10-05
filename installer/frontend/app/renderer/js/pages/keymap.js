/**
 * 高级 · 键盘布局页（装后系统的控制台 keymap）
 *
 * 试打区在**列表上方**（维护者 2026-10-05）：放到页面底部要先滚下去才能用，很别扭。
 * 预览只在有输入时出现，出现时带一次淡入上浮 —— 条件渲染的组件不该「啪」地跳出来。
 */

import { h } from '../dom.js';
import { pageHead, panel, field, textInput } from '../components.js';
import { reveal } from '../motion.js';
import { selectableList } from './shared.js';

export default {
  id: 'keymap',

  render(ctx) {
    const t = ctx.t;
    const { setup, mock } = ctx;

    const preview = h('div', { class: 'key-preview', id: 'keymap-preview', hidden: true, text: '' });

    const applyText = (value, { animate = true } = {}) => {
      if (!value) {
        preview.hidden = true;
        preview.textContent = '';
        return;
      }
      const wasHidden = preview.hidden;
      preview.textContent = value;
      preview.hidden = false;
      if (wasHidden && animate) reveal(preview);
    };

    const tryField = field({
      controlId: 'keymap-try',
      label: t('keymap.try'),
      control: textInput({
        id: 'keymap-try',
        value: setup.data.keymapText || '',
        onInput: (value) => {
          setup.set('keymapText', value);
          applyText(value);
        },
      }),
    });

    // 重新进入这一页（重画）时若已有内容：直接显示，不再播动画
    if (setup.data.keymapText) applyText(setup.data.keymapText, { animate: false });

    const list = selectableList(
      {
        id: 'keymap-list',
        searchId: 'keymap-search',
        searchKey: 'keymap.search',
        selected: setup.data.keymap,
        items: mock.keymaps.map((keymap) => ({ value: keymap.id, display: keymap.name, meta: keymap.id })),
        matches: (item, query) => {
          const needle = query.trim().toLowerCase();
          if (!needle) return true;
          return `${item.display} ${item.value}`.toLowerCase().includes(needle);
        },
        iconFor: () => 'keyboard',
        emptyText: () => t('locale.empty'),
        onPick: (item) => {
          setup.set('keymap', item.value);
          ctx.rerender();
        },
      },
      ctx
    );

    return h('div', { class: 'stack' }, [
      pageHead({ title: t('keymap.title'), desc: t('keymap.desc') }),
      panel({ fill: true }, [h('div', { class: 'stack' }, [tryField, preview]), list]),
    ]);
  },

  isComplete() {
    return true;
  },
};
