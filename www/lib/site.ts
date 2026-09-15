export const SITE = {
  url: 'https://claudectl.space',
  docs: 'https://docs.claudectl.space',
  name: 'archeus',
  tagline: 'The memory and workspace layer for AI coding agents.',
  repo: 'https://github.com/babarmuhammad/archeus',
  pypi: 'https://pypi.org/project/archeus/',
  npm: 'https://www.npmjs.com/package/archeus',
  rubygems: 'https://rubygems.org/gems/archeus',
  author: 'Babar Muhammad Anas',
  authorGithub: 'https://github.com/babarmuhammad',
  license: 'MIT',
  ogImage: '/og-card.png',
  /* The operator of both hosts, named because a policy has to name somebody and
     a project is not a legal person. `contact` is a real mailbox: the address in
     CODE_OF_CONDUCT.md is a GitHub users.noreply alias, which is send-only and
     bounces, so it cannot be the contact route a privacy notice publishes. */
  operator: 'Babar Muhammad Anas',
  operatorCountry: 'Italy',
  contact: 'babarh174@gmail.com',
  /* Donations only — no tier, perk or benefit, and that is not a detail. The
     moment a donation buys something it stops being a gift and becomes a
     consumer supply contract, with a right of withdrawal and a real refund
     policy behind it. See lib/legal.ts. */
  kofi: 'https://ko-fi.com/babarmuhammad',
} as const;

/** Every profile the author controls, for schema.org `sameAs`.
 *
 *  This is the disambiguation mechanism, not decoration. The name is a
 *  dictionary word — Paracelsus' term — and it sits one vowel from Nintendo's
 *  Arceus, so a search for it returns encyclopedias and a Pokemon and nothing
 *  of this project (measured, every engine). What tells a search engine which
 *  "archeus" this is, is one entity corroborated by a set of profiles that all
 *  link back here. Add a URL only once it exists AND links to claudectl.space —
 *  a dead or one-way profile weakens the graph.
 *
 *  Deliberately absent: the Reddit account. It is pseudonymous and shares no
 *  string with the name or the project, so it corroborates nothing, and
 *  publishing it here would permanently tie that pseudonym to a real identity.
 *  It lives in the growth repo's ledger, which is where it is actually used. */
export const PROFILES = [
  'https://github.com/babarmuhammad',
  'https://www.linkedin.com/in/muhammad-anas-babar-819647240',
  'https://dev.to/muhammad_anasbabar_31256',
  'https://babarmuhammad.hashnode.dev',
  'https://www.instagram.com/muhammad_anas_babar',
] as const;

export const NAV = [
  { href: '/features', label: 'Features' },
  { href: '/download', label: 'Download' },
  { href: '/architecture', label: 'Architecture' },
  { href: '/changelog', label: 'Changelog' },
  { href: '/blog', label: 'Blog' },
  { href: '/faq', label: 'FAQ' },
  { href: '/community', label: 'Community' },
  { href: '/about', label: 'About' },
] as const;

/** Old docs URLs that now live on the docs subdomain. */
export const DOC_REDIRECTS = [
  'install', 'usage', 'gui', 'graph', 'token-economy', 'health', 'sessions',
  'memory', 'accounts', 'mcp', 'agents', 'hooks', 'statusline', 'plan-execute',
  'reference', 'api', 'dashboard', 'context-handoff', 'agent-library',
] as const;

export const url = (path: string) => new URL(path, SITE.url).toString();
