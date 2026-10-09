/**
 * pages/shared.js —— 页面之间共用的两件小事（搜索 + 列表选择）
 *
 * 三个「搜索 + 从名单里选一个」的页面（语言 / 键盘 / 时区）只有取数不同，
 * 交互完全一样，所以放在这里 —— 免得三份实现各自漂。
 */

import { h, clear, attachScrollFade } from '../dom.js';
import { searchInput, option, emptyState, listBox } from '../components.js';

/**
 * 把**默认值**那一项排到第一行，其余保持后端给的顺序。
 *
 * 为什么置顶的是「默认值」而不是「当前选中」（维护者 2026-10-05）：选中项一置顶，
 * 点一条列表就在手指底下重排一次 —— 紧接着的第二次点击会落到**刚挪上来**的那一行上。
 * 默认值是开工时就定下、之后不再变的那个，放在第一行既让人一眼看到「不选会得到什么」，
 * 列表本身又是稳的：**选中不参与排序**。
 *
 * 纯函数（不碰 DOM）：排序规则是这一页最容易写错的一处，单独测。
 */
export function withDefaultFirst(items, defaultValue) {
  const index = items.findIndex((item) => item.value === defaultValue);
  if (index <= 0) return items;
  return [items[index], ...items.slice(0, index), ...items.slice(index + 1)];
}

/**
 * 可搜索的单选列表。
 *
 * @param {object} config
 * @param {string} config.id            列表容器 id（探针要查）
 * @param {string} config.searchId      搜索框 id
 * @param {Array}  config.items         候选（含 display / meta 字段）
 * @param {string} config.selected      当前选中的值
 * @param {string} config.defaultValue  默认值 —— 这一项排第一行（见 `withDefaultFirst`）
 * @param {Function} config.onPick      (item) => void
 * @param {Function} config.iconFor     (item) => 图标名
 * @param {Function} config.emptyText   () => 空态文案
 * @param {object} ctx                  页面上下文
 */
export function selectableList(config, ctx) {
  const t = ctx.t;
  // 外层撑满面板：搜索框固定，只有下面的列表滚（页面本体不滚）
  const wrapper = h('div', { class: 'list-wrap', id: config.id });
  let query = '';

  // 顺序在过滤**之前**定下来：搜索时默认项也还在第一行（它不匹配就不会出现在结果里）
  const ordered = withDefaultFirst(config.items, config.defaultValue);

  const renderItems = () => {
    const matched = ordered.filter((item) => config.matches(item, query));
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
    const fresh = h('div', { class: 'list-wrap', dataset: { list: '1' } }, box);
    if (old) old.replaceWith(fresh);
    else wrapper.append(fresh);
    // 渐隐按「当前滚动位置」更新；列表重建后要重新挂
    attachScrollFade(box.classList && box.classList.contains('list') ? box : box.querySelector('.list'));
  };

  const search = searchInput({
    id: config.searchId,
    placeholder: t(config.searchKey),
    onInput: (value) => {
      query = value;
      renderItems();
    },
  });

  wrapper.append(search, h('div', { class: 'list-wrap', dataset: { list: '1' } }));
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
