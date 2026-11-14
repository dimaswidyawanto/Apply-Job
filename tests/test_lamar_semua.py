"""Peluncur satu klik: JobStreet → Glints → Indeed dalam sekali jalan."""

import lamar_semua
from config import config


def _siapkan(monkeypatch, terpakai=0, batas=50):
    """Ganti semua sisi luar (browser, kuota, Telegram, git) dengan palsu."""
    dicatat = {"situs": [], "laporan": 0, "galat": []}

    monkeypatch.setattr(lamar_semua.kuota, "habis", lambda *a, **k: (
        bool(batas) and terpakai >= batas
    ))
    monkeypatch.setattr(
        lamar_semua.kuota, "pesan_habis", lambda *a, **k: "Kuota harian habis."
    )
    monkeypatch.setattr(
        lamar_semua.kuota, "ringkasan", lambda *a, **k: "Kuota harian: 0 dilamar."
    )

    def jalankan_situs(nama, max_pages, batas_sesi):
        dicatat["situs"].append((nama, max_pages, batas_sesi))
        return {
            "dibaca": 10, "baru": 5, "dilamar": 2, "sudah": 1,
            "perlu_manual": 0, "dilewati": 2, "gagal": 0,
        }

    monkeypatch.setattr(lamar_semua, "_jalankan_situs", jalankan_situs)
    monkeypatch.setattr(
        lamar_semua.notifier, "send_daily_report",
        lambda stats: dicatat.__setitem__("laporan", dicatat["laporan"] + 1),
    )
    monkeypatch.setattr(
        lamar_semua.notifier, "send_error",
        lambda pesan: dicatat["galat"].append(pesan),
    )
    return dicatat


def test_tiga_situs_dijalankan_berurutan(monkeypatch):
    dicatat = _siapkan(monkeypatch)

    hasil = lamar_semua.jalankan(perbarui=False)

    assert [nama for nama, _, _ in dicatat["situs"]] == [
        "jobstreet", "glints", "indeed"
    ]
    assert set(hasil) == {"jobstreet", "glints", "indeed"}
    assert sum(data["dilamar"] for data in hasil.values()) == 6


def test_laporan_harian_hanya_sekali(monkeypatch):
    dicatat = _siapkan(monkeypatch)

    lamar_semua.jalankan(perbarui=False)

    assert dicatat["laporan"] == 1


def test_situs_bisa_dipilih(monkeypatch):
    dicatat = _siapkan(monkeypatch)

    lamar_semua.jalankan(situs="indeed,jobstreet", perbarui=False)

    assert [nama for nama, _, _ in dicatat["situs"]] == ["jobstreet", "indeed"]


def test_nama_situs_tidak_dikenal_diabaikan(monkeypatch):
    dicatat = _siapkan(monkeypatch)

    hasil = lamar_semua.jalankan(situs="kalibrr", perbarui=False)

    assert dicatat["situs"] == []
    assert hasil == {}


def test_situs_terpilih_memakai_setelan_env(monkeypatch):
    monkeypatch.setattr(config, "situs_aktif", "indeed,glints", raising=False)

    assert lamar_semua.situs_terpilih("") == ["glints", "indeed"]


def test_kata_semua_berarti_tiga_situs():
    assert lamar_semua.situs_terpilih("semua") == list(lamar_semua.SITUS_BAKU)


def test_kuota_habis_situs_berikutnya_dilewati(monkeypatch):
    dicatat = _siapkan(monkeypatch, terpakai=50, batas=50)

    hasil = lamar_semua.jalankan(perbarui=False)

    assert dicatat["situs"] == []
    assert hasil == {}
    assert dicatat["laporan"] == 1


def test_satu_situs_gagal_situs_lain_tetap_jalan(monkeypatch):
    dicatat = _siapkan(monkeypatch)

    def rusak(nama, max_pages, batas_sesi):
        dicatat["situs"].append((nama, max_pages, batas_sesi))
        if nama == "glints":
            raise RuntimeError("Cloudflare menolak")
        return {"dilamar": 1}

    monkeypatch.setattr(lamar_semua, "_jalankan_situs", rusak)

    hasil = lamar_semua.jalankan(perbarui=False)

    assert [nama for nama, _, _ in dicatat["situs"]] == [
        "jobstreet", "glints", "indeed"
    ]
    assert "glints" not in hasil
    assert "indeed" in hasil
    assert any("Glints" in pesan for pesan in dicatat["galat"])


def test_perbarui_dilewati_bila_bukan_repo_git(monkeypatch, tmp_path):
    monkeypatch.setattr(lamar_semua, "AKAR", tmp_path)

    berhasil, pesan = lamar_semua.perbarui_kode()

    assert berhasil is False
    assert "repo Git" in pesan


def test_perbarui_tidak_pernah_melempar_galat(monkeypatch, tmp_path):
    (tmp_path / ".git").mkdir()

    def meledak(*a, **k):
        raise OSError("git tidak ada")

    monkeypatch.setattr(lamar_semua, "AKAR", tmp_path)
    monkeypatch.setattr(lamar_semua, "_git", meledak)

    berhasil, pesan = lamar_semua.perbarui_kode()

    assert berhasil is False
    assert "pembaruan gagal" in pesan


# ---------------------------------------------- tarik pembaruan yang benar ---
class _Hasil:
    def __init__(self, stdout="", returncode=0):
        self.stdout = stdout
        self.returncode = returncode


def _git_palsu(monkeypatch, tmp_path, jawaban):
    """_git palsu: `jawaban` memetakan potongan argumen → hasil."""
    (tmp_path / ".git").mkdir(exist_ok=True)
    jejak = []

    def palsu(*argumen, **kwargs):
        kunci = " ".join(argumen)
        jejak.append(kunci)
        for pola, hasil in jawaban.items():
            if pola in kunci:
                return hasil
        return _Hasil()

    monkeypatch.setattr(lamar_semua, "AKAR", tmp_path)
    monkeypatch.setattr(lamar_semua, "_git", palsu)
    return jejak


def test_perbarui_menarik_main_bila_cabang_usang(monkeypatch, tmp_path):
    """ARENA_CABANG menunjuk cabang lama → tetap tarik main (bug nyata)."""
    jejak = _git_palsu(
        monkeypatch,
        tmp_path,
        {
            "rev-list --count HEAD..arena/main": _Hasil("3\n"),
            "merge --no-edit arena/arena/4ab2b9fa-dimastes": _Hasil(
                "Already up to date.\n"
            ),
            "merge --no-edit arena/main": _Hasil("ok\n"),
            "rev-parse --short HEAD": _Hasil("d72da3a\n"),
        },
    )

    berhasil, pesan = lamar_semua.perbarui_kode(
        cabang="arena/4ab2b9fa-dimastes"
    )

    assert berhasil is True
    assert "d72da3a" in pesan
    assert any("merge --no-edit arena/main" in k for k in jejak)


def test_perbarui_tidak_menggabung_dua_kali_bila_sudah_sama(
    monkeypatch, tmp_path
):
    jejak = _git_palsu(
        monkeypatch,
        tmp_path,
        {
            "rev-list --count HEAD..arena/main": _Hasil("0\n"),
            "rev-parse --short HEAD": _Hasil("d72da3a\n"),
        },
    )

    berhasil, pesan = lamar_semua.perbarui_kode(cabang="main")

    assert berhasil is True
    assert "d72da3a" in pesan
    # Hanya satu penggabungan: cabang baku itu sendiri, tanpa pengulangan.
    assert jejak.count("merge --no-edit arena/main") == 1


def test_perbarui_main_bentrok_dilaporkan(monkeypatch, tmp_path):
    _git_palsu(
        monkeypatch,
        tmp_path,
        {
            "rev-list --count HEAD..arena/main": _Hasil("2\n"),
            "merge --no-edit arena/main": _Hasil("", returncode=1),
        },
    )

    berhasil, pesan = lamar_semua.perbarui_kode()

    assert berhasil is False
    assert "bentrok" in pesan


def test_cabang_baku_adalah_main():
    """Bawaan harus `main`; cabang sesi lama tidak selalu ada di GitHub."""
    assert lamar_semua.CABANG_BAKU == "main"
