/**
 * 向导状态机与三条校验规则（用户名按后端规则、密码 6 位只是界面防呆、
 * 主机名由后端判定 —— 状态机只缓存它的结论，见 Issue #97）。
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';

import { Setup, PASSWORD_MIN } from '../renderer/js/setup.js';

test('初始状态：普通流程、第 0 页、主要选择都有默认值', () => {
  const setup = new Setup();
  assert.equal(setup.advanced, false);
  assert.equal(setup.stepId, 'welcome');
  assert.equal(setup.stepCount, 8);
  assert.equal(setup.data.locale, 'zh_CN.UTF-8');
  assert.equal(setup.data.keymap, 'us');
  assert.equal(setup.data.timezone, 'Asia/Shanghai');
});

test('切到高级：步骤变 12，且停在同一个页面 id 上', () => {
  const setup = new Setup();
  setup.go(3); // 普通流程的第 4 步是 account
  assert.equal(setup.stepId, 'account');
  setup.setAdvanced(true);
  assert.equal(setup.stepCount, 12);
  assert.equal(setup.stepId, 'account', '切档后不该跳回首页');
  setup.setAdvanced(false);
  assert.equal(setup.stepId, 'account');
});

test('用户名规则按后端：小写字母开头，后跟小写字母/数字/下划线/连字符', () => {
  const setup = new Setup();
  setup.set('user', 'mipl');
  assert.equal(setup.userError, null);
  setup.set('user', 'mipl_user-01');
  assert.equal(setup.userError, null);
  for (const bad of ['Mipl', '1user', '_user', 'user.name', '用户', 'user name']) {
    setup.set('user', bad);
    assert.equal(setup.userError, 'account.err.userFormat', `${bad} 应该被拒`);
  }
});

test('密码：少于 6 位报 pwShort（界面规则），确认不一致报 pwMismatch', () => {
  const setup = new Setup();
  setup.set('password', '12345');
  assert.equal(setup.passwordError, 'account.err.pwShort');
  setup.set('password', '123456');
  assert.equal(setup.passwordError, null);
  assert.equal(PASSWORD_MIN, 6);
  assert.equal(setup.confirmMismatch('123456'), null);
  assert.equal(setup.confirmMismatch('654321'), 'account.err.pwMismatch');
});

test('普通模式下主机名跟着用户名走；用户改过之后不再跟随', () => {
  const setup = new Setup();
  setup.set('user', 'mipluser');
  assert.equal(setup.data.hostname, 'mipluser');
  setup.data.hostnameTouched = true;
  setup.set('hostname', 'my-host');
  setup.set('user', 'otheruser');
  assert.equal(setup.data.hostname, 'my-host');
});

test('主机名：规则在后端，状态机只负责「把后端的话翻成文案键」', () => {
  const setup = new Setup();

  // 还没问到（或根本问不到）：**不算错**。把它当错会让人卡在一台起不了后端的机器上
  setup.set('hostname', 'mipl-pc');
  assert.equal(setup.data.hostnameOk, null);
  assert.equal(setup.hostnameError, null);

  // 后端说不合规 → 报错
  setup.data.hostnameOk = false;
  assert.equal(setup.hostnameError, 'hostname.err.format');

  // 后端说合规 → 放行
  setup.data.hostnameOk = true;
  assert.equal(setup.hostnameError, null);

  // 空值不报错（「必填」由页面用 isComplete 表达，不是格式错）
  setup.set('hostname', '');
  assert.equal(setup.hostnameError, null);
});

test('主机名一改，上一次的后端判定就作废（否则会拿旧结论说新值）', () => {
  const setup = new Setup();
  setup.set('hostname', 'mipl-pc');
  setup.data.hostnameOk = true;
  setup.set('hostname', 'mipl-pc-2');
  assert.equal(setup.data.hostnameOk, null, '改过之后必须是「还没问到」');

  // 普通模式下主机名跟着用户名走，那条路径同样要作废判定
  setup.data.hostnameOk = true;
  setup.set('user', 'someone');
  assert.equal(setup.data.hostname, 'someone');
  assert.equal(setup.data.hostnameOk, null);
});

test('擦除确认：必须与所选磁盘逐字一致（大小写不敏感）', () => {
  const setup = new Setup();
  setup.set('disk', '/dev/vda');
  setup.set('confirmText', '');
  assert.equal(setup.confirmTextMatches(), false);
  setup.set('confirmText', '/dev/vdb');
  assert.equal(setup.confirmTextMatches(), false);
  setup.set('confirmText', '/dev/vda');
  assert.equal(setup.confirmTextMatches(), true);
});

test('订阅者能收到状态变化', () => {
  const setup = new Setup();
  let calls = 0;
  const off = setup.subscribe(() => {
    calls += 1;
  });
  setup.set('user', 'mipluser');
  assert.equal(calls, 1);
  setup.set('user', 'mipluser'); // 同值不通知
  assert.equal(calls, 1);
  off();
  setup.set('user', 'otheruser');
  assert.equal(calls, 1);
});

test('密码强度只分三档，且不把短密码当强密码', () => {
  assert.equal(Setup.passwordLevel(''), 0);
  assert.equal(Setup.passwordLevel('12345'), 0);
  assert.equal(Setup.passwordLevel('123456'), 1);
  assert.equal(Setup.passwordLevel('1234567890'), 2);
  assert.equal(Setup.passwordLevel('Abcdef1234'), 3);
});
