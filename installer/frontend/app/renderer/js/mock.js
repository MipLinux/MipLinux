/**
 * mock.js —— 候选数据替身（真后端耦合层是后续独立工作）
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

export const KEYMAPS = [
  { id: 'us', name: 'English (US)' },
  { id: 'de', name: 'Deutsch' },
  { id: 'fr', name: 'Français' },
  { id: 'es', name: 'Español' },
  { id: 'ru', name: 'Русский' },
  { id: 'be-latin1', name: 'Belge (latin1)' },
];

export const LOCALES = [
  { id: 'zh_CN.UTF-8', name: '简体中文' },
  { id: 'en_US.UTF-8', name: 'English (US)' },
  { id: 'zh_TW.UTF-8', name: '繁體中文' },
  { id: 'ja_JP.UTF-8', name: '日本語' },
  { id: 'de_DE.UTF-8', name: 'Deutsch' },
];

/** 时区候选：`offset` 是静态替身值（不带 UTC 前缀），名字走 JSON 里的 `timezone.name.<id>`。 */
export const TIMEZONES = [
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
  { id: 'Europe/London', offset: '+00:00' },
  { id: 'Europe/Berlin', offset: '+01:00' },
  { id: 'Europe/Paris', offset: '+01:00' },
  { id: 'Europe/Moscow', offset: '+03:00' },
  { id: 'America/New_York', offset: '-05:00' },
  { id: 'America/Chicago', offset: '-06:00' },
  { id: 'America/Los_Angeles', offset: '-08:00' },
  { id: 'America/Sao_Paulo', offset: '-03:00' },
  { id: 'Africa/Cairo', offset: '+02:00' },
  { id: 'Africa/Johannesburg', offset: '+02:00' },
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
    this.network = {
      connected: true,
      kind: 'wired',
      ipv4: '192.168.1.23',
      ssid: '',
      scanning: false,
      connecting: false,
      failure: '',
      wifi: [],
    };
    /** 安装计划摘要（真后端接上后由 packages.py 给出）。 */
    this.plan = { packages: 412, download: '1.9 GiB', filesystem: 'ext4', boot: 'systemd-boot' };
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

  async scanWifi() {
    this.network = { ...this.network, scanning: true, failure: '' };
    await sleep(900);
    this.network = { ...this.network, scanning: false, wifi: CANDIDATE_WIFI.map((w) => ({ ...w })) };
    return this.network.wifi;
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
    this.network = {
      ...this.network,
      connected: true,
      kind: 'wireless',
      ssid,
      ipv4: '192.168.1.23',
      connecting: false,
      failure: '',
    };
    return true;
  }

  connectWired() {
    this.network = {
      ...this.network,
      connected: true,
      kind: 'wired',
      ssid: '',
      ipv4: '192.168.1.23',
      connecting: false,
      failure: '',
    };
  }

  disconnectNetwork() {
    this.network = {
      ...this.network,
      connected: false,
      kind: 'wired',
      ssid: '',
      ipv4: '',
      failure: '',
    };
  }
}
