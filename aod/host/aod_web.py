"""Web access for the assistant and page watches: search, and fetch a page as plain text.
Only public http(s) sites: addresses on your own network / this PC are refused (also after redirects)."""
import html
import ipaddress
import re
import socket
import urllib.parse
import urllib.request
from html.parser import HTMLParser

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36 AOD"
MAX_BYTES = 1_500_000


def check_url(url: str) -> str:
    u = urllib.parse.urlparse(url.strip())
    if u.scheme not in ("http", "https") or not u.hostname:
        raise ValueError("Only http(s) links are allowed")
    try:
        infos = socket.getaddrinfo(u.hostname, None)
    except OSError:
        raise ValueError("Could not find that website")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise ValueError("That address is on a private network, so I won't open it")
    return u.geturl()


class _Redirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        check_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_opener = urllib.request.build_opener(_Redirects)


class _Text(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "template", "iframe"}
    BLOCK = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "section", "article", "table", "ul", "ol"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.title, self._skip, self._in_title = [], "", 0, False

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self._skip += 1
        elif tag == "title":
            self._in_title = True
        elif tag in self.BLOCK:
            self.out.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self._skip:
            self._skip -= 1
        elif tag == "title":
            self._in_title = False
        elif tag in self.BLOCK:
            self.out.append("\n")

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif not self._skip and data.strip():
            self.out.append(data)


def html_to_text(raw: str):
    p = _Text()
    try:
        p.feed(raw)
    except Exception:
        pass
    text = "".join(p.out)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = "\n".join(l.strip() for l in text.split("\n") if l.strip())
    return p.title.strip(), text


def fetch(url: str, timeout: int = 20):
    """Return (title, plain text). Raises ValueError/OSError with a readable message."""
    url = check_url(url)
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,text/plain;q=0.9,*/*;q=0.5",
                                               "Accept-Language": "en-GB,en;q=0.9"})
    with _opener.open(req, timeout=timeout) as r:
        ctype = r.headers.get("Content-Type", "")
        if not any(x in ctype for x in ("text/", "json", "xml", "html")):
            raise ValueError("That link is not a web page (" + ctype.split(";")[0] + ")")
        raw = r.read(MAX_BYTES)
        enc = r.headers.get_content_charset() or "utf-8"
    body = raw.decode(enc, errors="replace")
    if "html" in ctype or body.lstrip()[:15].lower().startswith(("<!doctype", "<html")):
        return html_to_text(body)
    return "", body


def search(query: str, n: int = 8) -> list:
    """DuckDuckGo results: [{title, url, snippet}]."""
    url = "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(query)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=20) as r:
        page = r.read(600_000).decode("utf-8", errors="replace")
    out = []
    for m in re.finditer(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>(.*?)(?=<a[^>]+class="result__a"|$)', page, re.S):
        href, title, rest = m.groups()
        q = urllib.parse.parse_qs(urllib.parse.urlparse(html.unescape(href)).query)
        link = q.get("uddg", [html.unescape(href)])[0]
        sn = re.search(r'class="result__snippet"[^>]*>(.*?)</a>', rest, re.S)
        clean = lambda s: html.unescape(re.sub(r"<[^>]+>", "", s)).strip()
        if link.startswith("http"):
            out.append({"title": clean(title), "url": link, "snippet": clean(sn.group(1)) if sn else ""})
        if len(out) >= n:
            break
    return out
