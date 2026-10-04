/**
 * components.js —— 组件构件（CSS 在 components.css；这里只负责结构）
 *
 * 页面**只用这里的东西**拼界面：主面板一律双层壳、按钮一律 pill、输入一律 --r-field。
 * 所有给人看的字都通过 `t()` 传入 —— 本模块不写任何文案，也不 import i18n。
 */

import { h } from './dom.js';
import { icon } from './icons.js';

/* -------------------------------------------------------------- 排版件 */

export function pageHead({ title, desc }) {
  return h('header', { class: 'page-head', 'data-anim': '' }, [
    h('h1', { class: 'page-title', text: title }),
    desc ? h('p', { class: 'page-desc', text: desc }) : null,
  ]);
}

export function lead(text) {
  return h('p', { class: 'lead', text });
}

export function caption(text) {
  return h('p', { class: 'caption', text });
}

export function divider() {
  return h('hr', { class: 'divider' });
}

/* -------------------------------------------------------------- 面板 */

export function panel({ title, sub, actions, quiet = false, flush = false, narrow = false } = {}, ...children) {
  const head =
    title || actions
      ? h('div', { class: 'panel__head' }, [
          title ? h('h2', { class: 'panel__title', text: title }) : null,
          sub ? h('span', { class: 'panel__sub', text: sub }) : null,
          h('span', { class: 'panel__spacer' }),
          actions || null,
        ])
      : null;
  return h(
    'section',
    { class: `panel${quiet ? ' panel--quiet' : ''}${flush ? ' panel--flush' : ''}${narrow ? ' panel--narrow' : ''}`, 'data-anim': '' },
    h('div', { class: 'panel__core' }, head, ...children)
  );
}

export function stack(...children) {
  return h('div', { class: 'stack' }, ...children);
}

export function row(...children) {
  return h('div', { class: 'row' }, ...children);
}

export function grid2(...children) {
  return h('div', { class: 'grid-2' }, ...children);
}

/* -------------------------------------------------------------- 按钮 */

export function button({ label, variant = 'tonal', icon: iconName, onClick, disabled, id, type = 'button' }) {
  return h(
    'button',
    {
      id,
      type,
      class: `btn btn--${variant}`,
      disabled: Boolean(disabled) || null,
      onclick: onClick,
    },
    [
      label ? h('span', { text: label }) : null,
      iconName ? h('span', { class: 'btn__icon' }, icon(iconName)) : null,
    ]
  );
}

export function iconButton({ name, label, onClick, pressed, id }) {
  return h(
    'button',
    {
      id,
      type: 'button',
      class: 'icon-btn',
      title: label,
      'aria-label': label,
      'aria-pressed': pressed === undefined ? null : String(Boolean(pressed)),
      onclick: onClick,
    },
    icon(name)
  );
}

/* -------------------------------------------------------------- 表单 */

export function field({ label, hint, error, control, controlId }) {
  return h('div', { class: 'field' }, [
    label ? h('label', { class: 'field__label', for: controlId, text: label }) : null,
    control,
    error
      ? h('p', { class: 'field__error', id: controlId ? `${controlId}-error` : null }, [
          icon('warning'),
          h('span', { text: error }),
        ])
      : null,
    hint && !error ? h('p', { class: 'field__hint', text: hint }) : null,
  ]);
}

export function textInput({
  id,
  value = '',
  placeholder,
  type = 'text',
  onInput,
  onEnter,
  mono = false,
  invalid = false,
  autocomplete = 'off',
  descriptionId,
}) {
  return h('input', {
    id,
    class: `input${mono ? ' input--mono' : ''}`,
    type,
    value,
    placeholder,
    autocomplete,
    spellcheck: 'false',
    'aria-invalid': invalid ? 'true' : null,
    'aria-describedby': descriptionId,
    oninput: onInput ? (event) => onInput(event.target.value, event) : null,
    onkeydown: onEnter
      ? (event) => {
          if (event.key === 'Enter') {
            event.preventDefault();
            onEnter(event.target.value);
          }
        }
      : null,
  });
}

export function searchInput({ id, placeholder, onInput }) {
  return h('div', { class: 'search' }, [
    icon('magnifying-glass'),
    h('input', {
      id,
      type: 'text',
      placeholder,
      autocomplete: 'off',
      spellcheck: 'false',
      oninput: (event) => onInput(event.target.value),
    }),
  ]);
}

export function checkbox({ id, checked, label, onChange, hint }) {
  const input = h('input', {
    id,
    type: 'checkbox',
    checked: checked ? true : null,
    onchange: (event) => onChange(event.target.checked),
  });
  return h('label', { class: 'check', for: id }, [
    input,
    h('span', { class: 'check__box' }, icon('check')),
    h('span', { class: 'check__text' }, [
      h('span', { text: label }),
      hint ? h('span', { class: 'caption', text: hint }) : null,
    ]),
  ]);
}

export function segmented({ items, value, onChange, ariaLabel }) {
  return h(
    'div',
    { class: 'segmented', role: 'group', 'aria-label': ariaLabel },
    items.map((item) =>
      h('button', {
        type: 'button',
        class: 'segmented__item',
        'aria-pressed': String(item.value === value),
        onclick: () => onChange(item.value),
        text: item.label,
      })
    )
  );
}

export function chip({ label, icon: iconName, pressed, onClick }) {
  return h(
    'button',
    {
      type: 'button',
      class: 'chip',
      'aria-pressed': pressed === undefined ? null : String(Boolean(pressed)),
      onclick: onClick,
    },
    [iconName ? icon(iconName) : null, h('span', { text: label })]
  );
}

export function badge({ label, tone = '' }) {
  return h('span', { class: `badge${tone ? ` badge--${tone}` : ''}`, text: label });
}

/* -------------------------------------------------------------- 列表 */

export function option({ id, icon: iconName, title, meta, tail, selected, onClick, role = 'option' }) {
  return h(
    'button',
    {
      id,
      type: 'button',
      class: 'option',
      role,
      'aria-selected': String(Boolean(selected)),
      onclick: onClick,
    },
    [
      iconName ? h('span', { class: 'option__icon' }, icon(iconName)) : null,
      h('span', { class: 'option__body' }, [
        h('span', { class: 'option__title', text: title }),
        meta ? h('span', { class: 'option__meta', text: meta }) : null,
      ]),
      tail ? h('span', { class: 'option__tail' }, tail) : null,
    ]
  );
}

export function listBox(...children) {
  return h('div', { class: 'list', role: 'listbox' }, ...children);
}

export function kv(pairs) {
  return h(
    'div',
    { class: 'kv' },
    pairs.flatMap(([key, value]) => [
      h('span', { class: 'kv__k', text: key }),
      h('span', { class: 'kv__v', text: value }),
    ])
  );
}

export function emptyState({ icon: iconName = 'info', text, action }) {
  return h('div', { class: 'empty', 'data-anim': '' }, [icon(iconName), h('p', { text }), action || null]);
}

export function callout({ tone = 'info', icon: iconName = 'info', text, extra, id }) {
  // `data-anim`：警告条要和同一页的其他块**一起**展开，不许抢在它们前面出现
  return h('div', { id, class: `callout callout--${tone}`, 'data-anim': '' }, [
    icon(iconName),
    h('div', { class: 'stack' }, [h('span', { text }), extra || null]),
  ]);
}

/* -------------------------------------------------------------- 进度 */

export function meter({ percent = 0, indeterminate = false, id }) {
  return h('div', { id, class: `meter${indeterminate ? ' meter--indeterminate' : ''}`, role: 'progressbar' }, [
    h('span', { class: 'meter__fill', style: indeterminate ? {} : { width: `${percent}%` } }),
  ]);
}

export function rings({ percent = 0, label, value, id }) {
  // 纯 CSS 圆环（conic-gradient）：不用 SVG —— SVG 元素的 className 赋值与 defs 渐变
  // 在 h() 这套属性写入里都是额外的坑，而这里只需要「一圈进度」而已。
  return h('div', { id, class: 'rings', style: { '--p': String(Math.max(0, Math.min(100, percent))) } }, [
    h('div', { class: 'rings__track' }),
    h('div', { class: 'rings__label' }, [
      h('span', { class: 'rings__value', text: value ?? `${Math.round(percent)}%` }),
      label ? h('span', { class: 'caption', text: label }) : null,
    ]),
  ]);
}

export function phaseList(phases) {
  return h(
    'div',
    { class: 'phase-list' },
    phases.map((phase) =>
      h('div', { class: 'phase', dataset: { state: phase.state }, id: phase.id }, [
        h('span', { class: 'phase__mark' }, icon(phase.state === 'done' ? 'check' : 'caret-right')),
        h('span', { text: phase.label }),
      ])
    )
  );
}

/* -------------------------------------------------------------- 步骤轨道 */

export function stepsRail({ steps, index, onJump }) {
  const items = steps.map((step, i) => {
    const state = i < index ? 'done' : i === index ? 'current' : 'todo';
    return h(
      'div',
      { class: 'step', dataset: { state, step: step.id }, id: `rail-${step.id}` },
      [
        h('span', { class: 'step__dot' }, state === 'done' ? icon('check') : String(i + 1)),
        h('span', { class: 'step__label', text: step.label }),
      ]
    );
  });
  return h('nav', { class: 'steps', id: 'steps-rail', 'aria-label': 'steps' }, [
    h('div', { class: 'steps__head' }, [
      h('span', { class: 'steps__progress', id: 'rail-progress' }),
    ]),
    h('div', { class: 'steps__body' }, items),
  ]);
}

/* -------------------------------------------------------------- 对话框 */

export function dialogNode({ title, body, actions, labelledBy = 'dialog-title' }) {
  return h('div', { class: 'dialog', role: 'dialog', 'aria-modal': 'true', 'aria-labelledby': labelledBy }, [
    h('div', { class: 'dialog__body' }, [
      h('h2', { class: 'dialog__title', id: labelledBy, text: title }),
      ...body,
      h('div', { class: 'dialog__actions' }, actions),
    ]),
  ]);
}

export function snackbarNode(text) {
  return h('div', { class: 'snackbar', role: 'status' }, [icon('info'), h('span', { text })]);
}
