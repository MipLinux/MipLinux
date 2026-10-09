/**
 * 时区显示名：等价簇去重、无名回退、按偏移拼装 —— 三条已定口径的可执行版本。
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

import { canonicalId, displayName, formatZone, dedupeZones, matchesZone } from '../renderer/js/tz-names.js';
import { I18n } from '../renderer/js/i18n.js';

const here = path.dirname(fileURLToPath(import.meta.url));
const I18N_DIR = path.join(here, '..', 'renderer', 'i18n');

/** 造一个不联网的 I18n：直接把 JSON 灌进去（load() 走 fetch，Node 里没有页面 origin）。 */
async function fakeI18n(lang = 'zh_CN') {
  const i18n = new I18n(lang);
  for (const code of ['zh_CN', 'en_US']) {
    i18n.tables[code] = JSON.parse(await readFile(path.join(I18N_DIR, `${code}.json`), 'utf8'));
  }
  return i18n;
}

test('港 / 澳 / 台北收敛到 Asia/Shanghai', () => {
  assert.equal(canonicalId('Asia/Hong_Kong'), 'Asia/Shanghai');
  assert.equal(canonicalId('Asia/Macau'), 'Asia/Shanghai');
  assert.equal(canonicalId('Asia/Taipei'), 'Asia/Shanghai');
  assert.equal(canonicalId('Asia/Tokyo'), 'Asia/Tokyo');
});

test('有名时区给显示名 + 偏移；无名时区照实给 IANA id，绝不硬造名字', async () => {
  const t = await fakeI18n('zh_CN');
  assert.equal(formatZone({ id: 'Asia/Tokyo', offset: '+09:00' }, t), '日本标准时间（UTC+09:00）');
  // Kathmandu 故意不在名表里：显示 tzdata 自己的标识符。
  // 不编一个名字（那是我们要长期背的合规产物），也不像更早那样只剩「UTC+05:45」——
  // 真名单有 312 条、其中 278 条没名字，只留偏移会让它们塌成二十来行一模一样的字。
  assert.equal(displayName('Asia/Kathmandu', t), null);
  assert.equal(formatZone({ id: 'Asia/Kathmandu', offset: '+05:45' }, t), 'Asia/Kathmandu（UTC+05:45）');
});

test('同偏移的两条无名时区不许并成一条（偏移不是时区）', async () => {
  const t = await fakeI18n('zh_CN');
  const zones = [
    { id: 'Europe/Amsterdam', offset: '+01:00' },
    { id: 'Africa/Lagos', offset: '+01:00' },
  ];
  const rows = dedupeZones(zones, t);
  assert.equal(rows.length, 2, '它们现在同偏移，夏天却不是一个时区');
  assert.deepEqual(rows.map((row) => row.canonical), ['Europe/Amsterdam', 'Africa/Lagos']);
});

test('英文模式下名字跟着换', async () => {
  const t = await fakeI18n('en_US');
  assert.equal(formatZone({ id: 'Asia/Tokyo', offset: '+09:00' }, t), 'Japan Standard Time (UTC+09:00)');
  t.setLanguage('zh_CN');
  assert.equal(formatZone({ id: 'Asia/Tokyo', offset: '+09:00' }, t), '日本标准时间（UTC+09:00）');
});

test('去重：四条中国时区只出一行，且代表是规范 id', async () => {
  const t = await fakeI18n('zh_CN');
  const zones = [
    { id: 'Asia/Shanghai', offset: '+08:00' },
    { id: 'Asia/Hong_Kong', offset: '+08:00' },
    { id: 'Asia/Macau', offset: '+08:00' },
    { id: 'Asia/Taipei', offset: '+08:00' },
    { id: 'Asia/Kathmandu', offset: '+05:45' },
    { id: 'Asia/Tokyo', offset: '+09:00' },
  ];
  const deduped = dedupeZones(zones, t);
  assert.equal(deduped.length, 3, `去重后应为 3 条（上海簇 + 加德满都 + 东京），实际 ${deduped.length}`);
  assert.equal(deduped[0].canonical, 'Asia/Shanghai');
  assert.equal(deduped[0].display, '中国标准时间（UTC+08:00）');
});

test('搜索：显示名 / IANA id / 偏移都能命中', async () => {
  const t = await fakeI18n('zh_CN');
  const tokyo = { id: 'Asia/Tokyo', offset: '+09:00' };
  assert.ok(matchesZone(tokyo, '日本', t));
  assert.ok(matchesZone(tokyo, 'tokyo', t));
  assert.ok(matchesZone(tokyo, '+09', t));
  assert.ok(!matchesZone(tokyo, '柏林', t));
});
