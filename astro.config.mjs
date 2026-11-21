import { defineConfig } from 'astro/config';

// SITE_URL ve BASE_PATH yayın workflow'unda otomatik verilir.
export default defineConfig({
  site: process.env.SITE_URL || 'http://localhost:4321',
  base: process.env.BASE_PATH || '/',
});
