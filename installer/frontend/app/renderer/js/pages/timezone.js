/**
 * 高级 · 时区页 —— 显示名 + UTC 偏移，列表按「显示名 + 偏移」去重
 *
 * 四条已定口径（D17 / D19 / tech/09 附 A，别改坏）：
 *   1. **名单由后端给**：随包的 `data/timezones.txt`（D19 的精选子集，入表条件 = 附 A 里
 *      有过审中文名），表外的一律不在界面上 —— 本页不自己造名单、也不去扫运行系统；
 *   2. 名表里的时区显示**已过审的名字**（i18n 的 `timezone.name.<IANA>` 键下，改动逐次过审）；
 *   3. 名表没覆盖的时区**照实显示 IANA id**（`Europe/Amsterdam（UTC+02:00）`），不硬造名字
 *      —— 当前数据面下不会出现，留着是显示层的防线（见 `tz-names.js`）；
 *   4. 去重只收敛同一个已过审显示名的等价簇（港 / 澳 / 台北 → 上海），**不按偏移合并**，
 *      也**不按日期算夏令时**（DST 归数据源/后端）。
 */

import { h } from '../dom.js';
import { pageHead, panel } from '../components.js';
import { DEFAULTS } from '../setup.js';
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
        defaultValue: DEFAULTS.timezone,
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
