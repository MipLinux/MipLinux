/**
 * mock.js —— 候选数据替身（**只给离线自检用**，Issue #97）
 *
 * 产品路径上，候选数据来自真后端（`backend.js`）；这个类只在 `MIPL_PROBE=1`
 * 的离屏探针里出场。它因此有一个必须守住的职责：**与 `Backend` 同形**。
 * 探针跑的是同一份页面代码，契约一旦漂移（少一个键、方法签名变了），
 * 探针会先红 —— 这正是留着它的理由，不是历史包袱。
 *
 * 页面**只读**这里的数据；用户选择一律写 `setup.data`。本模块不持有任何用户状态。
 *
 * 纪律：
 *   - 名单类（disks / timezones / keymaps / locales）立即有值，页面不必写加载态；
 *   - 只有异步的两处用定时器：Wi-Fi 扫描与磁盘重扫（页面要能显示「扫描中」）；
 *   - **不写用户可见文案**：`keymaps/locales` 的 name 是母语自称（数据，不是审核稿文案），
 *     Wi-Fi 失败给的是**错误码**（`auth` / `notFound` / `timeout` / `other`），
 *     由页面拼成 `network.err.*` 的句子；时区名走 `timezone.name.<IANA>` 键。
 */

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

/**
 * 阶段名与「正在做什么」的离线替身。
 *
 * **与后端逐字同源**：`mipl_installer/events.py` 的 `PHASES` 与 `pipeline.py` 的
 * `PHASE_ACTIONS`。这里抄一份是为了让探针在没有后端的环境里也能跑完整条进度；
 * 真跑时这些字段由事件流带过来，页面用的是**翻译键**（`progress.phase.*`），
 * 不是这里的句子 —— 所以这份抄写不会漂成第二份用户可见文案。
 */
const PHASES = ['start', 'disk', 'packages', 'configure', 'boot'];
const PHASE_ACTIONS = {
  start: '正在准备安装环境',
  disk: '正在重新分区并创建文件系统',
  packages: '正在从镜像源下载并安装软件包',
  configure: '正在写入系统配置与账户',
  boot: '正在安装引导',
};

/**
 * 离线自检用的主键区（QWERTY）。
 *
 * 真数据来自 `--print-keymap`，那份是**跑得出来的**：`us`/`de`/`fr`/`dvorak`
 * 各自不同，一眼可辨。这里只要「能画出一张图」就够了 —— 探针验的是画法，
 * 不是某一份映射的内容。
 */
const MOCK_KEYMAP = {
  1: 'Escape', 41: 'grave', 2: 'one', 3: 'two', 4: 'three', 5: 'four', 6: 'five',
  7: 'six', 8: 'seven', 9: 'eight', 10: 'nine', 11: 'zero', 12: 'minus', 13: 'equal',
  14: 'BackSpace', 15: 'Tab',
  16: 'q', 17: 'w', 18: 'e', 19: 'r', 20: 't', 21: 'y', 22: 'u', 23: 'i', 24: 'o', 25: 'p',
  26: 'bracketleft', 27: 'bracketright', 28: 'Return',
  29: 'Control', 30: 'a', 31: 's', 32: 'd', 33: 'f', 34: 'g', 35: 'h', 36: 'j', 37: 'k',
  38: 'l', 39: 'semicolon', 40: 'apostrophe', 43: 'backslash',
  42: 'Shift', 86: 'less', 44: 'z', 45: 'x', 46: 'c', 47: 'v', 48: 'b', 49: 'n', 50: 'm',
  51: 'comma', 52: 'period', 53: 'slash', 54: 'Shift',
  56: 'Alt', 57: 'space', 100: 'AltGr',
};

/**
 * 换布局时**键位跟着换**的那几个（Dvorak 的上排，与真 `dvorak.map.gz` 一致）。
 *
 * 探针要验的是「图来自所选映射」，而不是「一张通用键盘图」——
 * 没有这一小张差异表，那个断言就只能验「图还在」，
 * 而「换布局图不变」正是这个功能最可能的坏法（把图画死在页面里）。
 */
const MOCK_KEYMAP_VARIANTS = {
  dvorak: {
    16: 'apostrophe', 17: 'comma', 18: 'period', 19: 'p', 20: 'y',
    21: 'f', 22: 'g', 23: 'c', 24: 'r', 25: 'l',
  },
};

const CANDIDATE_DISKS = [
  {
    id: '/dev/vda',
    model: 'QEMU HARDDISK',
    sizeBytes: 21474836480,
    sizeLabel: '20 GiB',
    partitions: 0,
    recommended: true,
  },
  {
    id: '/dev/sda',
    model: 'Samsung SSD 980 500GB',
    sizeBytes: 500107862016,
    sizeLabel: '465.8 GiB',
    partitions: 3,
    recommended: false,
  },
  {
    id: '/dev/nvme0n1',
    model: 'WD Black SN770 1TB',
    sizeBytes: 1000204886016,
    sizeLabel: '931.5 GiB',
    partitions: 1,
    recommended: false,
  },
];

/** Wi-Fi 候选（含一条中文 SSID：Live 里 `nmcli` 走 UTF-8，界面也得撑住）。 */
const CANDIDATE_WIFI = [
  { ssid: 'MipLab-5G', signal: 4, security: 'wpa2', password: 'miplinux' },
  { ssid: '家里的 Wi-Fi', signal: 3, security: 'wpa2', password: 'miplinux' },
  { ssid: 'Neighbour-2.4G', signal: 2, security: 'wpa2', password: 'wrong-password' },
  { ssid: 'Cafe Guest', signal: 1, security: 'open', password: '' },
];

/**
 * 键盘映射候选。顺序照 `localectl list-keymaps` —— **字母序**，所以默认值 `us`
 * 在最后一行，不在第一行。
 *
 * 三份名单都刻意**不**把默认值放在开头：真实的三个出口也不放
 * （`localectl` 按名字排、`zone1970.tab` 按大洲排、`/usr/share/i18n/SUPPORTED` 按
 * locale 名排）。默认值摆在第一行是**界面**的事（`shared.withDefaultFirst`），
 * 替身要是自己先摆好了，那条断言就成了在验替身。
 */
export const KEYMAPS = [
  { id: 'be-latin1', name: 'be-latin1' },
  { id: 'de', name: 'de' },
  { id: 'dvorak', name: 'dvorak' },
  { id: 'es', name: 'es' },
  { id: 'fr', name: 'fr' },
  { id: 'ru', name: 'ru' },
  { id: 'us', name: 'us' },
];

export const LOCALES = [
  { id: 'de_DE.UTF-8', name: 'Deutsch' },
  { id: 'en_US.UTF-8', name: 'English (US)' },
  { id: 'ja_JP.UTF-8', name: '日本語' },
  { id: 'zh_TW.UTF-8', name: '繁體中文' },
  { id: 'zh_CN.UTF-8', name: '简体中文' },
];

/** 时区候选：`offset` 是静态替身值（不带 UTC 前缀），名字走 JSON 里的 `timezone.name.<id>`。 */
export const TIMEZONES = [
  { id: 'Africa/Cairo', offset: '+02:00' },
  { id: 'Africa/Johannesburg', offset: '+02:00' },
  { id: 'America/Sao_Paulo', offset: '-03:00' },
  { id: 'America/Chicago', offset: '-06:00' },
  { id: 'America/Los_Angeles', offset: '-08:00' },
  { id: 'America/New_York', offset: '-05:00' },
  { id: 'Europe/London', offset: '+00:00' },
  { id: 'Europe/Berlin', offset: '+01:00' },
  { id: 'Europe/Paris', offset: '+01:00' },
  { id: 'Europe/Moscow', offset: '+03:00' },
  { id: 'Asia/Shanghai', offset: '+08:00' },
  { id: 'Asia/Hong_Kong', offset: '+08:00' },
  { id: 'Asia/Macau', offset: '+08:00' },
  { id: 'Asia/Taipei', offset: '+08:00' },
  { id: 'Asia/Tokyo', offset: '+09:00' },
  { id: 'Asia/Seoul', offset: '+09:00' },
  { id: 'Asia/Singapore', offset: '+08:00' },
  { id: 'Asia/Bangkok', offset: '+07:00' },
  { id: 'Asia/Jakarta', offset: '+07:00' },
  { id: 'Asia/Kolkata', offset: '+05:30' },
  { id: 'Asia/Kathmandu', offset: '+05:45' },
  { id: 'Asia/Dhaka', offset: '+06:00' },
  { id: 'Asia/Dubai', offset: '+04:00' },
  { id: 'Australia/Sydney', offset: '+10:00' },
  { id: 'Pacific/Auckland', offset: '+12:00' },
  { id: 'UTC', offset: '+00:00' },
];

export class Mock {
  constructor() {
    this.disks = [...CANDIDATE_DISKS];
    this.diskScanning = false;
    /** 名单类：页面直接读 `mock.timezones` / `mock.keymaps` / `mock.locales`。 */
    this.timezones = [...TIMEZONES];
    this.keymaps = [...KEYMAPS];
    this.locales = [...LOCALES];
    /**
     * 「这台机器现在的联网状况」—— 与 `network` **分开**。
     *
     * 真实后端里 `network` 是**上一次问回来的结果**（nmcli 那一刻说了什么），现状本身
     * 在 NetworkManager 那边。两者分开，才验得出「停留在网络页时，网通了界面会不会
     * 自己发现」：探针改这里的现状，等一轮轮询，看界面跟不跟上。
     */
    this.world = { connected: true, kind: 'wired', ipv4: '192.168.1.23', ssid: '' };
    /** 界面读的是这一份：现状经 `refreshNetwork()` / `connectWifi()` 落进来的结果。 */
    this.network = {
      ...this.world,
      scanning: false,
      connecting: false,
      failure: '',
      wifi: [],
    };
    /**
     * 安装计划摘要 —— 字段与 `queries.plan_summary()`（`--print-plan`）**逐字一致**。
     *
     * 刻意**不**放包数与下载量：那要读包清单、真的去问仓库（M4 的事）。
     * 编一个「412 个包 / 1.9 GiB」摆上去，就是界面在描述它没做过的事 ——
     * 而这正是这一层存在的理由（同形），不是可以各自发挥的地方。
     */
    this.plan = { filesystem: 'ext4', boot: 'systemd-boot', esp: '512.0 MiB', pacman_conf: '/etc/pacman.conf' };
    /** 装不装得成这件事在这里不重要（探针不装盘），但接口要与 Backend 同形。 */
    this.errors = {};
    this._installListeners = new Set();
    this._installTimers = [];
  }

  /* ---------------------------------------------------------- 安装事件流 */

  /**
   * 假的安装：按 `events.PHASES` 的顺序推一串事件，形状与 `events.JsonReporter`
   * 的行**逐字一致**（`kind` / `phase` / `percent` / `detail` / `step_id` /
   * `step` / `total`）。
   *
   * 细进度也要假戏真做：每个阶段推几个**真实的 step_id**，packages 那一步还带上
   * `(n/m)` 计数 —— 否则探针验的是一张空壳进度页，而真机上它画的正是这些东西。
   *
   * 慢到足够被看见：探针每页等 200ms，太快的话进度页会在截图前就跳走 ——
   * 那样「渲染了进度页」这条断言就变成了在测运气。
   */
  async startInstall() {
    this.stopInstall();
    const emit = (record) => {
      for (const listener of this._installListeners) listener(record);
    };
    emit({ kind: 'hello', protocol: 2, version: 'mock' });

    // [阶段, 子步骤 id, step, total]；`step` 为空 = 这一步数不出细进度（不确定态）
    const script = [
      ['disk', 'wait-devices'], ['disk', 'wipe'], ['disk', 'partition'], ['disk', 'mount'],
      ['packages', 'keyring-init'], ['packages', 'keyring-populate'],
      ['packages', 'install', 1, 12], ['packages', 'install', 5, 12], ['packages', 'install', 12, 12],
      ['configure', 'user'], ['configure', 'user-password'], ['configure', 'initramfs'],
      ['boot', 'bootctl'], ['boot', 'entry'], ['boot', 'verify'],
    ];

    let at = 400;
    let lastPhase = null;
    for (const [phase, stepId, step, total] of script) {
      // 替身不许自己发明阶段：阶段名与后端 `events.PHASES` 同源（见文件头）
      if (!PHASES.includes(phase)) throw new Error(`mock 的步骤表用了未知阶段：${phase}`);
      if (phase !== lastPhase) {
        const message = PHASE_ACTIONS[phase];
        this._installTimers.push(setTimeout(() => {
          emit({ kind: 'event', phase, message, percent: null, detail: null,
                 step_id: null, step: null, total: null });
        }, at));
        lastPhase = phase;
        at += 160;
      }
      this._installTimers.push(setTimeout(() => {
        emit({
          kind: 'event', phase, message: PHASE_ACTIONS[phase], percent: null, detail: null,
          step_id: stepId, step: step ?? null, total: total ?? null,
        });
      }, at));
      at += 180;
    }

    this._installTimers.push(setTimeout(() => {
      emit({ kind: 'event', phase: 'done', message: '装完了', percent: 100, detail: null,
             step_id: null, step: null, total: null });
      emit({ kind: 'end', code: 0 });
      this._installTimers.push(
        setTimeout(() => emit({ kind: 'exit', code: 0, cancelled: this._cancelled === true }), 200)
      );
    }, at + 300));

    this._cancelled = false;
    return { ok: true };
  }

  async cancelInstall() {
    this._cancelled = true;
    this.stopInstall();
    return { ok: true };
  }

  /**
   * 「卸载 /mnt」的离线替身（`Backend.unmountTarget` 的同形实现）。
   *
   * 离屏探针里 `/mnt` 当然没挂着，所以回「卸好了」—— 探针要验的是**按钮接上了、
   * 按下去有反馈**，不是真的去卸谁的东西。
   */
  async unmountTarget() {
    return { ok: true, mounted: false };
  }

  onInstallEvent(listener) {
    this._installListeners.add(listener);
    return () => this._installListeners.delete(listener);
  }

  stopInstall() {
    for (const timer of this._installTimers) clearTimeout(timer);
    this._installTimers = [];
  }

  /** 键位预览的离线替身（`Backend.keymapView` 的同形实现）。 */
  async keymapView(name) {
    if (!name) return null;
    const overrides = MOCK_KEYMAP_VARIANTS[name] || {};
    return {
      name,
      source: `mock:${name}`,
      lines: [],
      includes: [],
      keys: Object.entries(MOCK_KEYMAP).map(([code, plain]) => ({
        code: Number(code),
        plain: overrides[code] || plain,
        shift: '',
      })),
    };
  }

  async checkHostname() {
    // 离线自检不判主机名：返回「问不到」，页面据此放行（真守卫在 pipeline.preflight）
    return { ok: null, reason: null };
  }

  diskById(id) {
    return this.disks.find((disk) => disk.id === id) || null;
  }

  async rescanDisks() {
    this.diskScanning = true;
    await sleep(700);
    this.disks = [...CANDIDATE_DISKS];
    this.diskScanning = false;
    return this.disks;
  }

  /**
   * 扫 Wi-Fi。`rescan` 在替身里没有区别（没有真的 NetworkManager 可问），
   * 参数留着只为与 `Backend.scanWifi()` **同形** —— 页面两边都传 `{rescan:true}`。
   */
  async scanWifi({ rescan = false } = {}) {
    void rescan;
    this.network = { ...this.network, scanning: true, failure: '' };
    await sleep(900);
    this.network = { ...this.network, scanning: false, wifi: CANDIDATE_WIFI.map((w) => ({ ...w })) };
    return this.network.wifi;
  }

  /** 把「现状」读进 `network`（真实后端里这一步是再起一次 `--print-network`）。 */
  async refreshNetwork() {
    this.network = { ...this.network, ...this.world };
    return this.network;
  }

  /**
   * 连接 Wi-Fi：密码错 → `auth`；不存在的 SSID → `notFound`；其余随机成 `timeout`。
   * 错误码是数据，句子由页面用 `network.err.*` 拼。
   */
  async connectWifi(ssid, password) {
    const target = this.network.wifi.find((w) => w.ssid === ssid);
    this.network = { ...this.network, connecting: true, failure: '' };
    await sleep(1100);
    if (!target) {
      this.network = { ...this.network, connecting: false, failure: 'notFound' };
      return false;
    }
    if (target.security !== 'open' && target.password !== password) {
      this.network = { ...this.network, connecting: false, failure: 'auth' };
      return false;
    }
    // 连上 = 现状变了，再走一次「问回来」——与 Backend.connectWifi 同一条路
    this.world = { connected: true, kind: 'wireless', ssid, ipv4: '192.168.1.23' };
    await this.refreshNetwork();
    this.network = { ...this.network, connecting: false, failure: '' };
    return true;
  }

  /**
   * 「网线插上了」/「拔掉了」：**只动现状，不动 `network`**。
   *
   * 这正是要模拟的那件事：真实后端里它发生在 nmcli 那边，界面要下一次
   * `refreshNetwork()`（网络页的轮询）才知道。探针靠这个时间差验轮询。
   */
  connectWired() {
    this.world = { connected: true, kind: 'wired', ssid: '', ipv4: '192.168.1.23' };
  }

  disconnectNetwork() {
    this.world = { connected: false, kind: 'wired', ssid: '', ipv4: '' };
  }
}
