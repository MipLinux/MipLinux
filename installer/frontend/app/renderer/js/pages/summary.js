/**
 * 摘要页（5）—— 确认所有选择 + 「我已了解」勾选
 *
 * 只读：把 setup/mock 里的选择摊开给用户看。**不改任何状态**（除了那个勾选）。
 */

import { h } from '../dom.js';
import { pageHead, panel, kv, callout, checkbox } from '../components.js';
import { formatZone } from '../tz-names.js';

export default {
  id: 'summary',

  render(ctx) {
    const t = ctx.t;
    const { setup, mock } = ctx;
    const data = setup.data;

    const disk = mock.diskById(data.disk);
    const zone = mock && data.timezone ? { id: data.timezone, offset: offsetOf(mock, data.timezone) } : null;
    const networkLabel = mock.network.connected
      ? mock.network.ssid || mock.network.ipv4 || t('network.connected')
      : t('network.disconnected');

    const rows = [
      [t('disk.title'), disk ? `${disk.id} · ${disk.model} · ${disk.sizeLabel}` : '—'],
      [t('network.title'), networkLabel],
      [t('account.user'), data.user || '—'],
    ];
    if (setup.advanced) {
      rows.push(
        [t('locale.title'), data.locale],
        [t('keymap.title'), data.keymap],
        [t('timezone.title'), zone ? formatZone(zone, ctx.i18n) : '—'],
        [t('hostname.title'), data.hostname || data.user || '—']
      );
    }
    rows.push([t('disk.willDo'), `${mock.plan.filesystem} · ${mock.plan.boot}`]);

    return h('div', { class: 'stack' }, [
      pageHead({ title: t('summary.title'), desc: t('summary.desc') }),
      callout({ tone: 'danger', icon: 'warning', text: t('disk.desc') }),
      panel({ title: t('summary.title') }, [
        h('div', { 'data-anim': '' }, kv(rows)),
        checkbox({
          id: 'summary-understood',
          checked: data.understood,
          label: t('summary.understood'),
          onChange: (checked) => {
            setup.set('understood', checked);
            ctx.refresh();
          },
        }),
      ]),
    ]);
  },

  isComplete(ctx) {
    return Boolean(ctx.setup.data.understood);
  },

  primaryLabel(ctx) {
    return ctx.t('summary.install');
  },
};

function offsetOf(mock, id) {
  const zone = mock.timezones ? mock.timezones.find((z) => z.id === id) : null;
  return zone ? zone.offset : '+00:00';
}
