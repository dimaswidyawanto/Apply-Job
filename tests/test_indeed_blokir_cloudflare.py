"""Indeed: kenali blokir Cloudflare (bukan captcha biasa) dan berhenti cepat.

Latar belakang (layar pemakai, 2026-11-08): Indeed menampilkan halaman
"Diperlukan Verifikasi Tambahan" milik Cloudflare (ID Ray). Bot menunggu 60
detik untuk setiap kombinasi kata kunci x lokasi — 180 kombinasi, perkiraan
sisa 5943 detik — dan menghasilkan nol lowongan. Halaman itu tidak punya
centang yang bisa diklik program, jadi menunggu tidak menolong.

Tes memakai driver tiruan; tidak ada Chrome di sini.
"""

import indeed


class Badan:
    def __init__(self, teks):
        self.text = teks


class Driver:
    def __init__(self, teks="", judul="Indeed", url="https://id.indeed.com/jobs?q=x"):
        self.teks = teks
        self.title = judul
        self.current_url = url
        self.page_source = "<html><body>uji</body></html>"
        self.dibuka = []

    def get(self, url):
        self.dibuka.append(url)
        self.current_url = url

    def find_element(self, by, selector):
        if selector == "body":
            return Badan(self.teks)
        raise RuntimeError("tidak ada elemen")

    def find_elements(self, by, selector):
        return []

    def execute_script(self, *argumen):
        return None

    def save_screenshot(self, path):
        with open(path, "wb") as berkas:
            berkas.write(b"png")


def _bot(teks="", judul="Indeed", url="https://id.indeed.com/jobs?q=x"):
    bot = indeed.IndeedBot()
    bot.driver = Driver(teks, judul, url)
    return bot


# ------------------------------------------------------------------ deteksi ---
def test_kenali_teks_verifikasi_tambahan():
    bot = _bot("Diperlukan Verifikasi Tambahan ID Ray Anda a5956cc5fbed9fad")

    assert bot.diblokir_cloudflare() is True


def test_kenali_judul_tunggu_sebentar():
    bot = _bot("halaman kosong", judul="Tunggu sebentar...")

    assert bot.diblokir_cloudflare() is True


def test_kenali_judul_just_a_moment():
    bot = _bot("", judul="Just a moment...")

    assert bot.diblokir_cloudflare() is True


def test_halaman_pencarian_normal_bukan_blokir():
    bot = _bot("inventory staff jobs in Bandung", judul="inventory staff Jobs")

    assert bot.diblokir_cloudflare() is False


def test_captcha_biasa_tetap_terdeteksi_terpisah():
    bot = _bot("please complete the captcha", judul="Indeed")

    assert bot.kena_captcha() is True
    assert bot.diblokir_cloudflare() is False


# --------------------------------------------------- berhenti tanpa menunggu ---
def test_blokir_langsung_menghentikan_riset(monkeypatch):
    bot = _bot("Diperlukan Verifikasi Tambahan", judul="Tunggu sebentar...")

    dipanggil = []
    monkeypatch.setattr(
        indeed.time, "sleep", lambda detik: dipanggil.append(detik)
    )

    assert bot.buka_pencarian("inventory staff", "Bandung") is False
    # Tidak ada penantian 60 detik untuk tantangan Cloudflare.
    assert max(dipanggil or [0]) < 60
    assert bot.captcha_berturut == bot.BATAS_CAPTCHA_BERTURUT


def test_blokir_dilaporkan_sekali():
    bot = _bot("Diperlukan Verifikasi Tambahan", judul="Tunggu sebentar...")

    bot._laporkan_blokir("https://id.indeed.com/jobs")
    bot._laporkan_blokir("https://id.indeed.com/jobs")

    assert bot.blokir_dilaporkan is True


# -------------------------------------------------- riset berhenti seketika ---
class BotTiruan:
    BATAS_CAPTCHA_BERTURUT = 2

    def __init__(self):
        self.captcha_berturut = 2
        self.blokir_dilaporkan = True
        self.dipanggil = []

    def buka_pencarian(self, kata, lokasi=""):
        self.dipanggil.append((kata, lokasi))
        return True


def test_riset_tidak_mencari_lagi_setelah_diblokir():
    bot = BotTiruan()

    hasil = indeed.kumpulkan_lowongan(bot, ["inventory staff", "gudang"], 1)

    assert hasil == []
    assert bot.dipanggil == []


# ------------------------------------------------- blokir di halaman lowongan ---
def test_halaman_lowongan_diblokir_diberi_alasan_cloudflare():
    applier = indeed.IndeedApplier(
        Driver("Diperlukan Verifikasi Tambahan", "Tunggu sebentar...")
    )

    alasan = applier._blocker()

    assert "cloudflare" in alasan.lower()


def test_halaman_lowongan_captcha_biasa_tetap_dikenali():
    applier = indeed.IndeedApplier(Driver("please complete the captcha"))

    alasan = applier._blocker()

    assert "captcha" in alasan.lower()


def test_halaman_lowongan_normal_tanpa_alasan():
    applier = indeed.IndeedApplier(Driver("Deskripsi pekerjaan biasa"))

    assert applier._blocker() == ""
