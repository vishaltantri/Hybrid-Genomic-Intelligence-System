"""Official NCBI E-utilities client for PubMed (esearch / esummary-free efetch).

* Only `eutils.ncbi.nlm.nih.gov` is ever contacted (host is validated).
* Rate limit: NCBI allows 3 requests/s without an API key and 10/s with one; a process-wide limiter enforces it.
* `NCBI_API_KEY`, `NCBI_TOOL` and `NCBI_EMAIL` are read from the environment on the server only and never returned.
* Responses are cached in memory (TTL) so repeated UI searches do not hit NCBI again.
* The HTTP layer is injectable (`fetch=`) so tests never touch the network.
"""
from __future__ import annotations

import os
import threading
import time
import urllib.parse
import urllib.request
from typing import Callable, Dict, Optional

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
ALLOWED_HOST = "eutils.ncbi.nlm.nih.gov"
CACHE_TTL_S = 15 * 60
MAX_CACHE = 256
MAX_RETMAX = 50


class PubMedUnavailable(RuntimeError):
    """NCBI could not be reached or returned an error. Message is safe to show to users."""


class _Limiter:
    def __init__(self, per_second: float) -> None:
        self.interval = 1.0 / per_second
        self._lock = threading.Lock()
        self._next = 0.0

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            delay = self._next - now
            self._next = max(now, self._next) + self.interval
        if delay > 0:
            time.sleep(delay)


def _default_fetch(url: str, timeout: float) -> str:
    host = urllib.parse.urlparse(url).hostname
    if host != ALLOWED_HOST:
        raise PubMedUnavailable("Refusing to contact a non-NCBI host")
    req = urllib.request.Request(url, headers={"User-Agent": "Genomera/1.0 (clinical decision support)"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (host validated above)
        return resp.read().decode("utf-8", errors="replace")


class PubMedClient:
    def __init__(self, fetch: Optional[Callable[[str, float], str]] = None, api_key: Optional[str] = None,
                 timeout: float = 20.0) -> None:
        self.api_key = api_key if api_key is not None else os.environ.get("NCBI_API_KEY", "")
        self.tool = os.environ.get("NCBI_TOOL", "genomera")
        self.email = os.environ.get("NCBI_EMAIL", "")
        self.timeout = timeout
        self._fetch = fetch or _default_fetch
        self._limiter = _Limiter(10.0 if self.api_key else 3.0)
        self._cache: Dict[str, tuple] = {}
        self._lock = threading.Lock()

    @property
    def configured_key(self) -> bool:
        return bool(self.api_key)

    def _params(self, extra: Dict[str, str]) -> str:
        p = {"tool": self.tool, **extra}
        if self.email:
            p["email"] = self.email
        if self.api_key:
            p["api_key"] = self.api_key
        return urllib.parse.urlencode(p)

    def _get(self, endpoint: str, params: Dict[str, str]) -> str:
        url = f"{EUTILS}/{endpoint}?{self._params(params)}"
        cache_key = f"{endpoint}?{urllib.parse.urlencode(sorted(params.items()))}"
        now = time.monotonic()
        with self._lock:
            hit = self._cache.get(cache_key)
            if hit and now - hit[0] < CACHE_TTL_S:
                return hit[1]
        self._limiter.wait()
        try:
            body = self._fetch(url, self.timeout)
        except PubMedUnavailable:
            raise
        except Exception as ex:  # network, HTTP 4xx/5xx, timeout
            code = getattr(ex, "code", None)
            if code == 429:
                raise PubMedUnavailable("PubMed rate limit reached; retry in a few seconds") from None
            raise PubMedUnavailable("PubMed is currently unreachable") from None
        with self._lock:
            if len(self._cache) >= MAX_CACHE:
                self._cache.pop(next(iter(self._cache)))
            self._cache[cache_key] = (now, body)
        return body

    def search(self, term: str, retmax: int = 10, retstart: int = 0, sort: str = "relevance") -> dict:
        import json

        body = self._get("esearch.fcgi", {"db": "pubmed", "term": term, "retmax": str(min(max(retmax, 1), MAX_RETMAX)),
                                          "retstart": str(max(retstart, 0)), "retmode": "json", "sort": sort})
        try:
            res = json.loads(body).get("esearchresult", {})
        except ValueError:
            raise PubMedUnavailable("PubMed returned an unreadable response") from None
        if "ERROR" in res:
            raise PubMedUnavailable("PubMed rejected the query")
        return {"count": int(res.get("count", 0)), "ids": res.get("idlist", []), "query_translation": res.get("querytranslation", "")}

    def fetch_xml(self, pmids: list) -> str:
        if not pmids:
            return ""
        return self._get("efetch.fcgi", {"db": "pubmed", "id": ",".join(pmids), "retmode": "xml"})
