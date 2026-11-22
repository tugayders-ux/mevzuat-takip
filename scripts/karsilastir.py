"""Değiştiren düzenlemeyi mevzuat arşivindeki güncel metinle karşılaştırır.

Güvenilir işlemler otomatik yapılır: madde değiştirme, madde ekleme, madde kaldırma.
Fıkra/bent/ibare düzeyindeki değişiklikler tahmin edilmez; "elle uygula" diye işaretlenir.
"""
import difflib
import html
import json
import re
from pathlib import Path

ARSIV_DIZINI = Path(__file__).resolve().parent.parent / "mevzuat"

SIRA = r"(?:inci|ıncı|nci|ncı|üncü|uncu|ncü|ncu)"
HEDEF_RE = re.compile(rf"(geçici\s+|ek\s+)?(\d+(?:/[a-zçğıöşü])?)\s*{SIRA}\s+madde")
COKLU_RE = re.compile(rf"\d+\s*(?:,|ve)\s*\d+\s*{SIRA}\s+madde")
PARCA_RE = re.compile(r"fıkra|bent|cümle|ibare|sözcük|ifade|başlığ|bölüm|kısım|tablo|\bek-?\s*\d|liste|çizelge")
ALINTI_MADDE_RE = re.compile(
    r"^\s*((?:GEÇİCİ|Geçici)\s+|(?:EK|Ek)\s+)?(?:MADDE|Madde)\s+(\d+(?:/[A-ZÇĞİÖŞÜa-zçğıöşü])?)\s*[–—-]\s*"
)


def norm(s):
    s = s.replace("İ", "i").replace("I", "ı").lower()
    return re.sub(r"\s+", " ", s).strip()


def asil_ad(baslik):
    """'X Yönetmeliğinde Değişiklik Yapılmasına Dair Yönetmelik' -> 'X Yönetmeliği'"""
    m = re.match(r"^(.+?)\s+Değişiklik", baslik.strip())
    if not m:
        return None
    ad = m.group(1).strip()
    return re.sub(r"(Yönetmeli[kğ]i?|Tebli[ğg]i?)(?:nde|nda|de|da|te|ta)$", r"\1", ad)


def arsiv_bul(ad):
    if not ad:
        return None
    hedef = norm(ad)
    for dosya in sorted(ARSIV_DIZINI.glob("*.json")):
        try:
            veri = json.loads(dosya.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if norm(veri.get("ad", "")) == hedef:
            return veri
    return None


def madde_id(onek, no):
    o = (onek or "").strip().lower()
    return ("G" if o.startswith("geçici") else "E" if o == "ek" else "") + no.upper()


def etiket(mid):
    if mid[:1] == "G" and mid[1:2].isdigit():
        return f"Geçici Madde {mid[1:]}"
    if mid[:1] == "E" and mid[1:2].isdigit():
        return f"Ek Madde {mid[1:]}"
    return f"Madde {mid}"


def blok_ayir(metin):
    """Değiştiren düzenlemenin maddeleri: [(no, [satırlar])] (yürürlük/yürütme hariç)."""
    ilk = re.search(r"(?m)^MADDE\s*\d+\s*[-–—]", metin)
    if not ilk:
        return []
    sonuc = []
    for parca in re.split(r"(?m)^(?=MADDE\s*\d+\s*[-–—])", metin[ilk.start():]):
        satirlar = [l for l in parca.split("\n") if l.strip()]
        m = re.match(r"MADDE\s*(\d+)\s*[-–—]\s*(.*)", satirlar[0]) if satirlar else None
        if not m:
            continue
        govde = ([m.group(2)] if m.group(2) else []) + satirlar[1:]
        tam = " ".join(govde)
        if re.search(r"yürürlüğe girer|yürütür", tam) and "“" not in tam:
            continue
        sonuc.append((m.group(1), govde))
    return sonuc


def islem_cikar(govde):
    ham = "\n".join(govde)
    i, j = ham.find("“"), ham.rfind("”")
    yonerge = ham[:i] if i != -1 else ham
    alinti = ham[i + 1:j].strip() if i != -1 and j > i else ""
    c = norm(yonerge).replace("başlığıyla birlikte", "")
    hedefler = list(dict.fromkeys(madde_id(g, n) for g, n in HEDEF_RE.findall(c)))
    parca = bool(PARCA_RE.search(c)) or bool(COKLU_RE.search(c))
    yonerge = re.sub(r"\s+", " ", yonerge).strip()

    if not parca and alinti and "eklenmiştir" in c:
        m = ALINTI_MADDE_RE.match(alinti)
        if m:
            return {"tur": "ekle", "id": madde_id(m.group(1), m.group(2)),
                    "yeni": ALINTI_MADDE_RE.sub("", alinti, count=1)}
    if not parca and len(hedefler) == 1 and "yürürlükten kaldırılmıştır" in c:
        return {"tur": "kaldir", "id": hedefler[0]}
    if not parca and len(hedefler) == 1 and alinti and "aşağıdaki şekilde değiştirilmiştir" in c:
        return {"tur": "degistir", "id": hedefler[0], "yeni": ALINTI_MADDE_RE.sub("", alinti, count=1)}
    return {"tur": "manuel", "hedefler": hedefler, "yonerge": yonerge, "alinti": alinti}


def fark(eski, yeni):
    a = eski.replace("\n", " ¶ ").split()
    b = yeni.replace("\n", " ¶ ").split()
    parcalar = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if op == "equal":
            parcalar.append(html.escape(" ".join(a[i1:i2]), quote=False))
            continue
        if i2 > i1:
            parcalar.append("<del>" + html.escape(" ".join(a[i1:i2]), quote=False) + "</del>")
        if j2 > j1:
            parcalar.append("<ins>" + html.escape(" ".join(b[j1:j2]), quote=False) + "</ins>")
    return " ".join(parcalar).replace("¶", "<br>")


def alinti(t):
    return "\n>\n".join("> " + s for s in t.split("\n") if s.strip())


def baslik_satiri(mid, madde):
    b = f" — {madde['baslik']}" if madde and madde.get("baslik") else ""
    return f"#### {etiket(mid)}{b}\n"


def blok_yaz(i, maddeler):
    mid = i.get("id")
    madde = maddeler.get(mid)
    eski = madde["metin"] if madde else ""

    if i["tur"] == "degistir":
        s = baslik_satiri(mid, madde)
        if not madde:
            return f"{s}\n_Bu madde arşivde yok._\n\n**Önceki hâli:** TODO\n\n**Yeni hâli:**\n\n{alinti(i['yeni'])}\n"
        if norm(eski) == norm(i["yeni"]):
            return (f"{s}\n_Arşivdeki metin zaten yeni hâlle aynı; arşiv bu değişiklikten sonra alınmış. "
                    f"Önceki hâli elle ekle._\n\n**Önceki hâli:** TODO\n\n**Yeni hâli:**\n\n{alinti(i['yeni'])}\n")
        return (f"{s}\n**Fark:** {fark(eski, i['yeni'])}\n\n**Önceki hâli:**\n\n{alinti(eski)}\n\n"
                f"**Yeni hâli:**\n\n{alinti(i['yeni'])}\n")

    if i["tur"] == "ekle":
        s = baslik_satiri(mid, None)
        if madde and norm(eski) == norm(i["yeni"]):
            return f"{s}\n**Yeni madde eklendi** (arşiv zaten bu maddeyi içeriyor).\n\n{alinti(i['yeni'])}\n"
        return f"{s}\n**Yeni madde eklendi.**\n\n{alinti(i['yeni'])}\n"

    if i["tur"] == "kaldir":
        s = baslik_satiri(mid, madde)
        if not madde or not eski.strip():
            return f"{s}\n**Madde yürürlükten kaldırıldı.** _(Arşivde artık metni yok; önceki hâli elle ekle.)_\n\n**Önceki hâli:** TODO\n"
        return f"{s}\n**Madde yürürlükten kaldırıldı.**\n\n**Önceki hâli:**\n\n{alinti(eski)}\n"

    ad = ", ".join(etiket(h) for h in i["hedefler"]) or "Belirsiz madde"
    cikti = [f"#### {ad} — elle uygulanacak değişiklik\n",
             "_Fıkra, bent ya da ibare düzeyinde; otomatik uygulanmadı._\n",
             f"**Resmî metindeki ifade:**\n\n{alinti(i['yonerge'][:700])}\n"]
    if i["alinti"]:
        cikti.append(f"**Metinde verilen yeni kısım:**\n\n{alinti(i['alinti'])}\n")
    for h in i["hedefler"]:
        if h in maddeler:
            cikti.append(f"**Arşivdeki mevcut metin ({etiket(h)}):**\n\n{alinti(maddeler[h]['metin'])}\n")
    cikti.append("**Önceki hâli:** TODO\n\n**Yeni hâli:** TODO\n")
    return "\n".join(cikti)


def degisiklik_bolumu(metin, arsiv):
    maddeler = {m["id"]: m for m in arsiv["maddeler"]}
    ust = ("### Önceki hâli ve yeni hâli\n\n"
           f"_Karşılaştırma mevzuat arşivinden otomatik üretildi (arşiv tarihi: {arsiv.get('cekim', '?')}). "
           "Fark görünümünde <del>silinen</del> ve <ins>eklenen</ins> ifadeler işaretlidir. "
           "Resmî metinle doğrula._\n")
    bloklar = [blok_yaz(islem_cikar(g), maddeler) for _, g in blok_ayir(metin)]
    return ust + "\n" + ("\n".join(bloklar) if bloklar else "TODO: Değişen maddeler ayrıştırılamadı.\n")
