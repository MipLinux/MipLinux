#!/usr/bin/env node
'use strict';
/**
 * probe-render —— 在真 Electron 里跑离屏探针
 * ==========================================
 *
 *   node installer/frontend/app/tools/probe-render.js
 *   node installer/frontend/app/tools/probe-render.js --clean
 *   MIPL_ELECTRON_BIN=/path/to/electron node …/probe-render.js
 *   MIPL_PROBE_OUT=/tmp/probe node …/probe-render.js
 *
 * Electron 运行时的找法（按顺序）：
 *   1. 环境变量 `MIPL_ELECTRON_BIN`（宿主机上通常指向解包出来的 `electron44`）；
 *   2. PATH 里的 `electron`（Live / 构建容器里由 profile/packages.x86_64 提供）；
 *   3. `/usr/lib/electron44/electron` 与 `/usr/lib/electron43/electron`。
 *
 * 找不到就**明确失败**，不假装通过 —— 「没跑」和「跑过且绿」必须分得清。
 *
 * 安全与进程纪律（Issue #177）：
 *   探针必须携带独立的 `--user-data-dir`（默认 /tmp/mipl-probe-data），
 *   使 Chromium 衍生出的所有子进程（GPU、Zygote、Network、Utility）全链条携带该唯一特征，
 *   彻底与宿主机其他 Electron 应用（如 mip-paper）隔离；
 *   清理必须通过本工具 `--clean` 或精准匹配该唯一目录路径，严禁 `pkill -f electron*`。
 */

const { spawn } = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

/**
 * 为探针隔离 Chromium 数据：直接采用 MIPL_PROBE_USER_DATA，否则创建默认临时目录。
 * @returns {string} 用户数据目录路径；环境变量指定的目录不在此创建。
 */
function pickUserDataDir() {
  if (process.env.MIPL_PROBE_USER_DATA) return process.env.MIPL_PROBE_USER_DATA;
  const dir = path.join(os.tmpdir(), 'mipl-probe-data');
  fs.mkdirSync(dir, { recursive: true });
  return dir;
}

const APP_DIR = path.resolve(__dirname, '..');
const userDataDir = pickUserDataDir();
const PID_FILE = path.join(userDataDir, 'mipl-probe.pid');

/**
 * 按命令行特征收集候选探针 PID，排除自身与 mip-paper，忽略不可读的进程。
 * @param {string} [targetUserDataDir=userDataDir] 目标用户数据目录；仅匹配此目录衍生的进程。
 * @returns {number[]} 匹配的 PID；无 /proc 或无法读取时返回空数组。
 */
function findProbeProcesses(targetUserDataDir = userDataDir) {
  const pids = [];
  if (!fs.existsSync('/proc')) return pids;
  try {
    const entries = fs.readdirSync('/proc');
    for (const entry of entries) {
      if (!/^\d+$/.test(entry)) continue;
      const pid = Number(entry);
      if (pid === process.pid || pid === process.ppid || pid <= 1) continue;
      try {
        const cmd = fs.readFileSync(`/proc/${pid}/cmdline`, 'utf8');
        if (cmd.includes('mip-paper')) continue; // 绝对防护：宿主机服务绝不误杀
        const parts = cmd.split('\0').filter(Boolean);
        const isProbe = parts.some((arg) => arg === `--user-data-dir=${targetUserDataDir}`);
        if (isProbe) pids.push(pid);
      } catch {}
    }
  } catch {}
  return pids;
}

/**
 * 合并候选 PID 与 PID 文件记录，删除记录后发送 SIGTERM，最多等待 500ms 再尝试 SIGKILL。
 * @param {Object} [options={}] 清理选项。
 * @param {boolean} [options.verbose=true] 是否打印清理进度。
 * @returns {void}
 */
function cleanStaleProbes({ verbose = true } = {}) {
  const targetPids = new Set(findProbeProcesses(userDataDir));
  if (fs.existsSync(PID_FILE)) {
    try {
      const raw = fs.readFileSync(PID_FILE, 'utf8').trim();
      const saved = /^\d+$/.test(raw) ? Number(raw) : NaN;
      if (Number.isSafeInteger(saved) && saved > 1 && saved !== process.pid && saved !== process.ppid) {
        targetPids.add(saved);
      }
      fs.unlinkSync(PID_FILE);
    } catch {}
  }

  if (targetPids.size === 0) {
    if (verbose) console.log('（无残留探针进程）');
    return;
  }

  if (verbose) console.log(`发现 ${targetPids.size} 个残留探针进程：${[...targetPids].join(', ')}，正在清理...`);
  for (const pid of targetPids) {
    try {
      process.kill(pid, 'SIGTERM');
    } catch {}
  }

  const deadline = Date.now() + 500;
  while (Date.now() < deadline) {
    let alive = false;
    for (const pid of targetPids) {
      try {
        process.kill(pid, 0);
        alive = true;
      } catch {}
    }
    if (!alive) break;
  }

  for (const pid of targetPids) {
    try {
      process.kill(pid, 'SIGKILL');
    } catch {}
  }
  if (verbose) console.log('探针残留清理完成。');
}

if (process.argv.includes('--clean')) {
  cleanStaleProbes({ verbose: true });
  process.exit(0);
}

if (process.argv.includes('--help') || process.argv.includes('-h')) {
  console.log(`用法:
  node tools/probe-render.js           # 运行离屏探针
  node tools/probe-render.js --clean   # 安全清理残留的探针进程
  MIPL_ELECTRON_BIN=<path> node tools/probe-render.js
  MIPL_PROBE_OUT=<path> node tools/probe-render.js
`);
  process.exit(0);
}

/**
 * 优先采用 MIPL_ELECTRON_BIN，其次查找已知安装路径，最后交给 PATH 解析 electron。
 * @returns {string} Electron 可执行文件路径或命令名。
 */
function findElectron() {
  if (process.env.MIPL_ELECTRON_BIN) return process.env.MIPL_ELECTRON_BIN;
  const candidates = ['/usr/bin/electron', '/usr/lib/electron44/electron', '/usr/lib/electron43/electron'];
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

/**
 * 清理指定输出目录中的旧 PNG 截图产物，避免历史产物干扰本次运行判定。
 * @param {string} dir 截图输出目录。
 * @returns {void}
 */
function prepareOutDir(dir) {
  if (!fs.existsSync(dir)) return;
  try {
    for (const file of fs.readdirSync(dir)) {
      if (file.endsWith('.png')) {
        try {
          fs.unlinkSync(path.join(dir, file));
        } catch {}
      }
    }
  } catch {}
}

/**
 * 统计指定输出目录中有效的 PNG 截图产物数量（必须是实际文件且大小大于 0）。
 * @param {string} dir 截图输出目录。
 * @returns {number} 有效的截图文件数量。
 */
function countValidScreenshots(dir) {
  if (!fs.existsSync(dir)) return 0;
  try {
    let valid = 0;
    for (const name of fs.readdirSync(dir)) {
      if (name.endsWith('.png')) {
        try {
          const stat = fs.statSync(path.join(dir, name));
          if (stat.isFile() && stat.size > 0) valid += 1;
        } catch {}
      }
    }
    return valid;
  } catch {
    return 0;
  }
}

// 启动前先静默收敛一次历史残留，防止占用单实例锁
cleanStaleProbes({ verbose: false });

const electron = findElectron();
const outDir = pickOutDir();
prepareOutDir(outDir);

const args = [
  APP_DIR,
  `--user-data-dir=${userDataDir}`,
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
console.log(`数据目录: ${userDataDir}`);
console.log(`截图目录: ${outDir}\n`);

const child = spawn(electron, args, {
  cwd: APP_DIR,
  stdio: ['inherit', 'pipe', 'inherit'],
  env: { ...process.env, MIPL_PROBE: '1', MIPL_PROBE_OUT: outDir, ELECTRON_DISABLE_SECURITY_WARNINGS: '1' },
});

try {
  fs.writeFileSync(PID_FILE, String(child.pid), 'utf8');
} catch {}

/**
 * 仅在 PID 文件仍记录当前子进程时删除它，避免清掉另一实例的记录；忽略文件操作失败。
 * @returns {void}
 */
const cleanPid = () => {
  try {
    if (fs.existsSync(PID_FILE) && fs.readFileSync(PID_FILE, 'utf8').trim() === String(child.pid)) {
      fs.unlinkSync(PID_FILE);
    }
  } catch {}
};

let forceKillTimer = null;

/**
 * 向尚未标记为 killed 的 Electron 子进程转发信号，并在超时后强制清理，忽略发送失败。
 * @param {string} sig 要转发的信号名，例如 SIGINT 或 SIGTERM。
 * @returns {void}
 */
const forwardSignal = (sig) => {
  if (child && !child.killed) {
    try {
      child.kill(sig);
    } catch {}
    if (!forceKillTimer) {
      forceKillTimer = setTimeout(() => {
        try {
          child.kill('SIGKILL');
        } catch {}
      }, 1000);
    }
  }
};
process.on('SIGINT', () => forwardSignal('SIGINT'));
process.on('SIGTERM', () => forwardSignal('SIGTERM'));

let stdoutBuffer = '';
let passedSentinel = false;
let failedSentinel = false;
let lastProgressLine = '';

function recordLine(line) {
  const trimmed = line.trim();
  if (!trimmed) return;
  lastProgressLine = trimmed;
  if (trimmed.includes('✅ 探针全部通过')) {
    passedSentinel = true;
  }
  if (trimmed.includes('❌ 探针失败')) {
    failedSentinel = true;
  }
}

function flushRemainingStdout() {
  if (stdoutBuffer) {
    recordLine(stdoutBuffer);
    stdoutBuffer = '';
  }
}

if (child.stdout) {
  child.stdout.setEncoding('utf8');
  child.stdout.on('data', (chunk) => {
    process.stdout.write(chunk);
    stdoutBuffer += chunk;
    const lines = stdoutBuffer.split('\n');
    stdoutBuffer = lines.pop();
    for (const line of lines) {
      recordLine(line);
    }
  });
}

child.on('error', (error) => {
  if (forceKillTimer) clearTimeout(forceKillTimer);
  cleanPid();
  console.error(`\n❌ 起不了 Electron（${electron}）：${error.message}`);
  console.error('   宿主机上可以 `MIPL_ELECTRON_BIN=<解包的 electron44> node tools/probe-render.js`。');
  process.exit(2);
});

let terminated = false;
function handleTermination(code, signal) {
  if (terminated) return;
  terminated = true;
  if (forceKillTimer) clearTimeout(forceKillTimer);
  cleanPid();
  flushRemainingStdout();

  if (signal) {
    console.error(`\n❌ Electron 被信号终止：${signal}`);
    if (lastProgressLine) {
      console.error(`   最后进展：${lastProgressLine}`);
    }
    process.exit(2);
  }

  if (code !== 0) {
    if (!failedSentinel && !passedSentinel) {
      console.error(`\n❌ 探针异常退出（退出码 ${code}）`);
      console.error(`   最后进展：${lastProgressLine || '（无任何输出）'}`);
    }
    process.exit(code === null ? 2 : code);
  }

  // code === 0
  if (failedSentinel) {
    console.error('\n❌ 探针包含失败断言，不能视为通过');
    console.error(`   最后进展：${lastProgressLine || '（无任何输出）'}`);
    process.exit(1);
  }

  if (!passedSentinel) {
    console.error('\n❌ 探针未完成就提前退出（退出码 0，未见「✅ 探针全部通过」）');
    console.error(`   最后进展：${lastProgressLine || '（无任何输出）'}`);
    process.exit(1);
  }

  const pngCount = countValidScreenshots(outDir);
  if (pngCount === 0) {
    console.error('\n❌ 探针未生成任何截图产物（未见有效截图）');
    console.error(`   截图目录：${outDir}`);
    process.exit(1);
  }

  process.exit(0);
}

let exitCode = null;
let exitSignal = null;

child.on('exit', (code, signal) => {
  cleanPid();
  exitCode = code;
  exitSignal = signal;
  // Fallback: 如果 close 事件未在 1000ms 内触发，确保仍能收敛退出
  setTimeout(() => handleTermination(exitCode, exitSignal), 1000).unref();
});

child.on('close', (code, signal) => {
  const finalCode = code !== null ? code : exitCode;
  const finalSignal = signal !== null ? signal : exitSignal;
  handleTermination(finalCode, finalSignal);
});
