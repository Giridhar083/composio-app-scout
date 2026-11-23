# Csession.py
import os
from composio import Composio

USER_ID = os.getenv("COMPOSIO_USER_ID", "appscout")
SLUGS = [
    "COMPOSIO_SEARCH_TAVILY_SEARCH",
    "COMPOSIO_SEARCH_SEARCH",
    "COMPOSIO_SEARCH_DUCK_DUCK_GO",
    "COMPOSIO_SEARCH_DUCK_DUCK_GO_SEARCH",
]

c = Composio(toolkit_versions={"composio_search": "latest"})

# 1) Create a Tool Router session (also exposes MCP URL if supported)
s = c.create(user_id=USER_ID, toolkits=["composio_search"])
print("Session created | MCP URL:", getattr(getattr(s, "mcp", None), "url", "n/a"))

# 2) List available composio_search tools in your account/SDK
try:
    tools = c.tools.get(user_id=USER_ID, toolkits=["COMPOSIO_SEARCH"])
    print("Available tools:", [getattr(t, "slug", str(t)[:60]) for t in tools][:10])
except Exception as e:
    print("tools.get skipped:", str(e)[:150])

# 3) Test candidate slugs via session.execute, falling back to tools.execute
working = []
for slug in SLUGS:
    for mode, fn in [
        ("session.execute", lambda sl=slug: s.execute(sl, arguments={"query": "Stripe API authentication"})),
        ("tools.execute", lambda sl=slug: c.tools.execute(slug=sl, user_id=USER_ID, arguments={"query": "Stripe API authentication"})),
    ]:
        try:
            r = fn()
            err = r.get("error") if isinstance(r, dict) else getattr(r, "error", None)
            data = r.get("data") if isinstance(r, dict) else getattr(r, "data", r)
            if not err and data:
                print(f"WORKS [{mode}] {slug} -> {str(data)[:160]}")
                working.append((mode, slug))
                break
            else:
                print(f"empty [{mode}] {slug} | error={err}")
        except Exception as e:
            print(f"fail  [{mode}] {slug} -> {str(e)[:120]}")

print("\nRecommended SEARCH_SLUG:", working[0][1] if working else "None (check COMPOSIO_API_KEY)")