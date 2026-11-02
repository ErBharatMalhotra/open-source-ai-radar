# Frequently Asked Questions (FAQ)

### 1. How do I get my open-source AI project tracked on Radar?
Open a submission using our [Submit a Repo](https://github.com/ErBharatMalhotra/open-source-ai-radar/issues/new?template=submit-repo.yml) template. Submissions are reviewed and imported within a few days. The radar also runs automated 4-layer discovery (topics, keywords, trending activity, and free-text search) daily to discover emerging repositories automatically.

### 2. How often is the radar data refreshed?
- **Processing pipeline (`process.yml`)**: Runs **4 times daily** (00:00, 06:00, 12:00, 18:00 UTC) to update stars, forks, issues, PRs, and re-compute Impact, Velocity, and Health scores.
- **Discovery pipeline (`discover.yml`)**: Runs **twice daily** (02:00, 14:00 UTC) to discover newly published or trending AI projects.
- **Website deployment (`deploy.yml`)**: Automatically triggers after processing to publish the updated static dashboard to GitHub Pages.

### 3. Why did my project's Velocity score drop even though star count increased?
Radar uses **three-axis scoring**:
- **Impact (40%)**: Percentile ranking of stars, forks, and watchers.
- **Velocity (35%)**: 7-day and 30-day growth rate and acceleration, not absolute star volume.
- **Health (25%)**: Commit recency, release cadence, issue turnaround, and maintainer count.

If a project's star growth slows down relative to the prior week (e.g., from +100 stars/day to +20 stars/day), the acceleration drops, causing Velocity to decrease even while cumulative stars rise.

### 4. How can I embed a dynamic badge on my GitHub README?
Use the badge endpoint:
```markdown
[![AI Radar Score](https://erbharatmalhotra.github.io/open-source-ai-radar/api/badges/OWNER__REPO/score.svg)](https://erbharatmalhotra.github.io/open-source-ai-radar/project/OWNER/REPO/)
```
Replace `OWNER__REPO` with your repository path separated by two underscores (e.g. `BerriAI__litellm`).

### 5. Can I consume Radar data via API?
Yes, all radar intelligence is published statically under `/api/`:
- Top projects: `/api/top.json`
- All repos: `/api/repos.json` (and `/api/repos.csv`)
- Category intelligence: `/api/categories.json`
- Anomaly alerts: `/api/anomalies.json`
- Breakout candidates: `/api/breakouts.json`
- Machine-readable dataset for LLMs: `/api/llms.txt`
Full documentation is available at [API Docs](https://erbharatmalhotra.github.io/open-source-ai-radar/api-docs/).
