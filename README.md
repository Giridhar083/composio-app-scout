# AppScout (100% free-tier)
Keys: Gemini (free) -> aistudio.google.com/apikey ; Composio -> dashboard Settings > API Keys (docs.composio.dev)
1. `pip install requests composio`
2. `export GEMINI_API_KEY=... COMPOSIO_API_KEY=...`
2b. `python scout.py probe`  (confirms the Composio search call works; if args/slug differ, set SEARCH_SLUG or edit `search()`)
3. `python scout.py research`  -> pass1.json (search + schema extraction; saves after every app, re-run to resume)
4. `python scout.py sample`    -> gold.csv; fill ~20 rows BY HAND from official docs (human ground truth)
5. `python scout.py score`     -> pass1 accuracy (the "before")
6. `python scout.py verify`    -> pass2.json (skeptical re-check with full cited pages + fresh searches)
7. `python scout.py score`     -> pass1 vs pass2 vs gold (the "after")
8. `python scout.py patterns`  -> patterns.json
Free-tier limits: if you hit daily quota, stop and re-run tomorrow (resume skips finished apps), or raise PAUSE.
Manually re-check every `low_confidence` app and every pass1/pass2 disagreement; log them as "human needed".
9. `python scout.py bundle`    -> index.html (the case-study page with your real data inlined; deploy on GitHub Pages/Netlify/Vercel)
   Optional: notes.json = list of strings describing apps that defeated the agent and what you did by hand.
10. `python scout.py serve`    -> runnable trigger: GET /research?app=Linear[&verify=1]; also serves index.html. Deploy on Render/Railway/Fly (set the 2 API keys as env vars).
Optional browser loop: `pip install playwright && playwright install chromium` (verifier falls back to a headless browser when a cited page is JS-rendered/empty).
Deterministic checks (no LLM): enum/schema validation, evidence URLs must come from real search results, cited pages must load and mention the app.
