/**
 * 网络页（1）—— 状态 + Wi-Fi 选择 + 连接
 *
 * 门禁：没联网就过不去（`network.needNetwork`）。失败用**错误码**拼句子：
 * mock 只给 `auth` / `notFound` / `timeout` / `other`，句子一律走 `network.err.*`。
 */

import { h } from '../dom.js';
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
  const { mock, setup } = ctx;
  await mock.connectWifi(item.ssid, setup.data.wifiPassword || '');
  ctx.rerender();
}

export default {
  id: 'network',
  wantsWifiScan: true,

  render(ctx) {
    const t = ctx.t;
    const { setup, mock } = ctx;
    const net = mock.network;

    // 状态条：连上了就报「已连接 + 介质 + IP」，右侧永远只有「重新扫描」。
    // **不要**把「未连接」这种状态串做成按钮（2026-10-04 实机反馈：读起来像可以点，
    // 点了又什么都不说明）。Live 里断网就该走 blockedReason 那一条。
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
      panel({ title: t('network.available') }, [failure, wifiBody]),
    ]);
  },

  /** 门禁：没联网不许继续（文案 `network.needNetwork`）。 */
  isComplete(ctx) {
    return Boolean(ctx.mock.network.connected);
  },

  blockedReason(ctx) {
    return ctx.mock.network.connected ? '' : ctx.t('network.needNetwork');
  },

  primaryLabel() {
    return '';
  },
};
