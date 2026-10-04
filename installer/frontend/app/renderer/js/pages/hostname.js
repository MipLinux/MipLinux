/**
 * 高级 · 主机名页
 *
 * 默认值 = 用户名（技术审稿待确认 4）；规则见 `hostname.err.format`
 * （字母数字与连字符、不以连字符开头/结尾、最长 63）。
 */

import { h } from '../dom.js';
import { pageHead, panel, field, textInput } from '../components.js';

export default {
  id: 'hostname',

  render(ctx) {
    const t = ctx.t;
    const { setup } = ctx;

    // 第一次进这一页时把默认值落成用户名（用户没改过就跟着走）
    if (!setup.data.hostname && setup.data.user) {
      setup.data.hostname = setup.data.user;
    }

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
};
