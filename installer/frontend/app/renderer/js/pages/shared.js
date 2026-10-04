/**
 * pages/shared.js —— 页面之间共用的两件小事（搜索 + 列表选择）
 *
 * 三个「搜索 + 从名单里选一个」的页面（语言 / 键盘 / 时区）只有取数不同，
 * 交互完全一样，所以放在这里 —— 免得三份实现各自漂。
 */

import { h, clear } from '../dom.js';
import { searchInput, option, emptyState, listBox } from '../components.js';

/**
 * 可搜索的单选列表。
 *
 * @param {object} config
 * @param {string} config.id            列表容器 id（探针要查）
 * @param {string} config.searchId      搜索框 id
 * @param {Array}  config.items         候选（含 display / meta 字段）
 * @param {string} config.selected      当前选中的值
 * @param {Function} config.onPick      (item) => void
 * @param {Function} config.iconFor     (item) => 图标名
 * @param {Function} config.emptyText   () => 空态文案
 * @param {object} ctx                  页面上下文
 */
export function selectableList(config, ctx) {
  const t = ctx.t;
  const wrapper = h('div', { class: 'stack', id: config.id });
  let query = '';

  const renderItems = () => {
    const matched = config.items.filter((item) => config.matches(item, query));
    const box =
      matched.length > 0
        ? listBox(
            ...matched.map((item) =>
              option({
                id: `${config.id}-${slug(item.value)}`,
                icon: config.iconFor ? config.iconFor(item) : null,
                title: item.display,
                meta: item.meta,
                tail: item.tail || null,
                selected: item.value === config.selected,
                onClick: () => config.onPick(item),
              })
            )
          )
        : emptyState({ icon: 'magnifying-glass', text: config.emptyText() });
    const old = wrapper.querySelector('[data-list]');
    const fresh = h('div', { dataset: { list: '1' } }, box);
    if (old) old.replaceWith(fresh);
    else wrapper.append(fresh);
  };

  const search = searchInput({
    id: config.searchId,
    placeholder: t(config.searchKey),
    onInput: (value) => {
      query = value;
      renderItems();
    },
  });

  wrapper.append(search, h('div', { dataset: { list: '1' } }));
  wrapper.__renderItems = renderItems;
  renderItems();
  return wrapper;
}

export function slug(value) {
  return String(value).replace(/[^a-zA-Z0-9]+/g, '-').toLowerCase();
}

/** 用「标签 + 值」拼一页摘要（摘要页与完成页复用）。 */
export function readoutRows(pairs) {
  return pairs;
}
