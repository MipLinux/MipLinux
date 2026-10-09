/**
 * theme.js —— 主题状态（亮 / 暗 / 跟随本地时间）
 *
 * 首帧由启动器算好并通过 `window.mipl.config` 注入（P5：第一帧就得是对的主题）。
 * 这一层只负责「之后」：跟随时间的低频重算（30s）与用户手动锁定。
 */

const AUTO_LIGHT_FROM = 7;
const AUTO_LIGHT_UNTIL = 19;

/**
 * `auto` 模式下的判定（07:00–18:59 亮）。
 * **默认就是 auto**（维护者 2026-10-04）—— 白天落亮色（亮色是设计基线），入夜自动转暗；
 * 用户可以在顶栏把主题**锁**成亮或暗（锁了就不再跟时间走）。
 */
export function themeForNow(date = new Date()) {
  const hour = date.getHours();
  return hour >= AUTO_LIGHT_FROM && hour < AUTO_LIGHT_UNTIL ? 'light' : 'dark';
}

export class ThemeController {
  constructor({ theme = 'light', source = 'auto', intervalMs = 30_000 } = {}) {
    this.theme = theme === 'light' ? 'light' : 'dark';
    /** 'auto' = 跟时间；'light' | 'dark' = 用户手动锁定（08 §3.9） */
    this.source = ['auto', 'light', 'dark'].includes(source) ? source : 'auto';
    this.intervalMs = intervalMs;
    this.listeners = new Set();
    this.timer = null;
  }

  get locked() {
    return this.source !== 'auto';
  }

  apply() {
    document.documentElement.dataset.theme = this.theme;
  }

  /** 顶栏菜单用：auto = 跟随时间；light / dark = 锁定。 */
  setMode(mode) {
    if (mode === 'auto') {
      const changed = this.source !== 'auto';
      this.source = 'auto';
      this.theme = themeForNow();
      this.apply();
      this.emit();
      return changed;
    }
    if (mode !== 'light' && mode !== 'dark') return false;
    const changed = this.source !== mode;
    this.source = mode;
    this.theme = mode;
    this.apply();
    this.emit();
    return changed;
  }

  /** 手动切换：锁定到当前主题的相反面。 */
  toggle() {
    this.theme = this.theme === 'dark' ? 'light' : 'dark';
    this.source = this.theme;
    this.apply();
    this.emit();
    return this.theme;
  }

  /** 回到跟随时间（把锁定解开）。 */
  unfollow() {
    this.source = 'auto';
    this.theme = themeForNow();
    this.apply();
    this.emit();
  }

  start() {
    this.apply();
    if (this.timer) clearInterval(this.timer);
    this.timer = setInterval(() => this.tick(), this.intervalMs);
    return this;
  }

  stop() {
    if (this.timer) clearInterval(this.timer);
    this.timer = null;
  }

  tick() {
    if (this.locked) return;
    const next = themeForNow();
    if (next === this.theme) return;
    this.theme = next;
    this.apply();
    this.emit();
  }

  onChange(listener) {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  emit() {
    for (const listener of this.listeners) listener(this.theme, this.source);
  }
}
