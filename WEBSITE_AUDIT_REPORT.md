# 🔍 Open Source AI Radar — Website Audit Report

**Audit Date:** November 2, 2026  
**Live URL:** https://radar.bharatdn.com/  
**Local Repo:** 148 commits behind `origin/main`  

---

## 📊 Executive Summary

| Area | Status | Issues |
|------|--------|--------|
| **Broken API Endpoints** | 🔴 Critical | 5 documented endpoints return 404 |
| **SEO (Canonical / OG)** | 🔴 Critical | Every page has same canonical + og:url |
| **Rankings Page Performance** | 🔴 Critical | 14.8 MB HTML, 22s load, all 9,830 rows SSR'd |
| **Data Staleness** | 🟡 Moderate | 79% repos have no snapshots, badges for 95%+ repos missing |
| **Outdated Hardcoded Copy** | 🟡 Moderate | "7,000+" in 3 places while actual count is 9,830 |
| **Duplicate Repos in DB** | 🟡 Moderate | 14 duplicate entries in repos.json |
| **Stale Sitemap Pages** | 🟡 Moderate | 2,070 project pages in sitemap not in current DB |
| **All Categories "declining"** | 🟡 Moderate | Momentum always 0, trend always "declining" |
| **Digest Sections Empty** | 🟡 Moderate | "Hidden Gems" and "Established Leaders" empty every week |
| **Discovery Workflow Failing** | 🟡 Moderate | Last 2 discover runs cancelled |
| **Breakouts Always Empty** | 🟠 Minor | 0 breakouts since Aug 25 |
| **Accessibility (Contrast)** | 🟠 Minor | WCAG AA fail on stat-labels and project descriptions |
| **Compare Links Broken** | 🟠 Minor | Compiled JS uses literal `${i}project/…` in hrefs |

**Lighthouse Scores (Homepage):** Accessibility 96 · Best Practices 100 · SEO 100

---

## 🔴 CRITICAL ISSUES

### 1. Five Documented API Endpoints Return 404

The **API docs page** lists these endpoints, but they all return **404 Not Found** on the live site:

| Endpoint | Status | What Happened |
|----------|--------|---------------|
| `/api/trends.json` | 404 | `export.py` writes `trends.json` to `data/exports/` but NOT to `data/exports/api/` |
| `/api/category-intelligence.json` | 404 | Same — written to root exports, never copied to `api/` subfolder |
| `/api/history/{owner}__{repo}.json` | 404 | Written to `data/exports/history/` not `data/exports/api/history/` |
| `/api/projects/{owner}__{repo}.json` | 404 | API docs reference this path but it was never an API endpoint — files are in `data/exports/projects/` |
| `/api/favicon.ico` | 404 | Minor: browsers request this from `/api/` prefix |

**Root cause:** `export.py` writes `trends.json`, `category-intelligence.json`, `history/`, and `projects/` to `data/exports/` — but the deploy workflow only copies `data/exports/api/` to `dist/api/`. The `PublicAPI.generate_all()` endpoint generator doesn't produce these files.

**Impact:** Any developer following the API docs gets broken responses. The `llms.txt` file also links to these 404 endpoints, misleading AI agents.

---

### 2. Every Page Has the Same Canonical URL and og:url

**Every single page** on the site has:
```html
<link rel="canonical" href="https://radar.bharatdn.com/" />
<meta property="og:url" content="https://radar.bharatdn.com/" />
```

| Page | canonical Should Be | Actual canonical |
|------|---------------------|------------------|
| `/top/` | `.../top/` | `.../` ❌ |
| `/trending/` | `.../trending/` | `.../` ❌ |
| `/categories/` | `.../categories/` | `.../` ❌ |
| `/project/ggml-org/llama.cpp/` | `.../project/ggml-org/llama.cpp/` | `.../` ❌ |
| `/digests/week-2026-W43/` | `.../digests/week-2026-W43/` | `.../` ❌ |

**Root cause:** `Layout.astro` line 24 — only the homepage passes `canonical` prop. All other pages don't pass it, so the fallback `${siteUrl}${base}` always resolves to the root URL.

**Impact:**  
- Google treats ALL 11,900+ pages as duplicates of the homepage  
- 9,800+ project pages will never rank individually in search  
- Social sharing shows wrong URL for every page  

---

### 3. Rankings Page Is 14.8 MB — Unusable Performance

| Metric | Value |
|--------|-------|
| HTML size | **14.8 MB** (14,842,466 bytes) |
| DOM rows | **9,831** `<tr>` elements |
| DOMContentLoaded | **12.5 seconds** |
| Full Load | **22.3 seconds** |
| Total elapsed (navigation) | **52 seconds** |

All 9,830 repos are server-side rendered into a single HTML table. The client-side filter/search script then hides rows with `display: none` — but all 9,830 rows remain in the DOM.

**Also observed:** After filtering to "Declining" + searching "llama", the result count says "Showing 181 of 9,830 projects" but `visible` rows count is **0** — the search filter AND momentum filter don't compose correctly (they fight each other with `display:none`).

---

### 4. og:image Falls Back to favicon.svg (Not a Valid Social Image)

Every page except project detail pages uses **`favicon.svg`** as the OpenGraph image:
```html
<meta property="og:image" content=".../favicon.svg" />
```

- Twitter/LinkedIn/Slack **will not render SVG** as a social card — they expect PNG/JPEG
- The site has a perfectly good `og.png` (96 KB) at `/og.png` but it's not being used
- `og:image:width` says 1200×630 but the favicon.svg is a tiny icon

---

## 🟡 MODERATE ISSUES

### 5. Hardcoded "7,000+" in Multiple Places (Actual: 9,830)

| File | Line | Text |
|------|------|------|
| `Layout.astro` | 12 | `"Track 7,000+ AI open-source projects"` (default description) |
| `index.astro` | 78 | `"breakout detection for 7,000+ projects"` |
| `index.astro` | 89 | `"Track 7,000+ projects scored by impact"` |

The homepage stat cards correctly show the dynamic "9.8k" from `stats.json`, but the meta description and hero subtitle are hardcoded stale numbers.

---

### 6. `top.astro` Meta Description Has Unrendered Template Variable

```html
<meta name="description" content="Full rankings of {repos.length} AI open-source projects by momentum score." />
```

The literal text `{repos.length}` appears in the HTML — Astro doesn't interpolate inside string attribute values this way. Every search engine sees this broken text.

---

### 7. Scoring Coverage Is Only 7.1% — 79% of Repos Have No Snapshots

From the live `/status/` page:
- **Snapshot coverage:** 2,067 / 9,830 repos (21.0%)
- **Scoring coverage:** 700 / 9,830 repos (7.1%)

This means **7,763 repos** have **0 snapshots** and **9,130 repos** have no scores. Their project pages show:
- `7-Day Stars: +0`
- `30-Day Stars: +0`  
- `Acceleration: x` (literally the letter "x", no number)
- `Why it ranks: Strong momentum — adoption is accelerating week over week.` ← **This text appears even on repos with 0 velocity!**

---

### 8. All 11 Categories Show "declining" — Momentum Always 0

The `/api/categories.json` shows **every single category** has `"momentum": 0` and `"trend": "declining"`. The homepage, categories page, and trends page all show every category as red "declining".

This suggests the `CategoryTracker.compute_momentum()` method always returns 0 — making the entire momentum intelligence feature nonfunctional.

---

### 9. Discover Workflow Cancelled (Last 2 Runs)

| Run Date | Conclusion |
|----------|------------|
| Nov 1, 2026 18:45 UTC | **cancelled** |
| Nov 1, 2026 09:22 UTC | **cancelled** |
| Oct 31, 2026 18:13 UTC | success |

The last 2 discovery runs were cancelled (likely hitting the 25-minute timeout). This means no new repos are being discovered.

---

### 10. 14 Duplicate Repos in the Database

These repos appear twice in `repos.json`:

```
hmbown/codewhale, the-vibe-company/quivr, jub0t/concat, 
awarexone/agentic-bug-hunter, claration/feather, ccch1mneyyy/dsh-go,
moizibnyousaf/ai-agent-skills, anush008/fastembed-rs, coss-india/voicera,
datamllab/openebfm, veratools/vera, stevyhacker/lokalbot,
ronitgupta138/vectra-core, freddydeveloper/codewords
```

---

### 11. 2,070 Stale Project Pages in Sitemap

The sitemap has **11,900 project URLs** but the database only has **9,830 repos**. That means **2,070 project pages** (17%) exist in the sitemap/deployed site but are no longer in the database. These pages still load (200 OK) but show stale data and are unreachable from navigation.

---

### 12. Weekly Digest "Hidden Gems" and "Established Leaders" Always Empty

Checked digests W34 through W43 — every single week:
- **Hidden Gems** section: header exists but **0 entries** (just "Low stars but high velocity…" then nothing)
- **Established Leaders** section: header exists but **0 entries** (just "Mature, reliable projects…" then nothing)

The weekly report generation logic appears broken for these two sections.

---

### 13. Badges Only Exist for ~100 Repos (Not All 9,830)

Testing 21 random repos from the database: **20 out of 21** returned **404** for their badge SVG. Only the ~100 top-scored repos have generated badges. But the API docs and README encourage ANY tracked repo to use badges.

---

### 14. Breakouts Data Is 2+ Months Stale

`/api/breakouts.json` `generated_at` = **2026-08-25** — hasn't been regenerated since. Always shows `"total": 0, "candidates": []`. The breakouts page just says "No breakouts detected yet."

---

## 🟠 MINOR ISSUES

### 15. Compare Tool — Broken Links in Comparison Table

The compiled compare script has a variable collision. After Astro builds, the table header links use literal `${i}project/…` instead of the actual base URL:

```html
<a href="${i}project/ggml-org/llama.cpp">ggml-org/llama.cpp</a>
```

**Root cause:** In `compare.ts` the variable `i` is used in `SITE_BASE` context, but after Astro compilation the template literal string doesn't get the right SITE_BASE value injected.

**Impact:** Clicking a repo name in the comparison table goes to a 404 page.

---

### 16. Category Page Title Is Doubled

```html
<title>AI Agents — Open Source AI Radar — Open Source AI Radar</title>
```

The `[name].astro` template passes a title that already includes the site name, then `Layout.astro` appends it again.

---

### 17. Accessibility — Insufficient Color Contrast (WCAG AA Fail)

| Element | Foreground | Background | Ratio | Required |
|---------|-----------|------------|-------|----------|
| `.stat-label` | #71717a | #18181b | 3.66:1 | 4.5:1 ❌ |
| `.project-desc` | #71717a | #09090b | 4.11:1 | 4.5:1 ❌ |

---

### 18. `robots.txt` Points to Wrong Sitemap URL

```
Sitemap: https://radar.bharatdn.com/sitemap.xml
```

But the actual sitemap is at `/sitemap-index.xml`. The URL `/sitemap.xml` returns **404**.

---

### 19. JSON-LD Structured Data Only on Homepage

Only the homepage has `application/ld+json` schema markup. The 9,800+ project pages, categories, and other pages have **no structured data** — missed opportunity for rich snippets.

---

### 20. `"Why it ranks"` Text Is Generic and Often Wrong

Every project page shows one of these canned messages:
- `"Strong momentum — adoption is accelerating week over week."` — even for repos with 0 velocity and 0 recent stars
- `"Modest but positive momentum."` — for repos that haven't been updated in months

---

## ✅ WHAT'S WORKING WELL

| Feature | Status |
|---------|--------|
| **Process workflow** | ✅ Running 4x/day successfully |
| **Weekly report generation** | ✅ Running every Monday |
| **Deploy workflow** | ✅ Auto-deploys on push to main |
| **Project detail pages** | ✅ All 9,800+ load correctly (200 OK) |
| **Compare tool (core)** | ✅ Search, suggest, comparison table all work |
| **RSS feed** | ✅ 20 items, fresh dates |
| **Core API endpoints** | ✅ repos.json, top.json, trending.json, gems.json, categories.json, compare-index.json all work |
| **Badge SVG quality** | ✅ Clean, correct score values for repos that have badges |
| **Sitemap structure** | ✅ 11,932 URLs, no duplicates |
| **Lighthouse Best Practices** | ✅ 100/100 |
| **Lighthouse SEO** | ✅ 100/100 (ironic given the canonical issue) |
| **Avatar fallback system** | ✅ Works well with initials |
| **Mobile nav** | ✅ Hamburger menu works |

---

## 📋 Prioritized Fix List

### 🔥 Fix First (High Impact, Relatively Easy)

1. **Fix canonical/og:url** — Pass `canonical={Astro.url.pathname}` from every page template to Layout
2. **Fix og:image** — Use `/og.png` as default instead of `favicon.svg`
3. **Fix `{repos.length}` in top.astro description** — Use template expression properly
4. **Fix "7,000+" hardcoded text** — Use dynamic count from stats
5. **Fix `robots.txt` sitemap URL** — Point to `sitemap-index.xml`
6. **Fix category page double title** — Remove " — Open Source AI Radar" from the title prop
7. **Copy missing API files** — Add `trends.json`, `category-intelligence.json`, `history/` to `data/exports/api/` in `export.py` or in deploy workflow
8. **Fix compare link variable** — Use `SITE_BASE` correctly in render function

### 🔨 Fix Next (Medium Effort, Big Impact)

9. **Paginate rankings page** — Show 50-100 repos, load more on scroll/click
10. **Fix category momentum** — Debug `CategoryTracker.compute_momentum()` returning 0
11. **Generate badges for all scored repos** — Not just top 100
12. **Fix "Why it ranks" text** — Make it conditional on actual velocity/growth data
13. **Fix Acceleration display** — Show "N/A" instead of bare "x" when data missing
14. **Fix discovery workflow timeouts** — Investigate why last 2 runs cancelled
15. **Fix contrast ratios** — Lighten `--text-muted` from `#71717a` to `#9ca3af` or similar

### 🧹 Cleanup (Lower Priority)

16. **Deduplicate repos** — Remove 14 duplicate entries
17. **Clean stale sitemap entries** — Remove 2,070 project URLs not in DB
18. **Fix digest empty sections** — Debug Hidden Gems / Established Leaders generation
19. **Update README stats** — Currently says "7,826 repos · Updated 2026-08-30"
20. **Add JSON-LD to project pages** — SoftwareApplication or Dataset schema

---

*Report generated by auditing the live website, GitHub API, workflow runs, source code, and browser testing.*
