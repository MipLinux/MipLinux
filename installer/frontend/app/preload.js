'use strict';
/**
 * preload —— 渲染层唯一的对外通道（contextIsolation: true，渲染层拿不到 Node）。
 *
 * 只暴露三样东西：
 *   - `config`：启动器算好的首帧参数（主题 / 主题来源 / 语言 / 设备缩放 / 是否探针）
 *   - `reboot()`：完成页的「重启」请求（真机由后端接管，本层不执行安装逻辑）
 *   - `windowInfo()`：窗口状态（探针与缩放判定用）
 */

const { contextBridge, ipcRenderer } = require('electron');

function argValue(prefix) {
  const hit = process.argv.find((arg) => arg.startsWith(prefix));
  return hit ? hit.slice(prefix.length) : null;
}

const config = {
  theme: argValue('--mipl-theme=') === 'light' ? 'light' : 'dark',
  themeSource: argValue('--mipl-theme-source=') || 'auto',
  lang: argValue('--mipl-lang=') === 'en_US' ? 'en_US' : 'zh_CN',
  scale: Number.parseInt(argValue('--mipl-scale=') || '0', 10) || 0,
  probe: argValue('--mipl-probe=') === '1',
  electron: process.versions.electron,
};

contextBridge.exposeInMainWorld('mipl', {
  config: Object.freeze(config),
  reboot: () => ipcRenderer.invoke('mipl:reboot'),
  windowInfo: () => ipcRenderer.invoke('mipl:window-info'),
});
