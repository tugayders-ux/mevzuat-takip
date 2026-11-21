#!/usr/bin/env python3
"""Resmî Gazete günlük taraması.

Takip listesiyle eşleşen düzenlemeler için icerik/yazilar/ altına Markdown
taslağı üretir. Taslak PR olarak açılır; sen onaylayınca (merge) yayına çıkar.

Kullanım:
    python scripts/tara.py              # bugünü tara
    python scripts/tara.py 2026-11-20   # belirli bir günü tara (test için)
"""
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

KOK = Path(__file__).resolve().parent.parent
BASE = "https://www.resmigazete.gov.tr"
HDR = {"User-Agent": "Mozilla/5.0 (kisisel mevzuat takip projesi)"}
YAZI_DIZINI = KOK / "icerik" / "yazilar"
TELEGRAM_DOSYA = Path("/tmp/telegram.txt")
PR_GOVDE_DOSYA = Path("/tmp/pr_govde.md")


def norm(s: str) -> str:
    """Türkçe uyumlu küçük harfe çevirme + boşluk temizliği."""
    s = s.replace("İ", "i").replace("I", "ı").lower()
    return re.sub(r"\s+", " ", s).strip()


def slug(s: str) -> str:
    tablo = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")
    s = s.translate(tablo).lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")[:70].strip("-")


def cikti(**kv):
    """GitHub Actions çıktıları (yerelde ekrana basar)."""
    yol = os.environ.get("GITHUB_OUTPUT")
    if yol:
        with open(yol, "a", encoding="utf-8") as f:
            for k, v in kv.items():
                f.write(f"{k}={v}\n")
    else:
        print("[cikti]", kv)


def gun_bul():
    g = (os.environ.get("GUN") or (sys.argv[1] if len(sys.argv) > 1 else "")).strip()
    if g:
        return datetime.strptime(g, "%Y-%m-%d").date()
    return datetime.now(ZoneInfo("Europe/Istanbul")).date()


def gunluk_sayfa(g):
    url = f"{BASE}/eskiler/{g:%Y}/{g:%m}/{g:%Y%m%d}.htm"
    r = requests.get(url, headers=HDR, timeout=30)
    if r.status_code == 404:
        bugun = datetime.now(ZoneInfo("Europe/Istanbul")).date()
        if g == bugun:  # arşiv sayfası henüz oluşmamış olabilir
            url = BASE + "/"
            r = requests.get(url, headers=HDR, timeout=30)
    r.raise_for_status()
    return url, BeautifulSoup(r.content, "html.parser")


def kurallari_yukle():
    with open(KOK / "takip_listesi.json", encoding="utf-8") as f:
        return json.load(f)["kurallar"]


def eslesenler(baslik, kurallar):
    n = norm(baslik)
    return [k for k in kurallar if any(norm(a) in n for a in k["anahtar_kelimeler"])]


def ham_metin(url):
    """Düzenlemenin HTML metninden ilk bölümü alır (PDF ise boş döner)."""
    if url.lower().endswith(".pdf"):
        return ""
    try:
        r = requests.get(url, headers=HDR, timeout=30)
        r.raise_for_status()
        metin = BeautifulSoup(r.content, "html.parser").get_text("\n")
        metin = re.sub(r"\n\s*\n+", "\n\n", metin).strip()
        return metin[:3000].replace("-->", "--&gt;")
    except Exception as e:  # ham metin zorunlu değil
        return f"(Metin çekilemedi: {e})"


def taslak_yaz(g, sayi, baslik, url, kurallar):
    etiketler = [k["etiket"] for k in kurallar]
    konular = ", ".join(k["ad"] for k in kurallar)
    tur = "Değişiklik" if "değişiklik" in norm(baslik) else "Yeni düzenleme / diğer"
    dosya = YAZI_DIZINI / f"{g:%Y-%m-%d}-{slug(baslik)}.md"
    if dosya.exists():
        return None
    baslik_fm = baslik.replace('"', '\\"')
    ham = ham_metin(url)
    icerik = f"""---
title: "{baslik_fm}"
date: {g:%Y-%m-%d}
resmi_gazete_sayi: "{sayi}"
kaynak: "{url}"
tur: "{tur}"
etiketler: [{", ".join(etiketler)}]
---

> **Resmî Gazete:** {g:%d.%m.%Y} — Sayı: {sayi}
> **Konu:** {konular}
> **Tür:** {tur}
> **Kaynak:** [{url}]({url})

## Ne değişti?

TODO: 2-3 cümleyle özetle.

## Önemli maddeler

TODO: Değişen/eklenen maddeleri listele (madde no + kısa açıklama).

## Kimleri etkiler?

TODO: Üreticiler, belediyeler, tesis sahipleri vb.

## Yürürlük tarihi

TODO

## Kaynak

[Resmî Gazete'de oku]({url})

<!--
HAM METİN (yazıyı hazırlarken referans; yayından önce bu bloğu sil)
{ham}
-->
"""
    dosya.write_text(icerik, encoding="utf-8")
    return dosya


def main():
    g = gun_bul()
    kurallar = kurallari_yukle()
    try:
        sayfa_url, soup = gunluk_sayfa(g)
    except Exception as e:
        print(f"Sayfa alınamadı ({g}): {e}")
        cikti(bulundu="false", gun=f"{g:%Y-%m-%d}")
        return

    m = re.search(r"Say[ıi]\s*:?\s*(\d{4,6})", soup.get_text(" "))
    sayi = m.group(1) if m else "?"

    gorulen, bulunanlar = set(), []
    for a in soup.find_all("a", href=True):
        baslik = a.get_text(" ", strip=True)
        if len(baslik) < 15:
            continue
        url = urljoin(sayfa_url, a["href"])
        if url in gorulen:
            continue
        gorulen.add(url)
        es = eslesenler(baslik, kurallar)
        if es:
            bulunanlar.append((baslik, url, es))

    print(f"{g}: {len(gorulen)} bağlantı tarandı, {len(bulunanlar)} eşleşme.")

    YAZI_DIZINI.mkdir(parents=True, exist_ok=True)
    olusan = []
    for baslik, url, es in bulunanlar:
        d = taslak_yaz(g, sayi, baslik, url, es)
        if d:
            olusan.append((baslik, url, es))

    if not olusan:
        cikti(bulundu="false", gun=f"{g:%Y-%m-%d}")
        return

    satirlar = [f"📌 Mevzuat taraması — {g:%d.%m.%Y} (Sayı {sayi})", ""]
    for baslik, url, es in olusan:
        satirlar.append(f"• {baslik}\n  [{', '.join(k['ad'] for k in es)}]")
    satirlar += ["", "Taslak(lar) hazır, onayını bekliyor:"]
    TELEGRAM_DOSYA.write_text("\n".join(satirlar), encoding="utf-8")

    govde = [f"## {g:%d.%m.%Y} taraması", ""]
    for baslik, url, es in olusan:
        govde.append(f"- [{baslik}]({url}) — {', '.join(k['ad'] for k in es)}")
    govde += [
        "",
        "### Onay öncesi kontrol listesi",
        "- [ ] Tüm `TODO` alanlarını doldurdum",
        "- [ ] Madde numaralarını resmî metinden kontrol ettim",
        "- [ ] Dosyanın sonundaki HAM METİN yorum bloğunu sildim",
        "- [ ] Yürürlük tarihini doğruladım",
        "",
        "Merge = yayın.",
    ]
    PR_GOVDE_DOSYA.write_text("\n".join(govde), encoding="utf-8")
    cikti(bulundu="true", gun=f"{g:%Y-%m-%d}", adet=len(olusan))


if __name__ == "__main__":
    main()
