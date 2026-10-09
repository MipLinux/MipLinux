/**
 * 步骤表 / 页面注册表 / 页面契约的形状 —— 三条最容易漂的地方
 *
 * 跑法：`node --test installer/frontend/app/tests/`
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

import { FLOWS, flowFor, STEP_TITLE_KEY, NO_BACK, shouldRestartRun } from '../renderer/js/steps.js';
import { PAGES } from '../renderer/js/pages/index.js';

const here = path.dirname(fileURLToPath(import.meta.url));
const I18N_DIR = path.join(here, '..', 'renderer', 'i18n');

test('普通 8 步 / 高级 12 步，且高级严格是普通 + 4 个高级页', () => {
  assert.equal(FLOWS.normal.length, 8);
  assert.equal(FLOWS.advanced.length, 12);
  const extra = FLOWS.advanced.filter((id) => !FLOWS.normal.includes(id));
  assert.deepEqual(extra.sort(), ['hostname', 'keymap', 'locale', 'timezone']);
  assert.equal(FLOWS.normal[0], 'welcome');
  assert.equal(FLOWS.normal.at(-1), 'finish');
});

test('flowFor 跟着 advanced 开关走', () => {
  assert.deepEqual(flowFor(false), FLOWS.normal);
  assert.deepEqual(flowFor(true), FLOWS.advanced);
});

test('步骤表里每个 id 都有页面模块，反之亦然', () => {
  const stepIds = new Set([...FLOWS.normal, ...FLOWS.advanced]);
  for (const id of stepIds) {
    assert.ok(PAGES[id], `步骤 ${id} 没有页面模块`);
  }
  for (const id of Object.keys(PAGES)) {
    assert.ok(stepIds.has(id), `页面模块 ${id} 不在任何步骤表里`);
  }
});

test('每个页面模块声明了 id 与 render，且 id 与文件名一致', () => {
  for (const [key, page] of Object.entries(PAGES)) {
    assert.equal(page.id, key, `${key} 的 page.id 不一致`);
    assert.equal(typeof page.render, 'function', `${key} 缺 render`);
  }
});

test('每个步骤都有标题键，且标题键在文案表里存在（两种语言）', async () => {
  const zh = JSON.parse(await readFile(path.join(I18N_DIR, 'zh_CN.json'), 'utf8'));
  const en = JSON.parse(await readFile(path.join(I18N_DIR, 'en_US.json'), 'utf8'));
  const stepIds = new Set([...FLOWS.normal, ...FLOWS.advanced]);
  for (const id of stepIds) {
    const key = STEP_TITLE_KEY[id];
    assert.ok(key, `${id} 缺标题键`);
    assert.ok(zh[key], `zh_CN 缺 ${key}`);
    assert.ok(en[key], `en_US 缺 ${key}`);
  }
});

test('进度页与完成页不许后退', () => {
  assert.ok(NO_BACK.has('progress'));
  assert.ok(NO_BACK.has('finish'));
  assert.ok(!NO_BACK.has('summary'));
});

test('装失败之后不许自己重开一轮（无限重装是个真会写出来的 bug）', () => {
  const failed = { percent: 40, phase: 1, startedAt: 1, done: false, cancelled: false, failed: true };

  // 进度页自己重画（`finish()` 里那句 `ctx.rerender()`，为的是把后端那句话摆出来）：
  // 这一条要是返回 true，就会出现「失败 → 清空状态 → 又 startRun() → 又失败」的死循环
  assert.equal(
    shouldRestartRun(failed, { cameFromProgress: true }),
    false,
    '进度页自己的重画绝不是「重新进入」'
  );

  // 从别的页走过来才算重跑（用户点了返回、又从前面的页面走到这一步）
  assert.equal(shouldRestartRun(failed, { cameFromProgress: false }), true);
  assert.equal(shouldRestartRun({ cancelled: true }, { cameFromProgress: false }), true);
  assert.equal(shouldRestartRun({ done: true }, { cameFromProgress: false }), true);

  // 一轮正在跑的时候，怎么进来都不该清状态
  const running = { percent: 40, phase: 1, startedAt: 1, done: false, cancelled: false, failed: false };
  assert.equal(shouldRestartRun(running, { cameFromProgress: false }), false);
  assert.equal(shouldRestartRun(running, { cameFromProgress: true }), false);
  assert.equal(shouldRestartRun(undefined, {}), false);
});
