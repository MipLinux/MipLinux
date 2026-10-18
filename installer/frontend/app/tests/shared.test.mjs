/**
 * 名单页的排序规则（`pages/shared.js` 的 `withDefaultFirst`）与它读的那份默认值。
 *
 * 钉住的是维护者 2026-10-05 那条口径：
 *   - **默认值**那一项排第一行（一眼看到「不选会得到什么」）；
 *   - **选中项不参与排序** —— 选中一置顶，点一条列表就在手指底下重排一次，
 *     紧接着的第二次点击会落到刚挪上来的那一行上。
 *
 * 顺带钉住替身名单的形状：键盘与语言两份替身**不**把默认值放在开头（真实出口也不放：
 * `localectl` 按名字排、`SUPPORTED` 按 locale 名排），替身要是先摆好了，
 * 探针里那条「默认项在第一行」就成了在验替身、不是在验界面。
 * 时区是例外：它的名单按附 A 顺序（D19），默认项本来就在首行。
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

import { withDefaultFirst } from '../renderer/js/pages/shared.js';
import { DEFAULTS, Setup } from '../renderer/js/setup.js';
import { KEYMAPS, LOCALES, TIMEZONES } from '../renderer/js/mock.js';

const APP = path.join(path.dirname(fileURLToPath(import.meta.url)), '..');
const ZONE_TABLE = path.join(APP, '..', '..', 'backend', 'mipl_installer', 'data', 'timezones.txt');

const values = (items) => items.map((item) => item.value);

test('替身的时区名单与后端随包的表逐条同序（D19）', async () => {
  // 替身是探针与单测唯一见得到的「名单」；它要是和后端那份漂开，
  // 探针就在验一个真后端不会给出的界面 —— 而且没有任何东西会红。
  const table = (await readFile(ZONE_TABLE, 'utf8'))
    .split('\n')
    .map((line) => line.split('#', 1)[0].trim())
    .filter(Boolean);
  assert.ok(table.length > 0, `随包的表是空的：${ZONE_TABLE}`);
  assert.deepEqual(TIMEZONES.map((zone) => zone.id), table);
});

test('默认项提到第一行，其余保持后端给的顺序', () => {
  const items = [{ value: 'a' }, { value: 'b' }, { value: 'c' }, { value: 'd' }];
  assert.deepEqual(values(withDefaultFirst(items, 'c')), ['c', 'a', 'b', 'd']);
});

test('顺序只由「默认值」决定 —— 选中谁都不重排（选中项不参与排序）', () => {
  const items = [{ value: 'a' }, { value: 'b' }, { value: 'c' }];
  const once = values(withDefaultFirst(items, 'c'));
  // 选完 c 之后再画一次：还是同一个顺序（函数签名里根本没有 selected，这是有意的）
  assert.deepEqual(values(withDefaultFirst(items, 'c')), once);
  // 选中的是 b 也一样：置顶的那个永远是默认值
  assert.deepEqual(values(withDefaultFirst(items, 'c')), ['c', 'a', 'b']);
});

test('不动传进来的数组（页面每次重画都拿同一份 items）', () => {
  const items = [{ value: 'a' }, { value: 'b' }];
  withDefaultFirst(items, 'b');
  assert.deepEqual(values(items), ['a', 'b']);
});

test('默认值本来就在第一行 / 不在名单里 / 是空值 —— 都原样返回', () => {
  const items = [{ value: 'a' }, { value: 'b' }];
  assert.equal(withDefaultFirst(items, 'a'), items);
  assert.equal(withDefaultFirst(items, 'zzz'), items);
  assert.equal(withDefaultFirst(items, ''), items);
});

test('开工时落进 `data` 的选择就是 DEFAULTS —— 第一行那条正是「不选会得到的值」', () => {
  const setup = new Setup();
  assert.equal(setup.data.locale, DEFAULTS.locale);
  assert.equal(setup.data.keymap, DEFAULTS.keymap);
  assert.equal(setup.data.timezone, DEFAULTS.timezone);
});

test('三份名单各过一遍之后，默认项都在第一行（页面就是这么调的）', () => {
  const first = (items, defaultValue) =>
    withDefaultFirst(items.map((item) => ({ value: item.id })), defaultValue)[0].value;
  assert.equal(first(KEYMAPS, DEFAULTS.keymap), DEFAULTS.keymap);
  assert.equal(first(LOCALES, DEFAULTS.locale), DEFAULTS.locale);
  assert.equal(first(TIMEZONES, DEFAULTS.timezone), DEFAULTS.timezone);
});

test('替身名单里默认值都不在第一行（否则探针那条断言是在验替身）', () => {
  // 键盘与语言：真实出口按名字排（`localectl` / `SUPPORTED`），默认值确实不在开头，
  // 所以「置顶」这件事在它们身上是**能被验出来的**（探针拿它们当判据）。
  assert.notEqual(KEYMAPS[0].id, DEFAULTS.keymap);
  assert.notEqual(LOCALES[0].id, DEFAULTS.locale);
  // 时区是**例外**：D19 的名单按 tech/09 附 A 的顺序（亚洲在前），`Asia/Shanghai` 本来就在首行。
  // 这条断言因此只对前两份名单成立 —— 别把它推广成「三份都不在首行」，
  // 那要么逼替身偏离真出口的顺序，要么让探针去验一个真后端不会给出的排列。
  assert.equal(TIMEZONES[0].id, DEFAULTS.timezone);
  // 而且默认值确实在名单里 —— 不在的话「置顶」根本无从谈起
  assert.ok(KEYMAPS.some((item) => item.id === DEFAULTS.keymap));
  assert.ok(LOCALES.some((item) => item.id === DEFAULTS.locale));
  assert.ok(TIMEZONES.some((item) => item.id === DEFAULTS.timezone));
});
