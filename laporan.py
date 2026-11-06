"""Laporan & evaluasi kinerja (master prompt pasal 12.4).

Menghitung dari database yang sudah ada — bukan data simulasi:

- jumlah lowongan ditemukan / lamaran terkirim / sisa kuota,
- sebaran status antrean,
- hasil per lokasi dan per kategori,
- alasan penolakan tersering,
- tingkat keberhasilan pengiriman.

Dipakai perintah `laporan` dan dashboard.
"""

from datetime import date
from pathlib import Path
from typing import Dict, List, Optional

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
        "per_sumber": db.statistik_sumber(10),
        "sesi_terakhir": db.sesi_terakhir(3),
        "statistik_sesi": db.statistik_sesi(),
        "per_kata_kunci": db.statistik_kata_kunci(12),
        "alasan_tersering": db.alasan_tersering(8),
        "tingkat_berhasil": (
            round(100 * terkirim / percobaan, 1) if percobaan else 0.0
        ),
    }


FOLDER_LAPORAN = Path(__file__).resolve().parent / "reports"


def teks_markdown(data: Optional[Dict] = None) -> str:
    """Laporan dalam bentuk teks Markdown (untuk berkas harian)."""
    data = data or ringkasan()
    hari = date.today().isoformat()
    rasio_duplikat = (data.get("statistik_sesi") or {}).get("rasio_duplikat", 0)

    baris = [
        f"# Laporan Lamar Otomatis — {hari}",
        "",
        "## Angka utama",
        "",
        f"- Lowongan tersimpan: {data['lowongan_tersimpan']}",
        f"- Lamaran terkirim: {data['lamaran_terkirim']}",
        f"- Lamaran hari ini (WIB): {data['lamaran_hari_ini']}",
        "- Sisa kuota: "
        + ("tanpa batas" if data["sisa_kuota"] is None else str(data["sisa_kuota"])),
        f"- Tingkat berhasil: {data['tingkat_berhasil']}%",
        f"- Rasio duplikat (semua sesi): {rasio_duplikat}%",
        "",
        "## Status antrean",
        "",
        "| Status | Jumlah |",
        "|---|---|",
    ]
    baris += [
        f"| {nama} | {jumlah} |"
        for nama, jumlah in data["status_antrean"].items()
        if jumlah
    ] or ["| (kosong) | 0 |"]

    if data["per_lokasi"]:
        baris += [
            "",
            "## Per lokasi",
            "",
            "| Lokasi | Lowongan | Dilamar |",
            "|---|---|---|",
        ]
        baris += [
            f"| {i['lokasi']} | {i['jumlah']} | {i['dilamar']} |"
            for i in data["per_lokasi"]
        ]

    if data.get("per_kata_kunci"):
        baris += [
            "",
            "## Per kata kunci",
            "",
            "| Kata kunci | Lowongan | Dilamar |",
            "|---|---|---|",
        ]
        baris += [
            f"| {i['kata_kunci']} | {i['jumlah']} | {i['dilamar']} |"
            for i in data["per_kata_kunci"]
        ]

    if data.get("per_sumber"):
        baris += [
            "",
            "## Per sumber",
            "",
            "| Sumber | Lowongan | Dilamar |",
            "|---|---|---|",
        ]
        baris += [
            f"| {i['sumber']} | {i['jumlah']} | {i['dilamar']} |"
            for i in data["per_sumber"]
        ]

    if data["alasan_tersering"]:
        baris += [
            "",
            "## Alasan paling sering",
            "",
            "| Alasan | Jumlah |",
            "|---|---|",
        ]
        baris += [
            f"| {i['alasan']} | {i['jumlah']} |" for i in data["alasan_tersering"]
        ]

    sesi = data.get("sesi_terakhir") or []
    if sesi:
        baris += [
            "",
            "## Sesi terakhir",
            "",
            "| Selesai | Situs | Lowongan | Dilamar | Gagal | Duplikat |",
            "|---|---|---|---|---|---|",
        ]
        baris += [
            f"| {s['selesai']} | {s['situs']} | {s['ditemukan']} | "
            f"{s['dilamar']} | {s['gagal']} | {s['duplikat']} |"
            for s in sesi
        ]

    saran_saran = saran(data)
    if saran_saran:
        baris += ["", "## Saran", ""]
        baris += [f"- {satu}" for satu in saran_saran]

    return "\n".join(baris) + "\n"


def simpan(folder: Optional[str | Path] = None,
           data: Optional[Dict] = None) -> Path:
    """Simpan laporan harian ke `reports/laporan-YYYY-MM-DD.md`.

    Berkas hari yang sama ditimpa, jadi menjalankan beberapa kali dalam sehari
    tidak menumpuk berkas.
    """
    tujuan = Path(folder) if folder else FOLDER_LAPORAN
    tujuan.mkdir(parents=True, exist_ok=True)

    berkas = tujuan / f"laporan-{date.today().isoformat()}.md"
    berkas.write_text(teks_markdown(data), encoding="utf-8")
    return berkas


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

    # Kata kunci yang tidak menghasilkan lamaran sama sekali.
    kk = data.get("per_kata_kunci") or []
    sia_sia = [
        item["kata_kunci"] for item in kk
        if item.get("jumlah", 0) >= 5 and not item.get("dilamar")
    ]
    if sia_sia:
        hasil.append(
            "Kata kunci tanpa hasil lamaran: "
            + ", ".join(sia_sia[:3])
            + ". Pertimbangkan menggantinya (cek `config` lalu `.env`)."
        )

    # Kata kunci paling produktif — dipertahankan, bukan diubah otomatis.
    produktif = [item for item in kk if item.get("dilamar")]
    if produktif:
        teratas = produktif[0]
        hasil.append(
            f"Kata kunci paling produktif: \"{teratas['kata_kunci']}\" "
            f"({teratas['dilamar']} lamaran). Pertahankan di daftar."
        )

    sumber = data.get("per_sumber") or []
    if len(sumber) > 1:
        tanpa_lamaran = [
            item["sumber"] for item in sumber
            if item.get("jumlah", 0) >= 5 and not item.get("dilamar")
        ]
        if tanpa_lamaran:
            hasil.append(
                "Sumber tanpa lamaran terkirim: "
                + ", ".join(tanpa_lamaran)
                + ". Periksa apakah situs itu masih memuat logo/gaji."
            )

    rasio = (data.get("statistik_sesi") or {}).get("rasio_duplikat", 0)
    if rasio >= 30:
        hasil.append(
            f"Rasio duplikat {rasio}% — banyak lowongan sama ditemukan dari "
            "kombinasi berbeda. Pertimbangkan mengurangi kata kunci yang "
            "tumpang tindih."
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
