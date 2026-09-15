# Moving archeus to a new domain

The repository half is one command. Everything below it is the half no script can
do, and the order is load-bearing: two of these steps are irreversible in
practice, and one of them has to happen *before* the switch rather than after.

Today's hosts:

| What | Host | Built by | Deployed by |
|---|---|---|---|
| Marketing site | `claudectl.space` | Next.js in `www/` | Vercel (git integration) |
| Manual | `docs.claudectl.space` | MkDocs from `docs/` | Vercel **and** GitHub Pages, from one build |

The manual is published twice from the same `mkdocs build`, both emitting the same
`site_url`, so search engines index one of them rather than splitting the content.
`docs/CNAME` is what points the GitHub Pages copy at the custom domain.

---

## 0. Before you buy anything

**Do not submit either host to the HSTS preload list.** `www/next.config.ts` and
`vercel.json` send `Strict-Transport-Security` with `includeSubDomains` and
deliberately **without** `preload`. The preload list ships inside browsers and
removal takes months, so preloading a host you are about to leave strands it.
Revisit once the new domain has been live and settled for a few months.

Check the new name the way the current one was chosen: an unrelated Rust project
already publishes as `archeus`, and the whole entity-graph strategy in
`www/lib/site.ts` exists because of it. A name with no incumbent lands cleaner
than one you have to out-rank.

---

## 1. The repository — one command

```bash
py tools/set_domain.py --check        # what it will touch, and what it will not
py tools/set_domain.py newdomain.dev  # do it
```

It rewrites every tracked text file naming the host: `mkdocs.yml` (`site_url` and
`extra.apex`), `docs/CNAME`, `docs/robots.txt`, `docs/llms.txt`, the docs pages,
`README.md`, `pyproject.toml`, `CITATION.cff`, `claude_sessions/cli.py`, the two
issue templates, `tools/gen_metrics.py`, `www/lib/site.ts`, the blog markdown, and
the tests that assert all of it.

Then, in the same commit:

1. **Change `CURRENT` in `tools/set_domain.py`.** Everything in
   `tests/test_site_links.py` reads the host from there. Leave it pointing at the
   old domain and the switch rewrites nothing next time while every check goes on
   passing — a gate that has stopped watching.
2. **Fix what it printed under `STILL NAMING`.** `CHANGELOG.md` is skipped by
   design: its entries describe releases that really did point at the old host.
   Decide per line. (Two links in there were wrong for months precisely because
   nothing printed them.)
3. Run the gates:

   ```bash
   py -m pytest tests/ -q
   py -m mkdocs build --strict
   cd www && npm ci && npm run lint && npm run build
   ```

`test_the_pages_deploy_keeps_the_custom_domain` fails if `docs/CNAME` and
`mkdocs.yml`'s `site_url` disagree, and `test_both_hosts_assert_the_same_author_entity`
fails if `mkdocs.yml`'s profile list and `www/lib/site.ts`'s `PROFILES` drift —
both hosts have to assert one entity or the graph says there are two of them.

---

## 2. DNS and the two Vercel projects

1. Add the apex and `docs.` to their Vercel projects (**Settings → Domains**, one
   project each — they are two deployments, not one).
2. Point DNS at Vercel as it instructs. Wait for both certificates.
3. **Keep the old domain.** Do not let it lapse and do not repoint it at the new
   one with a wildcard. It needs to serve a **301 per path** to the matching new
   path for at least twelve months. A wildcard redirect to the new homepage throws
   away every deep link: Google treats a redirect to an unrelated page as a soft
   404, not as a move.

   The cheapest correct shape is a third Vercel project holding nothing but a
   `vercel.json`:

   ```json
   {
     "redirects": [
       { "source": "/:path*", "destination": "https://newdomain.dev/:path*", "permanent": true }
     ]
   }
   ```

   and the same again for `docs.` → `docs.newdomain.dev`. Path-preserving, one hop,
   no chains.
4. **GitHub Pages**: Settings → Pages → Custom domain → the new `docs.` host, and
   leave **Enforce HTTPS** ticked. `docs/CNAME` is already rewritten, so the next
   deploy sets it; the repo setting has to be changed by hand once.

---

## 3. Search Console and Bing

Full detail in `notes/search-console.md`. The move-specific parts:

1. Verify the **new** domain as a **Domain property** (DNS TXT) *before* switching
   traffic. A URL-prefix property does not cover subdomains — that already cost 28
   of 46 URLs on the docs host once.
2. Keep the old property verified. The **Change of address** tool needs both, and
   it only works apex-to-apex: run it once for `claudectl.space` → the new apex,
   and separately for `docs.claudectl.space` → the new docs host.
3. Submit both new sitemaps: `https://<new>/sitemap.xml` and
   `https://docs.<new>/sitemap.xml`.
4. Bing Webmaster Tools → **Site Move**, same two pairs. Yahoo is Bing's index, so
   nothing separate.
5. Expect a few weeks of ranking wobble. Do not also change URL structure, page
   titles or content in the same window — one variable at a time, or you cannot
   tell a bad move from a bad rewrite.

---

## 4. Everything that links here and is not in this repo

Each of these is a corroborating link in the entity graph; a stale one weakens
exactly the thing the `sameAs` list was built for.

- [ ] **PyPI** — `project.urls` in `pyproject.toml` is rewritten, but PyPI only
      reads it from a **new release**. Cut one.
- [ ] **GitHub repo** — the website field (`gh repo edit --homepage https://<new>`).
- [ ] **GitHub profile bio** — it names the site.
- [ ] Every profile in `PROFILES` (`www/lib/site.ts`) and `extra.profiles`
      (`mkdocs.yml`): LinkedIn, dev.to, Hashnode, Instagram. The graph is
      two-way — a profile that no longer links back stops corroborating.
- [ ] **dev.to / Hashnode cross-posts** — their `canonical_url` front matter points
      at the old apex. Update each, or they become the canonical.
- [ ] The private growth repo's ledger (a sibling checkout, not this one):
      `data/submission_targets.json`, `data/visibility.json`, the drafts, and the
      referrer baselines in `data/metrics.json` — which will show a cliff at the
      move regardless.
- [ ] Anywhere already submitted and accepted: awesome-lists, console.dev,
      AlternativeTo. `BACKLINKS.md` in the growth repo is the list.

---

## 5. After

- `curl -sI https://<old>/features` → `301` to `https://<new>/features` (one hop,
  not two).
- `curl -sI https://<new>/` → `Strict-Transport-Security` present.
- `curl https://<new>/llms.txt` and `https://docs.<new>/llms-full.txt` → the new
  host inside the files, not just in the URL bar.
- Search Console: Coverage clean, the sitemaps read, the old property showing
  traffic draining rather than vanishing.
- PageSpeed Insights on the new host — the CDN and certificate are new, so the
  numbers are new too.
