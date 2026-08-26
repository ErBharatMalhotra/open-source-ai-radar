# Open Source AI Radar — Website

Astro static site for the [Open Source AI Radar](https://erbharatmalhotra.github.io/open-source-ai-radar/).

## Data Source

Pages are pre-rendered at **build time** from committed exports in
`../data/exports/` (refreshed by the CI pipelines — this repo does not
call the GitHub API during builds):

- `projects/*.json` → one page per project at `/project/{owner}/{repo}/`
- `history/*.json` → 90-day star/score charts on project pages
- `category-intelligence.json` → `/categories` and category pages
- `trends.json` → `/trends` (rising stars, hidden gems, anomalies)
- The `/compare` tool fetches `/api/compare-index.json` client-side

## Commands

| Command | Action |
| :------ | :----- |
| `npm install` | Install dependencies |
| `npm run dev` | Local dev server at `localhost:4321` |
| `npm run build` | Production build to `./dist/` |
| `npm run preview` | Preview the production build |

## Notes

- `BASE_URL` is repo-relative (`/open-source-ai-radar/`) for GitHub Pages.
- OG images per project are generated with satori + resvg (`src/pages/project/[owner]/[repo]/og.png.ts`).
- Deploy happens via `.github/workflows/deploy.yml` on every push that touches site or data.
