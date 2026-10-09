/**
 * 账户页（3）—— 用户名 / 密码 / root 密码
 *
 * 三条已定口径（tech/09 待确认 1–3，别自己改）：
 *   1. 用户名规则按**后端** `validate_user()`：小写字母开头，后跟小写字母/数字/下划线/连字符；
 *   2. 「至少 6 位」**只是界面防呆**（后端不校验长度）；
 *   3. root 密码留空 = 与用户密码相同。
 */

import { h } from '../dom.js';
import { pageHead, panel, field, textInput, divider } from '../components.js';
import { Setup, PASSWORD_MIN } from '../setup.js';

export default {
  id: 'account',

  render(ctx) {
    const t = ctx.t;
    const { setup } = ctx;

    const userError = setup.userError;
    const pwError = setup.passwordError;
    const confirmError = setup.confirmMismatch(setup.data.passwordConfirm || '');
    const level = Setup.passwordLevel(setup.data.password);

    return h('div', { class: 'stack' }, [
      pageHead({ title: t('account.title') }),
      panel({ narrow: true }, [
        h('div', { class: 'form-col' }, [
        field({
          controlId: 'account-user',
          label: t('account.user'),
          hint: t('account.userHint'),
          error: userError ? t(userError) : '',
          control: textInput({
            id: 'account-user',
            value: setup.data.user,
            mono: true,
            invalid: Boolean(userError),
            descriptionId: 'account-user-hint',
            onInput: (value) => {
              setup.set('user', value.trim());
              ctx.refresh();
            },
          }),
        }),
        field({
          controlId: 'account-password',
          label: t('account.password'),
          hint: t('account.passwordHint'),
          error: pwError ? t(pwError) : '',
          control: h('div', {}, [
            textInput({
              id: 'account-password',
              type: 'password',
              value: setup.data.password,
              autocomplete: 'new-password',
              invalid: Boolean(pwError),
              onInput: (value) => {
                setup.set('password', value);
                // 只更新强度条与动作区，不重画整页（否则每敲一个字符就丢焦点）
                const meter = document.getElementById('pw-meter');
                if (meter) meter.dataset.level = String(Setup.passwordLevel(value));
                ctx.refresh();
              },
            }),
            h('div', { class: 'pw-meter', dataset: { level: String(level) }, id: 'pw-meter' }, [
              h('i'),
              h('i'),
              h('i'),
            ]),
          ]),
        }),
        field({
          controlId: 'account-password-confirm',
          label: t('account.passwordConfirm'),
          error: confirmError ? t(confirmError) : '',
          control: textInput({
            id: 'account-password-confirm',
            type: 'password',
            value: setup.data.passwordConfirm || '',
            autocomplete: 'new-password',
            invalid: Boolean(confirmError),
            onInput: (value) => {
              setup.set('passwordConfirm', value);
              ctx.refresh();
            },
          }),
        }),
        divider(),
          field({
            controlId: 'account-root',
            label: t('account.rootPassword'),
            hint: t('account.rootPasswordHint'),
            control: textInput({
              id: 'account-root',
              type: 'password',
              value: setup.data.rootPassword,
              autocomplete: 'new-password',
              onInput: (value) => setup.set('rootPassword', value),
            }),
          }),
        ]),
      ]),
    ]);
  },

  isComplete(ctx) {
    const { setup } = ctx;
    const { user, password, passwordConfirm } = setup.data;
    if (!user || setup.userError) return false;
    if (!password || password.length < PASSWORD_MIN) return false;
    return password === passwordConfirm;
  },
};
