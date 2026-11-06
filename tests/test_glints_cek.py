"""Pemeriksaan kesehatan Glints berurutan (`glints cek`).

Semua bagian yang butuh Chrome diganti palsu; yang diuji adalah alur laporan
lulus/gagal, bukan mesin Selenium-nya.
"""

import glints as glints_module
import simulasi_glints


class DriverPalsu:
    def __init__(self, judul="Lowongan Kerja Glints"):
        self._judul = judul
        self.teks = "Masuk Daftar Pekerjaan"
        self.tautan = []

    @property
    def title(self):
        return self._judul


def _uuid(i: int) -> str:
    return f"0000000{i}-1111-2222-3333-44444444444{i}"


def _kartu_mentah(jumlah=12, logo=None):
    if logo is None:
        logo = [{"src": "https://images.glints.com/logo/pt-contoh.png", "alt": ""}]
    return [
        {
            "url": f"https://glints.com/id/opportunities/jobs/staff-gudang/"
            f"{_uuid(i)}",
            "title": f"Staff Gudang {i}",
            "company": f"PT Contoh {i}",
            "text": "Staff gudang · Jakarta · 3 hari lalu",
            "location": "Jakarta",
            "logo": logo,
        }
        for i in range(jumlah)
    ]


DEFAULT_KARTU = _kartu_mentah()


class BotPalsu:
    cloudflare = False
    kartu = DEFAULT_KARTU
    login = True

    def __init__(self):
        self.driver = DriverPalsu()
        self.ditutup = False

    def init_browser(self):
        self.driver = DriverPalsu()

    def buka_pencarian(self, keyword):
        return True

    def kena_cloudflare(self):
        return type(self).cloudflare

    def sudah_login(self):
        return type(self).login

    def _kartu_mentah(self):
        return list(type(self).kartu)

    def _kartu_fallback(self):
        return []

    def tutup(self):
        self.ditutup = True


KANDIDAT = [
    {
        "title": f"Staff {i}",
        "company": f"PT {i}",
        "url": f"https://glints.com/id/opportunities/jobs/x/{_uuid(i)}",
        "has_logo": True,
    }
    for i in range(3)
]


def _siapkan(monkeypatch, kandidat=None, kartu=None, cloudflare=False):
    BotPalsu.cloudflare = cloudflare
    BotPalsu.kartu = DEFAULT_KARTU if kartu is None else list(kartu)
    BotPalsu.login = True
    monkeypatch.setattr(glints_module, "GlintsBot", BotPalsu)
    monkeypatch.setattr(
        glints_module, "kumpulkan_lowongan",
        lambda bot, kata, halaman: list(KANDIDAT if kandidat is None else kandidat),
    )
    monkeypatch.setattr(
        glints_module, "pilih_kandidat",
        lambda lowongan, batas=0, semuanya=False: list(lowongan)[:batas],
    )

    class Statistik:
        total_applied = 7
        today = 2

    monkeypatch.setattr(
        glints_module.db, "get_stats", lambda: {"total_applied": 7}
    )
    monkeypatch.setattr(glints_module.db, "get_today_apply_count", lambda: 2)


def _tanpa_simulasi(monkeypatch, lulus=True):
    monkeypatch.setattr(simulasi_glints, "jalankan", lambda: lulus)


def test_cek_lulus_tanpa_melamar(monkeypatch):
    _siapkan(monkeypatch)
    _tanpa_simulasi(monkeypatch)
    dipanggil = {"lamar": 0}
    monkeypatch.setattr(
        glints_module, "jalankan_glints",
        lambda **kwargs: dipanggil.__setitem__("lamar", dipanggil["lamar"] + 1),
    )

    assert glints_module.cek_glints(keyword="inventory staff") is True
    assert dipanggil["lamar"] == 0  # tidak melamar tanpa --lamar


def test_cek_gagal_saat_cloudflare(monkeypatch):
    _siapkan(monkeypatch, cloudflare=True)
    _tanpa_simulasi(monkeypatch)
    dipanggil = {"kumpul": 0}

    def kumpul(*_args, **_kwargs):
        dipanggil["kumpul"] += 1
        return []

    monkeypatch.setattr(glints_module, "kumpulkan_lowongan", kumpul)

    assert glints_module.cek_glints(keyword="inventory") is False
    # Cloudflare: pencarian tidak diulang, hemat waktu.
    assert dipanggil["kumpul"] == 0


def test_cek_gagal_bila_kartu_sedikit(monkeypatch):
    _siapkan(monkeypatch, kartu=_kartu_mentah(1))
    _tanpa_simulasi(monkeypatch)

    assert glints_module.cek_glints(keyword="inventory") is False


def test_cek_lulus_walau_kandidat_tanpa_logo(monkeypatch):
    """Logo bukan syarat: kartu tanpa gambar tetap diperiksa dan dilamar."""
    _siapkan(monkeypatch)
    _tanpa_simulasi(monkeypatch)
    tanpa_logo = [dict(KANDIDAT[0], has_logo=False)]
    monkeypatch.setattr(
        glints_module, "kumpulkan_lowongan", lambda *a, **k: tanpa_logo
    )
    monkeypatch.setattr(
        glints_module, "pilih_kandidat", lambda low, batas=0, semuanya=False: low
    )

    assert glints_module.cek_glints(keyword="inventory") is True


def test_cek_gagal_bila_simulasi_tidak_sesuai(monkeypatch):
    _siapkan(monkeypatch)
    _tanpa_simulasi(monkeypatch, lulus=False)

    assert glints_module.cek_glints(keyword="inventory") is False


def test_cek_lamar_dibatalkan_tanpa_persetujuan(monkeypatch):
    _siapkan(monkeypatch)
    _tanpa_simulasi(monkeypatch)
    monkeypatch.setattr(glints_module, "_setuju_lamar", lambda jumlah, kandidat: False)
    dipanggil = {"n": 0}
    monkeypatch.setattr(
        glints_module, "jalankan_glints",
        lambda **kwargs: dipanggil.__setitem__("n", dipanggil["n"] + 1),
    )

    assert glints_module.cek_glints(keyword="inventory", lamar=3) is True
    assert dipanggil["n"] == 0


def test_cek_lamar_menjalankan_sesi_kecil(monkeypatch):
    _siapkan(monkeypatch)
    _tanpa_simulasi(monkeypatch)
    dipanggil = {}

    def jalankan(**kwargs):
        dipanggil.update(kwargs)
        return {"dilamar": 2, "sudah": 0, "gagal": 0, "perlu_manual": 0}

    monkeypatch.setattr(glints_module, "jalankan_glints", jalankan)

    assert glints_module.cek_glints(keyword="inventory", lamar=3, ya=True) is True
    assert dipanggil["batas"] == 3


def test_cek_lamar_gagal_bila_tidak_ada_terkirim(monkeypatch):
    _siapkan(monkeypatch)
    _tanpa_simulasi(monkeypatch)
    monkeypatch.setattr(
        glints_module, "jalankan_glints",
        lambda **kwargs: {"dilamar": 0, "sudah": 0, "gagal": 3, "perlu_manual": 0},
    )

    assert glints_module.cek_glints(keyword="inventory", lamar=3, ya=True) is False
