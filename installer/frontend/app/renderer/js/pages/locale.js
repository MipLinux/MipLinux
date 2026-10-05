/**
 * 高级 · 系统语言页（装后系统的 locale）
 *
 * 注意语义：这一页管的是**装好之后系统的语言与区域设置**；
 * 安装器自己的界面语言是顶栏那个「中 / EN」按钮（两条线，别混）。
 */

import { h } from '../dom.js';
import { pageHead, panel } from '../components.js';
import { selectableList } from './shared.js';

export default {
  id: 'locale',

  render(ctx) {
    const t = ctx.t;
    const { setup, backend } = ctx;

    const list = selectableList(
      {
        id: 'locale-list',
        searchId: 'locale-search',
        searchKey: 'locale.search',
        selected: setup.data.locale,
        items: backend.locales.map((locale) => ({
          value: locale.id,
          display: locale.name,
          meta: locale.id,
        })),
        matches: (item, query) => {
          const needle = query.trim().toLowerCase();
          if (!needle) return true;
          return `${item.display} ${item.value}`.toLowerCase().includes(needle);
        },
        iconFor: () => 'translate',
        emptyText: () => t('locale.empty'),
        onPick: (item) => {
          setup.set('locale', item.value);
          ctx.rerender();
        },
      },
      ctx
    );

    return h('div', { class: 'stack' }, [
      pageHead({ title: t('locale.title'), desc: t('locale.desc') }),
      panel({ fill: true }, list),
    ]);
  },

  isComplete() {
    return true;
  },
};
