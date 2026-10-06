/**
 * setup.js —— 向导状态（唯一的状态机）
 *
 * 页面**只读写这里**，不自己导航、不自己取数据（页面契约，与旧 QML 版一致）：
 *   - 页面调 `setup.set(key, value)` 写选择；
 *   - 页面通过 `page.isComplete(setup, t)` / `blockedReason(...)` 表达「能不能走」；
 *   - 导航由 app.js 执行，页面只发 `primaryRequested` 的意图（在 action bar 上）。
 */

import { flowFor } from './steps.js';

/** 后端 `validate_user()` 的规则（tech/09 待确认 2：文案按后端写，别放宽）。 */
const USER_RE = /^[a-z][a-z0-9_-]*$/;

export const PASSWORD_MIN = 6;

/**
 * 向导的默认值 —— **唯一来源**：`data` 的初始值与「名单页把默认项放在第一行」
 * 读的是同一份。
 *
 * 为什么不各页各写一个：那两处一旦不一致，第一行那条就不再是「不选会得到的值」——
 * 而这条纪律的全部价值就在于「一眼看到不选是什么」。见 `pages/shared.js` 的
 * `withDefaultFirst()`。
 */
export const DEFAULTS = {
  locale: 'zh_CN.UTF-8',
  keymap: 'us',
  timezone: 'Asia/Shanghai',
};

export class Setup {
  constructor() {
    this.advanced = false;
    this.index = 0;
    this.listeners = new Set();
    this.data = {
      ...DEFAULTS,
      disk: '',
      user: '',
      password: '',
      rootPassword: '',
      hostname: '',
      hostnameTouched: false,
      /**
       * 后端对当前主机名的判定：`null` = 还没问到 / 问不到，`true` / `false` = 后端说的。
       *
       * **这条替换掉了界面自己那份 RFC 1123 正则**（Issue #97）：主机名规则原来在
       * 这里是第二份实现（第一份在后端 `options.validate_hostname()`），
       * 两份迟早不一致 —— 而不一致的表现是「界面放行、动盘后被后端拒」。
       * 现在界面只**缓存后端的话**，规则只有一处。
       */
      hostnameOk: null,
      understood: false,
      confirmText: '',
      wifiPassword: '',
      progress: { percent: 0, phase: 0, done: false, cancelled: false },
    };
  }

  get steps() {
    return flowFor(this.advanced);
  }

  get stepId() {
    return this.steps[this.index] || this.steps[0];
  }

  get stepCount() {
    return this.steps.length;
  }

  get isFirst() {
    return this.index === 0;
  }

  get isLast() {
    return this.index === this.steps.length - 1;
  }

  get stepPercent() {
    return Math.round(((this.index + 1) / this.stepCount) * 100);
  }

  /** 切换「高级安装」：步骤表即时变长/变短，停在同一个页面 id 上，不跳回第一步。 */
  setAdvanced(value) {
    const currentId = this.stepId;
    this.advanced = Boolean(value);
    const nextIndex = this.steps.indexOf(currentId);
    this.index = nextIndex >= 0 ? nextIndex : 0;
    this.emit();
  }

  set(key, value) {
    if (this.data[key] === value) return;
    this.data[key] = value;
    // 主机名一变，上一次的后端判定就作废了 —— 留着它，界面会拿旧结论说新值
    if (key === 'hostname') this.data.hostnameOk = null;
    // 普通模式下主机名默认跟用户名（技术审稿：普通模式主机名 = 用户名）
    if (key === 'user' && !this.advanced && !this.data.hostnameTouched) {
      this.data.hostname = value;
      this.data.hostnameOk = null;
    }
    this.emit();
  }

  go(index) {
    const clamped = Math.max(0, Math.min(this.steps.length - 1, index));
    if (clamped === this.index) return false;
    this.index = clamped;
    this.emit();
    return true;
  }

  next() {
    return this.go(this.index + 1);
  }

  back() {
    return this.go(this.index - 1);
  }

  /** 进入进度页时重置进度状态（重跑一遍时不该带着上一次的 100%）。 */
  resetProgress() {
    this.data.progress = { percent: 0, phase: 0, done: false, cancelled: false };
    this.emit();
  }

  onProgress(percent, phase) {
    this.data.progress = { ...this.data.progress, percent, phase };
    this.emit();
  }

  emit() {
    for (const listener of this.listeners) listener(this);
  }

  subscribe(listener) {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  // ------------------------------------------------------------ 校验

  get userError() {
    const value = this.data.user;
    if (!value) return null;
    return USER_RE.test(value) ? null : 'account.err.userFormat';
  }

  get passwordError() {
    const value = this.data.password;
    if (!value) return null;
    return value.length >= PASSWORD_MIN ? null : 'account.err.pwShort';
  }

  /** 二次输入（确认密码）由页面自己存，这里只给规则。 */
  confirmMismatch(confirm) {
    const { password } = this.data;
    if (!password && !confirm) return null;
    return password === confirm ? null : 'account.err.pwMismatch';
  }

  /**
   * 主机名合不合规 —— **后端说了算**（`options.validate_hostname()`），
   * 这里只把它的结论翻成文案键。
   *
   * 三种状态要分清：
   *   - `hostnameOk === false`（后端说不合规）→ 报错，`下一步` 拦住；
   *   - `hostnameOk === true`（后端说合规）→ 放行；
   *   - `hostnameOk === null`（还没问到，或后端够不着）→ **不算错**。
   *
   * 最后那条是有意的：「问不到」不等于「不合法」，把它当错会让人卡在一台
   * 起不了后端的机器上出不去。真正的守卫在 `pipeline.preflight()` ——
   * 它在**动盘之前**跑，所以漏网的名字会在盘被擦之前被拒。
   */
  get hostnameError() {
    const value = this.data.hostname;
    if (!value) return null;
    // 后端目前对主机名只有一条规则，`reason` 只有 `format` 一种；
    // 将来多了别的 reason，在这里加映射，别把界面文案塞回后端。
    return this.data.hostnameOk === false ? 'hostname.err.format' : null;
  }

  /** 密码强度只用于界面提示（0–3），不是安全判据。 */
  static passwordLevel(password) {
    if (!password) return 0;
    let score = 0;
    if (password.length >= PASSWORD_MIN) score += 1;
    if (password.length >= 10) score += 1;
    if (/[A-Z]/.test(password) && /[a-z]/.test(password)) score += 1;
    if (/[0-9]/.test(password) && /[^A-Za-z0-9]/.test(password)) score += 1;
    return Math.min(3, score);
  }

  /** 擦除确认：必须逐字输入所选磁盘名（不区分大小写地宽松一点，但不接受空）。 */
  confirmTextMatches() {
    const disk = this.data.disk;
    const typed = (this.data.confirmText || '').trim();
    if (!typed) return false;
    return typed.toLowerCase() === disk.toLowerCase();
  }
}
