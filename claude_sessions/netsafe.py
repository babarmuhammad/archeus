"""urllib re-sends every request header, Authorization included, to whatever a
3xx `Location` names. A provider target or a stale base URL that answers with a
redirect to another host would be handed the user's key, so a redirect that
leaves the origin of a request with any header beyond a plain set is refused
(a same-host upgrade from http to https is not leaving it):
the caller sees the 3xx as an HTTPError, like every other non-2xx."""

import urllib.parse
import urllib.request

# Only these names may follow a redirect to another origin; any other header
# (api-key, x-goog-api-key, a custom token) is taken to hold a credential.
# Content-Length and Host are added by urllib itself.
_PLAIN_HEADERS = {'accept', 'accept-encoding', 'user-agent', 'content-type', 'content-length',
                  'host', 'anthropic-version', 'anthropic-beta'}
_DEFAULT_PORT = {'http': 80, 'https': 443}


def _origin(url):
    u = urllib.parse.urlsplit(url)
    return u.scheme, (u.hostname or '').lower(), u.port or _DEFAULT_PORT.get(u.scheme)


def _may_follow(url, newurl):
    """The same origin, or the same host's default https port for its default http
    port (a stale http base URL answering with the upgrade); a downgrade, another
    host or port, and a URL that does not parse are not followed."""
    try:
        old, new = _origin(url), _origin(newurl)
    except ValueError:
        return False
    return old == new or (old[0], new[0], old[2], new[2]) == ('http', 'https', 80, 443) and old[1] == new[1]


class SameOriginRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if ({k.lower() for k, _ in req.header_items()} - _PLAIN_HEADERS
                and not _may_follow(req.full_url, newurl)):
            return None
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_installed = False


def install():
    global _installed
    if not _installed:
        urllib.request.install_opener(urllib.request.build_opener(SameOriginRedirect))
        _installed = True
