import { readFileSync } from 'fs';
import { join } from 'path';

const OG_LIMIT = 800;

let cached: Set<string> | null = null;

/** full_names of projects that get a real OG card (top N by score). */
export function topProjectSet(): Set<string> {
  if (cached) return cached;
  try {
    const index = JSON.parse(
      readFileSync(join(process.cwd(), '..', 'data', 'exports', 'projects-index.json'), 'utf-8')
    );
    cached = new Set(
      (index.projects || [])
        .sort((a: any, b: any) => (b.radar_score || 0) - (a.radar_score || 0))
        .slice(0, OG_LIMIT)
        .map((p: any) => p.full_name)
    );
  } catch {
    cached = new Set();
  }
  return cached;
}
