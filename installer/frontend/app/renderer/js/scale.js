/**
 * scale.js —— 界面层缩放（下拉：自动检测 / 100% / 167% / 200%）
 *
 * 只有**一层**缩放（维护者 2026-10-04）：
 *   - 设备层（1x/2x/3x）不再单独生效 —— 两层相乘会把 4K 屏推到 4x；
 *   - 界面层这一层承担全部缩放，落到 CSS 的 `--ui-scale`。
 *
 * 「自动检测」的值由**启动器**算（`theme/device_scale.py: recommend_ui_scale_percent`，
 * 纯函数 + 单测：判据是「逻辑宽度落在 1536 附近」，2560×1600 → 167%），经
 * `window.mipl.config` 传进来。这里**不复制**那套判据 —— 两处各写一份必然漂；
 * 拿不到推荐值就退 100%（最保守的一档）。
 *
 * 纪律：**页面不许自己乘 `--ui-scale`** —— 只在 token 层用一次（`calc(… * var(--ui-scale))`）。
 */

export const SCALE_PERCENTS = [100, 167, 200];
export const SCALE_AUTO = 'auto';

export class ScaleController {
  /**
   * @param {object} options
   * @param {'auto'|number} options.mode    当前模式
   * @param {number} options.recommended    启动器算出的推荐百分比（0 = 没给）
   */
  constructor({ mode = SCALE_AUTO, recommended = 0 } = {}) {
    this.recommended = SCALE_PERCENTS.includes(recommended) ? recommended : 0;
    this.mode = mode === SCALE_AUTO || SCALE_PERCENTS.includes(mode) ? mode : SCALE_AUTO;
    this.listeners = new Set();
  }

  /** 当前生效的百分比（自动档 = 启动器给的推荐值）。 */
  get percent() {
    if (this.mode === SCALE_AUTO) return this.recommended || 100;
    return this.mode;
  }

  get isAuto() {
    return this.mode === SCALE_AUTO;
  }

  apply() {
    document.documentElement.style.setProperty('--ui-scale', String(this.percent / 100));
    document.documentElement.dataset.uiScale = String(this.percent);
  }

  setMode(mode) {
    if (mode !== SCALE_AUTO && !SCALE_PERCENTS.includes(mode)) return false;
    if (mode === this.mode) return false;
    this.mode = mode;
    this.apply();
    for (const listener of this.listeners) listener(this.percent, this.mode);
    return true;
  }

  onChange(listener) {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }
}
