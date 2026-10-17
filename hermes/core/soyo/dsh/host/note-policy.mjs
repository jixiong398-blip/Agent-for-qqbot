// SPDX-License-Identifier: MIT
// Pure limits over durable note admissions; identity/trust is supplied by Host bindings.
export const noteTextLimit = (source, target) =>
  source.session_class === 'owner_private' && (target.kind === 'home' || target.home) ? 1500 : 300;

export function noteQuotaReason(rows, source, target, now, timeZone = 'UTC', homePlaces = new Set()) {
  const all = [...rows].filter(row => row.probe === Boolean(source.probe));
  if (all.filter(row => row.from_consumer === source.consumer).length >= 2) return '本轮已经写了两张便签；其余内容留到下一回合。';
  const formatter = new Intl.DateTimeFormat('en-CA', { timeZone, year: 'numeric', month: '2-digit', day: '2-digit' });
  const today = formatter.format(now), daily = all.filter(row => formatter.format(row.created_at) === today);
  if (daily.length >= 40) return 'NOTE_QUOTA: daily total 40';
  if (source.session_class !== 'owner_private') {
    if ((target.kind === 'home' || target.home) && daily.filter(row => row.from_class !== 'owner_private' &&
        (row.target_kind === 'home' || row.target_home || homePlaces.has(row.to))).length >= 6)
      return 'NOTE_QUOTA: public-to-home daily 6';
    if (target.kind === 'group') {
      if (daily.filter(row => row.from_class !== 'owner_private' && row.target_kind === 'group').length >= 10)
        return 'NOTE_QUOTA: public-to-group daily total 10';
      if (daily.filter(row => row.from === source.route_id && row.to === target.place).length >= 3)
        return 'NOTE_QUOTA: group-pair daily 3';
    }
  }
  return null;
}
