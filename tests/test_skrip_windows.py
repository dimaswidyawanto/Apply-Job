"""Kesehatan skrip Windows/Linux di akar repo.

Batch berakhir LF pernah membuat cmd melompat ke tengah baris dan mencetak
`'gabungan' is not recognized` pada `tarik.bat`. Tes ini menjaga:
* semua `.bat`/`.vbs` memakai CRLF (wajib untuk cmd.exe),
* semua `.sh` tetap LF,
* `tarik.bat` tidak memakai `goto :label` (sumber lompatan yang salah).
"""

from pathlib import Path

AKAR = Path(__file__).resolve().parents[1]


def _berkas(pola: str):
    return sorted(AKAR.glob(pola))


def test_bat_memakai_akhir_baris_crlf():
    berkas = _berkas("*.bat")
    assert berkas, "tidak ada berkas .bat di akar repo"

    for path in berkas:
        data = path.read_bytes()
        jumlah_lf = data.count(b"\n")
        jumlah_crlf = data.count(b"\r\n")
        assert jumlah_lf == jumlah_crlf, (
            f"{path.name} punya baris berakhir LF; cmd.exe bisa salah melompat"
        )


def test_vbs_memakai_akhir_baris_crlf():
    for path in _berkas("*.vbs"):
        data = path.read_bytes()
        assert data.count(b"\n") == data.count(b"\r\n"), f"{path.name} bukan CRLF"


def test_sh_memakai_akhir_baris_lf():
    for path in _berkas("*.sh"):
        data = path.read_bytes()
        assert b"\r\n" not in data, f"{path.name} memakai CRLF; bash menolaknya"


def test_tarik_bat_tanpa_label_goto():
    isi = (AKAR / "tarik.bat").read_text(encoding="utf-8")
    baris_kode = [
        b.strip()
        for b in isi.splitlines()
        if b.strip() and not b.strip().lower().startswith("rem")
    ]
    assert not any(b.lower().startswith("goto ") for b in baris_kode)
    assert not any(b.startswith(":") and b != ":" for b in baris_kode)


def test_tarik_bat_menyimpan_perubahan_lokal():
    isi = (AKAR / "tarik.bat").read_text(encoding="utf-8")
    assert "git stash push" in isi
    assert "git stash pop" in isi
    assert "git merge --abort" in isi


def test_cek_glints_memakai_venv_langsung():
    isi = (AKAR / "cek-glints.bat").read_text(encoding="utf-8")
    assert '.venv\\Scripts\\python.exe" cli.py glints cek' in isi


def test_jalankan_memasang_dependensi_sekali_saja():
    """pip tidak boleh dipasang ulang setiap perintah (dulu bikin macet)."""
    isi = (AKAR / "jalankan.bat").read_text(encoding="utf-8")

    assert ".deps-terpasang" in isi
    assert "LEWATI_PASANG" in isi
    assert "PAKSA_PASANG" in isi
    # Python 3.14+ membuat pip macet; skrip harus memilih versi lain.
    assert "3.12" in isi
    assert "VENVMINOR" in isi


def test_jalankan_sh_memasang_dependensi_sekali_saja():
    isi = (AKAR / "jalankan.sh").read_text(encoding="utf-8")

    assert ".deps-terpasang" in isi
    assert "LEWATI_PASANG" in isi


def test_peluncur_satu_klik_ada_dan_benar():
    """Satu berkas: tarik kode, pasang dependensi bila perlu, jalankan 3 situs."""
    jalur = AKAR / "Lamar Otomatis.bat"
    assert jalur.exists()

    mentah = jalur.read_bytes()
    assert b"\r\n" in mentah
    assert mentah.count(b"\r\n") == mentah.count(b"\n")

    isi = mentah.decode("utf-8")
    assert "tarik.bat" in isi
    assert "jalankan.bat lamar" in isi
    assert "--tanpa-perbarui" in isi
    assert "pause" in isi

    # Tanpa perintah goto / label: pola itu pernah merusak batch berakhiran LF.
    baris = [b.strip().lower() for b in isi.splitlines()]
    assert not any(b.startswith("goto") for b in baris)
    assert not any(b.startswith(":") for b in baris)


def test_pembuat_pintasan_desktop_ada():
    jalur = AKAR / "buat-pintasan.bat"
    assert jalur.exists()

    mentah = jalur.read_bytes()
    assert mentah.count(b"\r\n") == mentah.count(b"\n")

    isi = mentah.decode("utf-8")
    assert "Lamar Otomatis" in isi
    assert "CreateShortcut" in isi


def test_peluncur_per_situs():
    """Satu berkas per situs: JobStreet, Glints, Indeed."""
    for nama, kunci in (
        ("Lamar JobStreet", "jobstreet"),
        ("Lamar Glints", "glints"),
        ("Lamar Indeed", "indeed"),
    ):
        jalur = AKAR / f"{nama}.bat"
        assert jalur.exists(), nama

        mentah = jalur.read_bytes()
        assert mentah.count(b"\r\n") == mentah.count(b"\n"), nama

        isi = mentah.decode("utf-8")
        assert f"--situs {kunci}" in isi, nama
        assert "tarik.bat" in isi, nama
        assert "jalankan.bat lamar" in isi, nama
        assert "pause" in isi, nama

        baris = [b.strip().lower() for b in isi.splitlines()]
        assert not any(b.startswith("goto") for b in baris), nama
        assert not any(b.startswith(":") for b in baris), nama


def test_tiap_peluncur_hanya_satu_situs():
    """JobStreet tidak boleh ikut menjalankan Glints/Indeed, dan sebaliknya."""
    for nama, lain in (
        ("Lamar JobStreet", ("glints", "indeed")),
        ("Lamar Glints", ("jobstreet", "indeed")),
        ("Lamar Indeed", ("jobstreet", "glints")),
    ):
        isi = (AKAR / f"{nama}.bat").read_text(encoding="utf-8")
        perintah = [
            b for b in isi.splitlines()
            if "jalankan.bat lamar" in b
        ]
        assert len(perintah) == 1, nama
        for situs_lain in lain:
            assert situs_lain not in perintah[0], nama


def test_pembuat_pintasan_mencakup_semua_peluncur():
    isi = (AKAR / "buat-pintasan.bat").read_text(encoding="utf-8")

    for nama in ("Lamar JobStreet", "Lamar Glints", "Lamar Indeed",
                 "Lamar Otomatis"):
        assert nama in isi
    assert "CreateShortcut" in isi


def test_dashboard_bat_ada():
    jalur = AKAR / "Dashboard.bat"
    assert jalur.exists()

    mentah = jalur.read_bytes()
    assert mentah.count(b"\r\n") == mentah.count(b"\n")

    isi = mentah.decode("utf-8")
    assert "jalankan.bat dashboard" in isi
    assert not any(b.strip().lower().startswith("goto") for b in isi.splitlines())
