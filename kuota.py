"""Kuota lamaran per situs dalam **siklus 24 jam bergulir**.

Aturan pemakai (2026-11-11): setiap situs wajib mengirim 50 lamaran, dan
hitungannya bukan "hari kalender" yang di-reset tengah malam. Siklus dimulai
pada **lamaran pertama**, berjalan 24 jam, lalu kembali 50 slot.

Contoh: lamaran pertama pukul 20:30 → slot ke-51 baru bisa dikirim besok
20:30, bukan besok 00:00.

* JobStreet, Glints, dan Indeed masing-masing punya siklus sendiri.
* `MAX_APPLY_PER_DAY=0` berarti tanpa batas untuk semua situs.
* Target harian tetap 50 (bukan hanya batas): akhir sesi melaporkan bila
  belum tercapai.
"""

from datetime import UTC, datetime

from config import config
from database import WIB
from database import db as db_baku

SITUS_BAKU = ("jobstreet", "glints", "indeed")
NAMA_SITUS = {
    "jobstreet": "JobStreet",
    "glints": "Glints",
    "indeed": "Indeed",
}


def batas(cfg=None) -> int:
    """Batas/target lamaran per siklus per situs (0 = tanpa batas)."""
    cfg = cfg or config
    return max(0, int(getattr(cfg, "max_apply_per_day", 0) or 0))


def target(cfg=None) -> int:
    """Nama lain `batas()`: angka yang wajib dicapai tiap situs per siklus."""
    return batas(cfg)


def _siklus(db_obj, situs: str) -> dict:
    """Data siklus dari database; cadangan untuk objek database lama/palsu."""
    fungsi = getattr(db_obj, "siklus_kuota", None)

    if callable(fungsi):
        try:
            return fungsi(situs)
        except TypeError:
            return fungsi()

    # Objek lama: hanya tahu jumlah lamaran hari ini, bukan siklus.
    try:
        jumlah = int(db_obj.get_today_apply_count(situs) or 0)
    except TypeError:
        jumlah = int(db_obj.get_today_apply_count() or 0)

    return {
        "jumlah": jumlah,
        "mulai_at": "",
        "berakhir_at": "",
        "sisa_detik": None,
        "aktif": jumlah > 0,
    }


def terpakai(db_obj=None, situs: str = "") -> int:
    """Lamaran yang sudah terkirim pada siklus berjalan situs ini."""
    return int(_siklus(db_obj or db_baku, situs).get("jumlah", 0) or 0)


def tanpa_batas(cfg=None) -> bool:
    return batas(cfg) <= 0


def sisa(db_obj=None, cfg=None, situs: str = "") -> int | None:
    """Sisa slot situs ini pada siklus berjalan; None bila tanpa batas."""
    batas_siklus = batas(cfg)

    if batas_siklus <= 0:
        return None

    return max(0, batas_siklus - terpakai(db_obj or db_baku, situs))


def kurang(db_obj=None, cfg=None, situs: str = "") -> int:
    """Berapa lamaran lagi yang dibutuhkan situs ini untuk mencapai target."""
    sisa_siklus = sisa(db_obj, cfg, situs)
    return 0 if sisa_siklus is None else sisa_siklus


def habis(db_obj=None, cfg=None, situs: str = "") -> bool:
    sisa_siklus = sisa(db_obj, cfg, situs)
    return sisa_siklus is not None and sisa_siklus <= 0


def sisa_detik(db_obj=None, situs: str = "") -> float | None:
    """Detik tersisa sampai siklus berganti (None bila belum ada siklus)."""
    return _siklus(db_obj or db_baku, situs).get("sisa_detik")


def teks_sisa_waktu(detik) -> str:
    """Ubah detik menjadi 'X jam Y menit' (atau 'kurang dari 1 menit')."""
    if detik is None:
        return ""
    detik = max(0, int(detik))
    jam, sisa_jam = divmod(detik, 3600)
    menit = sisa_jam // 60

    if jam and menit:
        return f"{jam} jam {menit} menit"
    if jam:
        return f"{jam} jam"
    if menit:
        return f"{menit} menit"
    return "kurang dari 1 menit"


def waktu_berakhir(db_obj=None, situs: str = "") -> str:
    """Waktu siklus berakhir dalam WIB, mis. 'besok 20:30'."""
    teks = _siklus(db_obj or db_baku, situs).get("berakhir_at") or ""
    if not teks:
        return ""

    try:
        saat = datetime.strptime(teks[:19], "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=UTC
        )
    except ValueError:
        return ""

    lokal = saat.astimezone(WIB)
    hari_ini = datetime.now(WIB).date()
    selisih = (lokal.date() - hari_ini).days

    if selisih == 0:
        return f"hari ini {lokal:%H:%M}"
    if selisih == 1:
        return f"besok {lokal:%H:%M}"
    return f"{lokal:%d-%m %H:%M}"


def ringkasan(db_obj=None, cfg=None, situs: str = "") -> str:
    """Kalimat kuota satu situs (atau gabungan bila situs kosong)."""
    nama = NAMA_SITUS.get(str(situs or "").lower(), "")
    awalan = f"Kuota {nama}: " if nama else "Kuota harian: "

    if tanpa_batas(cfg):
        return f"{awalan}tanpa batas (MAX_APPLY_PER_DAY=0)."

    db_obj = db_obj or db_baku
    data = _siklus(db_obj, situs)
    teks = (
        f"{awalan}{data.get('jumlah', 0)} sudah dilamar pada siklus ini, "
        f"sisa {sisa(db_obj, cfg, situs)} dari {batas(cfg)}."
    )

    berakhir = waktu_berakhir(db_obj, situs)
    if berakhir:
        teks += f" Siklus 24 jam berakhir {berakhir}."

    return teks


def ringkasan_situs(db_obj=None, cfg=None, daftar=SITUS_BAKU) -> list[dict]:
    """Angka kuota tiap situs, siap ditampilkan sebagai tabel."""
    db_obj = db_obj or db_baku
    hasil = []

    for nama in daftar:
        data = _siklus(db_obj, nama)
        sisa_siklus = sisa(db_obj, cfg, nama)
        hasil.append(
            {
                "situs": nama,
                "nama": NAMA_SITUS.get(nama, nama.title()),
                "terpakai": int(data.get("jumlah", 0) or 0),
                "batas": batas(cfg),
                "sisa": sisa_siklus,
                "berakhir_at": data.get("berakhir_at") or "",
                "berakhir": waktu_berakhir(db_obj, nama),
                "sisa_detik": data.get("sisa_detik"),
                "sisa_waktu": teks_sisa_waktu(data.get("sisa_detik")),
                "tercapai": (
                    sisa_siklus == 0 if sisa_siklus is not None else None
                ),
            }
        )

    return hasil


def potong(kandidat: list[dict], db_obj=None, cfg=None, situs: str = "") -> list[dict]:
    """Batasi kandidat sesuai sisa kuota situs ini (tanpa batas = utuh)."""
    sisa_siklus = sisa(db_obj, cfg, situs)

    if sisa_siklus is None:
        return list(kandidat)

    return list(kandidat)[:sisa_siklus]


def pesan_habis(situs: str = "") -> str:
    nama = NAMA_SITUS.get(str(situs or "").lower(), "")
    siapa = f" {nama}" if nama else ""
    berakhir = waktu_berakhir(situs=situs) if situs else ""
    tambahan = f" Siklus baru dibuka {berakhir}." if berakhir else ""

    return (
        f"Kuota{siapa} untuk siklus 24 jam ini sudah habis. Tidak ada lamaran "
        "dikirim. Kuota dihitung per situs, jadi situs lain tetap jalan."
        + tambahan
    )
