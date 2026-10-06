/**
 * 网络页（1）—— 状态 + Wi-Fi 选择 + 连接
 *
 * 门禁：没联网就过不去（`network.needNetwork`）。失败用**错误码**拼句子：
 * 后端只给 `auth` / `notFound` / `timeout` / `other`，句子一律走 `network.err.*`。
 *
 * 这一页的现状**不能只读一次**：网线是人在装的途中插上的，NetworkManager 也会自己
 * 连上，所以停留期间每 `POLL_MS` 问一次（`onEnter` / `onLeave` 管生灭），
 * 列表下方另有一枚手动「重新扫描」（`--rescan`，让 NM 真扫一遍）。
 */

import { h, attachScrollFade } from '../dom.js';
import {
  pageHead,
  panel,
  badge,
  button,
  field,
  textInput,
  option,
  emptyState,
  callout,
  listBox,
  divider,
} from '../components.js';
import { staggerIn } from '../motion.js';

const FAILURE_KEY = {
  auth: 'network.err.auth',
  notFound: 'network.err.notFound',
  timeout: 'network.err.timeout',
  other: 'network.err.other',
};

function signalBars(level) {
  return h('span', { class: 'net-item__signal', dataset: { level: String(level) } }, [
    h('i'),
    h('i'),
    h('i'),
    h('i'),
  ]);
}

async function connect(ctx, item) {
  const { setup, backend } = ctx;
  await backend.connectWifi(item.ssid, setup.data.wifiPassword || '');
  ctx.rerender();
}

/** 停留本页时多久问一次联网现状。只问 `network`（很快），不扫 Wi-Fi（那个要几秒）。 */
const POLL_MS = 3000;

/**
 * 画面用到的联网事实。**只有它们变了才重画** —— 每 3 秒无条件重画的话，
 * 人正在输入 Wi-Fi 密码时会被抢走焦点。
 */
function snapshot(net) {
  return [net.connected, net.kind, net.ipv4, net.ssid, net.connecting, net.failure].join('\u0000');
}

let poll = null;

function stopPoll() {
  if (poll) clearInterval(poll);
  poll = null;
}

/**
 * 停留期间定时问一次现状：网线插上了、NetworkManager 自己连上了，界面都得跟上。
 *
 * 为什么必须有它：现状原本只在开工那一次读（`Backend.load()`），进来之后网通了界面
 * 也不知道 —— 而这一页没连上就不让往下走，于是人卡在这里出不去（维护者 2026-10-05）。
 */
function startPoll(ctx) {
  stopPoll();
  poll = setInterval(async () => {
    const net = ctx.backend.network;
    // 正在连、正在扫的时候不插一脚：那两条路自己会问一次，抢着问只会读到中间态
    if (net.connecting || net.scanning) return;
    const before = snapshot(net);
    await ctx.backend.refreshNetwork();
    // 问回来的这一趟可能已经不在网络页了（人点了「下一步」）——
    // 不在就别去重画别人的页面。判据与进度页推下一步那条一样，都用 `stepId`。
    if (ctx.setup.stepId !== 'network') return;
    if (snapshot(ctx.backend.network) !== before) ctx.rerender();
  }, POLL_MS);
}

/** 重新扫描：让 NetworkManager **真扫一遍**（`--rescan`），不是把缓存再画一次。 */
async function rescan(ctx) {
  await ctx.backend.refreshNetwork(); // 现状很快，先问它
  // 起手**不 await**：`Backend.scanWifi()` 一进去就置上 `scanning`，紧接着重画才画得出
  // 「正在扫描…」；直接 await 的话这几秒界面一动不动，人会以为没点上。
  const scanning = ctx.scanWifi({ rescan: true }); // 它扫完自己会再重画一次
  ctx.rerender();
  await scanning;
}

export default {
  id: 'network',
  wantsWifiScan: true,

  render(ctx) {
    const t = ctx.t;
    const { setup, backend } = ctx;
    const net = backend.network;

    // 状态条：只报事实（已连接 / 未连接 + 介质 + IP），**这一行里没有任何按钮**。
    // 曾经这里放过一枚「重新扫描」，读起来像是「点一下就能连上」——
    // 它挪到了列表下方（见本文件末尾那段），状态串本身则永远不做成按钮
    // （2026-10-04 实机反馈：读起来像可以点，点了又什么都不说明）。
    // Live 里断网就该走 `blockedReason` 那一条。
    const status = panel({}, [
      h('div', { class: 'row', 'data-anim': '' }, [
        badge({
          label: net.connected ? t('network.connected') : t('network.disconnected'),
          tone: net.connected ? 'ok' : 'danger',
        }),
        badge({ label: net.kind === 'wired' ? t('network.wired') : t('network.wireless') }),
        net.ipv4 ? h('span', { class: 'mono muted', text: net.ipv4 }) : null,
        net.connected && net.ssid ? h('span', { class: 'muted', text: net.ssid }) : null,
        h('span', { class: 'panel__spacer' }),
        net.scanning ? h('span', { class: 'label faint', text: t('network.scanning') }) : null,
      ]),
    ]);

    const wifiBody = net.scanning
      ? h('div', { class: 'stack' }, [
          h('div', { class: 'skeleton', style: { height: '64px' } }),
          h('div', { class: 'skeleton', style: { height: '64px' } }),
        ])
      : net.wifi.length === 0
        ? emptyState({ icon: 'wifi-high', text: t('network.none') })
        : listBox(
            ...net.wifi.map((item) => {
              const selected = setup.data.wifiSelected === item.ssid;
              const chipId = `wifi-${item.ssid.replace(/[^a-zA-Z0-9]+/g, '-')}`;
              return h('div', { class: 'stack', dataset: { wifi: item.ssid } }, [
                option({
                  id: chipId,
                  icon: 'wifi-high',
                  title: item.ssid,
                  meta: item.security === 'open' ? t('network.connect') : t('network.password'),
                  selected,
                  tail: [
                    net.connected && net.ssid === item.ssid
                      ? badge({ label: t('network.connected'), tone: 'ok' })
                      : null,
                    signalBars(item.signal),
                  ],
                  onClick: () => {
                    setup.set('wifiSelected', selected ? '' : item.ssid);
                    setup.set('wifiPassword', '');
                    ctx.rerender();
                  },
                }),
                selected
                  ? h('div', { class: 'wifi-editor' }, [
                      item.security === 'open'
                        ? null
                        : field({
                            controlId: 'wifi-password',
                            label: t('network.password'),
                            control: textInput({
                              id: 'wifi-password',
                              type: 'password',
                              value: setup.data.wifiPassword || '',
                              autocomplete: 'off',
                              invalid: net.failure === 'auth',
                              onInput: (value) => setup.set('wifiPassword', value),
                              onEnter: () => connect(ctx, item),
                            }),
                          }),
                      button({
                        id: 'wifi-connect',
                        label: net.connecting ? t('network.connecting') : t('network.connect'),
                        variant: 'primary',
                        disabled: net.connecting,
                        onClick: () => connect(ctx, item),
                      }),
                    ])
                  : null,
              ]);
            })
          );

    const failure = net.failure
      ? callout({
          id: 'wifi-error',
          tone: 'danger',
          icon: 'warning',
          text: t(FAILURE_KEY[net.failure] || 'network.err.other'),
        })
      : null;

    if (ctx.animateIn) queueMicrotask(() => staggerIn([...document.querySelectorAll('.option')]));

    return h('div', { class: 'stack' }, [
      pageHead({ title: t('network.title'), desc: t('network.desc') }),
      status,
      divider(),
      panel({ title: t('network.available') }, [
        failure,
        wifiBody,
        // 扫描动作跟在列表**下方**，与目标盘页同一条规矩（维护者 2026-10-05）：
        // 它是「对下面这份列表」的动作，浮在标题行右侧不合语义。
        //
        // 这枚按钮是补回来的：9a99666 那次「挪到列表下方」在 disk.js 挪对了，
        // 在网络页却是**直接删掉**（`?: null`），于是网卡住时既没有自动刷新、
        // 也没有手动入口（Issue #97 第 3 条实机反馈）。
        h('div', { class: 'row', style: { 'margin-top': '4px' } }, [
          button({
            id: 'wifi-rescan',
            label: t('nav.refresh'),
            variant: 'tonal',
            icon: 'arrows-clockwise',
            disabled: net.scanning || net.connecting,
            onClick: () => rescan(ctx),
          }),
        ]),
      ]),
    ]);
  },

  /** 进入本页就开始轮询现状；离开时必须停 —— 否则它会在别的页面上重画网络页。 */
  onEnter(ctx) {
    startPoll(ctx);
  },

  onLeave() {
    stopPoll();
  },

  /** 门禁：没联网不许继续（文案 `network.needNetwork`）。 */
  isComplete(ctx) {
    return Boolean(ctx.backend.network.connected);
  },

  blockedReason(ctx) {
    return ctx.backend.network.connected ? '' : ctx.t('network.needNetwork');
  },

  primaryLabel() {
    return '';
  },
};
