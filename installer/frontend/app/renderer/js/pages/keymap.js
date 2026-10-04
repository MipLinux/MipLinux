/**
 * 高级 · 键盘布局页（装后系统的控制台 keymap）
 *
 * 「在这里试打」给一个输入框：用户按几个键，看到实际字符 —— 选错布局最常见的原因
 * 就是「Y 和 Z 换了位置」，光看名字看不出来。
 */

import { h } from '../dom.js';
import { pageHead, panel, field, textInput } from '../components.js';
import { selectableList } from './shared.js';

export default {
  id: 'keymap',

  render(ctx) {
    const t = ctx.t;
    const { setup, mock } = ctx;

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

    const preview = h('div', { class: 'key-preview', id: 'keymap-preview', text: setup.data.keymapText || '' });

    const tryField = field({
      controlId: 'keymap-try',
      label: t('keymap.try'),
      control: textInput({
        id: 'keymap-try',
        value: setup.data.keymapText || '',
        placeholder: '',
        onInput: (value) => {
          setup.set('keymapText', value);
          preview.textContent = value;
        },
      }),
    });

    return h('div', { class: 'stack' }, [
      pageHead({ title: t('keymap.title'), desc: t('keymap.desc') }),
      panel({}, [list, preview, tryField]),
    ]);
  },

  isComplete() {
    return true;
  },
};
