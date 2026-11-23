# AppScout — Automated Agent Toolkit Research & Verification Pipeline

**Live Case Study:** [giridhar083.github.io/composio-app-scout](https://giridhar083.github.io/composio-app-scout/)  
**Repository:** [github.com/Giridhar083/composio-app-scout](https://github.com/Giridhar083/composio-app-scout)

AppScout is an end-to-end research, verification, and benchmarking pipeline built on free-tier APIs (Gemini + Composio) to evaluate **100 SaaS & developer apps** for AI agent toolkit buildability. It extracts authentication methods, self-serve access gates, API surfaces, MCP server availability, rate limits, and buildability verdicts—then audits its own claims against retrieved source pages and a 20-app human-verified gold standard.

---

## Architecture & Pipeline Stages

1. **Search (`scout.py research`)** — Runs targeted queries per app covering authentication docs, self-serve access/pricing tiers, and official/community MCP servers via Composio.
2. **Structured Extraction** — Uses Gemini to synthesize only retrieved sources into a strict JSON schema (`pass1.json`), checkpointing after every app so runs are safely resumable.
3. **Deterministic Guardrails** — Enforces enum/schema validation, strips hallucinated evidence URLs not present in retrieved search results, and downgrades confidence when citations are dropped.
4. **Skeptical Verification (`scout.py verify`)** — Re-fetches cited URLs via HTTP (falling back to headless Playwright/Chromium for JS-rendered pages), verifies page load and app mentions, runs fresh confirmation searches, and produces `pass2.json`.
5. **Human Ground Truth & Scoring (`scout.py sample` / `score`)** — Evaluates `pass1.json` and `pass2.json` accuracy against `gold.csv`, a 20-app sample manually audited against official documentation.
6. **Pattern Aggregation & Static Bundle (`scout.py patterns` / `bundle`)** — Generates cross-category insights (`patterns.json`), machine-readable summaries (`llms.txt`), and a self-contained static web report (`index.html`).

---

## Repository Artifacts

| File | Description |
| :--- | :--- |
| `scout.py` | Core CLI pipeline: `probe`, `research`, `sample`, `score`, `verify`, `patterns`, `bundle`, and `serve` |
| `page_template.html` | HTML/CSS/JS template used to compile the interactive case study |
| `index.html` | Self-contained static web report with inlined dataset, filters, charts, and verification metrics |
| `pass1.json` | Initial agent extraction results across 100 apps |
| `pass2.json` | Post-verification dataset with source-check diagnostics and field-level audit logs |
| `gold.csv` | 20-app hand-verified ground truth dataset |
| `score.json` | Before-vs-after accuracy metrics comparing `pass1` and `pass2` against `gold.csv` |
| `patterns.json` | Aggregated ecosystem findings (auth distribution, blockers, self-serve access, MCP adoption) |
| `llms.txt` | Concise, machine-readable dataset summary for LLM consumption |

---

## Quickstart & Local Setup

### 1. Prerequisites & API Keys
* **Gemini API Key (Free Tier):** Obtain from [Google AI Studio](https://aistudio.google.com/apikey)
* **Composio API Key:** Obtain from [Composio Dashboard](https://app.composio.dev) under **Settings → API Keys**

### 2. Installation
```bash
pip install requests composio
