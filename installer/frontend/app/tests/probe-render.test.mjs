/**
 * probe-render.test.mjs —— probe-render.js 驱动层与完成状态校验单测
 *
 * 断言：
 *   1. --help / --clean 返回码正常；
 *   2. Electron 提前以 0 退出时明确报非 0，且打印「最后跑到哪」（Issue #179）；
 *   3. 缺少截图产物时明确拦截（非 0）；
 *   4. 跑完且有产物时正常返回 0；
 *   5. 失败项存在时透传非 0 退出码。
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { mkdtemp, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const APP = path.join(here, '..');
const PROBE_RENDER = path.join(APP, 'tools', 'probe-render.js');

function runProbe(args = [], env = {}) {
  return new Promise((resolve) => {
    const child = spawn(process.execPath, [PROBE_RENDER, ...args], {
      env: { ...process.env, ...env },
    });
    let stdout = '';
    let stderr = '';
    child.stdout.on('data', (d) => {
      stdout += d.toString('utf8');
    });
    child.stderr.on('data', (d) => {
      stderr += d.toString('utf8');
    });
    child.on('close', (code, signal) => {
      resolve({ code, signal, stdout, stderr });
    });
  });
}

test('probe-render.js --help 输出用法且返回 0', async () => {
  const res = await runProbe(['--help']);
  assert.equal(res.code, 0);
  assert.match(res.stdout, /node tools\/probe-render\.js/);
});

test('probe-render.js --clean 安全清理命令返回 0', async () => {
  const res = await runProbe(['--clean']);
  assert.equal(res.code, 0);
});

test('Electron 立即以 0 退出且无输出时，driver 明确报非 0 且指出无任何输出（Issue #179）', async () => {
  const outDir = await mkdtemp(path.join(tmpdir(), 'probe-test-out-'));
  try {
    const res = await runProbe([], {
      MIPL_ELECTRON_BIN: '/bin/true',
      MIPL_PROBE_OUT: outDir,
    });
    assert.equal(res.code, 1);
    assert.match(res.stderr, /探针未完成就提前退出（退出码 0，未见「✅ 探针全部通过」）/);
    assert.match(res.stderr, /最后进展：（无任何输出）/);
  } finally {
    await rm(outDir, { recursive: true, force: true });
  }
});

test('Electron 中途退出时，driver 报非 0 并打印「最后跑到哪」（Issue #179）', async () => {
  const tmp = await mkdtemp(path.join(tmpdir(), 'probe-fake-'));
  const fakeBin = path.join(tmp, 'fake-electron.sh');
  try {
    await writeFile(
      fakeBin,
      '#!/bin/sh\necho "  ✅ 普通流程渲染 welcome"\necho "  ✅ 普通流程渲染 confirm"\nexit 0\n',
      { mode: 0o755 }
    );
    const res = await runProbe([], {
      MIPL_ELECTRON_BIN: fakeBin,
      MIPL_PROBE_OUT: tmp,
    });
    assert.equal(res.code, 1);
    assert.match(res.stderr, /探针未完成就提前退出（退出码 0，未见「✅ 探针全部通过」）/);
    assert.match(res.stderr, /最后进展：✅ 普通流程渲染 confirm/);
  } finally {
    await rm(tmp, { recursive: true, force: true });
  }
});

test('带有通过标记但未生成任何截图产物时，driver 拒绝并报非 0', async () => {
  const tmp = await mkdtemp(path.join(tmpdir(), 'probe-fake-'));
  const fakeBin = path.join(tmp, 'fake-electron.sh');
  try {
    await writeFile(
      fakeBin,
      '#!/bin/sh\necho "✅ 探针全部通过（离屏旁证；cage / 真 ISO 仍未实测）"\nexit 0\n',
      { mode: 0o755 }
    );
    const res = await runProbe([], {
      MIPL_ELECTRON_BIN: fakeBin,
      MIPL_PROBE_OUT: tmp,
    });
    assert.equal(res.code, 1);
    assert.match(res.stderr, /探针未生成任何截图产物（未见有效截图）/);
  } finally {
    await rm(tmp, { recursive: true, force: true });
  }
});

test('通过标记与有效截图产物齐全时，driver 正常返回 0', async () => {
  const tmp = await mkdtemp(path.join(tmpdir(), 'probe-fake-'));
  const fakeBin = path.join(tmp, 'fake-electron.sh');
  try {
    await writeFile(
      fakeBin,
      '#!/bin/sh\ntouch "$MIPL_PROBE_OUT/shot.png"\necho "✅ 探针全部通过（离屏旁证；cage / 真 ISO 仍未实测）"\nexit 0\n',
      { mode: 0o755 }
    );
    const res = await runProbe([], {
      MIPL_ELECTRON_BIN: fakeBin,
      MIPL_PROBE_OUT: tmp,
    });
    assert.equal(res.code, 0);
  } finally {
    await rm(tmp, { recursive: true, force: true });
  }
});

test('探针明确断言失败时，driver 透传退出码且不报提前退出', async () => {
  const tmp = await mkdtemp(path.join(tmpdir(), 'probe-fake-'));
  const fakeBin = path.join(tmp, 'fake-electron.sh');
  try {
    await writeFile(
      fakeBin,
      '#!/bin/sh\necho "❌ 探针失败 1 项："\necho "  - 界面没有暴露探针接口"\nexit 1\n',
      { mode: 0o755 }
    );
    const res = await runProbe([], {
      MIPL_ELECTRON_BIN: fakeBin,
      MIPL_PROBE_OUT: tmp,
    });
    assert.equal(res.code, 1);
    assert.doesNotMatch(res.stderr, /探针未完成就提前退出/);
  } finally {
    await rm(tmp, { recursive: true, force: true });
  }
});
