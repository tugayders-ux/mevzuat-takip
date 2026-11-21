import { defineCollection, z } from 'astro:content';
import { glob } from 'astro/loaders';

const yazilar = defineCollection({
  loader: glob({ pattern: '**/*.md', base: './icerik/yazilar' }),
  schema: z.object({
    title: z.string(),
    date: z.coerce.date(),
    resmi_gazete_sayi: z.string().optional(),
    kaynak: z.string().url().optional(),
    tur: z.string().optional(),
    etiketler: z.array(z.string()).default([]),
  }),
});

export const collections = { yazilar };
