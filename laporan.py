"""Laporan & evaluasi kinerja (master prompt pasal 12.4).

Menghitung dari database yang sudah ada — bukan data simulasi:

- jumlah lowongan ditemukan / lamaran terkirim / sisa kuota,
- sebaran status antrean,
- hasil per lokasi dan per kategori,
- alasan penolakan tersering,
- tingkat keberhasilan pengiriman.

Dipakai perintah `laporan` dan dashboard.
"""

from typing import Dict, List

import kuota
from config import config
from database import db
from notifier import notifier


def ringkasan() -> Dict:
    """Angka utama untuk laporan satu halaman."""
    stats = db.get_stats()
    status = db.hitung_status_antrean()

    terkirim = int(stats.get("total_applied", 0))
    gagal = int(status.get("failed", 0)) + int(status.get("expired", 0))
    percobaan = terkirim + gagal

    return {
        "lowongan_tersimpan": int(stats.get("total_jobs_found", 0)),
        "lamaran_terkirim": terkirim,
        "lamaran_hari_ini": int(stats.get("today_applied", 0)),
        "sisa_kuota": kuota.sisa(db),
        "status_antrean": status,
        "per_lokasi": db.statistik_lokasi(10),
        "per_kategori": db.statistik_kategori(10),
        "alasan_tersering": db.alasan_tersering(8),
        "tingkat_berhasil": (
            round(100 * terkirim / percobaan, 1) if percobaan else 0.0
        ),
    }


def saran(data: Dict) -> List[str]:
    """Saran singkat dari angka — bagian "continuous improvement" yang aman.

    Hanya berupa anjuran; tidak mengubah aturan apa pun secara otomatis
    (pasal 12.5).
    """
    hasil: List[str] = []
    status = data.get("status_antrean") or {}

    revisi = int(status.get("review_required", 0))
    if revisi:
        hasil.append(
            f"{revisi} lowongan menunggu pemeriksaan Anda (REVIEW_REQUIRED). "
            "Buka `history` atau dashboard untuk meninjaunya."
        )

    tanpa_hasil = [
        item["lokasi"] for item in data.get("per_lokasi", [])
        if item.get("jumlah", 0) < 3
    ]
    if tanpa_hasil:
        hasil.append(
            "Lokasi dengan hasil sedikit: "
            + ", ".join(tanpa_hasil[:3])
            + ". Pertimbangkan menambah kata kunci."
        )

    if data.get("tingkat_berhasil", 0) and data["tingkat_berhasil"] < 80:
        hasil.append(
            "Tingkat keberhasilan pengiriman di bawah 80%. Periksa alasan "
            "kegagalan tersering di bawah."
        )

    alasan = data.get("alasan_tersering") or []
    if alasan and alasan[0]["jumlah"] >= 5:
        hasil.append(
            f"Alasan penolakan terbanyak: \"{alasan[0]['alasan']}\" "
            f"({alasan[0]['jumlah']} lowongan)."
        )

    if not config.cv_path:
        hasil.append(
            "CV_PATH belum diisi, jadi skor 6 parameter belum aktif. "
            "Isi dengan `jalankan.bat cv --pasang \"C:\\path\\cv.docx\"`."
        )

    return hasil


def kirim_telegram(data: Dict) -> bool:
    """Kirim ringkasan ke Telegram (opsional)."""
    try:
        notifier.send_daily_report(db.get_stats())
        return True
    except Exception:
        return False
