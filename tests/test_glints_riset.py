"""Riset Glints harus mengikuti aturan JobStreet.

Yang diuji di sini: urutan "Baru Ditambahkan" tetap dipakai walau riset
memuat beberapa kali (5 muat), umur lowongan dibaca dari teks kartu supaya
dimensi tanggal ikut menilai, dan rincian skor ditampilkan.
"""

import glints as glints_module
from config import config

UUID = "123e4567-e89b-12d3-a456-426614174000"


class DriverPalsu:
    def __init__(self):
        self.url = ""

    def get(self, url):
        self.url = url

    def find_elements(self, *args, **kwargs):
        return []

    def execute_script(self, *args, **kwargs):
        return []


def kartu_glints(job_id, judul="Inventory Staff", teks="", uuid=UUID):
    return {
        "url": f"https://glints.com/id/opportunities/jobs/inventory-staff/{uuid}",
        "title": judul,
        "company": "PT Contoh",
        "location": "Bekasi",
        "salary": "Rp 6-7jt",
        "text": teks or "PT Contoh · Bekasi · Rp 6-7jt",
        "logo": [{"alt": "logo PT Contoh", "src": "https://x/logo.png",
                  "penanda": ""}],
        "job_id": job_id,
    }


def test_umur_lowongan_dibaca_dari_teks_kartu():
    assert glints_module.umur_dari_teks("Baru saja") == 0
    assert glints_module.umur_dari_teks("3 hari lalu") == 3
    assert glints_module.umur_dari_teks("2 minggu lalu") == 14
    assert glints_module.umur_dari_teks("5 jam lalu") == 0
    assert glints_module.umur_dari_teks("tanpa keterangan") is None
    assert glints_module.umur_dari_teks("") is None


def test_rapikan_kartu_mengisi_tanggal_publikasi():
    job = glints_module.rapikan_kartu(
        kartu_glints("x", teks="PT Contoh · Bekasi · 2 hari lalu")
    )

    assert job is not None
    assert job["age_days"] == 2
    assert job["date_posted"] == "2 hari lalu"
    assert job["has_logo"] is True


def test_urutkan_terbaru_dipakai_walau_memuat_beberapa_kali(monkeypatch):
    bot = glints_module.GlintsBot()
    bot.driver = DriverPalsu()

    urut_dipanggil = []
    muat_dipanggil = []

    monkeypatch.setattr(config, "prefer_newest", True)
    monkeypatch.setattr(bot, "buka_pencarian", lambda keyword, location="": True)
    monkeypatch.setattr(
        bot, "urutkan_terbaru", lambda: urut_dipanggil.append(1) or True
    )
    monkeypatch.setattr(
        bot, "muat_lebih", lambda: muat_dipanggil.append(1) or False
    )

    # Riset memuat 5 kali -> cari(keyword, 4); urutan terbaru tetap dipakai.
    bot.cari("inventory", 4)

    assert urut_dipanggil == [1]
    assert len(muat_dipanggil) == 1


def test_tanggal_ikut_menilai_lowongan_glints():
    baru = glints_module.rapikan_kartu(
        kartu_glints(
            "baru",
            teks="PT Contoh · Bekasi · Baru saja",
            uuid="11111111-1111-1111-1111-111111111111",
        )
    )
    lama = glints_module.rapikan_kartu(
        kartu_glints(
            "lama",
            teks="PT Contoh · Bekasi · 9 hari lalu",
            uuid="22222222-2222-2222-2222-222222222222",
        )
    )

    hasil = glints_module.pilih_teratas([lama, baru], batas=0)

    assert [job["age_days"] for job in hasil] == [0, 9]
    assert (
        hasil[0]["_skor_rincian"]["tanggal"]
        > hasil[1]["_skor_rincian"]["tanggal"]
    )


def test_rincian_skor_ditampilkan_untuk_glints(capsys):
    job = glints_module.rapikan_kartu(kartu_glints("baru"))
    glints_module.pilih_teratas([job], batas=0)

    glints_module.tampilkan_rincian_skor([job])

    keluaran = capsys.readouterr().out.lower()
    assert "rincian skor" in keluaran
    # Tabel lebar di terminal sempit membungkus teks, jadi hitung isi tabel:
    # 1 baris judul lowongan + 9 kolom skor.
    assert keluaran.count("│") >= 10


def test_kartu_tanpa_logo_dilewati_di_glints(monkeypatch, capsys):
    """Logo wajib di JobStreet & Glints (pasal 6.1 master prompt)."""
    from config import config as cfg

    monkeypatch.setattr(cfg, "require_company_logo", True)
    monkeypatch.setattr(cfg, "max_apply_per_day", 50)
    monkeypatch.setattr(cfg, "locations", ["Bekasi"])
    monkeypatch.setattr(cfg, "keywords", ["inventory"])
    monkeypatch.setattr(cfg, "research_keywords", [])
    monkeypatch.setattr(cfg, "research_max_pages", 1)
    monkeypatch.setattr(cfg, "require_keyword_match", False)
    monkeypatch.setattr(cfg, "glints_min_salary", 0)
    monkeypatch.setattr(cfg, "delay_between_apply", 0)

    kartu = glints_module.rapikan_kartu(kartu_glints("x"))
    kartu["has_logo"] = False

    class BotPalsu:
        def __init__(self):
            self.filters = glints_module.JobFilter()
            self.dilamar = []

        def init_browser(self):
            return True

        def login(self):
            return True

        def cari(self, keyword, nomor=0, location=""):
            return [dict(kartu)] if nomor == 0 else []

        def lamar(self, job):
            from auto_apply import ApplyResult

            self.dilamar.append(job["job_id"])
            return ApplyResult(True, "applied", "Terkirim")

        def tutup(self):
            return None

    monkeypatch.setattr(glints_module, "GlintsBot", BotPalsu)
    monkeypatch.setattr(glints_module.notifier, "send_apply_success", lambda job: None)
    monkeypatch.setattr(glints_module.notifier, "send_daily_report", lambda s: None)
    monkeypatch.setattr(glints_module.time, "sleep", lambda *_: None)

    laporan = glints_module.jalankan_glints()

    assert laporan["dilamar"] == 0
    assert laporan["dilewati"] == 1
    keluaran = " ".join(capsys.readouterr().out.lower().split())
    assert "logo" in keluaran
