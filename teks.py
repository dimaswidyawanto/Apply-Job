"""Normalisasi teks bersama (temuan audit E-12).

Sebelumnya ada dua fungsi normalisasi terpisah yang sama-sama harus
membuang karakter tak terlihat (word joiner, zero-width space, NBSP, BOM):
`jawaban.bersihkan_teks()` untuk label/pertanyaan formulir dan
`scraper._norm_teks()` untuk mencocokkan nama perusahaan pada logo. Keduanya
kini memakai satu tempat ini, dengan nama yang menjelaskan tujuannya:

* `bersihkan()` — buang karakter tak terlihat, rapikan spasi (teks tampil).
* `kunci_nama()` — huruf kecil tanpa tanda baca (kunci pembanding nama).
"""

import re

# Karakter tak terlihat yang sering disisipkan situs lowongan ke teks tombol,
# label opsi, dan judul pertanyaan: word joiner (U+2060), zero-width space
# (U+200B), zero-width joiner/non-joiner, BOM, dan penanda arah teks.
# Tanpa dibuang, "\u2060Submit application" tidak pernah sama dengan
# "submit application" sehingga tombol/opsi tidak dikenali.
TAK_TERLIHAT = dict.fromkeys(
    map(ord, "\u2060\u200b\u200c\u200d\ufeff\u200e\u200f"),
    None,
)

# Semua yang bukan huruf/angka ASCII, dipakai `kunci_nama()`.
_BUKAN_ALFANUMERIK = re.compile(r"[^a-z0-9]+")


def bersihkan(teks) -> str:
    """Buang karakter tak terlihat dan rapikan spasi.

    NBSP diganti spasi (bukan dihapus) supaya "years\u00a0experience" tidak
    menempel menjadi "yearsexperience".
    """
    teks = str(teks or "").replace("\u00a0", " ")
    return " ".join(teks.translate(TAK_TERLIHAT).split())


def kunci_nama(teks) -> str:
    """Kunci pembanding nama: huruf kecil, hanya huruf/angka ASCII.

    "PT. Sumber Makmur, Tbk" → "ptsumbermakmurtbk". Dipakai untuk menilai
    apakah teks alternatif gambar memuat nama perusahaan (`logo_perusahaan`).
    """
    return _BUKAN_ALFANUMERIK.sub("", bersihkan(teks).lower())
