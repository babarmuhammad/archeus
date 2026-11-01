"""urllib re-sends every request header, Authorization included, to whatever a
3xx `Location` names. A provider target or a stale base URL that answers with a
redirect to another host would be handed the user's key, so a redirect that
leaves the origin of a request carrying a credential is refused: the caller sees
the 3xx as an HTTPError, like every other non-2xx."""

import urllib.parse
import urllib.request

_CREDENTIAL_HEADERS = {'authorization', 'x-api-key', 'proxy-authorization', 'cookie'}


class SameOriginRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if _CREDENTIAL_HEADERS & {k.lower() for k, _ in req.header_items()}:
            a, b = urllib.parse.urlsplit(req.full_url), urllib.parse.urlsplit(newurl)
            if (a.scheme, a.netloc.lower()) != (b.scheme, b.netloc.lower()):
                return None
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_installed = False


def install():
    global _installed
    if not _installed:
        urllib.request.install_opener(urllib.request.build_opener(SameOriginRedirect))
        _installed = True
