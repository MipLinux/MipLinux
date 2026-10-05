/**
 * 文案守卫（Node 侧）：
 *   1. 两份 JSON 键集一致、值非空、无审阅排版残留（`**`）；
 *   2. 页面源码里 `t('…')` 引用的每个键都真实存在 —— 这是「页面写错键」的唯一本地防线。
 *
 * （表 ↔ JSON 的逐字比对在 `tools/i18n.py --check`，它会连 §三 与附 A 一起比。）
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile, readdir } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const here = path.dirname(fileURLToPath(import.meta.url));
const APP = path.join(here, '..');
const I18N_DIR = path.join(APP, 'renderer', 'i18n');
const JS_DIR = path.join(APP, 'renderer', 'js');

const load = async (lang) => JSON.parse(await readFile(path.join(I18N_DIR, `${lang}.json`), 'utf8'));

async function jsFiles(dir) {
  const out = [];
  for (const entry of await readdir(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) out.push(...(await jsFiles(full)));
    else if (entry.name.endsWith('.js')) out.push(full);
  }
  return out;
}

test('两份 JSON 键集完全一致，且都没有空值', async () => {
  const zh = await load('zh_CN');
  const en = await load('en_US');
  const zhKeys = Object.keys(zh).sort();
  const enKeys = Object.keys(en).sort();
  assert.deepEqual(zhKeys, enKeys, '两份 JSON 的键不一致');
  assert.ok(zhKeys.length >= 130, `键太少（${zhKeys.length}），文案表是不是没生成全？`);
  for (const key of zhKeys) {
    assert.ok(zh[key].trim().length > 0, `zh_CN.${key} 是空的`);
    assert.ok(en[key].trim().length > 0, `en_US.${key} 是空的`);
  }
});

test('文案里不残留审阅排版（**）', async () => {
  for (const lang of ['zh_CN', 'en_US']) {
    const table = await load(lang);
    for (const [key, value] of Object.entries(table)) {
      assert.ok(!value.includes('**'), `${lang}.${key} 里有 ** ：${value}`);
    }
  }
});

test('34 条时区名齐全（附 A），且中英都有', async () => {
  const zh = await load('zh_CN');
  const en = await load('en_US');
  const zones = Object.keys(zh).filter((key) => key.startsWith('timezone.name.'));
  assert.equal(zones.length, 34, `时区名条数不对：${zones.length}`);
  for (const key of zones) {
    assert.ok(en[key], `en_US 缺 ${key}`);
    assert.notEqual(zh[key], en[key], `${key} 中英相同，像是漏译`);
  }
});

test('页面源码里 t(\'key\') 引用的键都存在', async () => {
  const zh = await load('zh_CN');
  const files = await jsFiles(path.join(JS_DIR, 'pages'));
  files.push(path.join(JS_DIR, 'app.js'));
  let checked = 0;
  for (const file of files) {
    const source = await readFile(file, 'utf8');
    for (const match of source.matchAll(/\bt\(\s*'([a-zA-Z][\w.\-]*)'/g)) {
      const key = match[1];
      checked += 1;
      assert.ok(zh[key], `${path.relative(APP, file)} 引用了不存在的键 ${key}`);
    }
  }
  assert.ok(checked > 50, `只检查到 ${checked} 个键，扫描是不是失效了？`);
});

test('i18n.py 生成器与守卫脚本在位', async () => {
  const script = await readFile(path.join(APP, 'tools', 'i18n.py'), 'utf8');
  assert.ok(script.includes('parse_zone_names'), 'i18n.py 里没有附 A 的解析');
});
