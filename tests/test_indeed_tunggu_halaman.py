"""Indeed: halaman perantara Cloudflare vs blokir sungguhan vs hasil kosong.

Latar belakang (log 2026-11-14, dua sesi berturut-turut):

    Indeed diblokir Cloudflare — halaman "Diperlukan Verifikasi Tambahan"
    Judul: Security Check - Indeed.com / Tunggu sebentar...
    Kemajuan riset Indeed: 1/180 kombinasi, 0 lowongan, 2 detik berlalu

Bot memeriksa halaman hanya 1 detik setelah `driver.get`, sehingga yang
terbaca selalu halaman perantara Cloudflare — yang bagi manusia biasanya
lolos sendiri dalam beberapa detik. Akibatnya 180 kombinasi dibatalkan
karena satu halaman yang belum selesai dimuat.

Tes ini menjaga tiga hal:
* halaman perantara yang lolos TIDAK dianggap blokir,
* halaman hasil kosong ("did not match any jobs") juga bukan blokir,
* tantangan yang bertahan sampai batas waktu tetap menghentikan riset.
"""

import indeed


class DriverPalsu:
    """Driver minimal: cukup mencatat URL yang dibuka."""

    def __init__(self):
        self.dibuka = []
        self.current_url = ""

    def get(self, url):
        self.dibuka.append(url)
        self.current_url = url


class BotUji(indeed.IndeedBot):
    """IndeedBot tanpa browser: kartu/judul/teks ditentukan tes."""

    def __init__(self, kartu_urut=(), judul="", teks=""):
        super().__init__()
        self.driver = DriverPalsu()
        self.kartu_urut = list(kartu_urut)
        self.terakhir = 0
        self.judul = judul
        self.teks = teks
        self.blokir_dilaporkan = []
        self.sudah_login = lambda: True

    def _tautan_kartu(self):
        """Jumlah kartu mengikuti urutan; nilai terakhir dipertahankan.

        Ini penting karena `buka_pencarian` memanggil `_tautan_kartu` lagi di
        `_tunggu_kartu()`; kartu yang sudah muncul tidak boleh "hilang".
        """
        if self.kartu_urut:
            self.terakhir = self.kartu_urut.pop(0)
        return [
            f"https://id.indeed.com/viewjob?jk=abc{i}"
            for i in range(self.terakhir)
        ]

    def _judul_halaman(self):
        return self.judul

    def _teks_halaman(self):
        return self.teks

    def _laporkan_blokir(self, url=""):
        self.blokir_dilaporkan.append(url)


class WaktuPalsu:
    """Pengganti modul `time` di indeed.py agar tes tidak menunggu 15 detik."""

    def __init__(self):
        self.sekarang = 0.0

    def time(self):
        return self.sekarang

    def sleep(self, detik):
        self.sekarang += float(detik)


def _siapkan(monkeypatch, di):
    jam = WaktuPalsu()
    monkeypatch.setattr(indeed, "time", jam)
    return di


def test_kartu_muncul_langsung_tanpa_menunggu(monkeypatch):
    bot = _siapkan(monkeypatch, BotUji(kartu_urut=[5]))

    assert bot.buka_pencarian("inventory", "Bandung") is True
    assert bot.blokir_dilaporkan == []
    assert bot.captcha_berturut == 0


def test_halaman_perantara_yang_lolos_bukan_blokir(monkeypatch):
    """Inti perbaikan: halaman 'Tunggu sebentar...' yang selesai sendiri."""
    bot = _siapkan(
        monkeypatch,
        BotUji(kartu_urut=[0, 0, 0, 4], judul="Tunggu sebentar..."),
    )

    assert bot.buka_pencarian("inventory control", "Bandung") is True
    assert bot.blokir_dilaporkan == []
    assert bot.captcha_berturut == 0
    # Hanya satu navigasi: tidak perlu bentuk URL cadangan.
    assert len(bot.driver.dibuka) == 1


def test_tantangan_yang_bertahan_tetap_menghentikan_riset(monkeypatch):
    bot = _siapkan(
        monkeypatch,
        BotUji(
            kartu_urut=[0] * 60,
            judul="Security Check - Indeed.com",
            teks="diperlukan verifikasi tambahan",
        ),
    )

    assert bot.buka_pencarian("inventory control", "Bandung") is False
    assert bot.blokir_dilaporkan, "blokir sungguhan harus dilaporkan"
    # Bentuk cadangan dicoba lebih dulu: URL pertama + URL tanpa sort=date.
    assert len(bot.driver.dibuka) == 2
    assert "sort=date" not in bot.driver.dibuka[1]


def test_hasil_kosong_bukan_blokir(monkeypatch, capsys):
    bot = _siapkan(
        monkeypatch,
        BotUji(
            kartu_urut=[0],
            judul="inventory staff Jobs in Bandung - Indeed",
            teks="the search inventory staff jobs in bandung did not match "
            "any jobs. search suggestions:",
        ),
    )

    assert bot.buka_pencarian("inventory staff", "Bandung") is False
    assert bot.blokir_dilaporkan == []
    assert bot.captcha_berturut == 0
    assert "Tidak ada lowongan untuk kombinasi ini" in capsys.readouterr().out


def test_url_cadangan_tanpa_sort_date_dipakai_bila_perlu(monkeypatch):
    """Bentuk pertama diblokir, bentuk tanpa sort=date berhasil."""

    bot = _siapkan(
        monkeypatch,
        BotUji(
            kartu_urut=[0] * 16 + [3],
            judul="Tunggu sebentar...",
        ),
    )

    # 16 putaran pertama (batas waktu 15 detik) diblokir, lalu bentuk cadangan
    # berhasil tanpa `sort=date`.
    assert bot.buka_pencarian("staf gudang", "Cimahi") is True
    assert len(bot.driver.dibuka) == 2
    assert "sort=date" in bot.driver.dibuka[0]
    assert "sort=date" not in bot.driver.dibuka[1]
    assert bot.blokir_dilaporkan == []


def test_batas_tunggu_memakai_konstanta_modul(monkeypatch):
    """Batas waktu tidak lagi 1 detik, dan bisa diatur dari satu tempat."""
    assert indeed.BATAS_TUNGGU_HALAMAN >= 10

    jam = WaktuPalsu()
    monkeypatch.setattr(indeed, "time", jam)
    monkeypatch.setattr(indeed, "BATAS_TUNGGU_HALAMAN", 4)

    bot = BotUji(kartu_urut=[0] * 60, judul="Tunggu sebentar...")
    bot.buka_pencarian("inventory", "Bandung")

    # Dua percobaan × 4 detik tunggu (bentuk utama lalu cadangan).
    assert jam.sekarang == 8.0
