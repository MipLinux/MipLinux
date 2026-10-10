/**
 * 设计 token：品牌色板（palette.css ↔ color.json）与设计 token（tokens.css）的静态检查。
 *
 * 三方里的第三方（tech/10 附录 A.1 的文档表）由 `tools/check-tokens.py` 比，
 * 这里只保证「生成物没被手改」与「设计 token 该有的都有」。
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const here = path.dirname(fileURLToPath(import.meta.url));
const APP = path.join(here, '..');
const CSS = path.join(APP, 'renderer', 'css');
const read = (rel) => readFile(path.join(APP, rel), 'utf8');

function themeBlock(css, theme) {
  const match = new RegExp(`\\[data-theme="${theme}"\\]\\s*\\{([\\s\\S]*?)\\}`).exec(css);
  assert.ok(match, `palette.css 里没有 [data-theme="${theme}"]`);
  const vars = {};
  for (const line of match[1].split('\n')) {
    const hit = /--md-([\w-]+):\s*(#[0-9a-fA-F]{6})\s*;/.exec(line);
    if (hit) vars[hit[1]] = hit[2].toLowerCase();
  }
  return vars;
}

test('palette.css 的 35 个角色 × 2 模式与 color.json 逐项相等', async () => {
  const snapshot = JSON.parse(await read('design/color.json'));
  const css = await read('renderer/css/palette.css');
  for (const theme of ['dark', 'light']) {
    const vars = themeBlock(css, theme);
    assert.equal(Object.keys(vars).length, 35, `${theme} 的角色数不是 35`);
    for (const [role, value] of Object.entries(snapshot[theme])) {
      assert.equal(vars[role], value.toLowerCase(), `${theme}.${role} 与 color.json 不一致`);
    }
  }
});

test('palette.css 顶部写明它是生成物', async () => {
  const css = await read('renderer/css/palette.css');
  assert.match(css.split('\n')[0], /gen-tokens\.py/);
  assert.match(css, /不要手改/);
});

test('tokens.css 定义了双主题的设计 token 与四档动效', async () => {
  const css = await read('renderer/css/tokens.css');
  const required = [
    '--bg',
    '--surface',
    '--surface-solid',
    '--hairline',
    '--text',
    '--text-muted',
    '--accent',
    '--on-accent',
    '--danger',
    '--aurora-1',
    '--shadow-2',
    '--focus-ring',
  ];
  for (const theme of ['dark', 'light']) {
    const block = new RegExp(`\\[data-theme='${theme}'\\]\\s*\\{([\\s\\S]*?)\\}`).exec(css);
    assert.ok(block, `tokens.css 缺 [data-theme='${theme}']`);
    for (const name of required) {
      assert.ok(block[1].includes(`${name}:`), `${theme} 缺 ${name}`);
    }
  }
  for (const dur of ['--dur-fast', '--dur-base', '--dur-slow', '--dur-page']) {
    assert.ok(css.includes(dur), `缺时长 token ${dur}`);
  }
  assert.match(css, /prefers-reduced-motion/, '缺动效降级（reduced-motion）');
});

test('字号与圆角只用规定的那几档（防止页面里偷偷加新值）', async () => {
  const css = await read('renderer/css/tokens.css');
  const radii = [...css.matchAll(/--r-([\w-]+):\s*([^;]+);/g)].map((m) => m[2].trim());
  assert.deepEqual(radii.sort(), ['18px', '24px', '26px', '999px', '14px'].sort());
  const scale = /--ui-scale:\s*1;/.test(css);
  assert.ok(scale, '缺 --ui-scale 默认值');
});

test('logo 资产在位（512 / 128 / 64）且没有把 1 MB 原图提交进来', async () => {
  for (const name of ['logo-512.png', 'logo-128.png', 'logo-64.png', 'README.md']) {
    const stats = await import('node:fs/promises').then((fs) =>
      fs.stat(path.join(APP, 'renderer', 'assets', 'logo', name))
    );
    assert.ok(stats.isFile(), `缺 ${name}`);
    if (name.endsWith('.png')) assert.ok(stats.size < 400 * 1024, `${name} 太大了（${stats.size} B）`);
  }
});
