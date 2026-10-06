/**
 * 后端适配层（`renderer/js/backend.js`）与键位图（`renderer/js/keymap-rows.js`）。
 *
 * 这一层是**界面读到的字段名的唯一来源**，所以这里钉的是：
 *   - 后端吐的**事实**（字节数、`secured: true`、0–100 的信号）→ 页面读的**形状**；
 *   - 不编造：取不到就是空，不给一个看起来合理的默认值。
 *
 * 这些断言以前是 Python 侧的 `installer/tests/test_records.py` 与
 * `test_qemu_scenario.py` —— 那两份测的是**已随 #74 移出**的 `frontend/bridge/`
 * （Qt 时代的 Python 翻译层）。翻译层搬到渲染层之后，断言也跟着搬到这里（Issue #97）。
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { execFile } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { promisify } from 'node:util';

import {
  Backend,
  buildPlan,
  buildSecrets,
  diskRecord,
  localeRecord,
  signalBars,
} from '../renderer/js/backend.js';
import { buildRows, hasAnyKey, keycapLabel, MAIN_ROWS } from '../renderer/js/keymap-rows.js';
import { Mock } from '../renderer/js/mock.js';

const run = promisify(execFile);
const BACKEND_DIR = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..', '..', 'backend');

/* ------------------------------------------------------------ 同形 */

test('Mock 与 Backend 同形 —— 探针跑的因此是产品代码的契约', () => {
  // 「Mock 只给离屏探针、产品路径读真后端」这个安排成立的前提就是**同形**：
  // 页面读的每个键、调的每个方法都一样。不同形的话，探针验的是一套页面代码、
  // 真机跑的是另一套 —— 那探针的绿就一文不值了。
  const mock = new Mock();
  const real = new Backend({ channel: null });

  for (const field of ['disks', 'diskScanning', 'timezones', 'keymaps', 'locales', 'network', 'plan']) {
    assert.equal(
      typeof mock[field],
      typeof real[field],
      `${field} 两边不一致：Mock=${typeof mock[field]} Backend=${typeof real[field]}`
    );
  }

  for (const name of ['diskById', 'rescanDisks', 'scanWifi', 'connectWifi', 'refreshNetwork', 'keymapView',
    'checkHostname', 'onInstallEvent', 'startInstall', 'cancelInstall']) {
    assert.equal(
      typeof mock[name],
      typeof real[name],
      `${name} 两边不一致：Mock=${typeof mock[name]} Backend=${typeof real[name]}`
    );
  }

  // 嵌套结构也得同形：页面读的是 network.connected / kind / ipv4 / ssid / wifi…
  assert.deepEqual(Object.keys(mock.network).sort(), Object.keys(real.network).sort());
  // 摘要页读 plan.filesystem / plan.boot
  assert.deepEqual(Object.keys(mock.plan).sort(), Object.keys(real.plan).sort());
  // 磁盘页读 id / model / sizeLabel / partitions / recommended
  assert.deepEqual(Object.keys(mock.disks[0]).sort(), Object.keys(diskRecord(candidate())).sort());
});

/* ------------------------------------------------------------ 磁盘 */

/** 后端 `--print-disks` 报的一块盘（字段名照抄 `queries.candidate_dict`）。 */
function candidate(overrides = {}) {
  return {
    path: '/dev/vda',
    model: '',
    size: 42949672960,
    size_label: '40.0 GiB',
    removable: false,
    in_use: false,
    table_type: null,
    too_small: false,
    usable: true,
    partitions: [],
    ...overrides,
  };
}

test('盘的字段名与 Mock 完全一致（页面读的键一个不差）', () => {
  const record = diskRecord(candidate());
  assert.deepEqual(Object.keys(record).sort(), ['id', 'model', 'partitions', 'recommended', 'sizeBytes', 'sizeLabel']);
  assert.equal(record.id, '/dev/vda');
  assert.equal(record.sizeLabel, '40.0 GiB');
  assert.equal(record.partitions, 0);
});

test('virtio-blk 没有型号时显示「（型号未报告）」，但绝不编一个型号出来', () => {
  // QEMU 的 virtio-blk 在 sysfs 里就是没有 model；`vendor` 是 PCI 厂商号 0x1af4，
  // 曾经被当成型号读出来过（用户看到它学不到任何东西，比空着更糟）
  assert.equal(diskRecord(candidate({ model: '' })).model, '（型号未报告）');
  assert.equal(diskRecord(candidate({ model: 'QEMU HARDDISK' })).model, 'QEMU HARDDISK');
});

test('「推荐」= 空的、内置的、能装的盘', () => {
  assert.equal(diskRecord(candidate()).recommended, true, '空的内置盘应当被推荐（QEMU 那一轮就靠它）');
  assert.equal(diskRecord(candidate({ partitions: [{ number: 1 }] })).recommended, false, '盘上有东西就别替他决定擦');
  assert.equal(diskRecord(candidate({ removable: true })).recommended, false, 'U 盘常常就是安装介质本身');
});

test('只列能装的盘，全部候选另存一份（页面只读前者）', async () => {
  const backend = new Backend({ channel: { query: async () => ({ ok: true, data: { disks: [
    candidate({ path: '/dev/vda' }),
    candidate({ path: '/dev/sda', in_use: true, usable: false }),
    candidate({ path: '/dev/sdb', too_small: true, usable: false }),
  ] } }) } });
  await backend.rescanDisks();
  assert.deepEqual(backend.disks.map((disk) => disk.id), ['/dev/vda']);
  assert.deepEqual(backend.allDisks.map((disk) => disk.id), ['/dev/vda', '/dev/sda', '/dev/sdb']);
});

/* ------------------------------------------------------------ 网络 */

test('信号百分比 → 四格：1% 也算有信号，100% 是满格', () => {
  assert.equal(signalBars(0), 0);
  assert.equal(signalBars(1), 1, '有信号就不该画成零格');
  assert.equal(signalBars(25), 1);
  assert.equal(signalBars(26), 2);
  assert.equal(signalBars(100), 4);
  assert.equal(signalBars(undefined), 0);
});

test('无线的 IPv4 报不出来就留空 —— 不拿有线的地址顶上', async () => {
  const channel = {
    query: async (name) => {
      if (name === 'network') {
        return {
          ok: true,
          data: { online: true, wired: false, wired_interface: '', wired_ipv4: '', wifi_interface: 'wlan0', wifi_ssid: 'MyNet' },
        };
      }
      if (name === 'wifi') {
        return { ok: true, data: { wifi: [{ ssid: 'MyNet', signal: 80, secured: true }] } };
      }
      // `--connect-wifi` 是唯一有副作用的出口：它用「查询成功 + ok:false」表达连不上
      return { ok: true, data: { ok: true, reason: null, message: '' } };
    },
  };
  const backend = new Backend({ channel });
  await backend.scanWifi();
  await backend.connectWifi('MyNet', 'hunter2');
  assert.equal(backend.network.connected, true);
  assert.equal(backend.network.kind, 'wireless');
  assert.equal(backend.network.ssid, 'MyNet');
  assert.equal(backend.network.ipv4, '', '后端没给无线的地址，就该是空的');
});

test('Wi-Fi 失败按错误码走，不把 nmcli 的英文原文透给页面', async () => {
  const channel = {
    query: async (name) => {
      if (name === 'connectWifi') {
        return { ok: true, data: { ok: false, reason: 'auth', message: 'Secrets were required, but not provided' } };
      }
      return { ok: true, data: {} };
    },
  };
  const backend = new Backend({ channel });
  assert.equal(await backend.connectWifi('MyNet', 'wrong'), false);
  assert.equal(backend.network.failure, 'auth');
  assert.equal(backend.network.connecting, false);
});

test('「重新扫描」必须让 NetworkManager 真扫一遍，不能拿缓存再画一次', async () => {
  const seen = [];
  const backend = new Backend({
    channel: {
      query: async (name, options) => {
        seen.push([name, options]);
        return { ok: true, data: { wifi: [] } };
      },
    },
  });
  await backend.scanWifi(); // 进页面那次：用 NM 的缓存，不让人干等
  assert.deepEqual(seen.at(-1), ['wifi', undefined]);
  await backend.scanWifi({ rescan: true }); // 点「重新扫描」：`--print-wifi --rescan`
  assert.deepEqual(seen.at(-1), ['wifi', { rescan: true }]);
});

test('停留网络页时的轮询能发现「外面通了」；但绝不抹掉上一次连接失败的原因', async () => {
  // 现状在对面变（真机上就是网线插上了）。`network` 是**上一次问回来的结果**，
  // 界面要靠 `refreshNetwork()` 才知道 —— 这正是网络页那 3 秒一次轮询做的事
  let online = false;
  const backend = new Backend({
    channel: {
      query: async (name) => {
        if (name === 'network') {
          return {
            ok: true,
            data: {
              online,
              wired: true,
              wired_interface: 'eth0',
              wired_ipv4: online ? '10.0.2.15' : '',
              wifi_interface: '',
              wifi_ssid: '',
            },
          };
        }
        return { ok: true, data: { ok: false, reason: 'auth', message: 'secrets were required' } };
      },
    },
  });
  await backend.refreshNetwork();
  assert.equal(backend.network.connected, false);

  // 一次失败的连接尝试：原因要留在界面上等人读
  await backend.connectWifi('MyNet', 'wrong');
  assert.equal(backend.network.failure, 'auth');

  online = true;
  await backend.refreshNetwork();
  assert.equal(backend.network.connected, true, '轮询要把「通了」反映出来，否则人卡在网络页出不去');
  assert.equal(backend.network.ipv4, '10.0.2.15');
  assert.equal(backend.network.failure, 'auth', '失败原因是连接尝试的结果、不是现状的一部分 —— 轮询不许抹掉它');
});

/* ------------------------------------------------------------ 名单与校验 */

test('语言的显示名是母语自称；表外的一律用 locale 自己当名字', () => {
  assert.deepEqual(localeRecord('ja_JP.UTF-8'), { id: 'ja_JP.UTF-8', name: '日本語' });
  assert.deepEqual(localeRecord('xx_YY.UTF-8'), { id: 'xx_YY.UTF-8', name: 'xx_YY.UTF-8' });
});

test('校验：后端说不行才不行；问不到（ok: null）不算错', async () => {
  const okChannel = { query: async () => ({ ok: true, data: { ok: false, reason: 'format' } }) };
  assert.deepEqual(await new Backend({ channel: okChannel }).checkHostname('-bad-'), { ok: false, reason: 'format' });

  const dead = new Backend({ channel: { query: async () => ({ ok: false, error: '起不了后端' }) } });
  assert.deepEqual(await dead.checkHostname('mipl'), { ok: null, reason: null });
});

test('取不到的出口记进 errors，而不是静默变成空数组', async () => {
  const backend = new Backend({ channel: { query: async () => ({ ok: false, error: '没有 nmcli' }) } });
  await backend.load();
  assert.equal(backend.locales.length, 0);
  assert.equal(backend.errors.locales, '没有 nmcli', '空数组和「这台机器真的没有无线网卡」长得一样');
});

/* ------------------------------------------------------------ Plan */

test('Plan 的字段名与后端 dataclass 对得上', () => {
  const plan = buildPlan({
    data: { disk: '/dev/vda', user: 'mipl', hostname: '', locale: 'ja_JP.UTF-8', timezone: 'Asia/Tokyo', keymap: 'de' },
  });
  assert.deepEqual(plan, {
    disk: '/dev/vda',
    hostname: 'mipl', // 普通流程没有主机名那一页：回退到用户名
    user: 'mipl',
    locale: 'ja_JP.UTF-8',
    timezone: 'Asia/Tokyo',
    keymap: 'de',
  });
  // 界面不暴露的字段（packages_file / steps / no_nvram …）不许在这里编一个值
  assert.deepEqual(Object.keys(plan).sort(), ['disk', 'hostname', 'keymap', 'locale', 'timezone', 'user']);
});

test('密码只进 secrets，不进 Plan（Plan 会被写进日志与命令行）', () => {
  const setup = { data: { disk: '/dev/vda', user: 'mipl', password: 'hunter2', rootPassword: 'rootpw' } };
  const plan = buildPlan(setup);
  assert.ok(!JSON.stringify(plan).includes('hunter2'));
  assert.deepEqual(buildSecrets(setup), { user: 'hunter2', rootPassword: 'rootpw' });
  // root 留空 = 不设，后端据此保持 root 锁定
  assert.deepEqual(buildSecrets({ data: { password: 'hunter2', rootPassword: '' } }), {
    user: 'hunter2',
    rootPassword: '',
  });
});

test('没有后端通道时不抛，回一句能显示的话', async () => {
  const backend = new Backend({ channel: null });
  assert.equal(await backend.checkHostname('mipl').then((r) => r.ok), null);
  const started = await backend.startInstall({ disk: '/dev/vda' }, {});
  assert.equal(started.ok, false);
  assert.match(started.error, /后端通道/);
});

/* ------------------------------------------------------------ 键位图 */

test('键位名 → 键帽上的字；认不出来就原样显示', () => {
  assert.equal(keycapLabel('minus'), '-');
  assert.equal(keycapLabel('bracketleft'), '[');
  assert.equal(keycapLabel('Return'), '⏎');
  assert.equal(keycapLabel('space'), '');
  assert.equal(keycapLabel(''), '');
  assert.equal(keycapLabel('VoidSymbol'), 'VoidSymbol', '看不懂的名字也比编一个强');
});

test('数字键的 keysym 是单词，键帽上要画成数字', () => {
  // `man keymaps`：xmodmap 的 '0'…'9' 记法改成了 zero/one/… 以免与数字记法撞车。
  // 漏了这张映射，整排会画成 `one two three` —— 图能看，但没人认得出那是数字排。
  const row = buildRows([
    { code: 2, plain: 'one', shift: 'exclam' },
    { code: 3, plain: 'two', shift: 'quotedbl' },
    { code: 11, plain: 'zero', shift: 'parenright' },
  ]).flat();
  const label = (code) => row.find((cell) => cell.code === code).label;
  assert.equal(label(2), '1');
  assert.equal(label(3), '2');
  assert.equal(label(11), '0');
});

test('主键区：映射里没有的键留空位，不整排错位', () => {
  const rows = buildRows([{ code: 16, plain: 'q', shift: '' }]);
  assert.equal(rows.length, MAIN_ROWS.length);
  const row = rows.find((cells) => cells.some((cell) => cell.code === 16));
  assert.equal(row.find((cell) => cell.code === 16).label, 'q');
  assert.equal(row.find((cell) => cell.code === 17).label, '', '没写的键留空，不是跳过');
  assert.ok(!hasAnyKey(buildRows([])), '一个键都没解析出来时不该画一张空键盘');
  assert.ok(hasAnyKey(rows));
});

test('键帽宽度按物理排布给：空格最宽，Shift / Backspace 次之', () => {
  const rows = buildRows([
    { code: 57, plain: 'space', shift: '' },
    { code: 42, plain: 'Shift', shift: '' },
    { code: 16, plain: 'q', shift: '' },
  ]);
  const flat = rows.flat();
  const width = (code) => flat.find((cell) => cell.code === code).width;
  assert.ok(width(57) > width(42));
  assert.ok(width(42) > width(16));
  assert.equal(width(16), 1);
});

test('Shift 层只画映射里真写了的那一列（不从小写推导大写）', () => {
  // `man keymaps`：生效的是「修饰键权重之和」指向的那一列；文件只写了一列时，
  // 其余列由**内核默认表**兜底 —— 那一列不在文件里，这一层看不到，就不能画。
  const withShift = buildRows([{ code: 2, plain: 'one', shift: 'exclam' }]).flat();
  assert.equal(withShift.find((cell) => cell.code === 2).shiftLabel, '!', 'exclam 画成 !，不是把 keysym 抄上去');

  const plainOnly = buildRows([{ code: 16, plain: 'q', shift: '' }]).flat();
  assert.equal(plainOnly.find((cell) => cell.code === 16).label, 'q');
  assert.equal(
    plainOnly.find((cell) => cell.code === 16).shiftLabel,
    '',
    '文件没写 Shift 列 → 键帽上就不该出现 Q'
  );
});

/* ------------------------------------------------------------ 真数据（跑后端） */

/**
 * 这一节真的起一次 `python3 -m mipl_installer --print-keymap <名字>`。
 *
 * 为什么值得让 Node 测试依赖 python3：这一层是**界面与后端的接缝**，
 * 接缝两边各自绿、合起来错，是这类改动最典型的坏法。而且它不需要 root、
 * 不需要 Live，只读 `/usr/share/kbd/keymaps` —— 与本仓库其它非 root 验收同级。
 * python3 与 kbd 是安装器的硬依赖，缺了就是环境不对，所以这里**响亮地失败**，
 * 不静默跳过（静默跳过等于给一条假绿）。
 */
async function realKeymap(name) {
  const { stdout } = await run('python3', ['-m', 'mipl_installer', `--print-keymap=${name}`], {
    cwd: BACKEND_DIR,
    env: { ...process.env, PYTHONPATH: BACKEND_DIR },
    maxBuffer: 32 * 1024 * 1024,
  });
  return JSON.parse(stdout);
}

test('真映射：us / de / fr / dvorak 画出来一眼可辨（不是同一张通用键盘图）', async () => {
  const seen = new Map();
  for (const name of ['us', 'de', 'fr', 'dvorak']) {
    const view = await realKeymap(name);
    const rows = buildRows(view.keys);
    assert.ok(hasAnyKey(rows), `${name} 应当解析出键位`);
    // 字母排的签名：主键区所有键帽上的字连起来
    seen.set(name, rows.flat().map((cell) => cell.label).join('|'));
    // `--print-keymap` 的 `lines` 是原文逐字 —— 解析没吃掉东西这件事是可自证的
    assert.ok(view.lines.length > 20, `${name} 应当带回原文行`);
  }
  assert.equal(new Set(seen.values()).size, 4, '四份布局必须画出四张不同的图');
});

test('真映射：同一排上 de 是 q、fr 是 a、dvorak 是撇号（德语/法语/德沃夏克的分水岭）', async () => {
  const at16 = async (name) => {
    const view = await realKeymap(name);
    const cell = buildRows(view.keys).flat().find((item) => item.code === 16);
    return cell.label;
  };
  assert.equal(await at16('us'), 'q');
  assert.equal(await at16('de'), 'q', '德语也是 QWERTZ 的上排首键');
  assert.equal(await at16('fr'), 'a', '法语是 AZERTY');
  assert.equal(await at16('dvorak'), "'", '德沃夏克把那一位给了撇号');

  // 数字排画成数字（keysym 是 `one`/`two` 这种单词）
  const view = await realKeymap('de');
  const rows = buildRows(view.keys).flat();
  assert.equal(rows.find((cell) => cell.code === 2).label, '1');
  assert.equal(rows.find((cell) => cell.code === 2).shiftLabel, '!');
});
