// Times as the owner reads them: Today 08:34, Yesterday 23:10, Mon 14:20 within the week, then a date; Never when there is none.
// The exact value (an ISO local time) goes in the title. The simulated day starts at 09:00 on SIM_DAY, the day the fixtures call today.
const DAY = 86400000, START = 9 * 3600000, SIM_DAY = Date.UTC(2026, 9, 28);
const DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const day = (ms) => Math.floor((ms + START) / DAY);
const date = (ms) => new Date(SIM_DAY + day(ms) * DAY);

// label(ms) gives HH:MM, as clockLabel does.
export function whenShort(t, clock, label) {
  if (t == null) return 'Never';
  const d = day(clock) - day(t);
  if (d <= 0) return 'Today ' + label(t);
  if (d === 1) return 'Yesterday ' + label(t);
  return d < 7 ? DAYS[date(t).getUTCDay()] + ' ' + label(t) : date(t).toISOString().slice(0, 10);
}
// '2026-10-28 08:34:12', for the title; null when there is no time.
export const whenExact = (t, label) => (t == null ? null : date(t).toISOString().slice(0, 10) + ' ' + label(t, true));
