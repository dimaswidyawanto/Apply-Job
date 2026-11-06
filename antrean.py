"""Pemakaian status antrean di alur lamar (master prompt pasal 4.2-4.3).

Satu tempat untuk memetakan hasil penyaringan/lamaran menjadi status antrean,
supaya JobStreet, Glints, dan Indeed mencatat hal yang sama ke database.
"""

from typing import Optional

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
           skor: Optional[float] = None) -> bool:
    """Simpan status antrean tanpa pernah menggagalkan sesi lamar."""
    if str(status or "").lower() not in STATUS_ANTREAN:
        return False

    try:
        return db.set_status_antrean(job_id, status, alasan, skor)
    except Exception:
        return False


def tandai_hasil(job_id: str, alasan: str = "", skor: Optional[float] = None) -> str:
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
