/**
 * i18n.js —— 界面语言
 *
 * 唯一源：`renderer/i18n/{zh_CN,en_US}.json`（由 `tools/i18n.py` 从
 * docs/work/tech/09-安装器界面文案.md 生成，104 条界面文案 + 34 条时区名）。
 *
 * 纪律：**页面里不许出现裸字面量** —— 所有给人看的字都走 `t('key')`。
 * 键不存在时返回 `⟨key⟩` 并 warn（探针会把它判成失败，避免静默漏译）。
 */

export const LANGUAGES = ['zh_CN', 'en_US'];
export const LANGUAGE_LABEL = { zh_CN: '中', en_US: 'EN' };

export class I18n {
  constructor(lang = 'zh_CN') {
    this.language = lang;
    this.tables = {};
    this.listeners = new Set();
  }

  async load() {
    for (const code of LANGUAGES) {
      const url = new URL(`../i18n/${code}.json`, import.meta.url);
      const res = await fetch(url);
      if (!res.ok) throw new Error(`载入 ${url.pathname} 失败：HTTP ${res.status}`);
      this.tables[code] = await res.json();
    }
    if (!this.tables[this.language]) this.language = LANGUAGES[0];
    return this;
  }

  /** 取一条文案；`%1 %2 …` 用后面的参数替换。 */
  t(key, ...args) {
    const table = this.tables[this.language];
    const value = table ? table[key] : undefined;
    if (value === undefined) {
      console.warn(`[i18n] 缺键：${key}`);
      return `⟨${key}⟩`;
    }
    if (!args.length) return value;
    return value.replace(/%(\d)/g, (whole, index) => {
      const arg = args[Number(index) - 1];
      return arg === undefined ? whole : String(arg);
    });
  }

  has(key) {
    return Object.prototype.hasOwnProperty.call(this.tables[this.language] || {}, key);
  }

  get available() {
    return LANGUAGES.filter((code) => this.tables[code]);
  }

  setLanguage(code) {
    if (!this.tables[code] || code === this.language) return false;
    this.language = code;
    for (const listener of this.listeners) listener(code);
    return true;
  }

  /** 另一种语言（顶栏那个「中 / EN」按钮用）。 */
  get other() {
    return LANGUAGES.find((code) => code !== this.language) || this.language;
  }

  subscribe(listener) {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }
}
