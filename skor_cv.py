"""AI Matching Score berbobot (master prompt pasal 7).

Enam parameter dengan bobot persen:

| Parameter | Bobot |
|---|---|
| Kesesuaian pengalaman kerja | 30% |
| Kesesuaian keterampilan | 25% |
| Kesesuaian tanggung jawab pekerjaan | 20% |
| Kesesuaian pendidikan | 10% |
| Kesesuaian jabatan | 10% |
| Kesesuaian lokasi | 5% |

Skor total 0–100 dengan kategori 90/80/70. Skor hanya menentukan **prioritas**;
persyaratan wajib (logo, gaji, judul, blacklist, dan seterusnya) tetap menjadi
filter mutlak di `job_filter` sebelum skor ini dihitung.

Bila CV belum tersedia (`CV_PATH` kosong / tidak terbaca), modul ini tidak
memakai nilai karangan: `aktif()` mengembalikan False dan pemeringkatan jatuh
ke skor lama, sehingga perilaku sistem tidak berubah diam-diam.
"""

import re

from config import config

BOBOT = {
    "pengalaman": 30,
    "keterampilan": 25,
    "tanggung_jawab": 20,
    "pendidikan": 10,
    "jabatan": 10,
    "lokasi": 5,
}

# Istilah sebidang dengan inventori/PPIC (pencocokan makna, bukan hanya kata).
SINONIM = {
    "inventory": ("inventory", "inventaris", "stock", "stok", "persediaan",
                  "material", "gudang", "warehouse"),
    "ppic": ("ppic", "production planning", "perencanaan produksi",
             "production control", "pengendalian produksi", "scheduling"),
    "supply": ("supply chain", "logistik", "logistics", "distribusi",
               "distribution", "pengiriman", "shipping"),
    "procurement": ("procurement", "purchasing", "pembelian", "sourcing",
                    "pengadaan", "vendor"),
}

KATEGORI = ((90, "Sangat sesuai"), (80, "Sesuai"), (70, "Cukup sesuai"))

_potret: dict[str, dict] = {}


# ------------------------------------------------------------- profil CV ----
def muat_profil(path: str = "") -> dict | None:
    """Baca profil CV sekali, lalu simpan di memori (hindari baca berulang)."""
    import cv as modul_cv

    kunci = str(path or config.cv_path or "").strip()
    if not kunci:
        return None

    if kunci in _potret:
        return _potret[kunci]

    try:
        profil = modul_cv.profil_cv(kunci)
    except Exception:
        return None

    _potret[kunci] = profil
    return profil


def aktif() -> bool:
    """True bila profil CV tersedia sehingga skor berbobot bisa dipakai."""
    return muat_profil() is not None


def lupakan() -> None:
    """Hapus potret CV (dipakai tes & setelah `cv` dijalankan ulang)."""
    _potret.clear()


# ------------------------------------------------------------------ skor ----
def _rasio(kata: list[str], teks: str) -> float:
    if not kata:
        return 0.0
    isi = teks.lower()
    cocok = sum(1 for k in kata if k and k in isi)
    return cocok / len(kata)


def _pengalaman(profil: dict, job: dict) -> float:
    """0..1 — CV memenuhi pengalaman yang diminta lowongan."""
    punya = profil.get("pengalaman_tahun")
    diminta = _pengalaman_diminta(job)

    if punya is None:
        return 0.3
    if diminta is None:
        return 1.0
    if punya >= diminta:
        return 1.0
    if diminta <= 0:
        return 1.0
    return max(0.0, punya / diminta)


def _pengalaman_diminta(job: dict) -> int | None:
    teks = f"{job.get('title') or ''} {job.get('description') or ''}".lower()
    pola = (
        r"minimal\s*(\d{1,2})\s*(?:tahun|year)",
        r"(\d{1,2})\s*(?:tahun|years?)\s*(?:pengalaman|experience)",
        r"pengalaman\s*(?:minimal|min\.?)?\s*(\d{1,2})\s*(?:tahun|year)",
    )
    angka = []
    for pola_ in pola:
        angka.extend(int(m.group(1)) for m in re.finditer(pola_, teks))
    angka = [n for n in angka if 0 <= n <= 30]
    return min(angka) if angka else None


def _keterampilan(profil: dict, job: dict) -> float:
    teks = f"{job.get('title') or ''} {job.get('description') or ''}"
    kata = profil.get("keterampilan") or []
    if not kata:
        # Tanpa daftar keterampilan di CV, pakai bidang sebagai pengganti.
        return _tanggung_jawab(profil, job)
    return min(1.0, _rasio(kata, teks) * 2)  # 50% kata cocok sudah penuh


def _tanggung_jawab(profil: dict, job: dict) -> float:
    teks = f"{job.get('title') or ''} {job.get('description') or ''}".lower()
    bidang_cv = profil.get("bidang") or []

    if not bidang_cv:
        return 0.4

    cocok = 0
    for nama in bidang_cv:
        if any(k in teks for k in SINONIM.get(nama, ())):
            cocok += 1

    if cocok:
        return min(1.0, cocok / len(bidang_cv))

    # Tidak satu pun bidang CV disebut: cek istilah sebidang secara umum.
    semua = [k for kata in SINONIM.values() for k in kata]
    return 0.5 if any(k in teks for k in semua) else 0.0


def _pendidikan(profil: dict, job: dict) -> float:
    import cv as modul_cv

    milik = modul_cv.peringkat_pendidikan(profil.get("pendidikan"))
    diminta = _pendidikan_diminta(job)

    if not milik:
        return 0.4
    if diminta is None:
        return 1.0
    return 1.0 if milik >= diminta else 0.4


def _pendidikan_diminta(job: dict) -> int | None:
    import cv as modul_cv

    teks = f"{job.get('title') or ''} {job.get('description') or ''}".lower()
    for jenjang, kata in modul_cv.POLA_PENDIDIKAN:
        if any(re.search(rf"\b{k}\b", teks) for k in kata):
            return modul_cv.PERINGKAT_PENDIDIKAN.get(jenjang)
    return None


def _jabatan(profil: dict, job: dict) -> float:
    judul = str(job.get("title") or "").lower()
    bidang_cv = profil.get("bidang") or []

    for nama in bidang_cv:
        if any(k in judul for k in SINONIM.get(nama, ())):
            return 1.0

    kata_kunci = [str(k).lower() for k in (config.title_keywords or [])]
    if any(k and k in judul for k in kata_kunci):
        return 0.7

    return 0.0


def _lokasi(profil: dict, job: dict) -> float:
    lokasi = str(job.get("location") or "").strip().lower()

    if not lokasi:
        return 0.5
    daftar = [l.lower() for l in (config.locations or []) if l]
    if not daftar:
        return 1.0
    return 1.0 if any(l in lokasi for l in daftar) else 0.2


_PENILAI = {
    "pengalaman": _pengalaman,
    "keterampilan": _keterampilan,
    "tanggung_jawab": _tanggung_jawab,
    "pendidikan": _pendidikan,
    "jabatan": _jabatan,
    "lokasi": _lokasi,
}


def kategori(skor: float) -> str:
    for ambang, nama in KATEGORI:
        if skor >= ambang:
            return nama
    return "Tidak diprioritaskan"


def hitung(job: dict, profil: dict | None = None) -> dict | None:
    """Skor 0-100 per parameter. None bila CV belum tersedia."""
    profil = profil or muat_profil()
    if not profil:
        return None

    rincian = {}
    for nama, bobot in BOBOT.items():
        rasio = max(0.0, min(1.0, _PENILAI[nama](profil, job)))
        rincian[nama] = round(rasio * bobot, 1)

    skor = round(sum(rincian.values()), 1)
    cocok = sorted(
        (nama for nama, nilai in rincian.items()
         if nilai >= BOBOT[nama] * 0.7),
        key=lambda n: -rincian[n],
    )
    kurang = [nama for nama, nilai in rincian.items() if nilai <= 0.1]

    return {
        "skor": skor,
        "kategori": kategori(skor),
        "rincian": rincian,
        "cocok": cocok,
        "kurang": kurang,
    }


def terapkan(job: dict, profil: dict | None = None) -> dict | None:
    """Hitung dan tempelkan hasil skor ke dict lowongan."""
    hasil = hitung(job, profil)
    if not hasil:
        return None

    job["_skor_cv"] = hasil["skor"]
    job["_kategori_skor"] = hasil["kategori"]
    job["_skor_cv_rincian"] = hasil["rincian"]
    job["_alasan_cocok"] = ", ".join(hasil["cocok"]) or "-"
    job["_alasan_kurang"] = ", ".join(hasil["kurang"]) or "-"
    return hasil


def saring_minimal(kandidat: list[dict], minimal: int | None = None,
                   skor_sudah: bool = False) -> tuple:
    """Pisahkan kandidat yang skornya memenuhi `MIN_SKOR_CV`.

    Kembalikan (lolos, dibuang). Bila CV belum ada atau batas 0, semua lolos —
    syarat wajib tetap sudah disaring `job_filter` sebelumnya.
    """
    batas = config.min_skor_cv if minimal is None else minimal
    daftar = list(kandidat or [])

    if not batas or batas <= 0 or not aktif():
        return daftar, []

    if not skor_sudah:
        for job in daftar:
            terapkan(job)

    lolos, dibuang = [], []
    for job in daftar:
        nilai = job.get("_skor_cv")
        if nilai is None or nilai >= batas:
            lolos.append(job)
        else:
            dibuang.append(job)

    return lolos, dibuang


def tabel_rincian(kandidat: list[dict], maksimal: int = 5) -> list[list[str]]:
    """Baris siap tampil untuk tabel CLI."""
    baris = []
    for job in kandidat[:maksimal]:
        rincian = job.get("_skor_cv_rincian") or {}
        baris.append(
            [
                str(job.get("title") or "-")[:34],
                str(job.get("_skor_cv", "-")),
                str(job.get("_kategori_skor") or "-"),
                *[str(rincian.get(n, "-")) for n in BOBOT],
            ]
        )
    return baris
