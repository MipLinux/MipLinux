'use strict';
/**
 * MipLinux 安装器 · Electron 主进程
 * ==================================
 *
 * 它只做四件事，**不实现任何安装逻辑**：
 *   1. 注册 `mipl://` 私有协议，把 `renderer/` 当静态站点端出来（这样 ES module 与 fetch 才有
 *      正常的 origin —— `file://` 下两者都会被 Chromium 拦掉）。
 *   2. 开一个 kiosk 窗口：无边框、全屏、深色底（首帧不闪白）。
 *   3. 把启动器算好的三件事（主题 / 设备缩放 / 界面语言）透给渲染层。
 *   4. 封死出口：不允许导航到外部 URL、不允许开新窗口。
 *
 * 启动参数（由 `installer/frontend/mipl-installer` 传进来）
 * -------------------------------------------------------
 *   --theme=auto|light|dark   首帧主题（auto 由启动器按本地时间算好后再传）
 *   --scale=1|2|3             设备层缩放（启动器按 DRM 信息算好）
 *   --lang=zh_CN|en_US        首帧语言
 *
 * Chromium 的开关（`--no-sandbox` / `--ozone-platform=wayland` …）**由启动器写在命令行上**，
 * 因为其中一部分必须在 Electron 进程启动前就位；主进程里再 appendSwitch 已经晚了。
 */

const { app, BrowserWindow, ipcMain, protocol } = require('electron');
const path = require('node:path');
const fs = require('node:fs');

// 协议根目录 = 应用目录：这样 `../../vendor/...` 这种相对路径在浏览器与 Node 里语义一致
const ROOT_DIR = __dirname;
const SCHEME = 'mipl';
const HOST = 'app';
const INDEX_URL = `${SCHEME}://${HOST}/renderer/index.html`;

const APP_THEME_BG = { dark: '#06070b', light: '#f7f8fb' };

// ---------------------------------------------------------------- 启动参数

function parseLaunchArgs(argv) {
  const wanted = { theme: 'auto', scale: null, lang: 'zh_CN' };
  for (const raw of argv) {
    const match = /^--(theme|scale|lang)=(.+)$/.exec(raw);
    if (!match) continue;
    const [, key, value] = match;
    if (key === 'scale') {
      const parsed = Number.parseInt(value, 10);
      wanted.scale = [1, 2, 3].includes(parsed) ? parsed : null;
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
        `--mipl-scale=${launch.scale ?? 0}`,
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

app.whenReady().then(() => {
  protocol.handle(SCHEME, serveRenderer);

  const launch = parseLaunchArgs(process.argv);
  const win = createWindow(launch);

  ipcMain.handle('mipl:reboot', () => {
    // v0.1：完成页的「重启」在真机由后端接管（systemctl reboot）；本层只记录，不做安装逻辑
    console.log('[mipl-installer] 完成页请求重启（真机由后端接管，前端不执行）');
    return { ok: true, handled: false };
  });

  ipcMain.handle('mipl:window-info', () => ({
    fullscreen: win.isFullScreen(),
    bounds: win.getBounds(),
  }));

  if (process.env.MIPL_PROBE) {
    // 探针只在显式要求时加载；生产路径不会碰它
    require('./tools/probe-main.js')({ app, win, launch });
  }

  app.on('window-all-closed', () => app.quit());
});

// 单实例：kiosk 里被拉起两次时，第二次直接退出，不要叠两个全屏窗口
if (!app.requestSingleInstanceLock()) app.quit();
