#!/usr/bin/env python3
"""Check every external link in the built site (public/) and report the ones that do not answer 2xx/3xx."""
import html, re, sys, pathlib, concurrent.futures, urllib.parse, urllib.request, urllib.error

root = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "public")
own = re.search(r"^baseURL:\s*https?://([^/\s]+)", pathlib.Path("hugo.yaml").read_text(), re.M).group(1)
hrefs = set()
for f in root.rglob("*.html"):
    for u in re.findall(r'href="(https?://[^"]+)"', f.read_text(encoding="utf-8")):
        if urllib.parse.urlparse(u).hostname not in (own, "ahippelainen.github.io"):
            hrefs.add(u)

HEADERS = {"User-Agent": "Mozilla/5.0 (link check)"}

def fetch(url, method):
    with urllib.request.urlopen(urllib.request.Request(url, method=method, headers=HEADERS), timeout=30) as r:
        return r.status

def check(url):
    target = html.unescape(url)
    try:
        return url, fetch(target, "HEAD")
    except urllib.error.HTTPError as e:
        if e.code not in (403, 405):
            return url, e.code
    except Exception:
        pass
    try:  # some hosts reject or stall on HEAD; a GET settles it
        return url, fetch(target, "GET")
    except urllib.error.HTTPError as e:
        return url, e.code
    except Exception as e:
        return url, str(e)

with concurrent.futures.ThreadPoolExecutor(8) as ex:
    results = list(ex.map(check, sorted(hrefs)))
bad = [(u, s) for u, s in results if not (isinstance(s, int) and s < 400)]
print(f"{len(results)} external links, {len(bad)} problems")
for u, s in bad:
    print(f"  {s}\t{u}")
sys.exit(1 if bad else 0)
