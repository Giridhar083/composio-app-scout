#!/usr/bin/env python3
"""AppScout: research -> verify -> sample -> score -> patterns -> bundle, plus `serve` (runnable trigger).
Search runs through the Composio SDK (COMPOSIO_SEARCH toolkit) with Tavily/DDG fallbacks. LLM = Groq (default).
Env: GROQ_API_KEY, COMPOSIO_API_KEY. Optional: LLM_PROVIDER, MODEL, SEARCH_SLUG, PAUSE, PORT, TAVILY_API_KEY."""
import os, sys, json, csv, re, time, random, threading, collections
import requests

GROQ_KEY = os.getenv("GROQ_API_KEY")
GEMINI_KEY = os.getenv("GEMINI_API_KEY")
CF_ACCOUNT_ID = os.getenv("CLOUDFLARE_ACCOUNT_ID")
CF_API_TOKEN = os.getenv("CLOUDFLARE_API_TOKEN")
XAI_KEY = os.getenv("XAI_API_KEY")
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "groq")        # "groq", "gemini", or "xai"
MODEL = os.getenv("MODEL", "llama-3.3-70b-versatile")
SEARCH_SLUG = os.getenv("SEARCH_SLUG", "COMPOSIO_SEARCH_TAVILY_SEARCH")
USER_ID = os.getenv("COMPOSIO_USER_ID", "appscout")
PAUSE = float(os.getenv("PAUSE", "4"))                  # 4s avoids Groq free-tier TPM bursts

ENUMS = {"self_serve": "free|trial|paid_plan_required|approval_required|partner_gated|contact_sales|n/a|unknown",
         "verdict": "yes|partial|no", "confidence": "high|medium|low",
         "blocker": "none|partner_gate|paid_plan|app_review|contact_sales|no_public_api|cli_only|unofficial_api|other",
         "webhooks": "yes|no|unknown", "sandbox": "yes|no|unknown"}
AUTH = "oauth2|api_key|basic|bearer_token|jwt|hmac|none|other"
FIELDS = f"""Return ONLY JSON:
{{"category": str, "one_liner": str, "auth": [{AUTH}],
 "self_serve": "{ENUMS['self_serve']}", "gate_detail": str,
 "api": {{"type": "REST|GraphQL|SOAP|RPC|CLI_only|none", "breadth": "narrow|medium|broad", "docs_public": bool}},
 "mcp": {{"status": "official|community|none|unknown", "url": str|null}},
 "rate_limits": str, "webhooks": "{ENUMS['webhooks']}", "sandbox": "{ENUMS['sandbox']}" (free dev/test environment),
 "verdict": "{ENUMS['verdict']}", "blocker": "{ENUMS['blocker']}", "blocker_detail": str,
 "evidence": [{{"field": str, "url": str}}], "confidence": "{ENUMS['confidence']}"}}
Rules: use ONLY the SOURCES provided. Evidence URLs must be copied from the sources, never invented.
If sources do not show a fact, answer "unknown"/"other" and set confidence low; never guess.
'verdict' = could an agent toolkit be built today by a developer with only self-serve credentials."""

# ---------- tools: Composio search, Groq/Gemini/xAI LLM, page fetch (+ browser fallback) ----------
_composio = None
def composio_client():
    global _composio
    if _composio is None:
        from composio import Composio            # pip install -U composio ; needs COMPOSIO_API_KEY
        _composio = Composio()
    return _composio

def _collect(node, out):
    if isinstance(node, dict):
        u = node.get("url") or node.get("link")
        if isinstance(u, str) and u.startswith("http"):
            t = next((node[k] for k in ("content", "snippet", "text", "description", "title") if node.get(k)), "")
            out.append({"url": u, "text": str(t)[:900]})
        for v in node.values(): _collect(v, out)
    elif isinstance(node, list):
        for v in node: _collect(v, out)

_session = None
def composio_session():
    """Composio SDK session using the `tavily` toolkit (replaces retired `composio_search`)."""
    global _session
    if _session is None:
        c = composio_client()
        try:
            _session = c.create(
                user_id=USER_ID,
                toolkits=["tavily"],
                **{"instant": {"toolkits": {"enable": ["tavily"]}}},
            )
        except TypeError:
            _session = c.create(user_id=USER_ID, toolkits=["tavily"])
    return _session

def _composio_search(q):
    r = composio_session().execute("TAVILY_SEARCH", arguments={"query": q})
    err = r.get("error") if isinstance(r, dict) else getattr(r, "error", None)
    if err:
        raise RuntimeError(f"composio search failed: {err}")
    out = []
    _collect(r.get("data", r) if isinstance(r, dict) else getattr(r, "data", r), out)
    if not out:
        raise RuntimeError("composio search returned 0 results")
    return out

_COMPOSIO_SLUGS = [
    SEARCH_SLUG,
    "COMPOSIO_SEARCH_TAVILY_SEARCH",
    "COMPOSIO_SEARCH_SEARCH",
    "COMPOSIO_SEARCH_DUCK_DUCK_GO",
]


def _tavily_search(q, n):
    r = requests.post("https://api.tavily.com/search", timeout=30,
                      headers={"Authorization": "Bearer " + os.environ["TAVILY_API_KEY"]},
                      json={"query": q, "max_results": n}); r.raise_for_status()
    return [{"url": x["url"], "text": x.get("content", "")[:900]} for x in r.json().get("results", [])]

def _ddg_search(q, n):                              # zero-key fallback: pip install ddgs
    from ddgs import DDGS
    return [{"url": x["href"], "text": x.get("body", "")[:900]} for x in DDGS().text(q, max_results=n)]

_composio_ok = True
def search(q, n=5):
    """Order: SEARCH_PROVIDER if set, else Composio session -> Tavily (if key) -> ddgs. Composio failures are logged once, then skipped."""
    global _composio_ok
    prov = os.getenv("SEARCH_PROVIDER")
    chain = [prov] if prov else (["composio"] if _composio_ok else []) + (["tavily"] if os.getenv("TAVILY_API_KEY") else []) + ["ddg"]
    fns = {"composio": lambda: _composio_search(q), "tavily": lambda: _tavily_search(q, n), "ddg": lambda: _ddg_search(q, n)}
    for name in chain:
        try:
            out = fns[name](); seen = set()
            out = [r for r in out if not (r["url"] in seen or seen.add(r["url"]))][:n]
            if out: search.used = name; return out
        except Exception as e:
            if name == "composio" and not prov: _composio_ok = False
            print(f"[search] {name} failed: {str(e)[:140]}", file=sys.stderr)
    return []
search.used = None

def probe():
    res = search("Stripe API authentication")
    print("provider used:", search.used)
    for r in res: print(r["url"], "|", r["text"][:80])

def llm(prompt):
    for attempt in range(6):
        if LLM_PROVIDER == "gemini":
            r = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent",
                timeout=45,
                headers={"x-goog-api-key": str(GEMINI_KEY)},
                json={"contents": [{"parts": [{"text": prompt}]}],
                      "generationConfig": {"temperature": 0, "responseMimeType": "application/json"}},
            )
        elif LLM_PROVIDER == "cloudflare":
            r = requests.post(
                f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/ai/v1/chat/completions",
                timeout=45,
                headers={"Authorization": "Bearer " + str(CF_API_TOKEN)},
                json={
                    "model": MODEL,
                    "temperature": 0,
                    "max_tokens": 700,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
        else:
            url = "https://api.x.ai/v1/chat/completions" if LLM_PROVIDER == "xai" else "https://api.groq.com/openai/v1/chat/completions"
            key = XAI_KEY if LLM_PROVIDER == "xai" else GROQ_KEY
            r = requests.post(
                url,
                timeout=120,
                headers={"Authorization": "Bearer " + str(key)},
                json={"model": MODEL, "temperature": 0, "response_format": {"type": "json_object"},
                      "messages": [{"role": "user", "content": prompt}]},
            )

        if r.status_code in (429, 500, 503):
            wait = min(float(r.headers.get("Retry-After", 5 * (attempt + 1))), 20)
            print(f"[llm] HTTP {r.status_code}, retrying in {wait}s...", file=sys.stderr)
            time.sleep(wait)
            continue

        if not r.ok:
            raise RuntimeError(f"LLM HTTP {r.status_code}: {r.text[:250]}")

        j = r.json()
        txt = j["candidates"][0]["content"]["parts"][0]["text"] if LLM_PROVIDER == "gemini" else j["choices"][0]["message"]["content"]
        time.sleep(PAUSE)
        m = re.search(r"\{.*\}", txt, re.S)
        try: return json.loads(m.group(0)) if m else {"_error": txt[:300]}
        except json.JSONDecodeError: return {"_error": "bad json: " + txt[:200]}
    return {"_error": "rate limited after retries"}

def strip(html): return re.sub(r"\s+", " ", re.sub(r"<(script|style)[^>]*>.*?</\1>|<[^>]+>", " ", html, flags=re.S))

def browser_render(url):
    """Verification loop 3: headless browser for JS-rendered docs. pip install playwright && playwright install chromium"""
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            b = p.chromium.launch(); pg = b.new_page(); pg.goto(url, timeout=30000, wait_until="networkidle")
            t = pg.inner_text("body"); b.close(); return re.sub(r"\s+", " ", t)
    except Exception as e:
        return f"[browser render unavailable: {e}]"

def fetch(url, n=6000):
    """returns (text, how) where how = http | browser | failed"""
    try:
        r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"}); r.raise_for_status()
        t = strip(r.text)
        if len(t) >= 400: return t[:n], "http"
    except Exception: pass
    t = browser_render(url)
    return (t[:n], "browser") if len(t) >= 400 and not t.startswith("[browser") else ("", "failed")

# ---------- deterministic checks (no LLM) ----------
def validate(rec):
    bad = [k for k, v in ENUMS.items() if rec.get(k) is not None and rec.get(k) not in v.split("|")]
    bad += [f"auth:{a}" for a in (rec.get("auth") or []) if a not in AUTH.split("|")]
    return bad

def clamp_evidence(rec, allowed):
    if isinstance(rec.get("auth"), str):
        rec["auth"] = [rec["auth"]]
    ev = rec.get("evidence") or []
    rec["evidence"] = [e for e in ev if e.get("url") in allowed]
    rec["dropped_evidence"] = len(ev) - len(rec["evidence"])      # hallucinated/unsourced URLs removed
    if not rec["evidence"]: rec["confidence"] = "low"
    rec["schema_issues"] = validate(rec)
def _hint_url(hint):
    tok = (hint or "").split()[0].strip()
    if "." in tok and "/" not in tok[:4]:
        return tok if tok.startswith("http") else "https://" + tok
    return None

# ---------- pipeline ----------
def load_apps(): return list(csv.DictReader(open("apps.csv")))

def research_one(a):
    hint = a.get("hint", "")
    srcs = []
    for q in (
        f"{a['name']} {hint} API authentication OAuth API key docs",
        f"{a['name']} developer API access pricing approval self-serve credentials",
        f"{a['name']} MCP server",
    ):
        srcs += search(q, n=4)
    out = llm(
        f"You research apps for an agent-tool platform.\nApp: {a['name']} (hint: {hint}).\n"
        f"SOURCES: {json.dumps(srcs)[:9000]}\n{FIELDS}"
    )
    rec = {"id": a.get("id", ""), "name": a["name"], "listed_category": a.get("category", ""), "hint": hint, **out}
    if "_error" not in out: clamp_evidence(rec, {s["url"] for s in srcs})
    return rec

def research():
    done = {r["id"]: r for r in json.load(open("pass1.json"))} if os.path.exists("pass1.json") else {}
    for a in load_apps():
        if a["id"] in done and "_error" not in done[a["id"]]: continue
        try: rec = research_one(a)
        except Exception as e: rec = {"id": a["id"], "name": a["name"], "listed_category": a["category"], "_error": str(e)}
        done[a["id"]] = rec; json.dump(list(done.values()), open("pass1.json", "w"), indent=1); print("done", a["name"])

def verify_one(rec):
    """Independent skeptical pass: official hint page + cited pages (HTTP, else headless browser) + fresh search + deterministic checks."""
    pages, how = {}, collections.Counter()
    urls = [e["url"] for e in (rec.get("evidence") or [])[:3]]
    hu = _hint_url(rec.get("hint", ""))
    if hu and hu not in urls:
        urls.insert(0, hu)
    for u in urls[:4]:
        t, h = fetch(u, n=3500); how[h] += 1
        if t: pages[u] = t
    fresh = search(f"{rec['name']} official developer docs authentication access requirements", 3)
    claim = {k: v for k, v in rec.items() if k not in ("evidence",)}
    out = llm(
        "You are a skeptical fact-checker. Assume the claim may be wrong.\n"
        f"CLAIM: {json.dumps(claim)}\nCITED PAGES: {json.dumps(pages)[:7500]}\nFRESH SOURCES: {json.dumps(fresh)[:3000]}\n"
        f'Return the full corrected record plus "checks": {{field: "supported|contradicted|unverifiable"}} and "changes": [str].\n{FIELDS}'
    )
    merged = {**rec, **{k: v for k, v in out.items() if not k.startswith("_")}}
    clamp_evidence(merged, set(pages) | {s["url"] for s in fresh} | {e["url"] for e in rec.get("evidence") or []})
    nm = rec["name"].split()[0].lower()
    merged["evidence_check"] = {
        "urls": sum(how.values()), "loaded": how["http"] + how["browser"],
        "browser_used": how["browser"], "mention_app": sum(nm in t.lower() for t in pages.values()),
    }
    merged["verified"] = "_error" not in out
    return merged

def verify():
    p1 = json.load(open("pass1.json"))
    done = {r["id"]: r for r in json.load(open("pass2.json"))} if os.path.exists("pass2.json") else {}
    for rec in p1:
        if rec["id"] in done and done[rec["id"]].get("verified"): continue
        try: merged = verify_one(rec) if "_error" not in rec else {**rec, "verified": False}
        except Exception as e: merged = {**rec, "verified": False, "_verify_error": str(e)}
        done[rec["id"]] = merged; json.dump(list(done.values()), open("pass2.json", "w"), indent=1); print("verified", rec["name"])

# ---------- human ground truth + scoring ----------
def sample(n=20, seed=7):
    random.seed(seed); by = collections.defaultdict(list)
    for a in load_apps(): by[a["category"]].append(a)
    pick = [a for v in by.values() for a in random.sample(v, n // len(by))]
    with open("gold.csv", "w", newline="") as f:
        w = csv.writer(f); w.writerow(["name", "auth(; separated)", "self_serve", "mcp", "verdict", "evidence_url"])
        for a in pick: w.writerow([a["name"], "", "", "", "", ""])
    print(f"wrote gold.csv with {len(pick)} apps - fill from official docs BY HAND, not via an LLM")

def norm_auth(v): return frozenset(x.strip().lower() for x in (v if isinstance(v, list) else str(v).split(";")) if x.strip())

def score():
    gold = {r["name"]: r for r in csv.DictReader(open("gold.csv")) if r["verdict"]}
    out = json.load(open("score.json")) if os.path.exists("score.json") else {"misses": {}}
    out["n_gold"] = len(gold)
    for key in ("pass1", "pass2"):
        if not os.path.exists(key + ".json"): continue
        recs = {r["name"]: r for r in json.load(open(key + ".json"))}
        hit, tot, miss = collections.Counter(), collections.Counter(), []
        for n, g in gold.items():
            r = recs.get(n, {})
            tests = {"auth": (norm_auth(r.get("auth", [])), norm_auth(g["auth(; separated)"])),
                     "self_serve": (r.get("self_serve"), g["self_serve"]),
                     "mcp": ((r.get("mcp") or {}).get("status"), g["mcp"]), "verdict": (r.get("verdict"), g["verdict"])}
            for k, (got, want) in tests.items():
                tot[k] += 1; hit[k] += got == want
                if got != want: miss.append({"app": n, "field": k, "agent": str(sorted(got) if isinstance(got, frozenset) else got),
                                             "gold": str(sorted(want) if isinstance(want, frozenset) else want)})
        out[key] = {"fields": {k: [hit[k], tot[k]] for k in tot}, "overall": [sum(hit.values()), sum(tot.values())]}
        out["misses"][key] = miss; print(key, out[key]["fields"], f"overall {out[key]['overall'][0]}/{out[key]['overall'][1]}")
    json.dump(out, open("score.json", "w"), indent=1)

def patterns():
    d = json.load(open("pass2.json")); C = collections.Counter
    gate = collections.defaultdict(C); [gate[r.get("listed_category")].update([r.get("self_serve")]) for r in d]
    out = {"auth": C(a for r in d for a in (r.get("auth") or [])), "blockers": C(r.get("blocker") for r in d),
           "verdict": C(r.get("verdict") for r in d), "mcp": C((r.get("mcp") or {}).get("status") for r in d),
           "self_serve_by_category": gate, "easy_wins": [r["name"] for r in d if r.get("verdict") == "yes" and r.get("blocker") == "none"],
           "needs_outreach": [r["name"] for r in d if r.get("blocker") in ("partner_gate", "contact_sales", "app_review")],
           "low_confidence": [r["name"] for r in d if r.get("confidence") == "low"]}
    json.dump(out, open("patterns.json", "w"), indent=1); print(json.dumps(out, indent=1)[:3000])

# ---------- agent/human-readable output ----------
def bundle():
    d = {"rows": json.load(open("pass2.json"))}
    for k in ("pass1", "score", "notes", "patterns"):
        if os.path.exists(k + ".json"): d[k] = json.load(open(k + ".json"))
    ld = {"@context": "https://schema.org", "@type": "Dataset", "name": "AppScout: 100 apps researched for agent toolkits",
          "description": "Auth, access gating, API surface, MCP status and buildability verdict for 100 apps, with evidence URLs.",
          "distribution": [{"@type": "DataDownload", "encodingFormat": "application/json", "contentUrl": f} for f in ("pass2.json", "pass1.json", "score.json", "patterns.json")]}
    h = open("page_template.html").read().replace("/*DATA*/null", json.dumps(d).replace("</", "<\\/"))
    h = h.replace("<!--LD-->", '<script type="application/ld+json">' + json.dumps(ld) + "</script>")
    open("index.html", "w").write(h)
    open("llms.txt", "w").write("# AppScout\n> Research of 100 apps for agent-toolkit feasibility (auth, access, API, MCP, verdict) with evidence URLs.\n\n"
        "- [pass2.json](pass2.json): verified records, one per app (schema in scout.py FIELDS)\n- [pass1.json](pass1.json): first-pass records\n"
        "- [score.json](score.json): hand-checked accuracy, first pass vs verified, with misses\n- [patterns.json](patterns.json): clusters and counts\n"
        "- Trigger: GET /research?app=NAME[&verify=1] on `python scout.py serve`\n")
    print("wrote index.html, llms.txt")

# ---------- runnable trigger ----------
def serve():
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from urllib.parse import urlparse, parse_qs
    lock = threading.Lock()                       # free-tier LLM: one research job at a time
    class H(BaseHTTPRequestHandler):
        def _send(self, code, body, ct="application/json"):
            b = body if isinstance(body, bytes) else json.dumps(body, default=str).encode()
            self.send_response(code); self.send_header("Content-Type", ct); self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
        def do_GET(self):
            u = urlparse(self.path); q = parse_qs(u.query)
            if u.path == "/research":
                app = (q.get("app") or [""])[0].strip()[:80]
                if not app: return self._send(400, {"error": "use /research?app=Stripe[&verify=1]"})
                try:
                    with lock:
                        rec = research_one({"name": app, "hint": ""})
                        if q.get("verify") and "_error" not in rec: rec = verify_one(rec)
                    self._send(200, rec)
                except Exception as e: self._send(500, {"error": str(e)})
            elif u.path in ("/", "/index.html") and os.path.exists("index.html"): self._send(200, open("index.html", "rb").read(), "text/html")
            elif u.path in ("/pass2.json", "/pass1.json", "/score.json", "/patterns.json", "/llms.txt") and os.path.exists(u.path[1:]):
                self._send(200, open(u.path[1:], "rb").read(), "text/plain" if u.path.endswith(".txt") else "application/json")
            else: self._send(404, {"error": "not found"})
    port = int(os.getenv("PORT", "8000")); print(f"serving on :{port}  try /research?app=Stripe")
    ThreadingHTTPServer(("", port), H).serve_forever()

if __name__ == "__main__":
    globals()[sys.argv[1]]()