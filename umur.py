"""Umur lowongan dari label tanggal — relatif maupun absolut.

Satu tempat untuk semua platform (JobStreet, Glints, Indeed) supaya aturan
`MAX_AGE_DAYS` punya arti yang sama di mana pun. Sebelumnya setiap platform
punya caranya sendiri dan hanya mengenal label relatif ("3 hari lalu"),
sehingga tanggal absolut ("15 Nov 2026", "2026-11-15") terbaca sebagai
"umur tidak diketahui" lalu lolos filter umur tanpa catatan.

Aturan yang dipakai (audit #26):

* Zona waktu **WIB (Asia/Jakarta)**, bukan zona waktu komputer/server, supaya
  "hari ini" dan "kemarin" sama artinya di mana pun program dijalankan.
* Batas `MAX_AGE_DAYS` **inklusif**: umur 7 hari masih diterima saat batas 7,
  umur 8 hari ditolak.
* Tanggal yang tidak dapat dibaca → `None` ("DATE_UNKNOWN"), **bukan** 0.
  Pemanggil yang memutuskan apakah lowongan tanpa tanggal boleh dilamar
  (`TOLAK_UMUR_TAK_DIKETAHUI`).
"""

import re
from datetime import UTC, date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo


def zona_wib():
    """Zona WIB; jatuh ke offset tetap +07:00 bila database zona tidak ada.

    Windows tidak menyertakan database zona IANA. Tanpa paket `tzdata`,
    `ZoneInfo("Asia/Jakarta")` melempar `ZoneInfoNotFoundError` **saat impor**,
    sehingga seluruh program berhenti sebelum sempat berjalan (gejalanya:
    `ModuleNotFoundError: No module named 'tzdata'` lalu
    `ZoneInfoNotFoundError: 'No time zone found with key Asia/Jakarta'`
    pada perintah apa pun yang memakai filter lowongan).

    WIB tidak memakai DST, jadi offset tetap +07:00 menghasilkan waktu yang
    sama persis dengan `Asia/Jakarta`.
    """
    try:
        return ZoneInfo("Asia/Jakarta")
    except Exception:  # ZoneInfoNotFoundError / tzdata tidak terpasang
        return timezone(timedelta(hours=7), "WIB")


WIB = zona_wib()

# Singkatan dan nama bulan (Indonesia + Inggris).
BULAN = {
    "jan": 1, "januari": 1, "january": 1,
    "feb": 2, "februari": 2, "february": 2, "peb": 2,
    "mar": 3, "maret": 3, "march": 3,
    "apr": 4, "april": 4,
    "mei": 5, "may": 5,
    "jun": 6, "juni": 6, "june": 6,
    "jul": 7, "juli": 7, "july": 7,
    "agu": 8, "ags": 8, "agustus": 8, "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "okt": 10, "oktober": 10, "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "des": 12, "desember": 12, "dec": 12, "december": 12,
}

_NAMA_BULAN = "|".join(sorted(BULAN, key=len, reverse=True))

# Urutan penting: pola paling spesifik lebih dulu.
_POLA_RELATIF = (
    (
        (
            r"baru saja|hari ini|just posted|just now|today|baru dipasang"
            r"|baru saja dipasang"
        ),
        0,
    ),
    (r"kemarin|yesterday", 1),
    # Bentuk SINGKAT versi Inggris: JobStreet mengirim "9m ago", "3h ago",
    # "2d ago" (bukti cek-tanggal 17 Nov 2026), bukan "9 minutes ago".
    # Ditempatkan sebelum pola panjang, dan "mo" (month) sebelum "m" (minute)
    # supaya "1mo ago" tidak terbaca 1 menit.
    (r"(\d+)\s*\+?\s*mo(?:nth)?s?\s+ago", 30),
    (r"(\d+)\s*\+?\s*y(?:ear)?s?\s+ago", 365),
    (r"(\d+)\s*\+?\s*w(?:eek)?s?\s+ago", 7),
    (r"(\d+)\s*\+?\s*d(?:ay)?s?\s+ago", 1),
    (r"(\d+)\s*\+?\s*h(?:r|our)?s?\s+ago", 0),
    (r"(\d+)\s*\+?\s*m(?:in)?s?\s+ago", 0),
    (r"(\d+)\s*menit|(\d+)\s*minute", 0),
    (r"(\d+)\s*jam\b|(\d+)\s*hour", 0),
    (r"(\d+)\s*\+?\s*hari|(\d+)\s*\+?\s*day", 1),
    (r"(\d+)\s*minggu|(\d+)\s*week", 7),
    (r"(\d+)\s*bulan|(\d+)\s*month", 30),
    (r"(\d+)\s*tahun|(\d+)\s*year", 365),
)

_POLA_ISO = re.compile(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b")
_POLA_HARI_BULAN_TAHUN = re.compile(
    rf"\b(\d{{1,2}})\s+({_NAMA_BULAN})\.?\s+(\d{{4}})\b"
)
_POLA_BULAN_HARI_TAHUN = re.compile(
    rf"\b({_NAMA_BULAN})\.?\s+(\d{{1,2}}),?\s+(\d{{4}})\b"
)
# Format angka: Indonesia menulis hari/bulan/tahun.
_POLA_ANGKA = re.compile(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b")


def sekarang_wib(sekarang: datetime | None = None) -> datetime:
    """Waktu acuan dalam WIB (bisa diberikan pada pengujian)."""
    if sekarang is None:
        return datetime.now(UTC).astimezone(WIB)
    if sekarang.tzinfo is None:
        return sekarang.replace(tzinfo=UTC).astimezone(WIB)
    return sekarang.astimezone(WIB)


def tanggal_dari_teks(teks, sekarang: datetime | None = None) -> date | None:
    """Tanggal publikasi absolut dari teks; None bila tidak ada tanggal."""
    isi = " ".join(str(teks or "").lower().split())

    if not isi:
        return None

    for pola, urutan in (
        (_POLA_ISO, ("tahun", "bulan", "hari")),
        (_POLA_HARI_BULAN_TAHUN, ("hari", "bulan", "tahun")),
        (_POLA_BULAN_HARI_TAHUN, ("bulan", "hari", "tahun")),
        (_POLA_ANGKA, ("hari", "bulan", "tahun")),
    ):
        cocok = pola.search(isi)
        if not cocok:
            continue

        bagian = dict(zip(urutan, cocok.groups(), strict=False))
        tahun = int(bagian["tahun"])
        hari = int(bagian["hari"])

        # Bulan bisa berupa angka ("11") atau nama ("nov"/"november").
        mentah = bagian["bulan"]
        try:
            bulan = int(mentah)
        except (TypeError, ValueError):
            bulan = BULAN.get(str(mentah).strip("."))

        if not bulan:
            continue

        # Format angka dibaca hari/bulan/tahun (kebiasaan Indonesia). Bila
        # hasilnya mustahil tetapi tertukar ("11/15/2026"), tukar posisinya.
        if bulan > 12 and hari <= 12:
            bulan, hari = hari, bulan

        if not 1 <= bulan <= 12:
            continue

        try:
            return date(tahun, bulan, hari)
        except ValueError:
            return None

    return None


def umur_dari_teks(teks, sekarang: datetime | None = None) -> int | None:
    """Umur lowongan dalam hari; None bila tanggalnya tidak terbaca.

    Menerima label relatif ("3 hari lalu", "kemarin", "5 jam lalu",
    "2 minggu lalu", "1 tahun lalu") dan tanggal absolut. Umur tidak pernah
    negatif: tanggal di masa depan dianggap 0 hari.
    """
    isi = " ".join(str(teks or "").lower().split())

    if not isi:
        return None

    for pola, faktor in _POLA_RELATIF:
        cocok = re.search(pola, isi)
        if not cocok:
            continue

        if faktor in (0, 1) and not cocok.groups():
            return faktor

        angka = next((g for g in cocok.groups() if g), None)

        if angka is None:
            return faktor

        return int(angka) * faktor

    tanggal = tanggal_dari_teks(isi, sekarang)
    if tanggal is None:
        return None

    hari_ini = sekarang_wib(sekarang).date()
    return max(0, (hari_ini - tanggal).days)


def tanggal_iso_dari_umur(umur_hari, sekarang: datetime | None = None) -> str:
    """Tanggal absolut (ISO) dari umur relatif; "" bila umur tak diketahui."""
    if not isinstance(umur_hari, int):
        return ""

    hari = sekarang_wib(sekarang).date() - timedelta(days=max(0, umur_hari))
    return hari.isoformat()


def tanggal_simpan(teks, sekarang: datetime | None = None) -> str:
    """Tanggal yang layak DISIMPAN (ISO) dari label tanggal sebuah kartu.

    Tanggal absolut dipertahankan; label relatif ("9m ago", "3 hari lalu",
    "Hari ini") dikonversi ke tanggal absolut. Tanpa ini, label relatif yang
    tersimpan akan selamanya terbaca 0 hari — lowongan lama tampak baru.
    Teks yang tidak terbaca dikembalikan apa adanya ("" = DATE_UNKNOWN).
    """
    isi = " ".join(str(teks or "").split())

    if not isi:
        return ""

    tanggal = tanggal_dari_teks(isi, sekarang)
    if tanggal is not None:
        return tanggal.isoformat()

    umur_hari = umur_dari_teks(isi, sekarang)
    if isinstance(umur_hari, int):
        return tanggal_iso_dari_umur(umur_hari, sekarang)

    return isi


def label_umur(umur: int | None) -> str:
    """Teks tanggal publikasi untuk laporan & penyortiran."""
    if umur is None:
        return ""
    if umur <= 0:
        return "Hari ini"
    return f"{umur} hari lalu"


def batas_umur(
    umur: int | None, maks_hari: int, tolak_tak_diketahui: bool = False
) -> str:
    """Alasan penolakan umur ('' bila lolos); batas bersifat inklusif.

    `tolak_tak_diketahui` menentukan perlakuan tanggal yang tidak terbaca:
    bawaan `False` (lowongan tetap boleh dicoba) karena sebagian kartu
    memang tidak memuat tanggal — tetapi bila diaktifkan, "tidak terbaca"
    TIDAK dianggap baru.
    """
    if maks_hari <= 0:
        return ""

    if umur is None:
        if tolak_tak_diketahui:
            return "Umur lowongan tidak terbaca (DATE_UNKNOWN)"
        return ""

    if umur > maks_hari:
        return f"Lowongan terlalu lama ({umur} hari > MAX_AGE_DAYS={maks_hari})"

    return ""
