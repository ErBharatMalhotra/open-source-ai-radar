// @ts-check
import { defineConfig } from 'astro/config';
import sitemap from '@astrojs/sitemap';

// https://astro.build/config
export default defineConfig({
  // Canonical origin for canonical tags, sitemap and absolute URLs.
  // The site is served from the root of this domain (no repo-path base).
  site: 'https://radar.bharatdn.com',
  base: '/',
  output: 'static',
  outDir: '../dist',
  integrations: [
    sitemap({
      filter: (path) => !path.includes('/api/'),
    }),
  ],
});
