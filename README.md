# Mevzuat Takip

Resmî Gazete'yi her sabah tarar, `takip_listesi.json` ile eşleşen düzenlemeler için
Markdown taslağı hazırlar, PR açar ve Telegram'dan haber verir.
PR'ı merge ettiğinde yazı yayınlanır (`icerik/yazilar/`).

## Kurulum
1. Bu klasörü yeni bir GitHub reposuna yükle (ana dal: `main`).
2. Settings → Secrets and variables → Actions: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`
3. Settings → Actions → General → "Allow GitHub Actions to create and approve pull requests" kutusunu işaretle.
4. Actions → Mevzuat Taraması → Run workflow (istersen `gun` alanına geçmiş bir tarih yaz) ile test et.

## Yerelde test
    pip install -r requirements.txt
    python scripts/tara.py 2026-11-20

## Takip listesini güncelleme
`takip_listesi.json` içine yeni kural veya anahtar kelime ekle; başka bir şey değişmez.

## Web sitesi (Astro + Supabase + GitHub Pages)

1. **Supabase:** yeni proje aç → SQL Editor'da `supabase/schema.sql` dosyasını çalıştır →
   Authentication → Sign In / Providers → **Anonymous sign-ins**'i aç.
2. **GitHub → Settings → Secrets and variables → Actions → Variables** sekmesine ekle:
   `PUBLIC_SUPABASE_URL` ve `PUBLIC_SUPABASE_ANON_KEY` (Supabase → Project Settings → API).
   Anon key herkese açık olacak şekilde tasarlanmıştır; güvenliği RLS kuralları sağlar.
3. **GitHub → Settings → Pages → Source: GitHub Actions** seç.
4. `main`'e push edince `Yayın` workflow'u siteyi yayınlar. Adres: `https://KULLANICI.github.io/REPO/`
5. Yerelde dene: `.env.example` → `.env` kopyala, doldur, `npm install && npm run dev`.

`icerik/yazilar/ornek-yazi` dosyasını ilk gerçek yazıdan sonra sil.
Yazıda `TODO` kaldıysa yayın workflow'u bilerek durur.
