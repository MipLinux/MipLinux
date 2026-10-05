/**
 * 高级 · 时区页 —— 显示名 + UTC 偏移，列表按「显示名 + 偏移」去重
 *
 * 三条已定口径（tech/09 附 A / P12，别改坏）：
 *   1. 界面上**不出现 IANA id**（名字在 i18n 的 `timezone.name.<IANA>` 键下，改动逐次过审）；
 *   2. 名表没覆盖的时区**只显示偏移**（`UTC+05:45`），不硬造名字；
 *   3. 去重只做「显示名 + 偏移」等价的收敛，**不按日期算夏令时**（DST 归数据源/后端）。
 */

import { h } from '../dom.js';
import { pageHead, panel } from '../components.js';
import { selectableList } from './shared.js';
import { dedupeZones, matchesZone } from '../tz-names.js';

export default {
  id: 'timezone',

  render(ctx) {
    const t = ctx.t;
    const { setup, backend } = ctx;

    const zones = dedupeZones(backend.timezones, ctx.i18n);

    const list = selectableList(
      {
        id: 'timezone-list',
        searchId: 'timezone-search',
        searchKey: 'timezone.search',
        selected: setup.data.timezone,
        items: zones.map((zone) => ({
          value: zone.canonical,
          display: zone.display,
          meta: zone.offset,
        })),
        matches: (item, query) => {
          const zone = zones.find((z) => z.canonical === item.value);
          return zone ? matchesZone(zone, query, ctx.i18n) : true;
        },
        iconFor: () => 'globe-hemisphere-west',
        emptyText: () => t('locale.empty'),
        onPick: (item) => {
          setup.set('timezone', item.value);
          ctx.rerender();
        },
      },
      ctx
    );

    return h('div', { class: 'stack' }, [
      pageHead({ title: t('timezone.title'), desc: t('timezone.desc') }),
      panel({ fill: true }, list),
    ]);
  },

  isComplete() {
    return true;
  },
};
