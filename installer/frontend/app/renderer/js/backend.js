/**
 * backend.js —— 后端事实 → 界面数据的**唯一翻译层**（Issue #97）
 *
 * 后端的只读出口吐的是**事实**：字节数、布尔、`{id, offset}` 这样的平铺记录。
 * 页面要的是**界面形状**：`sizeLabel`、`recommended`、1–4 格信号、错误码对应的句子。
 * 这一层就是那道翻译，也是「后端不许认识界面词汇」的另一半 ——
 * 后端只提供 `signal: 0-100`，把它们切成四格是**界面**的决定，所以切在这里。
 *
 * ## 与 `mock.js` 的关系
 *
 * `Backend` 与 `Mock` **同形**：页面读的每一个键、调的每一个方法都一样。
 * 这样「换掉 Mock」才是一次替换而不是十二次改写，而且探针那套离屏自检
 * （`MIPL_PROBE=1`）继续跑 `Mock`，跑的是同一份契约 —— 契约一旦漂移，
 * 探针会先红。Mock 因此**只留离线自检**，不在产品路径上。
 *
 * ## 三条纪律
 *
 * 1. **不编造。** 取不到就留空、置 `false`、或把失败记进 `errors`——
 *    后端说 `model` 是空串时显示「（型号未报告）」是可以的（那是界面的措辞），
 *    但把它填成 `unknown device` 就是凭空造事实。
 * 2. **只显示能装的盘。** `disk.list_candidates()` 会连「正在使用」「太小」的盘
 *    一起报出来（`--print-disks` 要看得见全部）。那两类盘选中了也装不成 ——
 *    后端会在动盘前的守卫里拒绝。界面因此只列 `usable` 的，
 *    一个都列不出来时 `disk.empty`（「没有找到可用的磁盘」）说的正好是事实。
 *    全部候选留在 `allDisks` 里，供排查。
 * 3. **失败要说得出是哪一步。** 每个出口的失败都记进 `errors[名字]`，
 *    而不是静默变成空数组 —— 空数组和「这台机器真的没有无线网卡」长得一样。
 */

/** 语言页的显示名：**母语自称**，是数据不是审核稿文案（见 mock.js 的同一条纪律）。 */
const LOCALE_NAMES = {
  'zh_CN.UTF-8': '简体中文',
  'zh_TW.UTF-8': '繁體中文（台灣）',
  'zh_HK.UTF-8': '繁體中文（香港）',
  'en_US.UTF-8': 'English (US)',
  'en_GB.UTF-8': 'English (UK)',
  'ja_JP.UTF-8': '日本語',
  'ko_KR.UTF-8': '한국어',
  'de_DE.UTF-8': 'Deutsch',
  'fr_FR.UTF-8': 'Français',
  'es_ES.UTF-8': 'Español',
  'ru_RU.UTF-8': 'Русский',
};

/** 信号百分比 → 四格。`ceil` 而不是 `round`：1% 也是「有信号」，别画成零格。 */
export function signalBars(percent) {
  const value = Number(percent);
  if (!Number.isFinite(value) || value <= 0) return 0;
  return Math.min(4, Math.max(1, Math.ceil(value / 25)));
}

/** 后端的事实 → 页面读的盘记录。字段名与 `mock.js` 的 `CANDIDATE_DISKS` 完全一致。 */
export function diskRecord(candidate) {
  return {
    id: candidate.path,
    // 空型号是**真的读过而没有**（virtio-blk 的 sysfs 里就没有 model）。
    // 括号这句是界面的措辞，不是后端塞过来的字。
    model: candidate.model || '（型号未报告）',
    sizeBytes: candidate.size,
    sizeLabel: candidate.size_label,
    partitions: (candidate.partitions || []).length,
    // 「推荐」= 一块空的、内置的、能装的盘。可移动设备不做推荐（U 盘常常是安装介质本身），
    // 已有分区的盘也不推荐 —— 那块盘上有东西，值不值得擦该由人决定。
    recommended: Boolean(candidate.usable) && !candidate.removable && (candidate.partitions || []).length === 0,
  };
}

export function localeRecord(locale) {
  return { id: locale, name: LOCALE_NAMES[locale] || locale };
}

export class Backend {
  /**
   * @param {object} [options]
   * @param {object} [options.channel] `window.mipl.backend`；测试里注入替身
   */
  constructor({ channel } = {}) {
    this.channel = channel || (typeof window !== 'undefined' && window.mipl && window.mipl.backend) || null;

    /** 能装的盘（见文件头第 2 条）。页面读这个。 */
    this.disks = [];
    /** 全部候选，含不能装的 —— 只给排查用，页面不读。 */
    this.allDisks = [];
    /** 名单正在取的过程中：磁盘页据此画骨架屏。 */
    this.diskScanning = true;
    this.timezones = [];
    this.keymaps = [];
    this.locales = [];
    this.network = {
      connected: false,
      kind: 'wired',
      ipv4: '',
      ssid: '',
      scanning: false,
      connecting: false,
      failure: '',
      wifi: [],
    };
    /**
     * 摘要页要的「装成什么样」。
     *
     * **占位值与 `--print-plan` 的返回同形**（四个键一开始就都在），不是「先给两个、
     * 加载完再补」：形状中途变化的话，「Mock 与 Backend 同形」那条断言就只在某个
     * 时刻成立 —— 而那种断言最难查（有时绿有时红）。这里的值是**常量**
     * （ESP 大小、pacman.conf 的位置都是产品定死的），不是编出来的数字。
     */
    this.plan = { filesystem: 'ext4', boot: 'systemd-boot', esp: '512.0 MiB', pacman_conf: '/etc/pacman.conf' };
    /** 出口名 → 失败原因。空对象 = 全都取到了。 */
    this.errors = {};
    /** 键位预览的缓存：名字 → Promise（同一份映射不重复起 python）。 */
    this._keymapViews = new Map();
    /** 有没有一次 `load()` 跑完（探针与页面据此区分「还没取到」与「真的没有」）。 */
    this.loaded = false;
  }

  /* ------------------------------------------------------------ 取数 */

  async _query(name, options, stdinText) {
    if (!this.channel) {
      this.errors[name] = '没有后端通道（不在 Electron 里？）';
      return null;
    }
    const result = await this.channel.query(name, options, stdinText);
    if (!result || !result.ok) {
      this.errors[name] = (result && result.error) || '未知失败';
      return null;
    }
    delete this.errors[name];
    return result.data;
  }

  /**
   * 首帧之后拉一遍全部候选数据。**失败不抛** —— 一个出口取不到，
   * 不该让另外四个也拿不到（网络没起来时，磁盘页照样该能用）。
   */
  async load() {
    const [disks, timezones, locales, keymaps, network, plan] = await Promise.all([
      this._query('disks'),
      this._query('timezones'),
      this._query('locales'),
      this._query('keymaps'),
      this._query('network'),
      this._query('plan'),
    ]);

    if (disks) this._setDisks(disks.disks || []);
    if (timezones) this.timezones = timezones.timezones || [];
    if (locales) this.locales = (locales.locales || []).map(localeRecord);
    // 键位映射的显示名就是它的名字本身（`localectl` 的写法），没有第二套名字 ——
    // 旧 bridge 的 `keymap_records()` 也是原样返回名字，不编造译名。
    if (keymaps) this.keymaps = (keymaps.keymaps || []).map((name) => ({ id: name, name }));
    if (network) this._setNetwork(network);
    if (plan) this.plan = { ...this.plan, ...plan };

    this.diskScanning = false;
    this.loaded = true;
    return this;
  }

  _setDisks(candidates) {
    this.allDisks = candidates.map(diskRecord);
    // 只列能装的：选中一块装不成的盘，要等到动盘前的守卫才被拒绝 ——
    // 那时用户已经把账户、语言、键盘全填完了。后端照样报全部候选
    // （`--print-disks` 是排查用的），取舍发生在这里。
    this.disks = candidates.filter((candidate) => candidate.usable).map(diskRecord);
  }

  _setNetwork(state) {
    const wired = Boolean(state.wired);
    const online = Boolean(state.online);
    this.network = {
      ...this.network,
      connected: online,
      kind: wired ? 'wired' : 'wireless',
      // 无线的 IPv4 后端没报（`network.state()` 只给有线的），就不显示 ——
      // 拿有线的填上去会在只有 Wi-Fi 的机器上显示一个不存在的地址。
      ipv4: wired ? state.wired_ipv4 || '' : '',
      ssid: wired ? '' : state.wifi_ssid || '',
      failure: '',
    };
  }

  diskById(id) {
    return this.disks.find((disk) => disk.id === id) || null;
  }

  /* ------------------------------------------------------------ 磁盘 */

  async rescanDisks() {
    this.diskScanning = true;
    const data = await this._query('disks');
    if (data) this._setDisks(data.disks || []);
    this.diskScanning = false;
    return this.disks;
  }

  /* ------------------------------------------------------------ 网络 */

  async scanWifi() {
    this.network = { ...this.network, scanning: true, failure: '' };
    const data = await this._query('wifi');
    const wifi = ((data && data.wifi) || []).map((item) => ({
      ssid: item.ssid,
      signal: signalBars(item.signal),
      security: item.secured ? 'wpa2' : 'open',
    }));
    this.network = { ...this.network, scanning: false, wifi };
    return wifi;
  }

  /**
   * 连一个无线网络。**返回 bool**，失败原因写进 `network.failure`
   * （`auth` / `notFound` / `timeout` / `other`）—— 页面拿它查 `network.err.*`。
   */
  async connectWifi(ssid, password) {
    this.network = { ...this.network, connecting: true, failure: '' };
    const result = await this._query('connectWifi', { ssid }, `${password || ''}\n`);
    if (!result || result.ok !== true) {
      const reason = (result && result.reason) || 'other';
      this.network = { ...this.network, connecting: false, failure: reason };
      return false;
    }
    // 连上之后**重新问一次现状**，而不是把 ssid 拼成「已连接」：
    // 真正拿到地址之前就说连上了，是这句文案在替 NetworkManager 撒谎。
    const state = await this._query('network');
    if (state) this._setNetwork(state);
    this.network = { ...this.network, connecting: false, failure: '' };
    return true;
  }

  /* ------------------------------------------------------------ 键位预览 */

  /** 一份键位映射解析完的样子；失败回 null（页面据此不画图，不画一张空的）。 */
  keymapView(name) {
    if (!name) return Promise.resolve(null);
    if (!this._keymapViews.has(name)) {
      this._keymapViews.set(
        name,
        this._query('keymap', { name }).then((data) => data || null)
      );
    }
    return this._keymapViews.get(name);
  }

  /* ------------------------------------------------------------ 校验 */

  /**
   * 后端说了算的校验（`options.validate_hostname` 等）。回 `{ok, reason}`；
   * 后端够不着时回 `ok: null` —— **「问不到」不等于「不合法」**，
   * 页面据此放行，真正的守卫在 `pipeline.preflight()`（动盘之前）。
   */
  async check(name, value) {
    const result = await this._query(name, { value });
    if (!result) return { ok: null, reason: null };
    return { ok: Boolean(result.ok), reason: result.reason || null };
  }

  checkHostname(value) {
    return this.check('checkHostname', value);
  }

  checkLocale(value) {
    return this.check('checkLocale', value);
  }

  /* ------------------------------------------------------------ 安装 */

  /**
   * 开始装。进度通过 `onInstallEvent` 推回来。
   *
   * `secrets`（密码）从这里下去之后**只走子进程的 stdin**，绝不进 argv ——
   * argv 会留在进程列表与日志里。所以这个函数的返回值里也永远不会回显它们。
   */
  async startInstall(plan, secrets) {
    if (!this.channel || typeof this.channel.start !== 'function') {
      return { ok: false, error: '没有后端通道（不在 Electron 里？）' };
    }
    return this.channel.start(plan, secrets || {});
  }

  /** 请求取消。真正生效在**阶段之间**（退出码 130），见 `pipeline.run`。 */
  async cancelInstall() {
    if (!this.channel || typeof this.channel.cancel !== 'function') return { ok: false };
    return this.channel.cancel();
  }

  onInstallEvent(listener) {
    if (!this.channel || typeof this.channel.onEvent !== 'function') return () => {};
    return this.channel.onEvent(listener);
  }
}

/**
 * 界面上的选择 → `pipeline.Plan`（后端那份 dataclass 的同名字段）。
 *
 * 这是「12 页收集到的东西」与「后端要的东西」之间**唯一的翻译点**：
 * 页面只写 `setup.data`，翻译只发生在这里，所以加一个界面字段时，
 * 漏接的表现是「这个字段没进 Plan」，而不是散在十二个页面里各拼一半。
 *
 * 不出现在这里的字段（`packages_file` / `pacman_conf` / `steps` …）用后端的默认值 ——
 * 界面不暴露它们，就不该替它们编一个值。`hostname` 的回退是用户名：
 * 普通流程没有主机名那一页，但 `Plan.hostname` 是必填语义（后端会按 RFC 1123 校验）。
 */
export function buildPlan(setup) {
  const data = setup.data;
  return {
    disk: data.disk,
    hostname: data.hostname || data.user,
    user: data.user,
    locale: data.locale,
    timezone: data.timezone,
    keymap: data.keymap,
  };
}

/** `setup.data` → 两个密码。root 留空 = 不设（后端保持 root 锁定，只用 sudo）。 */
export function buildSecrets(setup) {
  const data = setup.data;
  return { user: data.password || '', rootPassword: data.rootPassword || '' };
}
