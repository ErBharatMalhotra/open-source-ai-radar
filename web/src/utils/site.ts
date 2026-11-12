/**
 * Absolute URL of the site root, without a trailing slash.
 *
 * e.g. `https://radar.bharatdn.com`
 *
 * Built from the Astro `site` config plus `base`, so changing the domain or
 * moving the site under a path prefix only touches astro.config.mjs.
 */
export function siteRoot(site: URL | undefined): string {
  const origin = site?.origin ?? '';
  const base = import.meta.env.BASE_URL || '/';
  return `${origin}${base}`.replace(/\/+$/, '');
}
