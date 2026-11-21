export const yol = (p: string) => import.meta.env.BASE_URL.replace(/\/$/, '') + p;
export const tarih = (d: Date) =>
  d.toLocaleDateString('tr-TR', { day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC' });
