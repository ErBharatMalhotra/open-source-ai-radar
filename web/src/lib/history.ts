import { readFileSync, readdirSync, existsSync } from 'fs';
import { join } from 'path';

export type RepoHistoryMap = Record<string, number[]>;

/**
 * Load star history for all exported repos at build time.
 *
 * Reads data/exports/history/{owner}__{repo}.json (top repos by score,
 * 90-day snapshots) and returns a map of full_name -> stars series
 * (oldest first). Returns an empty map when the directory is missing.
 */
export function loadRepoHistory(): RepoHistoryMap {
  const dir = join(process.cwd(), '..', 'data', 'exports', 'history');
  const map: RepoHistoryMap = {};
  if (!existsSync(dir)) return map;

  let files: string[] = [];
  try {
    files = readdirSync(dir).filter((f) => f.endsWith('.json'));
  } catch {
    return map;
  }

  for (const file of files) {
    try {
      const data = JSON.parse(readFileSync(join(dir, file), 'utf-8'));
      const name: string = data.full_name || file.replace(/\.json$/, '').replace('__', '/');
      const stars: number[] = (data.snapshots || [])
        .map((s: any) => Number(s.stars))
        .filter((v: number) => Number.isFinite(v));
      if (name && stars.length > 0) map[name] = stars;
    } catch {
      // Skip unreadable/corrupt history files
    }
  }
  return map;
}
