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


SAYI_RE = re.compile(r"say[ıiIİ]\s*[:：]?\s*(\d{5})", re.I)
RG_REF_RE = re.compile(r"(\d{1,2}/\d{1,2}/\d{4})\s+tarihli\s+ve\s+(\d{4,6})\s+sayılı")
KURUM_RE = re.compile(
    r"^\s*(.{3,120}?(?:Bakanlığı|Başkanlığı|Kurumu|Kurulu|Müdürlüğü|Üniversitesi))(?:ndan|nden):\s*$",
    re.M,
)
YURURLUK_RE = re.compile(r"MADDE\s*\d+\s*[-–—]\s*(Bu\s+[^.\n]{0,200}?yürürlüğe\s+girer)")
BASLIK_ASIL_RE = re.compile(
    r"^(.+?(?:Yönetmelik|Tebliğ|Kanun|Karar))(?:te|de|ta|da|nde|nda|inde|ında)?\s+Değişiklik"
)
ATLA_RE = re.compile(r"Bu\s+(?:Yönetmelik|Tebliğ)\s+(?:yayımı|yayım|\d)|Bu\s+(?:Yönetmelik|Tebliğ)\s+hükümlerini")


def sayfa_metni(url):
    """Düzenlemenin sayfa metnini satır yapısını koruyarak çeker (PDF ise boş)."""
    if url.lower().endswith(".pdf"):
        return ""
    try:
        r = requests.get(url, headers=HDR, timeout=30)
        r.raise_for_status()
        ham = BeautifulSoup(r.content, "html.parser").get_text("\n")
        satirlar = [re.sub(r"[ \t\u00a0]+", " ", x).strip() for x in ham.splitlines()]
        return "\n".join(x for x in satirlar if x)
    except Exception as e:
        print(f"Metin çekilemedi ({url}): {e}")
        return ""


def maddeleri_ayikla(metin):
    """Değiştiren düzenlemenin kendi maddelerini (yürürlük/yürütme hariç) döndürür."""
    i = re.search(r"(?m)^MADDE\s*1\s*[-–—]", metin)
    if not i:
        return []
    cikti_ = []
    for parca in re.split(r"(?m)^(?=MADDE\s*\d+\s*[-–—])", metin[i.start():]):
        parca = re.sub(r"\s+", " ", parca).strip()
        m = re.match(r"MADDE\s*(\d+)\s*[-–—]\s*(.*)", parca)
        if not m or ATLA_RE.match(m.group(2)):
            continue
        cikti_.append((m.group(1), m.group(2)))
    return cikti_


def asil_duzenleme(baslik, metin):
    """(değiştirilen düzenlemenin adı, ilk yayın bilgisi)"""
    m = BASLIK_ASIL_RE.match(baslik)
    ad = m.group(1) if m else None
    ref = RG_REF_RE.search(metin)
    ilk = f"{ref.group(1)} tarihli, {ref.group(2)} sayılı Resmî Gazete" if ref else None
    return ad, ilk


def kisalt(t, n=900):
    return t if len(t) <= n else t[:n].rsplit(" ", 1)[0] + " … (devamı resmî metinde)"


def taslak_icerik(g, sayi, baslik, url, kurallar, metin):
    etiketler = [k["etiket"] for k in kurallar]
    tur = "Değişiklik" if "değişiklik" in norm(baslik) else "Yeni düzenleme / diğer"
    degisiklik = tur == "Değişiklik"

    if not sayi:
        m = SAYI_RE.search(metin)
        sayi = m.group(1) if m else "TODO"
    km = KURUM_RE.search(metin)
    kurum = km.group(1).strip() if km else "TODO"
    ym = YURURLUK_RE.search(metin)
    yururluk = (ym.group(1).strip() + ".") if ym else "TODO"
    ad, ilk = asil_duzenleme(baslik, metin)

    etkilenenler = []
    for k in kurallar:
        for e in k.get("etkilenenler", []):
            if e not in etkilenenler:
                etkilenenler.append(e)

    satirlar = [
        f"- **Resmî Gazete:** {g:%d.%m.%Y} — Sayı: {sayi}",
        f"- **Yayımlayan kurum:** {kurum}",
    ]
    if degisiklik:
        asil = ad or "TODO"
        satirlar.append(f"- **Değiştirilen düzenleme:** {asil}" + (f" (ilk yayın: {ilk})" if ilk else ""))
    satirlar += [
        f"- **Yürürlük:** {yururluk}",
        f"- **Kaynak:** [{url}]({url})",
    ]

    if degisiklik:
        bloklar = []
        for no, yazi in (maddeleri_ayikla(metin) or [("TODO", "TODO")]):
            bloklar.append(
                f"#### Madde {no}\n\n**Önceki hâli:** TODO\n\n**Yeni hâli:**\n\n> {kisalt(yazi)}\n"
            )
        degisim = (
            "### Önceki hâli ve yeni hâli\n\n"
            "_Yeni hâl resmî metinden otomatik alındı; sadeleştir. Önceki hâli, değiştirilen "
            "düzenlemenin yürürlükteki metninden (mevzuat.gov.tr) elle yazılır._\n\n"
            + "\n".join(bloklar)
        )
    else:
        degisim = "### Ana hatlarıyla neler getiriyor?\n\nTODO: Başlıca hükümleri 3-5 maddede özetle.\n"

    etki = "\n".join(f"- {e}" for e in etkilenenler) or "- TODO"
    yapmali = "\n".join(f"- **{e}:** TODO" for e in etkilenenler) or "- **TODO:** TODO"
    baslik_fm = baslik.replace('"', '\\"')
    kurum_fm = kurum.replace('"', '\\"')

    return f"""---
title: "{baslik_fm}"
date: {g:%Y-%m-%d}
resmi_gazete_sayi: "{sayi}"
kaynak: "{url}"
tur: "{tur}"
kurum: "{kurum_fm}"
etiketler: [{", ".join(etiketler)}]
---

{chr(10).join(satirlar)}

## Ne değişti?

TODO: 2-3 cümlelik genel özet.

{degisim}
## Kimleri etkiler?

_Düzenlemenin kapsam maddesine göre doğrula; gerekmeyenleri sil, eksikleri ekle._

{etki}

## Bu düzenleme sonrası kim ne yapmalı?

{yapmali}

## Kaynak

[Resmî Gazete'de oku]({url})

<!--
HAM METİN (yazıyı hazırlarken referans; yayından önce bu bloğu sil)
{metin[:12000].replace("-->", "--&gt;")}
-->
"""


def taslak_yaz(g, sayi, baslik, url, kurallar):
    dosya = YAZI_DIZINI / f"{g:%Y-%m-%d}-{slug(baslik)}.md"
    if dosya.exists():
        return None
    dosya.write_text(
        taslak_icerik(g, sayi, baslik, url, kurallar, sayfa_metni(url)), encoding="utf-8"
    )
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

    m = SAYI_RE.search(soup.get_text(" "))
    sayi = m.group(1) if m else None

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

    satirlar = [f"📌 Mevzuat taraması — {g:%d.%m.%Y} (Sayı {sayi or '?'})", ""]
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
