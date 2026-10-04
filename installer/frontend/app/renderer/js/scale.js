/**
 * scale.js —— 界面层缩放（四档：85% / 100% / 115% / 130%）
 *
 * 与「设备层缩放」是两层（tech/08 §3.10 / tech/10 §6）：
 *   - 设备层：启动器按 DRM 分辨率与 EDID 物理尺寸算，写进 Chromium 的缩放（本层拿不到、也不该改）；
 *   - 界面层：用户在界面里选的这四档，只改 `--ui-scale`，字阶与间距一起放大。
 *
 * 纪律：**页面不许自己乘 `--ui-scale`** —— 只在 token 层用一次（`calc(… * var(--ui-scale))`）。
 */

export const SCALE_LEVELS = [0.85, 1, 1.15, 1.3];

export class ScaleController {
  constructor(level = 1) {
    this.level = SCALE_LEVELS.includes(level) ? level : 1;
    this.listeners = new Set();
  }

  get percent() {
    return Math.round(this.level * 100);
  }

  apply() {
    document.documentElement.style.setProperty('--ui-scale', String(this.level));
    document.documentElement.dataset.uiScale = String(this.level);
  }

  /** 下一档（循环）。 */
  cycle() {
    const index = SCALE_LEVELS.indexOf(this.level);
    this.level = SCALE_LEVELS[(index + 1) % SCALE_LEVELS.length];
    this.apply();
    for (const listener of this.listeners) listener(this.level);
    return this.level;
  }

  set(level) {
    if (!SCALE_LEVELS.includes(level) || level === this.level) return false;
    this.level = level;
    this.apply();
    for (const listener of this.listeners) listener(this.level);
    return true;
  }

  onChange(listener) {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }
}
