"""Standard-library web search and HTML-to-Markdown extraction with SSRF checks."""
from __future__ import annotations

import html
import ipaddress
import re
import socket
import urllib.parse
import urllib.request
from html.parser import HTMLParser


def normalize_url(value: str) -> str:
    parsed = urllib.parse.urlsplit(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("only absolute HTTP(S) URLs are supported")
    host = parsed.hostname.lower()
    if host == "localhost" or host.endswith((".localhost", ".local")):
        raise ValueError("local network targets are not allowed")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address is not None and not address.is_global:
        raise ValueError("non-public IP targets are not allowed")
    if parsed.username or parsed.password:
        raise ValueError("credentials in URLs are not allowed")
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path or "/", parsed.query, ""))


def _assert_public_host(url: str) -> None:
    host = urllib.parse.urlsplit(url).hostname
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)}
    except OSError as exc:
        raise ValueError("host DNS lookup failed") from exc
    if not addresses or any(not ipaddress.ip_address(address).is_global for address in addresses):
        raise ValueError("host resolves to a non-public address")


class _MarkdownParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.skip, self.pending = [], 0, ""
    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript", "svg", "nav", "footer"}:
            self.skip += 1
        if self.skip:
            return
        if tag in {"h1", "h2", "h3"}:
            self.parts.append("\\n" if self.parts else "")
            self.pending = "#" * int(tag[1]) + " "
        elif tag in {"p", "div", "section", "article", "li", "br"}:
            self.parts.append("\\n\\n")
            if tag == "li":
                self.parts.append("- ")
    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript", "svg", "nav", "footer"} and self.skip:
            self.skip -= 1
        elif not self.skip and tag in {"h1", "h2", "h3", "p", "div", "section", "article", "li"}:
            self.parts.append("\\n\\n")
    def handle_data(self, data):
        if not self.skip and data.strip():
            if self.pending:
                self.parts.append(self.pending)
                self.pending = ""
            self.parts.append(data.strip() + " ")


def html_to_markdown(source: str, max_chars: int = 20000) -> str:
    parser = _MarkdownParser()
    parser.feed(source[:max_chars * 4])
    text = html.unescape("".join(parser.parts))
    text = re.sub(r"[ \\t]+", " ", text)
    text = re.sub(r" *\\n *", "\\n", text)
    text = re.sub(r"\\n{3,}", "\\n\\n", text)
    return text.strip()[:max_chars]


class _SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        safe_url = normalize_url(urllib.parse.urljoin(req.full_url, newurl))
        _assert_public_host(safe_url)
        return super().redirect_request(req, fp, code, msg, headers, safe_url)


def _fetch(url: str, timeout: float = 12.0, limit: int = 2_000_000) -> str:
    current = normalize_url(url)
    _assert_public_host(current)
    request = urllib.request.Request(current, headers={"User-Agent": "ENGINE-research/1.0", "Accept": "text/html"})
    opener = urllib.request.build_opener(_SafeRedirectHandler())
    with opener.open(request, timeout=min(max(timeout, 2), 20)) as response:
        final = normalize_url(response.geturl())
        _assert_public_host(final)
        if "text/html" not in response.headers.get("Content-Type", ""):
            raise ValueError("URL did not return HTML")
        return response.read(limit + 1)[:limit].decode(response.headers.get_content_charset() or "utf-8", errors="replace")


class _SearchResultsParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.results, self.href, self.title, self.snippet = [], None, [], []
        self.in_title = self.in_snippet = False
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = attrs.get("class", "")
        if tag == "a" and "result__a" in classes:
            self.href, self.title, self.in_title = attrs.get("href"), [], True
        if "result__snippet" in classes:
            self.snippet, self.in_snippet = [], True
    def handle_endtag(self, tag):
        if tag == "a" and self.in_title:
            self.in_title = False
            href = self.href or ""
            if href.startswith("//"):
                href = "https:" + href
            if href.startswith("http"):
                self.results.append({"title": "".join(self.title).strip(), "url": href, "snippet": ""})
        if tag in {"a", "td", "div"} and self.in_snippet:
            self.in_snippet = False
            if self.results and not self.results[-1]["snippet"]:
                self.results[-1]["snippet"] = "".join(self.snippet).strip()
    def handle_data(self, data):
        if self.in_title: self.title.append(data)
        if self.in_snippet: self.snippet.append(data)


class WebResearch:
    def search(self, query: str, limit: int = 5) -> list[dict[str, str]]:
        if not query.strip():
            raise ValueError("query must not be empty")
        url = "https://html.duckduckgo.com/html/?" + urllib.parse.urlencode({"q": query[:300]})
        parser = _SearchResultsParser()
        parser.feed(_fetch(url))
        return parser.results[:max(1, min(int(limit), 10))]

    def fetch_markdown(self, url: str, max_chars: int = 20000) -> str:
        return html_to_markdown(_fetch(url), max_chars=max_chars)
