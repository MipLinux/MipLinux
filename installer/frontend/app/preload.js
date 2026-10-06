'use strict';
/**
 * preload —— 渲染层唯一的对外通道（contextIsolation: true，渲染层拿不到 Node）。
 *
 * 只暴露四样东西：
 *   - `config`：启动器算好的首帧参数（主题 / 主题来源 / 语言 / 界面缩放推荐值 / 是否探针）
 *   - `backend`：**后端通道**。取真数据、装系统、取消，全走它（见下）
 *   - `reboot()`：完成页的「重启」请求。**真的会重启** —— 它经主进程转到后端的
 *     `--reboot` 出口（`systemctl reboot`），本层不执行系统动作
 *   - `windowInfo()`：窗口状态（探针与缩放判定用）
 *
 * ## `backend` 的四个方法（冻结接口，见 app/README.md 的耦合层一节）
 *
 * | 方法 | 形态 | 说明 |
 * |---|---|---|
 * | `query(name, options?, stdinText?)` | 一问一答 | 只读出口。回 `{ok:true, data}` 或 `{ok:false, error}`，**不抛** |
 * | `start(plan, secrets)` | 一次 | 开始装。回 `{ok}`；进度走 `onEvent` |
 * | `cancel()` | 一次 | 请求取消。真正生效在**阶段之间**，退出码 130 |
 * | `onEvent(listener)` | 订阅 | 后端每一条 JSON 记录；回退订函数 |
 *
 * **不 reject** 是刻意的：后端不在、输出坏了、参数不对，都是这一层正常要面对的
 * 结果，渲染层看到 `ok:false` 就该显示「这个环境列不出名单」，而不是让整页崩掉。
 * 会抛的只有 `start` 之前就发现的用法错误。
 *
 * `secrets`（密码）**只经这个函数传下去**，主进程把它写进子进程的 stdin ——
 * 绝不进 argv（argv 会留在进程列表与日志里）。
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
  // 界面层缩放的推荐值（启动器算的）；0 = 自动档但没拿到推荐值 → 渲染层退 100%
  uiScale: Number.parseInt(argValue('--mipl-ui-scale=') || '0', 10) || 0,
  probe: argValue('--mipl-probe=') === '1',
  // 渲染模式由启动器判定：software 时渲染层走「低配模式」（关掉模糊/极光等重效果）
  renderer: argValue('--mipl-renderer=') === 'software' ? 'software' : 'gpu',
  electron: process.versions.electron,
};

const backend = {
  query: (name, options, stdinText) => ipcRenderer.invoke('mipl:backend:query', name, options, stdinText),
  start: (plan, secrets) => ipcRenderer.invoke('mipl:backend:start', plan, secrets),
  cancel: () => ipcRenderer.invoke('mipl:backend:cancel'),
  /** 订阅后端事件流；**回一个退订函数** —— 页面换掉时不退订，监听器会一直叠。 */
  onEvent: (listener) => {
    const handler = (_event, record) => listener(record);
    ipcRenderer.on('mipl:backend:event', handler);
    return () => ipcRenderer.removeListener('mipl:backend:event', handler);
  },
  /** 后端 stderr 的增量。装到一半失败时，真正的原因常在这里。 */
  onStderr: (listener) => {
    const handler = (_event, text) => listener(text);
    ipcRenderer.on('mipl:backend:stderr', handler);
    return () => ipcRenderer.removeListener('mipl:backend:stderr', handler);
  },
};

contextBridge.exposeInMainWorld('mipl', {
  config: Object.freeze(config),
  backend,
  reboot: () => ipcRenderer.invoke('mipl:reboot'),
  windowInfo: () => ipcRenderer.invoke('mipl:window-info'),
});
