import type { MetadataRoute } from 'next';
import { SITE } from '@/lib/site';

/**
 * The crawlers named one by one, and why naming them is not decoration.
 *
 * `User-agent: *` already allows every one of these — a bare `Allow: /` is the
 * default and always was. What an explicit group buys is an *unambiguous*
 * answer for the two agents that read this file looking for a specific
 * permission rather than a general one: `Google-Extended` (whether Gemini and
 * AI Overviews may use the content, which the wildcard group does NOT decide)
 * and `Applebot-Extended` (the same question for Apple Intelligence). Both
 * treat "no rule for me" differently from "a rule for me that allows it", and
 * the answer here is yes for both.
 *
 * The rest are listed so that this file states the policy instead of implying
 * it. archeus is a developer tool whose documentation is the product: being
 * quotable by an answer engine is the distribution channel, not a leak.
 *
 * Kept in step with `docs/robots.txt` by `tests/test_robots.py` — two hosts
 * that disagree about who may read them is one host contradicting the other.
 */
const CRAWLERS = [
  'GPTBot',            // OpenAI, training + ChatGPT retrieval
  'OAI-SearchBot',     // OpenAI, ChatGPT Search index
  'ChatGPT-User',      // OpenAI, a user asked ChatGPT to open this page
  'ClaudeBot',         // Anthropic, crawl
  'Claude-User',       // Anthropic, a user asked Claude to open this page
  'Claude-SearchBot',  // Anthropic, search index
  'PerplexityBot',     // Perplexity index
  'Perplexity-User',   // Perplexity, user-initiated fetch
  'Google-Extended',   // Gemini / AI Overviews opt-in — no rule means NO
  'Applebot-Extended', // Apple Intelligence opt-in — same
  'Bingbot',           // Bing, and therefore Yahoo and DuckDuckGo
  'CCBot',             // Common Crawl, which most open corpora are built from
];

export default function robots(): MetadataRoute.Robots {
  // A preview deployment is the whole site on a *.vercel.app origin. Indexed,
  // it is a duplicate of production with no canonical anyone believes.
  // next.config.ts sends X-Robots-Tag on the same condition, which is the half
  // that covers a preview URL someone linked to directly.
  if (process.env.VERCEL_ENV && process.env.VERCEL_ENV !== 'production') {
    return { rules: [{ userAgent: '*', disallow: '/' }] };
  }

  return {
    rules: [
      { userAgent: '*', allow: '/' },
      ...CRAWLERS.map((userAgent) => ({ userAgent, allow: '/' })),
    ],
    sitemap: `${SITE.url}/sitemap.xml`,
    host: SITE.url,
  };
}
