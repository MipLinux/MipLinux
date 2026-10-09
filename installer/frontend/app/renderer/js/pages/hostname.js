/**
 * 高级 · 主机名页
 *
 * 默认值 = 用户名（技术审稿待确认 4）。
 *
 * **规则不在这里，也不在 `setup.js` 里** —— 它只有一处：后端的
 * `options.validate_hostname()`（RFC 1123，见 Issue #97）。这一页只做两件事：
 * 把用户敲的值送去问一次，把后端的话落成 `hostnameOk`。
 *
 * 为什么要送出去问而不是本地校验：本地那份正则**已经是第二份实现**，
 * 而两份规则不一致的表现是「界面放行、动盘之后被后端拒」——
 * 顺序恰好是最坏的那个（盘已经擦了）。多一次往返换掉这个风险是划算的。
 *
 * 敲一个字问一次会把后端打爆（每次都是一次 `python3` 启动），所以按下述节奏问：
 * 停顿 300ms 之后问一次，且**同一个值只问一次**（`Setup.set` 同值不 emit，天然去重）。
 */

import { h } from '../dom.js';
import { pageHead, panel, field, textInput } from '../components.js';

/** 每个页面模块一份定时器：页面被换掉时 `onLeave` 收掉，不留一个「回来打一枪」的钩子。 */
let debounce = null;
let lastAsked = null;

function ask(ctx, value) {
  if (debounce) clearTimeout(debounce);
  if (!value) {
    ctx.setup.data.hostnameOk = null;
    return;
  }
  if (value === lastAsked) return;
  debounce = setTimeout(async () => {
    lastAsked = value;
    const verdict = await ctx.backend.checkHostname(value);
    // 回来的时候可能已经不是这一页、或值又变了：只把**当前值**的结论写回去
    if (ctx.setup.data.hostname !== value) return;
    ctx.setup.data.hostnameOk = verdict.ok;
    ctx.refresh();
  }, 300);
}

export default {
  id: 'hostname',

  render(ctx) {
    const t = ctx.t;
    const { setup } = ctx;

    // 第一次进这一页时把默认值落成用户名（用户没改过就跟着走）
    if (!setup.data.hostname && setup.data.user) {
      setup.data.hostname = setup.data.user;
    }
    ask(ctx, setup.data.hostname);

    const error = setup.hostnameError;

    return h('div', { class: 'stack' }, [
      pageHead({ title: t('hostname.title'), desc: t('hostname.desc') }),
      panel({ narrow: true }, [
        field({
          controlId: 'hostname-input',
          label: t('hostname.title'),
          hint: t('hostname.default', setup.data.user || '—'),
          error: error ? t(error) : '',
          control: textInput({
            id: 'hostname-input',
            value: setup.data.hostname,
            mono: true,
            invalid: Boolean(error),
            onInput: (value) => {
              setup.data.hostnameTouched = true;
              setup.set('hostname', value.trim());
              ask(ctx, setup.data.hostname);
              ctx.refresh();
            },
          }),
        }),
      ]),
    ]);
  },

  isComplete(ctx) {
    const { setup } = ctx;
    return Boolean(setup.data.hostname) && !setup.hostnameError;
  },

  onLeave() {
    if (debounce) clearTimeout(debounce);
    debounce = null;
    // 把「问过一次」也清掉：留着的话，第二次进这一页时同一个值**不会再问**，
    // 而 `setup.set()` 那条路径已经把上一次的结论作废了（`hostnameOk = null`）——
    // 于是界面既不报错也没验过，看起来像「校验被跳过了」。
    lastAsked = null;
  },
};
