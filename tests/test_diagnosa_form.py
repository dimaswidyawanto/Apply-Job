"""Diagnosa berkas debug HTML: temukan pertanyaan formulir yang belum terisi.

Dipakai saat bot melaporkan "please address the following issues": berkas
debug/….html berisi HTML halaman, dan perintah `diagnosa-form` menunjukkan
pertanyaan mana yang masih kosong tanpa perlu membuka Chrome.
"""

import diagnosa_form

HTML = """
<html><body>
<form>
  <fieldset>
    <legend>Do you have production support experience?</legend>
    <input type="radio" id="q1_yes" name="q1" value="yes">
    <label for="q1_yes">Yes</label>
    <input type="radio" id="q1_no" name="q1" value="no">
    <label for="q1_no">No</label>
  </fieldset>
  <fieldset>
    <legend>Which statement best describes your right to work?</legend>
    <input type="radio" id="q2_a" name="q2" value="a" checked>
    <label for="q2_a">I'm an Indonesian citizen</label>
    <input type="radio" id="q2_b" name="q2" value="b">
    <label for="q2_b">I hold a valid work permit</label>
  </fieldset>
  <fieldset>
    <legend>Berapa gaji bulanan yang kamu inginkan?</legend>
    <select name="gaji">
      <option value="">Pilih</option>
      <option value="4">Rp 4 Jt</option>
      <option value="5" selected>Rp 5 Jt</option>
    </select>
  </fieldset>
</form>
</body></html>
"""


def tulis(tmp_path, isi=HTML, nama="debug.html"):
    berkas = tmp_path / nama
    berkas.write_text(isi, encoding="utf-8")
    return berkas


def test_membaca_pertanyaan_dan_opsi(tmp_path):
    hasil = diagnosa_form.baca(tulis(tmp_path))

    assert hasil["jumlah"] == 3
    assert hasil["kosong"] == 1

    pertama = hasil["pertanyaan"][0]
    assert "production support" in pertama["pertanyaan"]
    assert pertama["terisi"] is False
    assert [item["teks"] for item in pertama["opsi"]] == ["Yes", "No"]


def test_pilihan_yang_sudah_terisi_dikenali(tmp_path):
    hasil = diagnosa_form.baca(tulis(tmp_path))
    kedua = hasil["pertanyaan"][1]

    assert kedua["terisi"] is True
    assert any(
        item["teks"].startswith("I'm an Indonesian citizen") and item["dipilih"]
        for item in kedua["opsi"]
    )


def test_dropdown_terpilih_dikenali(tmp_path):
    hasil = diagnosa_form.baca(tulis(tmp_path))
    gaji = hasil["pertanyaan"][2]

    assert gaji["terisi"] is True
    assert any(item["teks"] == "Rp 5 Jt" and item["dipilih"] for item in gaji["opsi"])


def test_laporan_menandai_kosong(tmp_path):
    teks = diagnosa_form.teks_laporan(diagnosa_form.baca(tulis(tmp_path)))

    assert "belum terisi: 1" in teks
    assert "[KOSONG]" in teks
    assert "[ ] Yes" in teks
    # Yang sudah terisi tidak ditampilkan kecuali diminta (--semua).
    assert "Indonesian citizen" not in teks


def test_laporan_semua_menampilkan_yang_terisi(tmp_path):
    teks = diagnosa_form.teks_laporan(
        diagnosa_form.baca(tulis(tmp_path)), semua=True
    )

    assert "[TERISI]" in teks
    assert "[x] I'm an Indonesian citizen" in teks


def test_html_tanpa_fieldset_tetap_terbaca(tmp_path):
    html = """
    <input type="radio" id="a" name="q_a" value="1" checked>
    <label for="a">Ya</label>
    <input type="radio" id="b" name="q_a" value="2">
    <label for="b">Tidak</label>
    """
    hasil = diagnosa_form.baca(tulis(tmp_path, html))

    assert hasil["jumlah"] == 1
    assert hasil["kosong"] == 0


def test_berkas_tidak_ada(tmp_path):
    import pytest

    with pytest.raises(FileNotFoundError):
        diagnosa_form.baca(tmp_path / "tidak-ada.html")


def test_berkas_terakhir_memilih_yang_baru(tmp_path):
    tulis(tmp_path, HTML, "20261108-100000-a.html")
    tulis(tmp_path, HTML, "20261108-120000-b.html")

    terakhir = diagnosa_form.berkas_terakhir(tmp_path)

    assert terakhir is not None
    assert terakhir.name.endswith("b.html")


def test_berkas_terakhir_kosong(tmp_path):
    assert diagnosa_form.berkas_terakhir(tmp_path / "belum-ada") is None
