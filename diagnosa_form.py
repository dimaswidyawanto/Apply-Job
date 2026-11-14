"""Baca berkas debug HTML JobStreet dan tunjukkan pertanyaan yang belum terisi.

Saat bot menemui formulir yang tidak dikenali, halaman disimpan ke
`debug/YYYYMMDD-HHMMSS-<id>.html`. Berkas itu berisi HTML lengkap termasuk
pertanyaan kuesioner. Perintah `diagnosa-form` membaca berkas tersebut dan
menampilkan: pertanyaan apa, jenis isiannya (radio/pilihan/teks), opsi apa saja,
mana yang sudah terpilih, dan mana yang masih kosong.

Tujuannya supaya penyebab "please address the following issues" bisa dilihat
tanpa perlu membuka Chrome.
"""

import re
from pathlib import Path

_LABEL_FOR = re.compile(
    r"<label\b[^>]*\bfor=[\"']([^\"']+)[\"'][^>]*>(.*?)</label>",
    re.IGNORECASE | re.DOTALL,
)
_FIELDSET = re.compile(
    r"<fieldset\b[^>]*>(.*?)</fieldset>", re.IGNORECASE | re.DOTALL
)
_LEGEND = re.compile(
    r"<legend\b[^>]*>(.*?)</legend>", re.IGNORECASE | re.DOTALL
)
_INPUT = re.compile(
    r"<input\b[^>]*type=[\"'](radio|checkbox)[\"'][^>]*>", re.IGNORECASE
)
_SELECT = re.compile(
    r"<select\b[^>]*>(.*?)</select>", re.IGNORECASE | re.DOTALL
)
_OPTION = re.compile(r"<option\b([^>]*)>(.*?)</option>", re.IGNORECASE | re.DOTALL)
_TAG = re.compile(r"<[^>]+>")
_ATTR = re.compile(r"([\w:-]+)\s*=\s*[\"']([^\"']*)[\"']")


def _bersih(teks: str) -> str:
    """Buang tag HTML, rapikan spasi."""
    return " ".join(_TAG.sub(" ", str(teks or "")).split())


def _atribut(tag: str) -> dict[str, str]:
    return {kunci.lower(): nilai for kunci, nilai in _ATTR.findall(tag)}


def _label_untuk(html: str) -> dict[str, str]:
    """Peta id -> teks label (`<label for="id">teks</label>`)."""
    hasil = {}
    for id_el, isi in _LABEL_FOR.findall(html):
        teks = _bersih(isi)
        if teks:
            hasil[id_el.strip()] = teks
    return hasil


def _opsi_dari(html: str) -> list[dict]:
    """Opsi dari sekumpulan input radio/checkbox atau select."""
    peta = _label_untuk(html)
    opsi = []

    for cocok in _INPUT.finditer(html):
        tag = cocok.group(0)
        atribut = _atribut(tag)
        id_el = atribut.get("id", "")
        teks = peta.get(id_el, "")
        opsi.append(
            {
                "teks": teks or atribut.get("value", ""),
                "dipilih": "checked" in tag.lower(),
                "id": id_el,
            }
        )

    for blok in _SELECT.findall(html):
        for tag_opsi, isi in _OPTION.findall(blok):
            atribut = _atribut(tag_opsi)
            teks = _bersih(isi) or atribut.get("value", "")
            if not teks:
                continue
            opsi.append(
                {
                    "teks": teks,
                    "dipilih": "selected" in tag_opsi.lower(),
                    "id": atribut.get("value", ""),
                }
            )

    return opsi


def baca(berkas: str | Path) -> dict:
    """Baca satu berkas debug dan kembalikan daftar pertanyaan."""
    path = Path(berkas)
    if not path.exists():
        raise FileNotFoundError(f"Berkas debug tidak ada: {path}")

    html = path.read_text(encoding="utf-8", errors="ignore")
    peta = _label_untuk(html)
    pertanyaan: list[dict] = []

    for blok in _FIELDSET.findall(html):
        cocok_legend = _LEGEND.search(blok)
        teks_pertanyaan = _bersih(cocok_legend.group(1)) if cocok_legend else ""
        opsi = _opsi_dari(blok)

        if not teks_pertanyaan and not opsi:
            continue

        if not teks_pertanyaan:
            # Pertanyaan tanpa <legend>: ambil aria-labelledby pertama.
            label_ids = re.search(r"aria-labelledby=[\"']([^\"']+)", blok)
            if label_ids:
                for id_rujukan in label_ids.group(1).split():
                    if id_rujukan in peta:
                        teks_pertanyaan = peta[id_rujukan]
                        break

        pertanyaan.append(
            {
                "pertanyaan": teks_pertanyaan or "(tanpa teks pertanyaan)",
                "jenis": "pilihan" if opsi else "lain",
                "opsi": opsi,
                "terisi": any(item["dipilih"] for item in opsi),
            }
        )

    if not pertanyaan:
        # Tidak ada <fieldset>: kelompokkan radio berdasarkan atribut name.
        nama_grup: dict[str, list[dict]] = {}
        for cocok in _INPUT.finditer(html):
            tag = cocok.group(0)
            atribut = _atribut(tag)
            nama = atribut.get("name", "")
            id_el = atribut.get("id", "")
            nama_grup.setdefault(nama, []).append(
                {
                    "teks": peta.get(id_el, atribut.get("value", "")),
                    "dipilih": "checked" in tag.lower(),
                    "id": id_el,
                }
            )

        for nama, opsi in nama_grup.items():
            if not nama or not opsi:
                continue
            pertanyaan.append(
                {
                    "pertanyaan": nama,
                    "jenis": "pilihan",
                    "opsi": opsi,
                    "terisi": any(item["dipilih"] for item in opsi),
                }
            )

    kosong = [item for item in pertanyaan if not item["terisi"]]

    return {
        "berkas": str(path),
        "jumlah": len(pertanyaan),
        "kosong": len(kosong),
        "pertanyaan": pertanyaan,
    }


def teks_laporan(hasil: dict, semua: bool = False) -> str:
    """Ringkasan yang mudah dibaca di terminal."""
    baris = [
        f"Berkas: {hasil['berkas']}",
        f"Pertanyaan ditemukan: {hasil['jumlah']} · belum terisi: {hasil['kosong']}",
        "",
    ]

    daftar = hasil["pertanyaan"] if semua else [
        item for item in hasil["pertanyaan"] if not item["terisi"]
    ]

    if not daftar:
        baris.append("Semua pertanyaan yang terbaca sudah terisi.")
        return "\n".join(baris)

    for nomor, item in enumerate(daftar, 1):
        tanda = "TERISI" if item["terisi"] else "KOSONG"
        baris.append(f"{nomor}. [{tanda}] {item['pertanyaan'][:120]}")
        for opsi in item["opsi"]:
            centang = "x" if opsi["dipilih"] else " "
            baris.append(f"   [{centang}] {opsi['teks'][:100]}")

    return "\n".join(baris)


def berkas_terakhir(folder: str | Path = "debug") -> Path | None:
    """Berkas debug terbaru (None bila belum ada)."""
    path = Path(folder)
    if not path.is_dir():
        return None

    daftar = sorted(path.glob("*.html"))
    return daftar[-1] if daftar else None
