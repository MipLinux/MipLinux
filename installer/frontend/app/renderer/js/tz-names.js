/**
 * tz-names.js —— 时区显示名与偏移的拼装
 *
 * 名字**不在本文件里**：34 条已过审的名字在 `i18n/*.json` 的 `timezone.name.<IANA>` 键下
 * （由 `tools/i18n.py` 从 tech/09 附 A 生成，改动逐次过维护者审核）。
 *
 * 两条纪律（都有实测依据，别改坏）：
 *   1. **不按日期算夏令时** —— `offset` 来自数据源（现在是 mock 的静态值）。
 *      要 DST 正确，改数据源/后端，不要在这里长出第二份时区规则。
 *   2. **名表没覆盖的时区不硬造名字** —— 只显示偏移（`UTC+05:45`）；
 *      `Asia/Kathmandu` 就是故意用来验这条的。
 */

/** 同一个「显示名 + 偏移」等价簇的代表 id（中国这一簇：港 / 澳 / 台北 → 上海）。 */
const CANONICAL = {
  'Asia/Hong_Kong': 'Asia/Shanghai',
  'Asia/Macau': 'Asia/Shanghai',
  'Asia/Taipei': 'Asia/Shanghai',
};

export function canonicalId(id) {
  return CANONICAL[id] || id;
}

/** 名字键（可能不存在 —— 调用方要能拿到 null）。 */
export function nameKeyFor(id, t) {
  const key = `timezone.name.${canonicalId(id)}`;
  return t.has(key) ? key : null;
}

/** 显示名；名表里没有 → null（不硬造）。 */
export function displayName(id, t) {
  const key = nameKeyFor(id, t);
  return key ? t.t(key) : null;
}

/**
 * 界面上的时区显示：有名 → `中国标准时间（UTC+08:00）`；无名 → `UTC+05:45`。
 * 系统值始终是 IANA id（显示与系统值分开）。
 */
export function formatZone(zone, t) {
  const name = displayName(zone.id, t);
  if (name) return t.t('timezone.display', name, zone.offset);
  return `UTC${zone.offset}`;
}

/** 按「显示名 + 偏移」去重，顺序按原表（等价簇只留第一条）。 */
export function dedupeZones(zones, t) {
  const seen = new Set();
  const out = [];
  for (const zone of zones) {
    const name = displayName(zone.id, t);
    const fingerprint = name ? `${name}|${zone.offset}` : `|${zone.offset}`;
    if (seen.has(fingerprint)) continue;
    seen.add(fingerprint);
    out.push({ ...zone, canonical: canonicalId(zone.id), display: formatZone(zone, t) });
  }
  return out;
}

/** 搜索用：把显示名、IANA id、偏移都当关键词（用户可能输入任一种）。 */
export function matchesZone(zone, query, t) {
  const needle = query.trim().toLowerCase();
  if (!needle) return true;
  return [formatZone(zone, t), zone.id, canonicalId(zone.id), zone.offset]
    .join(' ')
    .toLowerCase()
    .includes(needle);
}
