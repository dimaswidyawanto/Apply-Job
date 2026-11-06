"""Pembacaan CV dan profil terstruktur (master prompt pasal 2.2 & 6.3).

Mendukung:
- `.txt` / `.md` polos,
- `.docx` tanpa pustaka tambahan (docx = arsip zip berisi XML),
- `.pdf` bila `pypdf` terpasang (opsional, tidak wajib).

Profil yang dihasilkan dipakai mesin skor kecocokan; tidak ada data yang
dikarang: semua nilai diambil dari teks CV atau dari `.env`.
"""

import re
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from config import config

# Istilah yang dianggap satu bidang dengan inventori/PPIC.
KELOMPOK_ISTILAH = {
    "inventory": (
        "inventory", "inventaris", "stock", "stok", "persediaan",
        "material control", "gudang", "warehouse",
    ),
    "ppic": (
        "ppic", "production planning", "perencanaan produksi",
        "production control", "pengendalian produksi",
    ),
    "supply": (
        "supply chain", "rantai pasok", "logistik", "logistics",
        "distribusi", "distribution",
    ),
    "procurement": (
        "procurement", "purchasing", "pembelian", "sourcing", "pengadaan",
    ),
}

POLA_PENGALAMAN = re.compile(
    r"(\d{1,2})\s*(?:\+)?\s*(?:tahun|years?|thn|yr)"
    r"\s*(?:pengalaman|of experience|experience)?",
    re.IGNORECASE,
)
# Rentang tahun kerja, mis. "2020-2024", "Jan 2020 – sekarang", "2016 s/d 2020".
POLA_RENTANG_TAHUN = re.compile(
    r"\b((?:19|20)\d{2})\s*(?:-|–|—|s/d|s\.d\.|sampai|hingga|to)\s*"
    r"((?:19|20)\d{2}|sekarang|kini|present|now|current)\b",
    re.IGNORECASE,
)

# Baris yang menandakan bagian pendidikan — tahun di sini bukan pengalaman kerja.
TANDA_PENDIDIKAN_BARIS = (
    "universitas", "university", "institut", "institute", "sekolah", "school",
    "sma", "smk", "smp", "kuliah", "fakultas", "jurusan", "lulus", "graduate",
    "bachelor", "master", "diploma", "s1", "s2", "s3", "gpa", "ipk",
)

POLA_PENDIDIKAN = (
    ("s3", ("s3", "doktor", "doctoral", "phd")),
    ("s2", ("s2", "magister", "master", "mba", "msc")),
    ("s1", ("s1", "sarjana", "bachelor", "undergraduate", "degree")),
    ("d3", ("d3", "diploma", "diplomat", "associate degree")),
    ("sma", ("sma", "smk", "high school", "senior high")),
)
PERINGKAT_PENDIDIKAN = {"sma": 1, "d3": 2, "s1": 3, "s2": 4, "s3": 5}


class CvTidakTerbaca(Exception):
    """Berkas CV tidak ada atau formatnya tidak didukung."""


# ------------------------------------------------------------------ baca ----
def _teks_docx(path: Path) -> str:
    """Ambil teks dari .docx (zip + XML) tanpa pustaka tambahan."""
    with zipfile.ZipFile(path) as arsip:
        try:
            xml = arsip.read("word/document.xml").decode("utf-8", "ignore")
        except KeyError as exc:
            raise CvTidakTerbaca("Berkas .docx tidak memuat document.xml") from exc

    # Ganti paragraf jadi baris baru, lalu buang semua tag.
    xml = xml.replace("</w:p>", "\n")
    teks = re.sub(r"<[^>]+>", " ", xml)
    teks = teks.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    return re.sub(r"[ \t]+", " ", teks).strip()


def _teks_pdf(path: Path) -> str:
    """Ambil teks PDF memakai pypdf bila tersedia."""
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise CvTidakTerbaca(
            "Membaca PDF perlu pustaka pypdf. Pasang dengan: "
            ".venv\\Scripts\\python.exe -m pip install pypdf "
            "— atau simpan CV sebagai .docx/.txt."
        ) from exc

    try:
        pembaca = PdfReader(str(path))
        return "\n".join((halaman.extract_text() or "") for halaman in pembaca.pages)
    except Exception as exc:  # PDF rusak / terkunci
        raise CvTidakTerbaca(f"PDF tidak bisa dibaca: {exc}") from exc


def baca_berkas(path: str | Path) -> str:
    """Teks mentah CV; melempar CvTidakTerbaca bila gagal."""
    berkas = Path(str(path or "")).expanduser()

    if not str(path or "").strip():
        raise CvTidakTerbaca("CV_PATH belum diisi di .env")
    if not berkas.exists():
        raise CvTidakTerbaca(f"Berkas CV tidak ditemukan: {berkas}")

    akhiran = berkas.suffix.lower()

    if akhiran in (".txt", ".md"):
        return berkas.read_text(encoding="utf-8", errors="ignore")
    if akhiran == ".docx":
        return _teks_docx(berkas)
    if akhiran == ".pdf":
        return _teks_pdf(berkas)

    raise CvTidakTerbaca(
        f"Format {akhiran or '(tanpa akhiran)'} belum didukung. "
        "Pakai .pdf, .docx, .txt, atau .md."
    )


# ---------------------------------------------------------------- profil ----
def pengalaman_tahun(teks: str) -> Optional[int]:
    """Tahun pengalaman kerja tertinggi yang disebut di CV.

    Dua bentuk dikenali: angka eksplisit ("8 tahun pengalaman") dan rentang
    tahun pada riwayat kerja ("2020-2024"), karena CV Indonesia umumnya
    memakai rentang tanggal, bukan jumlah tahun.
    """
    angka = [int(cocok.group(1)) for cocok in POLA_PENGALAMAN.finditer(teks)]
    angka = [n for n in angka if 0 < n <= 45]

    rentang = pengalaman_dari_rentang(teks)
    if rentang is not None:
        angka.append(rentang)

    return max(angka) if angka else None


def _tahun_sekarang() -> int:
    return datetime.now().year


def pengalaman_dari_rentang(teks: str) -> Optional[int]:
    """Total tahun kerja dari rentang tanggal (irisan dihitung sekali)."""
    sekarang = _tahun_sekarang()
    selang = []

    for baris in str(teks or "").splitlines():
        isi = baris.lower()

        if any(tanda in isi for tanda in TANDA_PENDIDIKAN_BARIS):
            continue

        for cocok in POLA_RENTANG_TAHUN.finditer(baris):
            mulai = int(cocok.group(1))
            akhir = cocok.group(2).lower()

            selesai = int(akhir) if akhir.isdigit() else sekarang

            if not (1970 <= mulai <= sekarang) or selesai < mulai:
                continue

            if selesai > sekarang:
                selesai = sekarang

            selang.append((mulai, selesai))

    if not selang:
        return None

    # Gabungkan rentang yang tumpang tindih agar pekerjaan bersamaan tidak
    # dihitung dua kali.
    selang.sort()
    gabungan = [list(selang[0])]
    for mulai, selesai in selang[1:]:
        if mulai <= gabungan[-1][1]:
            gabungan[-1][1] = max(gabungan[-1][1], selesai)
        else:
            gabungan.append([mulai, selesai])

    total = sum(selesai - mulai for mulai, selesai in gabungan)
    return min(45, total) if total > 0 else None


def pendidikan(teks: str) -> Optional[str]:
    """Jenjang pendidikan tertinggi yang disebut di CV."""
    isi = teks.lower()
    terbaik = None
    for jenjang, kata in POLA_PENDIDIKAN:
        if any(k in isi for k in kata):
            terbaik = jenjang
            break
    return terbaik


def peringkat_pendidikan(jenjang: Optional[str]) -> int:
    return PERINGKAT_PENDIDIKAN.get(str(jenjang or "").lower(), 0)


def bidang(teks: str) -> List[str]:
    """Kelompok bidang yang muncul di CV (inventory, ppic, supply, ...)."""
    isi = teks.lower()
    return [
        nama
        for nama, kata in KELOMPOK_ISTILAH.items()
        if any(k in isi for k in kata)
    ]


def keterampilan(teks: str) -> List[str]:
    """Kata kunci keterampilan yang dikenal dan muncul di CV."""
    isi = teks.lower()
    hasil = []
    for kata in list(config.skill_keywords) + list(config.title_keywords):
        kata = str(kata).strip().lower()
        if kata and kata not in hasil and kata in isi:
            hasil.append(kata)
    return hasil


def profil_dari_teks(teks: str) -> Dict:
    """Profil terstruktur dari teks CV."""
    isi = str(teks or "")
    return {
        "panjang_teks": len(isi),
        "pengalaman_tahun": pengalaman_tahun(isi),
        "pendidikan": pendidikan(isi),
        "bidang": bidang(isi),
        "keterampilan": keterampilan(isi),
        "sertifikasi": _sertifikasi(isi),
        "alat": _alat(isi),
    }


def _sertifikasi(teks: str) -> List[str]:
    """Sertifikat/pelatihan resmi — bukan nama aplikasi."""
    isi = teks.lower()
    daftar = (
        "iso 9001", "iso 14001", "iso 45001", "six sigma", "lean",
        "apics", "cpim", "forklift", "k3", "ahli k3", "bnsp",
    )
    hasil = [kata for kata in daftar if kata in isi]

    # "ahli k3" sudah mencakup "k3" — jangan tampil dua kali.
    if "ahli k3" in hasil and "k3" in hasil:
        hasil.remove("k3")

    return hasil


def _alat(teks: str) -> List[str]:
    """Aplikasi/perangkat yang dikuasai (SAP, Excel, WMS, ...)."""
    isi = teks.lower()
    daftar = ("sap", "erp", "excel", "wms", "accurate", "odoo", "oracle")
    return [kata for kata in daftar if kata in isi]


def profil_cv(path: str | Path = "") -> Dict:
    """Baca CV dari path (bawaan `CV_PATH`) dan kembalikan profilnya."""
    teks = baca_berkas(path or config.cv_path)
    profil = profil_dari_teks(teks)
    profil["sumber"] = str(path or config.cv_path)
    profil["ringkas"] = teks[:400]
    return profil


def format_profil(profil: Dict) -> str:
    """Ringkasan satu blok untuk ditampilkan di CLI."""
    pengalaman = profil.get("pengalaman_tahun")
    return (
        f"pengalaman: {pengalaman if pengalaman is not None else '-'} tahun · "
        f"pendidikan: {profil.get('pendidikan') or '-'} · "
        f"bidang: {', '.join(profil.get('bidang') or []) or '-'} · "
        f"keterampilan: {len(profil.get('keterampilan') or [])} istilah · "
        f"teks: {profil.get('panjang_teks', 0)} karakter"
    )
