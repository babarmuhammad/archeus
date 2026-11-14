// An account's resource policy as the user types it (rulebook §43; D-7): the
// draft's own problems, said before anything is sent. Core still judges every
// save — a budget on a measure the account does not report is its refusal.

export type PolicyDraft = Record<'priority' | 'allocation_pct' | 'reserve_pct' | 'brain_reserve_pct' | 'tokens_per_day' | 'cost_per_day' | 'concurrency', string>;

export const BUDGETS = [
  ['tokens_per_day', 'Tokens per day'],
  ['cost_per_day', 'Cost per day'],
  ['concurrency', 'Attempts at once'],
] as const;

/** What is wrong with a draft, or null. */
export function policyProblem(d: PolicyDraft): string | null {
  const whole = (v: string) => /^\d+$/.test(v.trim());
  if (!/^-?\d+$/.test(d.priority.trim())) return 'The priority is a whole number.';
  for (const k of ['allocation_pct', 'reserve_pct', 'brain_reserve_pct'] as const) if (!whole(d[k])) return 'A share is a whole number from 0 to 100.';
  if (Number(d.allocation_pct) > 100) return 'The allocation ceiling is at most 100%.';
  if (Number(d.reserve_pct) + Number(d.brain_reserve_pct) > Number(d.allocation_pct)) return 'The two reserves together cannot exceed the allocation ceiling.';
  for (const [k] of BUDGETS) if (d[k].trim() && !(Number(d[k]) >= 0)) return 'A budget is a number of 0 or more, or blank for none.';
  return null;
}

/** The budgets a draft sets: only the filled ones (a blank one is removed). */
export const draftBudgets = (d: PolicyDraft) => Object.fromEntries(BUDGETS.filter(([k]) => d[k].trim()).map(([k]) => [k, Number(d[k])]));
