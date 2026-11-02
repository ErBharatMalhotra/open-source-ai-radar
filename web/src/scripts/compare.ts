interface Project {
  full_name: string;
  description?: string;
  language?: string | null;
  stars: number;
  forks?: number;
  license?: string | null;
  created_at?: string | null;
  pushed_at?: string | null;
  radar_score?: number;
  impact?: number;
  velocity?: number;
  health?: number;
  category?: string;
}

interface IndexData {
  projects: Project[];
}

const state = {
  data: [] as Project[],
  picks: [null, null, null] as (Project | null)[],
};

function fmt(n: number): string {
  if (!Number.isFinite(n)) return "—";
  if (n >= 1e6) return (n / 1e6).toFixed(1) + "M";
  if (n >= 1e3) return (n / 1e3).toFixed(1) + "k";
  return String(Math.round(n));
}

function age(created?: string | null): string {
  if (!created) return "—";
  const days = Math.max(1, Math.round((Date.now() - new Date(created).getTime()) / 86400000));
  if (days < 365) return `${Math.round(days / 30)} mo`;
  return `${(days / 365).toFixed(1)} yr`;
}

function bestIdx(values: (number | undefined)[], higher = true): number {
  const nums = values.filter((v): v is number => typeof v === "number" && Number.isFinite(v));
  if (nums.length < 2) return -1;
  const target = higher ? Math.max(...nums) : Math.min(...nums);
  if (nums.filter((v) => v === target).length === nums.length) return -1;
  return values.indexOf(target);
}

const SITE_BASE = import.meta.env.BASE_URL || "/";

async function load(): Promise<void> {
  const res = await fetch(`${SITE_BASE}api/compare-index.json`);
  const json: IndexData = await res.json();
  state.data = json.projects || [];
  const hint = document.getElementById("hint") as HTMLElement;
  hint.textContent = `${state.data.length.toLocaleString()} projects loaded — start typing above`;
}

function search(q: string, exclude: string[]): Project[] {
  const needle = q.toLowerCase().trim();
  if (!needle) return [];
  return state.data
    .filter((p) => !exclude.includes(p.full_name))
    .filter(
      (p) =>
        p.full_name.toLowerCase().includes(needle) ||
        (p.description || "").toLowerCase().includes(needle),
    )
    .slice(0, 8);
}

function renderSuggest(slot: number): void {
  const box = document.getElementById("suggest") as HTMLElement;
  const input = document.querySelector<HTMLInputElement>(`input[data-slot='${slot}']`);
  if (!input || !box.parentElement) return;
  const exclude = state.picks.filter(Boolean).map((p) => (p as Project).full_name);
  const results = search(input.value, exclude);

  const rect = input.getBoundingClientRect();
  const parentRect = box.parentElement.getBoundingClientRect();
  box.style.left = `${rect.left - parentRect.left}px`;
  box.style.width = `${rect.width}px`;

  if (results.length === 0) {
    box.style.display = "none";
    box.innerHTML = "";
    return;
  }
  box.style.display = "block";
  box.className = "cmp-suggest";
  box.innerHTML = results
    .map((p, i) => `<button type="button" data-i="${i}">${p.full_name} · ${fmt(p.stars)} ★</button>`)
    .join("");
  box.querySelectorAll("button").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.picks[slot] = results[Number(btn.dataset.i)];
      input.value = (state.picks[slot] as Project).full_name;
      box.style.display = "none";
      box.innerHTML = "";
      render();
    });
  });
}

function cell(label: string, vals: (string | number | undefined)[], numericBest = false, higher = true): string {
  const bi = numericBest ? bestIdx(vals as (number | undefined)[], higher) : -1;
  const tds = vals
    .map((v, i) => {
      const text = typeof v === "number" ? fmt(v) : v || "—";
      const cls = i === bi ? ' class="best"' : "";
      return `<td${cls}>${text}</td>`;
    })
    .join("");
  return `<tr><td class="metric">${label}</td>${tds}</tr>`;
}

function render(): void {
  const picked = state.picks.filter(Boolean) as Project[];
  const el = document.getElementById("result") as HTMLElement;
  if (picked.length < 2) {
    el.innerHTML =
      '<div class="card" style="padding:var(--sp-6); color:var(--text-muted); text-align:center;">Select at least two projects to compare.</div>';
    return;
  }

  const header = `<tr><th></th>${picked
    .map((p) => `<th><a href="${import.meta.env.BASE_URL}project/${p.full_name}" style="color:var(--accent); text-decoration:none;">${p.full_name}</a></th>`)
    .join("")}</tr>`;

  const body = [
    cell("Category", picked.map((p) => p.category || "—")),
    cell("Language", picked.map((p) => p.language || "—")),
    cell("License", picked.map((p) => p.license || "None")),
    cell("Stars", picked.map((p) => p.stars), true),
    cell("Forks", picked.map((p) => p.forks), true),
    cell("Radar Score", picked.map((p) => (typeof p.radar_score === "number" ? Number(p.radar_score.toFixed(1)) : undefined)), true),
    cell("Impact", picked.map((p) => (typeof p.impact === "number" ? Number(p.impact.toFixed(1)) : undefined)), true),
    cell("Velocity", picked.map((p) => (typeof p.velocity === "number" ? Number(p.velocity.toFixed(1)) : undefined)), true),
    cell("Health", picked.map((p) => (typeof p.health === "number" ? Number(p.health.toFixed(1)) : undefined)), true),
    cell("Age", picked.map((p) => age(p.created_at))),
    cell("Last Push", picked.map((p) => (p.pushed_at ? new Date(p.pushed_at).toLocaleDateString() : "—"))),
  ].join("");

  const colors = ["var(--accent, #6366f1)", "var(--green, #10b981)", "#f59e0b"];

  const chartBars = [
    { label: "Radar Score", key: "radar_score", max: 100 },
    { label: "Velocity", key: "velocity", max: 100 },
    { label: "Impact", key: "impact", max: 100 },
    { label: "Health", key: "health", max: 100 },
    { label: "Stars", key: "stars", max: Math.max(...picked.map((p) => p.stars || 1)) },
  ];

  const chartHtml = `
    <div class="card" style="padding:var(--sp-6); margin-bottom:var(--sp-6);">
      <h3 style="font-size:var(--text-md); font-weight:700; margin-bottom:var(--sp-4);">Metric Comparison Overlay</h3>
      <div style="display:flex; gap:var(--sp-6); margin-bottom:var(--sp-4); font-size:var(--text-xs);">
        ${picked
          .map(
            (p, i) =>
              `<div style="display:flex; align-items:center; gap:6px;"><span style="width:10px; height:10px; border-radius:2px; background:${colors[i]};"></span><strong>${p.full_name}</strong></div>`,
          )
          .join("")}
      </div>
      <div style="display:grid; gap:var(--sp-4);">
        ${chartBars
          .map((bar) => {
            return `
              <div>
                <div style="display:flex; justify-content:space-between; font-size:var(--text-xs); color:var(--text-muted); margin-bottom:4px;">
                  <span>${bar.label}</span>
                </div>
                <div style="display:grid; grid-template-columns:repeat(${picked.length}, 1fr); gap:8px;">
                  ${picked
                    .map((p, i) => {
                      const raw = (p as any)[bar.key] || 0;
                      const pct = Math.min(100, Math.max(4, (raw / bar.max) * 100));
                      const disp = bar.key === "stars" ? fmt(raw) : Number(raw).toFixed(1);
                      return `
                        <div>
                          <div style="display:flex; justify-content:space-between; font-size:11px; margin-bottom:2px;">
                            <span style="color:${colors[i]}; font-weight:600;">${disp}</span>
                          </div>
                          <div style="background:var(--border-subtle); height:8px; border-radius:4px; overflow:hidden;">
                            <div style="background:${colors[i]}; width:${pct}%; height:100%; border-radius:4px; transition:width 0.4s ease;"></div>
                          </div>
                        </div>
                      `;
                    })
                    .join("")}
                </div>
              </div>
            `;
          })
          .join("")}
      </div>
    </div>
  `;

  el.innerHTML = `${chartHtml}<div class="card" style="padding:var(--sp-4); overflow:auto;">
    <table class="cmp-table">${header}${body}</table>
  </div>`;
}

function init(): void {
  document.querySelectorAll<HTMLInputElement>(".compare-search").forEach((input) => {
    input.addEventListener("input", () => renderSuggest(Number(input.dataset.slot)));
    input.addEventListener("focus", () => renderSuggest(Number(input.dataset.slot)));
  });
  document.addEventListener("click", (e) => {
    const t = e.target as HTMLElement;
    if (!t.closest("#suggest") && !t.classList.contains("compare-search")) {
      const box = document.getElementById("suggest") as HTMLElement;
      box.style.display = "none";
    }
  });
  document.getElementById("compareBtn")?.addEventListener("click", render);
  load().then(() => {
    const params = new URLSearchParams(window.location.search);
    const p1 = params.get("p1") || params.get("a");
    const p2 = params.get("p2") || params.get("b");
    const p3 = params.get("p3") || params.get("c");
    const inputs = document.querySelectorAll<HTMLInputElement>(".compare-search");

    if (p1) {
      const match1 = state.data.find((p) => p.full_name.toLowerCase() === p1.toLowerCase());
      if (match1) {
        state.picks[0] = match1;
        if (inputs[0]) inputs[0].value = match1.full_name;
      }
    }
    if (p2) {
      const match2 = state.data.find((p) => p.full_name.toLowerCase() === p2.toLowerCase());
      if (match2) {
        state.picks[1] = match2;
        if (inputs[1]) inputs[1].value = match2.full_name;
      }
    }
    if (p3) {
      const match3 = state.data.find((p) => p.full_name.toLowerCase() === p3.toLowerCase());
      if (match3) {
        state.picks[2] = match3;
        if (inputs[2]) inputs[2].value = match3.full_name;
      }
    }
    render();
  });
}

init();

export {};
