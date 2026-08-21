// @ts-check
import { defineConfig } from 'astro/config';

// https://astro.build/config
export default defineConfig({
  site: 'https://erbharatmalhotra.github.io',
  base: '/open-source-ai-radar/',
  output: 'static',
  outDir: '../dist',
});
