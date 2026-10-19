/**
 * probe-render.test.mjs —— probe-render.js 驱动层与完成状态校验单测
 *
 * 断言：
 *   1. --help / --clean 返回码正常；
 *   2. Electron 提前以 0 退出时明确报非 0，且打印「最后跑到哪」（Issue #179）；
 *   3. 缺少截图产物时明确拦截（非 0）；
 *   4. 跑完且有产物时正常返回 0；
 *   5. 失败项存在时透传非 0 退出码；
 *   6. 含有失败标记即便退出码为 0 也拒绝通过；
 *   7. 每次运行隔离截图目录，保留已有 PNG 并防止历史旧图造成假通过。
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { mkdir, mkdtemp, readFile, readdir, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const APP = path.join(here, '..');
const PROBE_RENDER = path.join(APP, 'tools', 'probe-render.js');

async function runProbe(args = [], env = {}) {
  const ownsUserDataDir = !env.MIPL_PROBE_USER_DATA;
  const userDataDir =
    env.MIPL_PROBE_USER_DATA ?? (await mkdtemp(path.join(tmpdir(), 'probe-data-')));
  try {
    return await new Promise((resolve, reject) => {
      const child = spawn(process.execPath, [PROBE_RENDER, ...args], {
        env: { ...process.env, ...env, MIPL_PROBE_USER_DATA: userDataDir },
      });
      let stdout = '';
      let stderr = '';
      child.stdout.on('data', (d) => {
        stdout += d.toString('utf8');
      });
      child.stderr.on('data', (d) => {
        stderr += d.toString('utf8');
      });
      child.on('error', reject);
      child.on('close', (code, signal) => {
        resolve({ code, signal, stdout, stderr });
      });
    });
  } finally {
    if (ownsUserDataDir) {
      await rm(userDataDir, { recursive: true, force: true });
    }
  }
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
      '#!/bin/sh\nprintf \'\\211PNG\\015\\012\\032\\012\' > "$MIPL_PROBE_OUT/shot.png"\necho "✅ 探针全部通过（离屏旁证；cage / 真 ISO 仍未实测）"\nexit 0\n',
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

test('产物为 0 字节文件（touch）时，driver 拒绝并通过且报非 0', async () => {
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
    assert.equal(res.code, 1);
    assert.match(res.stderr, /探针未生成任何截图产物（未见有效截图）/);
  } finally {
    await rm(tmp, { recursive: true, force: true });
  }
});

test('产物缺少 PNG 签名头时，driver 拒绝并通过且报非 0', async () => {
  const tmp = await mkdtemp(path.join(tmpdir(), 'probe-fake-'));
  const fakeBin = path.join(tmp, 'fake-electron.sh');
  try {
    await writeFile(
      fakeBin,
      '#!/bin/sh\necho "not-a-png-file" > "$MIPL_PROBE_OUT/shot.png"\necho "✅ 探针全部通过（离屏旁证；cage / 真 ISO 仍未实测）"\nexit 0\n',
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

test('子进程退出 0 但含有失败标记时，driver 拒绝通过并报非 0', async () => {
  const tmp = await mkdtemp(path.join(tmpdir(), 'probe-fake-'));
  const fakeBin = path.join(tmp, 'fake-electron.sh');
  try {
    await writeFile(
      fakeBin,
      '#!/bin/sh\necho "❌ 探针失败 1 项："\necho "  - 示例断言失败"\nprintf \'\\211PNG\\015\\012\\032\\012\' > "$MIPL_PROBE_OUT/shot.png"\necho "✅ 探针全部通过（离屏旁证；cage / 真 ISO 仍未实测）"\nexit 0\n',
      { mode: 0o755 }
    );
    const res = await runProbe([], {
      MIPL_ELECTRON_BIN: fakeBin,
      MIPL_PROBE_OUT: tmp,
    });
    assert.equal(res.code, 1);
    assert.match(res.stderr, /探针包含失败断言，不能视为通过/);
  } finally {
    await rm(tmp, { recursive: true, force: true });
  }
});

test('每次运行使用独立截图目录并保留已有 PNG，旧图不能使本次运行通过', async () => {
  const tmp = await mkdtemp(path.join(tmpdir(), 'probe-fake-'));
  const fakeBin = path.join(tmp, 'fake-electron.sh');
  try {
    // 现有 PNG 即使签名有效且刚写入，也不能作为本次运行的产物。
    const png = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);
    const existingPng = path.join(tmp, 'old-shot.png');
    const previousRun = path.join(tmp, 'run-previous');
    await mkdir(previousRun);
    await writeFile(existingPng, png);
    await writeFile(path.join(previousRun, 'shot.png'), png);
    // fake 脚本打印通过但不产出任何截图
    await writeFile(
      fakeBin,
      '#!/bin/sh\necho "✅ 探针全部通过（离屏旁证；cage / 真 ISO 仍未实测）"\nexit 0\n',
      { mode: 0o755 }
    );
    for (let i = 0; i < 2; i += 1) {
      const res = await runProbe([], {
        MIPL_ELECTRON_BIN: fakeBin,
        MIPL_PROBE_OUT: tmp,
      });
      assert.equal(res.code, 1);
      assert.match(res.stderr, /探针未生成任何截图产物（未见有效截图）/);
    }
    assert.deepEqual(await readFile(existingPng), png);
    assert.deepEqual(await readFile(path.join(previousRun, 'shot.png')), png);
    const runDirs = (await readdir(tmp)).filter((name) => name.startsWith('run-') && name !== 'run-previous');
    assert.equal(runDirs.length, 2);
    for (const dir of runDirs) {
      assert.deepEqual(await readdir(path.join(tmp, dir)), []);
    }
  } finally {
    await rm(tmp, { recursive: true, force: true });
  }
});
