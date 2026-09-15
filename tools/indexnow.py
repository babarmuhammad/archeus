"""Tell Bing (and therefore DuckDuckGo, and part of ChatGPT search) that the
sites changed, instead of waiting to be crawled.

    py tools/indexnow.py            # what would be submitted, and nothing else
    py tools/indexnow.py --submit   # actually submit

IndexNow is a push protocol: one POST naming a host, a key, and up to 10,000
URLs. Bing, Yandex, Seznam and Naver share one endpoint, so a single call
reaches all of them; Google does not participate and is reached only by
crawling and Search Console.

Two rules the protocol enforces, and they are why this file exists rather than
one curl:

  The key has to be READABLE ON THE HOST WHOSE URLS ARE SUBMITTED. So there are
  two key files with the same key — `www/public/<key>.txt` for the apex and
  `docs/<key>.txt` for the manual, which MkDocs copies to the site root — and
  each host is submitted in its own call. A URL from the other host in the same
  call is rejected wholesale, not skipped.

  The URL list is the SITEMAP's, read live, not a list written down here. The
  sitemaps are generated from the page tables at build time, so a hand-kept copy
  would be a page behind the first time one was added — the same argument
  `www/app/sitemap.ts` already makes about its own route list.

It verifies the key is actually being served before submitting. A 404 there is
the whole failure mode: the endpoint answers 202 and silently drops everything,
because it fetches the key afterwards, out of band.
"""

import json
import re
import sys
import time
import urllib.error
import urllib.request

KEY = '216da8f491c6498c86010c5bc9089a25'
ENDPOINT = 'https://api.indexnow.org/IndexNow'
HOSTS = ('claudectl.space', 'docs.claudectl.space')
UA = 'archeus-indexnow/1.0 (+https://github.com/babarmuhammad/archeus)'


def _get(url):
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode('utf-8', 'replace')


def urls_for(host):
    """Every URL in that host's sitemap, in the order it lists them."""
    return re.findall(r'<loc>\s*([^<\s]+)\s*</loc>',
                      _get('https://%s/sitemap.xml' % host))


def key_is_served(host):
    try:
        return _get('https://%s/%s.txt' % (host, KEY)).strip() == KEY
    except urllib.error.HTTPError as e:
        return 'HTTP %s' % e.code
    except Exception as e:                                  # noqa: BLE001
        return str(e)


def submit(host, urls):
    body = json.dumps({
        'host': host,
        'key': KEY,
        'keyLocation': 'https://%s/%s.txt' % (host, KEY),
        'urlList': urls,
    }).encode('utf-8')
    req = urllib.request.Request(ENDPOINT, data=body, headers={
        'Content-Type': 'application/json; charset=utf-8', 'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.status, r.read().decode('utf-8', 'replace')[:200]


def main(argv):
    go = '--submit' in argv
    bad = 0
    for host in HOSTS:
        served = key_is_served(host)
        urls = urls_for(host)
        print('%s: %d URLs, key served: %s' % (host, len(urls), served))
        if served is not True:
            print('  the key is not readable on this host; '
                  'deploy it before submitting')
            bad += 1
            continue
        if not go:
            print('  would submit; pass --submit to do it')
            continue
        # One retry, because a 5xx here is the endpoint being busy rather than
        # the submission being wrong — measured: the second host answered 503
        # with an HTML error page and took the identical payload 20s later.
        for attempt in (1, 2):
            try:
                status, text = submit(host, urls)
                print('  submitted: HTTP %s %s' % (status, text.strip()))
                break
            except urllib.error.HTTPError as e:
                body = e.read().decode('utf-8', 'replace')[:200]
                if e.code >= 500 and attempt == 1:
                    print('  HTTP %s, retrying in 20s' % e.code)
                    time.sleep(20)
                    continue
                print('  REFUSED: HTTP %s %s' % (e.code, body))
                bad += 1
                break
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
