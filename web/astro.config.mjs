// @ts-check
import { defineConfig } from 'astro/config';
import sitemap from '@astrojs/sitemap';

// https://astro.build/config
export default defineConfig({
  site: 'https://erbharatmalhotra.github.io',
  base: '/open-source-ai-radar/',
  output: 'static',
  outDir: '../dist',
  integrations: [
    sitemap({
      filter: (path) => !path.includes('/api/'),
    }),
  ],
});
