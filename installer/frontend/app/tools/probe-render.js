#!/usr/bin/env node
'use strict';
/**
 * probe-render —— 在真 Electron 里跑离屏探针
 * ==========================================
 *
 *   node installer/frontend/app/tools/probe-render.js
 *   MIPL_ELECTRON_BIN=/path/to/electron node …/probe-render.js
 *   MIPL_PROBE_OUT=/tmp/probe node …/probe-render.js
 *
 * Electron 运行时的找法（按顺序）：
 *   1. 环境变量 `MIPL_ELECTRON_BIN`（宿主机上通常指向解包出来的 `electron44`）；
 *   2. PATH 里的 `electron`（Live / 构建容器里由 profile/packages.x86_64 提供）；
 *   3. `/usr/lib/electron44/electron`（Arch 官方 electron44 包的位置）。
 *
 * 找不到就**明确失败**，不假装通过 —— 「没跑」和「跑过且绿」必须分得清。
 */

const { spawn } = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const APP_DIR = path.resolve(__dirname, '..');

function findElectron() {
  if (process.env.MIPL_ELECTRON_BIN) return process.env.MIPL_ELECTRON_BIN;
  const candidates = ['/usr/bin/electron', '/usr/lib/electron44/electron'];
  for (const candidate of candidates) {
    if (fs.existsSync(candidate)) return candidate;
  }
  return 'electron'; // 交给 PATH；找不到时 spawn 会报 ENOENT，报错信息里带着它
}

function pickOutDir() {
  if (process.env.MIPL_PROBE_OUT) return process.env.MIPL_PROBE_OUT;
  const inRepo = path.resolve(APP_DIR, '..', '..', '..', 'out', 'probe-electron');
  try {
    fs.mkdirSync(inRepo, { recursive: true });
    return inRepo;
  } catch {
    // out/ 在构建机上是 root 属主，普通用户写不进去 —— 退回临时目录并说明
    const fallback = path.join(os.tmpdir(), 'mipl-probe');
    fs.mkdirSync(fallback, { recursive: true });
    console.log(`（out/ 不可写，截图改落 ${fallback}）`);
    return fallback;
  }
}

const electron = findElectron();
const outDir = pickOutDir();

const args = [
  APP_DIR,
  '--theme=light',  // 亮色是主主题：默认就按亮色验
  '--scale=1',
  '--lang=zh_CN',
  // kiosk 里由启动器给这些开关；探针在宿主机上跑，同样要绕开 root/合成器限制。
  // **不要**加 --ozone-platform=headless：那条路上离屏渲染只出 1×1 的空帧（实测），
  // 截不到真画面；离屏窗口本来就不上屏，用宿主合成器（X11/Wayland）反而拿得到帧。
  '--no-sandbox',
  '--disable-dev-shm-usage',
];

console.log(`Electron: ${electron}`);
console.log(`应用目录: ${APP_DIR}`);
console.log(`截图目录: ${outDir}\n`);

const child = spawn(electron, args, {
  cwd: APP_DIR,
  stdio: 'inherit',
  env: { ...process.env, MIPL_PROBE: '1', MIPL_PROBE_OUT: outDir, ELECTRON_DISABLE_SECURITY_WARNINGS: '1' },
});

child.on('error', (error) => {
  console.error(`\n❌ 起不了 Electron（${electron}）：${error.message}`);
  console.error('   宿主机上可以 `MIPL_ELECTRON_BIN=<解包的 electron44> node tools/probe-render.js`。');
  process.exit(2);
});

child.on('exit', (code, signal) => {
  if (signal) {
    console.error(`\n❌ Electron 被信号终止：${signal}`);
    process.exit(2);
  }
  process.exit(code === null ? 2 : code);
});
