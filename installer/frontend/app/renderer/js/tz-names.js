/**
 * tz-names.js —— 时区显示名与偏移的拼装
 *
 * 名字**不在本文件里**：34 条已过审的名字在 `i18n/*.json` 的 `timezone.name.<IANA>` 键下
 * （由 `tools/i18n.py` 从 tech/09 附 A 生成，改动逐次过维护者审核）。
 *
 * 三条纪律（都有实测依据，别改坏）：
 *   1. **不按日期算夏令时** —— `offset` 由后端按当前时刻算（`options.zone_offset`）。
 *      要 DST 正确，改后端，不要在这里长出第二份时区规则。
 *   2. **名表没覆盖的时区不硬造名字** —— 显示 **IANA id 本身**（`Europe/Amsterdam`）。
 *   3. **不做「按偏移合并」这种去重** —— 那正是 P12 里「偏移不是时区」那条：
 *      `Europe/Amsterdam` 与 `Africa/Lagos` 现在都是 +01:00，夏天却不一样；
 *      把它们合成一行，等于让用户选一个**会在某个季节变成另一个时区**的值。
 *
 * ## 为什么无名时区显示 IANA id 而不是只显示偏移
 *
 * 时区名表是一份**要长期维护的合规产物**（谁审、按什么标准、多久复核一次 —— P12）。
 * 我们只对 34 条走过审的名字负责；剩下的照实呈现 **tzdata 自己的标识符** ——
 * 那个名字不是我们写的，我们只是把它显示出来。这既让 312 条每一行都不同、可搜索，
 * 又不把任何表述揽到 MipLinux 身上；不写 id 的话，278 条会变成二十来行一模一样的
 * 「UTC+01:00」，人根本找不到自己那座城市。
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
 * 界面上的时区显示：有名 → `中国标准时间（UTC+08:00）`；
 * 无名 → `Europe/Amsterdam（UTC+01:00）`（**照实呈现 tzdata 的标识符**）。
 *
 * 两种都走 `timezone.display`（`%1（UTC%2）`）这**同一条已过审的模板** ——
 * 所以「无名时区显示 IANA id」这件事没有新增任何一句需要过审的人话。
 * 系统值始终是 IANA id（显示与系统值分开）。
 */
export function formatZone(zone, t) {
  return t.t('timezone.display', displayName(zone.id, t) || zone.id, zone.offset);
}

/**
 * 去重：只收敛**同一个已过审显示名**的等价簇（港 / 澳 / 台北 → 上海）。
 *
 * 无名时区各留各的 —— 它们显示的是各自的 IANA id，本来就互不相同。
 * 这里刻意**不**按偏移合并：见文件头第 3 条。
 */
export function dedupeZones(zones, t) {
  const seen = new Set();
  const out = [];
  for (const zone of zones) {
    const fingerprint = formatZone(zone, t);
    if (seen.has(fingerprint)) continue;
    seen.add(fingerprint);
    out.push({ ...zone, canonical: canonicalId(zone.id), display: fingerprint });
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
