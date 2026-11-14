"""Pemakaian status antrean di alur lamar (master prompt pasal 4.2-4.3).

Satu tempat untuk memetakan hasil penyaringan/lamaran menjadi status antrean,
supaya JobStreet, Glints, dan Indeed mencatat hal yang sama ke database.
"""


from database import STATUS_ANTREAN, db

# Alasan yang berarti "belum bisa diputuskan" -> REVIEW_REQUIRED (pasal 6.1).
ALASAN_RAGU = ("dipastikan", "tidak jelas", "ragu")


def status_untuk(alasan: str) -> str:
    """Status antrean dari alasan penolakan (`""` = layak)."""
    teks = str(alasan or "").strip().lower()

    if not teks:
        return "qualified"

    if any(kata in teks for kata in ALASAN_RAGU):
        return "review_required"

    if "sudah" in teks and "dilamar" in teks:
        return "applied"

    if "kedaluwarsa" in teks or "tidak aktif" in teks or "expired" in teks:
        return "expired"

    return "rejected"


def tandai(job_id: str, status: str, alasan: str = "",
           skor: float | None = None) -> bool:
    """Simpan status antrean tanpa pernah menggagalkan sesi lamar."""
    if str(status or "").lower() not in STATUS_ANTREAN:
        return False

    try:
        return db.set_status_antrean(job_id, status, alasan, skor)
    except Exception:
        return False


def tandai_hasil(job_id: str, alasan: str = "", skor: float | None = None) -> str:
    """Tandai hasil penyaringan; kembalikan status yang dipakai."""
    status = status_untuk(alasan)
    tandai(job_id, status, alasan, skor)
    return status


KATA_KEDALUWARSA = (
    "no longer accepting",
    "not accepting applications",
    "tidak lagi menerima",
    "lowongan ditutup",
    "job has expired",
    "expired",
)


def kedaluwarsa(teks: str) -> bool:
    """Apakah pesan situs menandakan lowongan sudah tidak menerima lamaran."""
    isi = str(teks or "").lower()
    return any(kata in isi for kata in KATA_KEDALUWARSA)


def status_gagal(teks: str) -> str:
    """Status akhir untuk kegagalan pengiriman (expired vs failed)."""
    return "expired" if kedaluwarsa(teks) else "failed"


# Pesan galat yang biasanya hanya SEMENTARA (master prompt pasal 10.1).
KATA_SEMENTARA = (
    "timeout",
    "timed out",
    "err_internet_disconnected",
    "err_name_not_resolved",
    "err_connection",
    "chrome not reachable",
    "chrome failed to start",
    "connection reset",
    "connection aborted",
    "connection refused",
    "remote end closed",
    "stale element",
    "net::err",
    "temporarily",
    "something has gone wrong",
    "502",
    "503",
    "504",
    "webdriver",
)


def sementara(galat: str) -> bool:
    """True bila galat pantas dicoba ulang (bukan kesalahan permanen)."""
    teks = str(galat or "").lower()
    return any(kata in teks for kata in KATA_SEMENTARA)


def maks_ulang() -> int:
    """Berapa kali kegagalan sementara diulang (0 = tidak diulang)."""
    from config import config as _config

    return max(0, min(5, int(getattr(_config, "maks_ulang", 2) or 0)))


def jeda_ulang() -> int:
    """Jeda (detik) sebelum mencoba lagi."""
    from config import config as _config

    return max(0, int(getattr(_config, "jeda_ulang", 3) or 0))


def ulang_berbatas(fungsi, judul: str = "", pemeriksa=None):
    """Panggil `fungsi`, ulangi hanya bila galatnya sementara.

    Kembalikan (hasil, galat_akhir, jumlah_ulang). `galat_akhir` None berarti
    berhasil. `pemeriksa` dipanggil sebelum tiap percobaan (mis. kendali sesi).
    """
    import time

    import log_aktivitas

    batas = maks_ulang()
    ulang = 0

    while True:
        if pemeriksa:
            pemeriksa()

        try:
            return fungsi(), None, ulang
        except KeyboardInterrupt:
            raise
        except Exception as galat:  # noqa: BLE001 (semua galat dicatat)
            pesan = str(galat) or galat.__class__.__name__

            if ulang >= batas or not sementara(pesan):
                return None, galat, ulang

            ulang += 1
            log_aktivitas.catat(
                f"Ulang {ulang}/{batas}: {judul or 'lowongan'} — {pesan[:160]}",
                "warning",
            )
            if jeda_ulang():
                time.sleep(jeda_ulang())


def klaim(job_id: str) -> bool:
    """Ambil hak memproses satu lowongan (idempotensi, pasal 4.3 & 10.3).

    False bila lowongan sudah pernah terkirim — mencegah lamaran ganda.
    """
    job_id = str(job_id or "").strip()
    if not job_id:
        return False

    try:
        if db.is_already_applied(job_id):
            return False
        # Baris lowongan boleh belum ada di database; yang penting status
        # "applying" tercatat bila barisnya ada.
        db.set_status_antrean(job_id, "applying")
        return True
    except Exception:
        return True


def selesai(job_id: str, status: str, catatan: str = "") -> None:
    """Tutup satu pemrosesan: applied / failed / review_required / expired."""
    tandai(job_id, status, catatan)
