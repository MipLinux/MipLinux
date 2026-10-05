/**
 * 目标盘页（2）—— 整块磁盘的选择
 *
 * 数据来自 `mock.disks`（真后端接上后由 `disk.py` 的候选枚举给出）。
 * 这一页是**危险动作的前一页**：真正的不可逆确认在下一页（`confirm.js`）。
 */

import { h } from '../dom.js';
import { pageHead, panel, badge, button, emptyState, callout, divider } from '../components.js';
import { icon } from '../icons.js';
import { staggerIn } from '../motion.js';

function diskCard(disk, selected, onClick, t) {
  // 用分区数画一条「已有内容」的示意条：不是精确用量，只是「这块盘不是空的」的视觉信号。
  // **0 个分区就不画** —— 画一条满格的蓝条会被读成「盘已经满了」，和事实正好相反。
  const bars = [];
  const segments = Math.min(6, disk.partitions);
  for (let i = 0; i < segments; i += 1) {
    bars.push(
      h('span', {
        class: `disk-card__seg${i === 0 ? ' disk-card__seg--esp' : ''}`,
        style: { flex: '1' },
      })
    );
  }

  return h(
    'button',
    {
      id: `disk-${disk.id.replace(/[^a-zA-Z0-9]+/g, '-')}`,
      type: 'button',
      class: 'disk-card',
      'aria-selected': String(selected),
      onclick: onClick,
    },
    [
      h('span', { class: 'option__icon' }, icon('hard-drives')),
      h('span', { class: 'option__body' }, [
        h('span', { class: 'row' }, [
          h('span', { class: 'option__title', text: disk.model }),
          disk.recommended && !selected ? badge({ label: t('disk.recommended'), tone: 'accent' }) : null,
          selected ? badge({ label: t('disk.selected'), tone: 'accent' }) : null,
        ]),
        h('span', { class: 'row' }, [
          h('span', { class: 'disk-card__size', text: disk.sizeLabel }),
          h('span', { class: 'option__meta mono', text: disk.id }),
          h('span', { class: 'option__meta', text: t('disk.partitions', disk.partitions) }),
        ]),
        bars.length ? h('span', { class: 'disk-card__bar' }, bars) : null,
      ]),
      h('span', { class: 'option__tail' }, [selected ? icon('check') : null]),
    ]
  );
}

export default {
  id: 'disk',

  render(ctx) {
    const t = ctx.t;
    const { setup, mock } = ctx;

    const body = mock.diskScanning
      ? h('div', { class: 'stack' }, [
          h('div', { class: 'skeleton', style: { height: '92px' } }),
          h('div', { class: 'skeleton', style: { height: '92px' } }),
        ])
      : mock.disks.length === 0
        ? emptyState({
            icon: 'hard-drives',
            text: t('disk.empty'),
            action: button({
              id: 'disk-rescan-empty',
              label: t('nav.refresh'),
              variant: 'tonal',
              icon: 'arrows-clockwise',
              onClick: () => rescan(ctx),
            }),
          })
        : h(
            'div',
            { class: 'stack', style: { marginTop: '4px' } },
            mock.disks.map((disk) =>
              diskCard(
                disk,
                setup.data.disk === disk.id,
                () => {
                  setup.set('disk', disk.id);
                  ctx.rerender();
                },
                t
              )
            )
          );

    if (ctx.animateIn) queueMicrotask(() => staggerIn([...document.querySelectorAll('.disk-card')]));

    return h('div', { class: 'stack' }, [
      pageHead({ title: t('disk.title'), desc: t('disk.desc') }),
      callout({ tone: 'warn', icon: 'warning', text: t('disk.willDo') }),
      panel({}, [
        body,
        // 扫描动作跟在列表后面，而不是浮在标题行右侧（维护者 2026-10-04）——
        // 它是「对下面这份列表」的动作，位置就该在列表之后
        h('div', { class: 'row', style: { 'margin-top': '4px' } }, [
          button({
            id: 'disk-rescan',
            label: t('nav.refresh'),
            variant: 'tonal',
            icon: 'arrows-clockwise',
            disabled: mock.diskScanning,
            onClick: () => rescan(ctx),
          }),
        ]),
      ]),
      divider(),
    ]);
  },

  isComplete(ctx) {
    return Boolean(ctx.setup.data.disk);
  },
};

async function rescan(ctx) {
  ctx.rerender();
  await ctx.mock.rescanDisks();
  ctx.rerender();
}
