/**
 * 高级 · 键盘布局页（装后系统的控制台 keymap）
 *
 * 这一页回答的是「这个布局长什么样」，不是「我能不能打出字」。
 *
 * **为什么删掉了试打框（Issue #65）。** 原来有一个输入框让人在里面敲字试效果。
 * 那测的是**当前会话**的键位（Live 里是 cage/Wayland 的合成器与桌面），
 * 而 `vconsole.conf` 管的是**装后系统的控制台**（`loadkeys` 那一层）——
 * 两者根本不是同一套映射。试打通过 ≠ 装完能用，那等于用一个假证据替换真证据。
 * 换成这张主键区图之后，「选错了会怎样」在**装之前**就看得见。
 *
 * 图上的每个字都来自 `--print-keymap` 解析出的那份映射，出处写在图下面那行
 * （映射文件的路径）—— 界面上每个字都要能指出出处，这一条不因为图好看就让位。
 */

import { h, clear } from '../dom.js';
import { pageHead, panel, caption } from '../components.js';
import { reveal } from '../motion.js';
import { selectableList } from './shared.js';
import { buildRows, hasAnyKey } from '../keymap-rows.js';

/** 画图是异步的（要起一次后端）。`token` 防的是「慢的那次盖掉刚选的那次」。 */
let token = 0;

function keycap(key) {
  return h(
    'span',
    {
      class: 'keycap',
      style: { '--key-w': String(key.width) },
      dataset: { code: String(key.code) },
    },
    [
      key.shiftLabel ? h('span', { class: 'keycap__shift', text: key.shiftLabel }) : null,
      h('span', { class: 'keycap__label', text: key.label }),
    ]
  );
}

/**
 * 把图直接画进 `node`，**不重画整页** —— 重画会把搜索框里的字清掉，
 * 而「一边搜一边看布局」正是这一页最常见的用法。
 */
async function drawBlock(ctx, node) {
  const mine = (token += 1);
  const view = await ctx.backend.keymapView(ctx.setup.data.keymap);
  if (mine !== token) return;
  clear(node);
  if (!view || !Array.isArray(view.keys) || view.keys.length === 0) {
    // 解析不出来就不画空框：一张空白键盘看起来像「这个布局没有键」，
    // 而事实是「这次没取到」。两者要说不同的话。
    node.append(h('p', { class: 'caption faint', text: ctx.t('locale.empty') }));
    return;
  }
  const rows = buildRows(view.keys);
  node.append(
    h(
      'div',
      {
        class: 'keyblock',
        id: 'keymap-block',
        role: 'img',
        'aria-label': `${ctx.t('keymap.title')}: ${view.name}`,
      },
      rows.map((row) => h('div', { class: 'keyblock__row' }, row.map(keycap)))
    ),
    caption(view.source)
  );
  if (hasAnyKey(rows)) reveal(node);
}

export default {
  id: 'keymap',

  render(ctx) {
    const t = ctx.t;
    const { setup, backend } = ctx;

    const block = h('div', { class: 'keyblock-wrap', id: 'keymap-preview' }, []);
    // 首帧先画空壳，图取回来再填 —— 取数要起一次后端，卡在 render() 里就是白屏
    drawBlock(ctx, block);

    const list = selectableList(
      {
        id: 'keymap-list',
        searchId: 'keymap-search',
        searchKey: 'keymap.search',
        selected: setup.data.keymap,
        // 键盘映射的显示名就是它自己的名字（`localectl` 的写法）：kbd 不给译名，
        // 我们也不编一个 —— 编了就会和 `localectl` / `vconsole.conf` 里的写法对不上。
        items: backend.keymaps.map((keymap) => ({ value: keymap.id, display: keymap.name, meta: '' })),
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
      panel({ fill: true }, [h('div', { class: 'stack' }, [block]), list]),
    ]);
  },

  isComplete() {
    return true;
  },
};
