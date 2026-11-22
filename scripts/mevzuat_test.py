#!/usr/bin/env python3
"""mevzuat.gov.tr erişim testi.

Amaç: yönetmelik metni makine tarafından hangi yoldan okunabiliyor?
Az sayıda istek atar (listedeki her yönetmelik için 4 deneme, aralarında bekleme).
Ham yanıtlar mevzuat_test_cikti/ klasörüne kaydedilir.
"""
import json
import re
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

KOK = Path(__file__).resolve().parent.parent
CIKTI = KOK / "mevzuat_test_cikti"
HOST = "https://www.mevzuat.gov.tr"
HDR = {"User-Agent": "Mozilla/5.0 (kisisel mevzuat takip projesi; dusuk hacimli kontrol)"}
BEKLE = 3


def yollar(no, tur, tertip):
    return {
        "sayfa": f"{HOST}/mevzuat?MevzuatNo={no}&MevzuatTur={tur}&MevzuatTertip={tertip}",
        "iframe": f"{HOST}/anasayfa/MevzuatFihristDetayIframe?MevzuatTur={tur}&MevzuatNo={no}&MevzuatTertip={tertip}",
        "pdf-a": f"{HOST}/MevzuatMetin/yonetmelik/{tur}.{tertip}.{no}.pdf",
        "pdf-b": f"{HOST}/MevzuatMetin/{tur}.{tertip}.{no}.pdf",
    }


def pdf_metni(yol):
    try:
        from pypdf import PdfReader
        okuyucu = PdfReader(str(yol))
        return "\n".join((s.extract_text() or "") for s in okuyucu.pages[:3])
    except Exception as e:
        return f"(PDF metni okunamadı: {e})"


def dene(no, ad, url):
    print(f"\n  [{ad}] {url}")
    try:
        r = requests.get(url, headers=HDR, timeout=40)
    except requests.RequestException as e:
        print(f"    BAĞLANTI HATASI: {e}")
        return
    ct = r.headers.get("content-type", "")
    pdf = "pdf" in ct.lower() or r.content[:4] == b"%PDF"
    dosya = CIKTI / f"{no}-{ad}.{'pdf' if pdf else 'html'}"
    dosya.write_bytes(r.content)
    print(f"    durum={r.status_code} tür={ct.split(';')[0]} boyut={len(r.content)}")
    if r.status_code != 200:
        return
    if pdf:
        metin = pdf_metni(dosya)
    else:
        soup = BeautifulSoup(r.content, "html.parser")
        baslik = soup.title.get_text(strip=True) if soup.title else "-"
        iframeler = [f.get("src") for f in soup.find_all("iframe") if f.get("src")]
        print(f"    <title>: {baslik}")
        if iframeler:
            print(f"    iframe src: {iframeler[:3]}")
        metin = soup.get_text("\n")
    metin = re.sub(r"\n\s*\n+", "\n", metin).strip()
    print(f"    'MADDE' geçen yer sayısı: {len(re.findall(r'MADDE|Madde', metin))}")
    print(f"    ilk 400 karakter: {metin[:400]!r}")


def main():
    CIKTI.mkdir(exist_ok=True)
    print("== robots.txt ==")
    try:
        r = requests.get(f"{HOST}/robots.txt", headers=HDR, timeout=30)
        print(f"durum={r.status_code}")
        print(r.text[:1000])
    except requests.RequestException as e:
        print(f"robots.txt alınamadı: {e}")

    for kayit in json.loads((KOK / "mevzuat_listesi.json").read_text(encoding="utf-8")):
        no, tur, tertip = kayit["no"], kayit["tur"], kayit["tertip"]
        print(f"\n==== MevzuatNo={no} ====")
        for ad, url in yollar(no, tur, tertip).items():
            dene(no, ad, url)
            time.sleep(BEKLE)


if __name__ == "__main__":
    main()
