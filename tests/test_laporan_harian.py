"""Laporan berkala: teks Markdown + berkas harian (master prompt pasal 12.4)."""

import laporan


def _data():
    return {
        "lowongan_tersimpan": 12,
        "lamaran_terkirim": 4,
        "lamaran_hari_ini": 3,
        "sisa_kuota": 47,
        "status_antrean": {"applied": 4, "rejected": 8, "failed": 0},
        "per_lokasi": [{"lokasi": "Bandung", "jumlah": 9, "dilamar": 4}],
        "per_kategori": [{"kategori": "inventory", "jumlah": 6, "dilamar": 4}],
        "alasan_tersering": [{"alasan": "Tanpa logo perusahaan", "jumlah": 5}],
        "tingkat_berhasil": 100.0,
    }


def test_teks_markdown_berisi_angka_dan_saran():
    teks = laporan.teks_markdown(_data())

    assert "Lowongan tersimpan: 12" in teks
    assert "Lamaran terkirim: 4" in teks
    assert "| Bandung | 9 | 4 |" in teks
    assert "Tanpa logo perusahaan" in teks
    # Status dengan jumlah 0 tidak ditampilkan agar tabel tetap ringkas.
    assert "failed" not in teks


def test_simpan_menulis_berkas_harian(tmp_path):
    berkas = laporan.simpan(tmp_path, _data())

    assert berkas.exists()
    assert berkas.name.startswith("laporan-")
    assert berkas.suffix == ".md"
    assert "Laporan Lamar Otomatis" in berkas.read_text(encoding="utf-8")


def test_simpan_menimpa_hari_yang_sama(tmp_path):
    pertama = laporan.simpan(tmp_path, _data())
    kedua = laporan.simpan(tmp_path, _data())

    assert pertama == kedua
    assert len(list(tmp_path.glob("laporan-*.md"))) == 1


def test_kuota_per_situs_tanpa_batas():
    data = _data()
    data["kuota_situs"] = [
        {"situs": "glints", "nama": "Glints", "terpakai": 3, "batas": 50,
         "sisa": 47},
    ]

    teks = laporan.teks_markdown(data)

    assert "Kuota per situs: Glints 3/50 (sisa 47)" in teks
