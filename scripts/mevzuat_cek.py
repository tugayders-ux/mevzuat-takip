#!/usr/bin/env python3
"""mevzuat.gov.tr'den takip listesindeki yönetmeliklerin güncel metnini çekip
mevzuat/ klasörüne madde madde arşivler.

- Önce robots.txt kontrol edilir; izin yoksa hiçbir şey çekilmez.
- Yönetmelik başına tek istek, aralarında bekleme (haftalık çalıştırma için tasarlandı).
- Metin değişmediyse dosya yeniden yazılmaz (gereksiz PR açılmaz).
- Site bozuk/boş yanıt verirse mevcut arşivin üzerine yazılmaz.
"""
import json
import re
import time
from datetime import datetime
from pathlib import Path
from urllib.robotparser import RobotFileParser
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

KOK = Path(__file__).resolve().parent.parent
ARSIV = KOK / "mevzuat"
HAM = KOK / "mevzuat_ham"  # hata ayıklama için; repoya eklenmez
HOST = "https://www.mevzuat.gov.tr"
UA = "Mozilla/5.0 (kisisel mevzuat takip projesi; haftalik dusuk hacimli kontrol)"
BEKLE = 3

MADDE_RE = re.compile(r"^((?:GEÇİCİ|EK)\s+)?MADDE\s+(\d+(?:/[A-ZÇĞİÖŞÜ])?)\s*(?:[–—-]\s*(.*))?$")
BOLUM_RE = re.compile(r"^(?:[A-ZÇĞİÖŞÜ]+\s+)*(?:BÖLÜM|KISIM)$")
EK_RE = re.compile(r"^(?:EKLER|EK[- ]\d+\w*\b.*)$")
NOT_RE = re.compile(r"\([^()]*\bRG[-–/ ][^()]*\)")
MADDE_OGE_RE = re.compile(r"^[a-zçğıöşü]\)|^\(|^\d+\)")


def slug(s):
    tablo = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")
    return re.sub(r"[^a-z0-9]+", "-", s.translate(tablo).lower()).strip("-")[:70]


def satirlar_al(html):
    soup = BeautifulSoup(html, "html.parser")
    for t in soup(["script", "style"]):
        t.decompose()
    metin = soup.get_text("\n").replace("\xa0", " ").replace("\r\n", " ").replace("\r", " ")
    satirlar = [re.sub(r"[ \t]+", " ", s).strip() for s in metin.split("\n")]
    return [s for s in satirlar if s]


def baslik_mi(s):
    return len(s) <= 100 and s[-1] not in ".;:," and not MADDE_OGE_RE.match(s)


def ayristir(satirlar):
    """Satırları madde listesine çevirir: [{id, no, tur, baslik, notlar, metin}]"""
    giris, maddeler = [], []
    mevcut, bekleyen = None, []
    bolum_modu = ek_modu = False

    for s in satirlar:
        if maddeler and EK_RE.match(s):
            ek_modu = True
        if ek_modu:
            continue
        if BOLUM_RE.match(s):
            bolum_modu, bekleyen = True, []
            continue
        m = MADDE_RE.match(s)
        if m:
            baslik = ""
            if bolum_modu:
                if bekleyen and baslik_mi(bekleyen[-1]):
                    baslik = bekleyen[-1]
                bolum_modu, bekleyen = False, []
            elif mevcut and mevcut["satirlar"] and baslik_mi(mevcut["satirlar"][-1]):
                baslik = mevcut["satirlar"].pop()
            tur = "gecici" if (m.group(1) or "").startswith("GEÇİCİ") else ("ek" if m.group(1) else "")
            no = m.group(2)
            mevcut = {
                "id": {"gecici": "G", "ek": "E", "": ""}[tur] + no,
                "no": no, "tur": tur or "madde", "baslik": baslik,
                "satirlar": [m.group(3)] if m.group(3) else [],
            }
            maddeler.append(mevcut)
        elif bolum_modu:
            bekleyen.append(s)
        elif mevcut:
            mevcut["satirlar"].append(s)
        else:
            giris.append(s)

    for md in maddeler:
        ham = "\n".join(md.pop("satirlar"))
        md["notlar"] = [n.strip("() ") for n in NOT_RE.findall(ham)]
        temiz = NOT_RE.sub("", ham)
        md["metin"] = "\n".join(x for x in (re.sub(r"\s+", " ", l).strip() for l in temiz.split("\n")) if x)
    return giris, maddeler


def robots_izin(url):
    try:
        r = requests.get(f"{HOST}/robots.txt", headers={"User-Agent": UA}, timeout=30)
        rp = RobotFileParser()
        rp.parse(r.text.splitlines())
        return rp.can_fetch(UA, url)
    except requests.RequestException as e:
        print(f"robots.txt okunamadı ({e}); güvenli tarafta kalıp çekmiyorum.")
        return False


def md_olustur(kayit):
    cikti = [f"# {kayit['ad']}", "",
             f"_Kaynak: {kayit['kaynak']} — çekim: {kayit['cekim']}_", ""]
    for m in kayit["maddeler"]:
        etiket = {"gecici": "Geçici Madde", "ek": "Ek Madde"}.get(m["tur"], "Madde")
        cikti.append(f"### {etiket} {m['no']}" + (f" — {m['baslik']}" if m["baslik"] else ""))
        if m["notlar"]:
            cikti.append("_" + "; ".join(m["notlar"]) + "_")
        cikti += ["", m["metin"], ""]
    return "\n".join(cikti)


def isle(kayit):
    no, tur, tertip, ad = kayit["no"], kayit["tur"], kayit["tertip"], kayit["ad"]
    url = f"{HOST}/anasayfa/MevzuatFihristDetayIframe?MevzuatTur={tur}&MevzuatNo={no}&MevzuatTertip={tertip}"
    print(f"\n== {ad} ({no})")
    if not robots_izin(url):
        print("  robots.txt bu adrese izin vermiyor; atlandı.")
        return False
    r = requests.get(url, headers={"User-Agent": UA}, timeout=60)
    if r.status_code != 200:
        print(f"  HATA: durum {r.status_code}")
        return False
    HAM.mkdir(exist_ok=True)
    (HAM / f"{no}.html").write_bytes(r.content)

    giris, maddeler = ayristir(satirlar_al(r.content))
    print(f"  {len(maddeler)} madde ayrıştırıldı; ilk satırlar: {giris[:2]}")

    dosya = ARSIV / f"{no}-{slug(ad)}.json"
    eski = json.loads(dosya.read_text(encoding="utf-8")) if dosya.exists() else None
    if len(maddeler) < 3 or (eski and len(maddeler) < 0.7 * len(eski["maddeler"])):
        print("  UYARI: madde sayısı beklenenden çok az; mevcut arşive dokunulmadı.")
        return False
    if eski and eski["maddeler"] == maddeler:
        print("  değişiklik yok.")
        return True

    kayit_json = {
        "ad": ad, "mevzuat_no": no, "etiket": kayit.get("etiket", ""),
        "kaynak": f"{HOST}/mevzuat?MevzuatNo={no}&MevzuatTur={tur}&MevzuatTertip={tertip}",
        "cekim": datetime.now(ZoneInfo("Europe/Istanbul")).strftime("%Y-%m-%d %H:%M"),
        "giris": giris[:30], "maddeler": maddeler,
    }
    ARSIV.mkdir(exist_ok=True)
    dosya.write_text(json.dumps(kayit_json, ensure_ascii=False, indent=1), encoding="utf-8")
    dosya.with_suffix(".md").write_text(md_olustur(kayit_json), encoding="utf-8")
    print("  arşiv güncellendi.")
    return True


def main():
    liste = json.loads((KOK / "mevzuat_listesi.json").read_text(encoding="utf-8"))
    for i, kayit in enumerate(liste):
        if i:
            time.sleep(BEKLE)
        try:
            isle(kayit)
        except Exception as e:
            print(f"  HATA ({kayit.get('ad')}): {e}")


if __name__ == "__main__":
    main()
