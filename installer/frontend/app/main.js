'use strict';
/**
 * MipLinux 安装器 · Electron 主进程
 * ==================================
 *
 * 它只做五件事，**不实现任何安装逻辑**：
 *   1. 注册 `mipl://` 私有协议，把 `renderer/` 当静态站点端出来（这样 ES module 与 fetch 才有
 *      正常的 origin —— `file://` 下两者都会被 Chromium 拦掉）。
 *   2. 开一个 kiosk 窗口：无边框、全屏、深色底（首帧不闪白）。
 *   3. 把启动器算好的三件事（主题 / 设备缩放 / 界面语言）透给渲染层。
 *   4. 封死出口：不允许导航到外部 URL、不允许开新窗口。
 *   5. 经 `child_process` 拉起后端（`python3 -m mipl_installer`）—— 只读出口一问一答、
 *      安装一条长跑的事件流；密码只走 stdin。见下面「后端通道」一节。
 *
 * 启动参数（由 `installer/frontend/mipl-installer` 传进来）
 * -------------------------------------------------------
 *   --theme=auto|light|dark   首帧主题（auto 由启动器按本地时间算好后再传）
 *   --ui-scale=100|167|200    界面层缩放的推荐值（启动器按分辨率算好）；0 = 自动档但没推荐值
 *   --lang=zh_CN|en_US        首帧语言
 *
 * Chromium 的开关（`--no-sandbox` / `--ozone-platform=wayland` …）**由启动器写在命令行上**，
 * 因为其中一部分必须在 Electron 进程启动前就位；主进程里再 appendSwitch 已经晚了。
 */

const { app, BrowserWindow, ipcMain, protocol } = require('electron');
const path = require('node:path');
const fs = require('node:fs');
const os = require('node:os');
const { spawn } = require('node:child_process');

// 协议根目录 = 应用目录：这样 `../../vendor/...` 这种相对路径在浏览器与 Node 里语义一致
const ROOT_DIR = __dirname;
const SCHEME = 'mipl';
const HOST = 'app';
const INDEX_URL = `${SCHEME}://${HOST}/renderer/index.html`;

const APP_THEME_BG = { dark: '#06070b', light: '#f7f8fb' };

// ---------------------------------------------------------------- 启动参数

function parseLaunchArgs(argv) {
  const wanted = { theme: 'auto', uiScale: 0, lang: 'zh_CN', renderer: 'gpu' };
  for (const raw of argv) {
    const match = /^--(theme|ui-scale|lang|renderer-mode)=(.+)$/.exec(raw);
    if (!match) continue;
    const [, key, value] = match;
    if (key === 'ui-scale') {
      const parsed = Number.parseInt(value, 10);
      wanted.uiScale = [100, 167, 200].includes(parsed) ? parsed : 0;
    } else if (key === 'renderer-mode') {
      wanted.renderer = value === 'software' ? 'software' : 'gpu';
    } else {
      wanted[key] = value;
    }
  }
  if (!['auto', 'light', 'dark'].includes(wanted.theme)) wanted.theme = 'auto';
  if (!['zh_CN', 'en_US'].includes(wanted.lang)) wanted.lang = 'zh_CN';
  return wanted;
}

/**
 * 主题兜底：启动器一般已经算好并传了 light/dark。
 * 亮色是**主**主题（维护者 2026-10-04）—— 所以 `auto` 在没有启动器时也先给亮色，
 * 不自己在主进程里按时间猜（时间规则只在启动器与渲染层各有一份）。
 */
function resolveTheme(theme) {
  return theme === 'dark' ? 'dark' : 'light';
}

// ---------------------------------------------------------------- mipl:// 协议

protocol.registerSchemesAsPrivileged([
  {
    scheme: SCHEME,
    privileges: { standard: true, secure: true, supportFetchAPI: true, stream: true },
  },
]);

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.woff2': 'font/woff2',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.md': 'text/markdown; charset=utf-8',
};

function serveRenderer(request) {
  const url = new URL(request.url);
  // 只认 mipl://app/...；路径穿越一律拒掉（renderer/ 之外的东西不给看）
  const relative = decodeURIComponent(url.pathname).replace(/^\/+/, '');
  const target = path.resolve(ROOT_DIR, relative || 'renderer/index.html');
  if (!target.startsWith(ROOT_DIR + path.sep)) {
    return new Response('forbidden', { status: 403 });
  }
  const type = MIME[path.extname(target).toLowerCase()];
  if (!type) {
    console.error(`[mipl-installer] 不认识的资源类型：${relative}`);
    return new Response(`unsupported: ${relative}`, { status: 415 });
  }
  try {
    // 自己读文件再包成 Response：不依赖 net.fetch 的 file:// 行为，路径与错误都看得见
    const data = fs.readFileSync(target);
    return new Response(data, { headers: { 'content-type': type } });
  } catch (error) {
    console.error(`[mipl-installer] 取不到资源 ${relative} → ${target}（${error.code}）`);
    return new Response(`not found: ${relative}`, { status: 404 });
  }
}

// ---------------------------------------------------------------- 后端通道

/**
 * 安装器后端 = `python3 -m mipl_installer`（`installer/backend/mipl_installer/`）。
 *
 * **这一节是界面与后端之间唯一的通道**（Issue #97 的「只建一处」）。渲染层拿不到
 * `child_process`（`contextIsolation: true`），它只知道几个**出口名**；把名字翻成
 * 命令行是这里的事。所以「界面上多一个出口」= 在这里加一行，而不是让渲染层拼 argv ——
 * 拼 argv 的那条路一旦开了，`--disk` 后面接什么就不是这张表说了算了。
 *
 * 后端目录由**相对位置**推出来，不写死绝对路径：开发树里是
 * `<仓库>/installer/backend`，Live 里构建脚本把整个 `installer/` 拷到
 * `/usr/local/lib/mipl-installer/`，两种布局下 `app/../../backend` 都对得上。
 */
const BACKEND_MODULE = 'mipl_installer';

function backendDir() {
  return process.env.MIPL_BACKEND_DIR || path.resolve(__dirname, '..', '..', 'backend');
}

function pythonBin() {
  return process.env.MIPL_PYTHON || 'python3';
}

function backendSpawnOptions() {
  // 后端不在 site-packages 里，靠 PYTHONPATH 找得到它自己（`-m` 需要包能被 import）
  const dir = backendDir();
  const existing = process.env.PYTHONPATH;
  return {
    cwd: dir,
    env: { ...process.env, PYTHONPATH: existing ? `${dir}${path.delimiter}${existing}` : dir },
  };
}

/**
 * 只读出口的白名单：出口名 → 拼命令行。
 *
 * 一律用 `--开关=值` 而不是 `--开关 值`：值以 `-` 开头时（`-bad-` 这种主机名
 * 是**测试用例**里就有的），分开写会被 argparse 当成另一个开关，然后报一句
 * 与事实无关的错。
 *
 * `connectWifi` 的密码不在这里 —— 它走 stdin（见 `runQuery`）。
 */
const QUERY_ARGV = {
  disks: () => ['--print-disks'],
  network: () => ['--print-network'],
  wifi: (options) => (options && options.rescan ? ['--print-wifi', '--rescan'] : ['--print-wifi']),
  timezones: () => ['--print-timezones'],
  locales: () => ['--print-locales'],
  keymaps: () => ['--print-keymaps'],
  plan: () => ['--print-plan'],
  keymap: (options) => [`--print-keymap=${str(options, 'name')}`],
  checkHostname: (options) => [`--check-hostname=${str(options, 'value')}`],
  checkLocale: (options) => [`--check-locale=${str(options, 'value')}`],
  checkKeymap: (options) => [`--check-keymap=${str(options, 'value')}`],
  checkTimezone: (options) => [`--check-timezone=${str(options, 'value')}`],
  connectWifi: (options) => [`--connect-wifi=${str(options, 'ssid')}`],
  // 完成页的「重启」也走这一层：系统动作在**后端**（`queries.reboot` → `systemctl reboot`），
  // 主进程只把出口名翻成命令行。前端自己 exec 系统命令，就等于多了一处没人记日志的动系统的地方。
  reboot: () => ['--reboot'],
  // 失败页的「卸载 /mnt」同理（`queries.unmount_target` → `umount -R /mnt`）
  unmountTarget: () => ['--unmount-target'],
};

function str(options, key) {
  const value = options && options[key];
  if (typeof value !== 'string' || !value) throw new Error(`出口参数 ${key} 必须是非空字符串`);
  return value;
}

/**
 * 跑一个只读出口，回 `{ok, data}` 或 `{ok: false, error}`。
 *
 * **不 reject**：失败是这一层的正常返回值之一（后端不在、JSON 坏了、参数不对），
 * 让渲染层的每个调用点都包 try/catch 只会把错误处理写散。渲染层看到 `ok:false`
 * 就知道该显示「这个环境列不出名单」而不是崩掉。
 */
function runQuery(name, options, stdinText) {
  return new Promise((resolve) => {
    const build = QUERY_ARGV[name];
    if (!build) {
      resolve({ ok: false, error: `没有这个只读出口：${name}` });
      return;
    }
    let argv;
    try {
      argv = build(options);
    } catch (error) {
      resolve({ ok: false, error: error.message });
      return;
    }

    const child = spawn(pythonBin(), ['-m', BACKEND_MODULE, ...argv], backendSpawnOptions());
    let out = '';
    let err = '';
    child.stdout.on('data', (chunk) => {
      out += chunk;
    });
    child.stderr.on('data', (chunk) => {
      err += chunk;
    });
    child.on('error', (error) => {
      resolve({ ok: false, error: `起不了后端（${pythonBin()}）：${error.message}` });
    });
    child.on('close', (code) => {
      if (code !== 0) {
        resolve({ ok: false, error: err.trim() || `后端退出码 ${code}`, code });
        return;
      }
      try {
        resolve({ ok: true, data: JSON.parse(out) });
      } catch (error) {
        // 把开头一段原文带回去：多半是后端往 stdout 里混了别的东西，
        // 而「JSON 解析失败」这句话本身对排查毫无用处。
        resolve({ ok: false, error: `后端输出不是 JSON：${error.message}`, raw: out.slice(0, 2000) });
      }
    });
    child.stdin.end(typeof stdinText === 'string' ? stdinText : '');
  });
}

/**
 * 渲染层给的 `Plan` → 命令行。**字段白名单**，未知字段直接忽略。
 *
 * 界面上的「高级安装」只决定**走哪几页**，不改变装盘的四个阶段 ——
 * 所以 `--steps` 不在这里：它永远是全部四段，省得界面上少勾一个就装出半成品。
 * `--yes` 是**擦除页已经确认过**的结论（`confirm.js` 那道逐字输入），
 * 后端因此不再问第二遍；守卫没有减少，只是换了个人回答。
 */
const PLAN_FLAGS = {
  disk: '--disk',
  target: '--target',
  hostname: '--hostname',
  user: '--user',
  locale: '--locale',
  timezone: '--timezone',
  keymap: '--keymap',
};

function installArgv(plan, logPath) {
  if (!plan || typeof plan !== 'object') throw new Error('没有安装计划');
  if (typeof plan.disk !== 'string' || !plan.disk) throw new Error('计划里没有目标盘');
  const argv = ['-m', BACKEND_MODULE, '--json-events', '--yes'];
  for (const [key, flag] of Object.entries(PLAN_FLAGS)) {
    const value = plan[key];
    if (value === undefined || value === null || value === '') continue;
    if (typeof value !== 'string') throw new Error(`计划字段 ${key} 必须是字符串`);
    argv.push(`${flag}=${value}`);
  }
  argv.push('--password-stdin');
  if (logPath) argv.push(`--log=${logPath}`);
  return argv;
}

/**
 * 安装日志的落盘路径：事件流原本只活在这条管道里，进程一没，实机上只剩屏幕上的
 * 截图 —— 「二十分钟花在哪了」「那行豆腐块是什么」都无从对证。落一份盘，复盘
 * 才有东西可读。优先 /var/log（Live 里是 root），写不了退临时目录；都建不出来就
 * 不传这个开关 —— 记日志不许把安装拖下水。
 */
function installLogPath() {
  const stamp = new Date().toISOString().replace(/[:.]/g, '-');
  const candidates = [
    `/var/log/mipl-installer/install-${stamp}.log`,
    path.join(os.tmpdir(), `mipl-installer-${stamp}.log`),
  ];
  for (const file of candidates) {
    try {
      fs.mkdirSync(path.dirname(file), { recursive: true });
      return file;
    } catch (error) {
      // 这一处建不出来就试下一处
    }
  }
  return null;
}

/** 正在跑的那一次安装。同一时刻只允许一个 —— 两个 `pacstrap` 抢同一块盘没有意义。 */
let installRun = null;

function startInstall(win, plan, secrets) {
  if (installRun) return { ok: false, error: '已经有一次安装在进行中' };
  // 两行密码的顺序固定：用户在前、root 在后（cli.py 的红线）。`rootPassword` 空 =
  // **不加**那个开关，后端据此保持 root 锁定。注意「root 留空 = 与用户密码相同」
  // 这条界面口径的翻译点在 `renderer/js/backend.js` 的 `buildSecrets()` —— 到这一步
  // 它已经是具体值了；在这里再补一次回退，等于把口径复制成两份。
  const user = typeof secrets.user === 'string' ? secrets.user : '';
  const root = typeof secrets.rootPassword === 'string' && secrets.rootPassword ? secrets.rootPassword : null;

  const logPath = installLogPath();
  if (logPath) console.log(`[mipl-installer] 安装日志：${logPath}`);

  let argv;
  try {
    argv = installArgv(plan, logPath);
  } catch (error) {
    return { ok: false, error: error.message };
  }
  if (root !== null) argv.push('--root-password-stdin');

  const child = spawn(pythonBin(), argv, backendSpawnOptions());
  installRun = { child, cancelled: false, finished: false };

  const send = (record) => {
    if (!win.isDestroyed()) win.webContents.send('mipl:backend:event', record);
  };

  // 后端一行一个 JSON 对象（`events.JsonReporter`）。半行要留着跟下一块拼 ——
  // 管道切分不保证按行，直接 `split('\n')` 迟早会在某个中文消息中间断开。
  let buffered = '';
  const flush = (text) => {
    const body = text.trim();
    if (!body) return;
    try {
      send(JSON.parse(body));
    } catch (error) {
      // 解析不了的一行也要给渲染层看：静默丢掉会让「进度页停在某一步」变成悬案。
      // 控制字符先洗掉（\t 除外）：这一支是兜底，兜底自己不该再画出豆腐块
      const clean = body.slice(0, 500).replace(/[\x00-\x08\x0b-\x1f\x7f]/g, ' ');
      send({ kind: 'note', message: `[后端输出无法解析] ${clean}` });
    }
  };
  child.stdout.on('data', (chunk) => {
    buffered += chunk;
    // 半行要留着跟下一块拼 —— 管道切分不保证按行，直接 `split('\n')` 迟早会在
    // 某个中文消息中间断开（多字节字符被切开时更隐蔽）
    const lines = buffered.split('\n');
    buffered = lines.pop();
    for (const line of lines) flush(line);
  });

  let stderrTail = '';
  child.stderr.on('data', (chunk) => {
    stderrTail = (stderrTail + chunk).slice(-4000);
    if (!win.isDestroyed()) win.webContents.send('mipl:backend:stderr', String(chunk));
  });

  child.on('error', (error) => {
    send({ kind: 'error', code: -1, message: `起不了后端（${pythonBin()}）：${error.message}`, hint: null });
    send({ kind: 'end', code: -1 });
    // **必须清掉**：留着的话 `startInstall` 会一直回「已经有一次安装在进行中」，
    // 而实际上一个进程都没起来 —— 界面从此再也开不了工，只能重启安装器。
    if (installRun && installRun.child === child) installRun = null;
  });

  child.on('close', (code) => {
    // 进程没了但缓冲区里还留着最后半行（没有以换行收尾的输出）：冲掉再收尾，
    // 否则「end 发出来了、end 后面那条却丢了」。`JsonReporter` 每条都带换行，
    // 所以这是给「将来某个往 stdout 里写别的东西的人」留的坑位。
    flush(buffered);
    buffered = '';
    if (installRun) installRun.finished = true;
    // `stderr` 尾巴附在收尾那条上：装到一半失败时，真正的原因常在后端的 stderr 里
    send({ kind: 'exit', code, cancelled: Boolean(installRun && installRun.cancelled), stderr: stderrTail });
    installRun = null;
  });

  // 密码只走 stdin，绝不进 argv。
  child.stdin.end(root === null ? `${user}\n` : `${user}\n${root}\n`);

  return { ok: true };
}

function cancelInstall() {
  if (!installRun) return { ok: false, error: '没有正在进行的安装' };
  installRun.cancelled = true;
  // `SIGUSR1` 而不是 `SIGINT`/`SIGKILL`：后两个会当场打断 `pacstrap`，留下一个
  // 谁都说不清的半成品。这个信号只是「举手」，取消发生在**阶段之间**
  // （`pipeline.run(should_cancel=…)`），退出码 130、并按失败的同一条路卸载目标。
  installRun.child.kill('SIGUSR1');
  return { ok: true };
}

// ---------------------------------------------------------------- 窗口

function createWindow(launch) {
  const theme = resolveTheme(launch.theme);
  const probing = Boolean(process.env.MIPL_PROBE);
  const win = new BrowserWindow({
    show: false,
    frame: false,
    // 探针要可复现的截图尺寸，所以用固定窗口；kiosk 里是全屏无边框
    fullscreen: !probing,
    width: probing ? 1440 : undefined,
    height: probing ? 900 : undefined,
    autoHideMenuBar: true,
    backgroundColor: APP_THEME_BG[theme] || APP_THEME_BG.dark,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
      spellcheck: false,
      // 探针走离屏渲染：headless 合成器下 capturePage() 只给 1×1，必须拿 paint 帧
      offscreen: probing,
      // 启动注入走这里：preload 从 process.argv 里读，渲染层不碰 Node
      additionalArguments: [
        `--mipl-theme=${theme}`,
        `--mipl-theme-source=${launch.theme}`,
        `--mipl-lang=${launch.lang}`,
        `--mipl-ui-scale=${launch.uiScale || 0}`,
        `--mipl-renderer=${launch.renderer}`,
        `--mipl-probe=${process.env.MIPL_PROBE ? '1' : '0'}`,
      ],
    },
  });

  // kiosk 纪律：不许导航出去、不许开新窗口
  win.webContents.on('will-navigate', (event, url) => {
    if (!url.startsWith(`${SCHEME}://${HOST}/`)) event.preventDefault();
  });
  win.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));

  win.once('ready-to-show', () => {
    // 部分合成器要等窗口 show 之后才认 fullscreen —— kiosk 不能先闪一帧带边框的窗口
    if (!probing) win.setFullScreen(true);
    win.show();
  });

  win.loadURL(INDEX_URL);
  return win;
}

// ---------------------------------------------------------------- main

/**
 * 把 GPU 的状态写进日志：实机上 `journalctl -u mipl-installer` 至少能看到设备与特性状态。
 *
 * **别指望这一行能判出软渲染**：Chromium 的 `gpu_compositing` 对 SwiftShader 也报 enabled，
 * 而 `auxAttributes` 里那组 GL 字段各平台/版本不一致（本机实测给的是 `gl=none`）。
 * 「到底走没走显卡」的权威证据在另外两行：
 *   - `mipl-kiosk: GPU … → WLR_RENDERER=gles2`（合成器侧有没有退回 pixman）
 *   - `mipl-installer: 渲染：硬件加速 / SwiftShader 软件渲染`（启动器的判定）
 */
async function logGpuStatus() {
  try {
    const basic = await app.getGPUInfo('basic');
    await new Promise((resolve) => setTimeout(resolve, 700));
    const status = app.getGPUFeatureStatus();
    const gpu = (basic.gpuDevice || []).map((device) => `${device.vendorId || '?'}:${device.deviceId || '?'}`);
    console.log(
      `[mipl-installer] GPU: ${gpu.join(', ') || '未识别'} | 合成器=${status.gpu_compositing || '?'}` +
        ` | WebGL=${status.webgl || '?'} | 光栅化=${status.rasterization || '?'}`
    );
  } catch (error) {
    console.log(`[mipl-installer] GPU 状态读取失败：${error.message}`);
  }
}

app.whenReady().then(async () => {
  protocol.handle(SCHEME, serveRenderer);

  const launch = parseLaunchArgs(process.argv);
  const gpuCheck = Boolean(process.env.MIPL_GPU_CHECK);
  await logGpuStatus();
  // `MIPL_GPU_CHECK=1`：只打印 GPU 状态就退出（在实机上排查「到底用没用上显卡」）
  if (gpuCheck) {
    app.exit(0);
    return;
  }
  const win = createWindow(launch);

  ipcMain.handle('mipl:reboot', async () => {
    // 完成页的「重启」= 后端的 `--reboot` 出口（`systemctl reboot`）。
    // v0.1 曾经只在这里打一行日志就回 `handled:false` —— 界面上按钮点得动、
    // 系统一动不动，是最难查的一类假按钮（实机反馈）。
    const result = await runQuery('reboot');
    // 失败的**原文**进 journal（中文），界面那侧只拿 `ok` 去查自己的文案 ——
    // 英文模式下界面不许出现后端的中文句子（app/README.md §7.2）。
    if (!result.ok) console.error(`[mipl-installer] 重启失败：${result.error}`);
    return result;
  });

  ipcMain.handle('mipl:window-info', () => ({
    fullscreen: win.isFullScreen(),
    bounds: win.getBounds(),
  }));

  // ── 后端通道（渲染层唯一的取数入口，见 preload.js 的 `window.mipl.backend`）──
  // 三个 handler 的名字是冻结接口的一部分（app/README.md）。
  ipcMain.handle('mipl:backend:query', (_event, name, options, stdinText) =>
    runQuery(name, options, stdinText)
  );
  ipcMain.handle('mipl:backend:start', (_event, plan, secrets) => startInstall(win, plan, secrets || {}));
  ipcMain.handle('mipl:backend:cancel', () => cancelInstall());

  if (process.env.MIPL_PROBE) {
    // 探针只在显式要求时加载；生产路径不会碰它
    require('./tools/probe-main.js')({ app, win, launch });
  }

  app.on('window-all-closed', () => app.quit());

  // 退出时不要留下一个还在擦盘的孤儿进程。只用 `SIGUSR1`（阶段之间取消），
  // 所以这一步是**尽力而为**：真在 `pacstrap` 里的话，它会跑完当前阶段才停 ——
  // 这正是我们要的，宁可多跑一会儿，也不要一个半个装完的目标系统。
  app.on('will-quit', () => {
    if (!installRun) return;
    console.log('[mipl-installer] 退出时仍有安装在进行，请求阶段之间取消');
    cancelInstall();
  });
});

// 单实例：kiosk 里被拉起两次时，第二次直接退出，不要叠两个全屏窗口
if (!app.requestSingleInstanceLock()) app.quit();

// **不要在这里加 `process.on('SIGTERM')`。** 实测（Electron 43，2026-10-06）：
// 浏览器进程里 Chromium 自己的信号处理器会把 Node 那个顶掉，注册了也不会被调用
// （退出码 0、我那句日志一次都没打）。而 Chromium 的默认行为本身是**干脆的**：
// 朝整个进程组发 SIGTERM，6 个 Electron 进程 3 秒内全部消失，没有残留。
// 也就是说「关机时安装器这个 stop job 卡住」的根因不在这一层，
// 停机上限由 unit 的 `TimeoutStopSec=` 兜（见 profile/.../mipl-installer.service）。
