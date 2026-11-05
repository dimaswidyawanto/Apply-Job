"""Alur riset: halaman 1–5 per kombinasi → gabung → dedup → skor → TOP 50.

Pengguna meminta riset dibatasi **5 halaman untuk setiap kombinasi kata
kunci × lokasi** (halaman 6 tidak pernah dibuka), sedangkan 50 hanya batas
LAMARAN per hari. Penilaian mencakup seluruh kategori dan seluruh lokasi
yang ditentukan. Berkas ini menguji alur tersebut di mesin JobStreet dan
aturan skor yang dipakai bersama oleh JobStreet & Glints.
"""

from types import SimpleNamespace

import pytest

import job_filter as job_filter_module
import main as main_module
from config import config
from database import Database


class BotPalsu:
    def __init__(self, halaman):
        self.halaman = halaman
        self.dilamar = []
        self.halaman_dicari = []

    def search_jobs(self, keyword, page=1, location=""):
        self.halaman_dicari.append((location, keyword, page))
        return list(self.halaman.get((location, keyword, page), []))

    def apply_job(self, job):
        self.dilamar.append(job["job_id"])
        return SimpleNamespace(
            applied=True, status="applied", reason="Terkirim otomatis"
        )


def lowongan(job_id, title="Inventory Staff", age_days=0, lokasi="Bandung",
             salary="Rp 6.000.000", deskripsi="", url=None):
    return {
        "job_id": str(job_id),
        "title": title,
        "company": "PT Contoh",
        "location": lokasi,
        "salary": salary,
        "description": deskripsi,
        "url": url or f"https://id.jobstreet.com/job/{job_id}",
        "date_posted": "Hari ini",
        "age_days": age_days,
    }


@pytest.fixture
def siapkan(tmp_path, monkeypatch):
    database = Database(str(tmp_path / "riset.db"))
    monkeypatch.setattr(main_module, "db", database)
    monkeypatch.setattr(job_filter_module, "db", database)

    monkeypatch.setattr(config, "locations", ["Bandung", "Jakarta"])
    monkeypatch.setattr(config, "keywords", ["inventory", "ppic"])
    monkeypatch.setattr(config, "research_keywords", [])
    monkeypatch.setattr(config, "max_pages", 1)
    monkeypatch.setattr(config, "research_max_pages", 5)
    monkeypatch.setattr(config, "research_max_jobs", 0)
    monkeypatch.setattr(config, "auto_apply", True)
    monkeypatch.setattr(config, "collect_before_apply", True)
    monkeypatch.setattr(config, "require_keyword_match", False)
    monkeypatch.setattr(config, "require_company_logo", False)
    monkeypatch.setattr(config, "max_age_days", 0)
    monkeypatch.setattr(config, "min_salary", 0)
    monkeypatch.setattr(config, "blacklist_companies", [])
    monkeypatch.setattr(config, "blocked_companies", [])
    monkeypatch.setattr(config, "max_apply_per_day", 0)
    monkeypatch.setattr(config, "auto_apply_max_per_session", 0)
    monkeypatch.setattr(config, "delay_between_apply", 0)
    monkeypatch.setattr(config, "sort_mode", "ListedDate")
    monkeypatch.setattr(config, "rank_by", "relevance")
    monkeypatch.setattr(main_module.notifier, "send_apply_success", lambda *_: None)
    monkeypatch.setattr(main_module.notifier, "send_error", lambda *_: None)

    mesin = main_module.AutoApplyEngine()
    return mesin, database


def test_riset_halaman_1_sampai_5_lalu_berhenti(siapkan):
    """Halaman 1–5 diproses; halaman 6 tidak pernah dibuka."""
    mesin, _ = siapkan
    mesin.bot = BotPalsu({
        ("Bandung", "inventory", 1): [lowongan("p1")],
        ("Bandung", "inventory", 2): [lowongan("p2", age_days=1)],
        ("Bandung", "inventory", 3): [lowongan("p3", age_days=2)],
        ("Bandung", "inventory", 4): [lowongan("p4", age_days=3)],
        ("Bandung", "inventory", 5): [lowongan("p5", age_days=4)],
        # Kalau sistem salah lanjut ke halaman 6, P6 akan ikut dilamar.
        ("Bandung", "inventory", 6): [lowongan("P6", age_days=5)],
    })

    mesin._kumpulkan_lalu_lamar()

    assert sorted(mesin.bot.dilamar) == ["p1", "p2", "p3", "p4", "p5"]
    assert ("Bandung", "inventory", 6) not in mesin.bot.halaman_dicari


def test_batas_5_halaman_independen_per_kombinasi(siapkan):
    """Setiap kata kunci × lokasi punya jatah 5 halaman sendiri."""
    mesin, _ = siapkan
    halaman = {}
    for lokasi in ("Bandung", "Jakarta"):
        for keyword in ("inventory", "ppic"):
            for page in range(1, 6):
                halaman[(lokasi, keyword, page)] = [
                    lowongan(f"{lokasi[:1]}-{keyword}-{page}", age_days=page)
                ]

    mesin.bot = BotPalsu(halaman)

    mesin._kumpulkan_lalu_lamar()

    assert len(mesin.bot.dilamar) == 20
    for lokasi in ("Bandung", "Jakarta"):
        for keyword in ("inventory", "ppic"):
            assert (lokasi, keyword, 5) in mesin.bot.halaman_dicari
            assert (lokasi, keyword, 6) not in mesin.bot.halaman_dicari


def test_permintaan_halaman_besar_tetap_dipotong_ke_5(siapkan):
    """Meski diminta 20 halaman, halaman 6 tidak boleh dibuka."""
    mesin, _ = siapkan
    mesin.bot = BotPalsu({
        ("Bandung", "inventory", page): [lowongan(f"p{page}", age_days=page)]
        for page in range(1, 8)
    })

    hasil = mesin._cari_keyword("inventory", "Bandung", halaman_maks=20)

    assert len(hasil) == 5
    assert ("Bandung", "inventory", 6) not in mesin.bot.halaman_dicari


def test_batas_halaman_riset_dari_config():
    from config import batas_halaman_riset

    assert batas_halaman_riset(0) == 5
    assert batas_halaman_riset(20) == 5
    assert batas_halaman_riset(3) == 3
    assert batas_halaman_riset("2") == 2
    assert batas_halaman_riset("bukan angka") == 5
    assert batas_halaman_riset(-4) == 5


def test_riset_boleh_dibatasi_lebih_kecil(siapkan, monkeypatch):
    """RESEARCH_MAX_PAGES=1 -> hanya halaman 1 yang dibuka."""
    mesin, _ = siapkan
    monkeypatch.setattr(config, "research_max_pages", 1)
    mesin.bot = BotPalsu({
        ("Bandung", "inventory", 1): [lowongan("A")],
        ("Bandung", "inventory", 2): [lowongan("B", age_days=1)],
    })

    mesin._kumpulkan_lalu_lamar()

    assert mesin.bot.dilamar == ["A"]


def test_riset_membuang_duplikat(siapkan):
    """Lowongan sama dari kata kunci/lokasi berbeda hanya dilamar sekali."""
    mesin, _ = siapkan
    sama = lowongan("X")
    mesin.bot = BotPalsu({
        ("Bandung", "inventory", 1): [sama],
        ("Bandung", "ppic", 1): [dict(sama)],
        ("Jakarta", "inventory", 1): [dict(sama), lowongan("Y")],
    })

    mesin._kumpulkan_lalu_lamar()

    assert mesin.bot.dilamar.count("X") == 1
    assert "Y" in mesin.bot.dilamar


def test_riset_memakai_kata_kunci_khusus(siapkan, monkeypatch):
    mesin, _ = siapkan
    monkeypatch.setattr(config, "research_keywords", ["logistik", "gudang"])
    mesin.bot = BotPalsu({
        ("Bandung", "logistik", 1): [lowongan("L")],
        ("Bandung", "gudang", 1): [lowongan("G")],
        ("Bandung", "inventory", 1): [lowongan("I")],
    })

    mesin._kumpulkan_lalu_lamar()

    assert sorted(mesin.bot.dilamar) == ["G", "L"]


def test_top_50_global_dari_semua_kategori_dan_lokasi(siapkan, monkeypatch):
    """60 kandidat -> hanya 50 terbaik yang dilamar, lintas lokasi."""
    mesin, _ = siapkan
    monkeypatch.setattr(config, "max_apply_per_day", 50)

    # 10 kandidat terbaik: judul persis cocok dengan kata kunci + gaji tinggi.
    terbaik = [
        lowongan(f"baik-{n}", title="Inventory Control", lokasi="Bandung")
        for n in range(10)
    ]
    # 50 kandidat lain: judul masih satu bidang, skor lebih rendah.
    biasa = [
        lowongan(f"biasa-{n}", title="Staf Gudang", lokasi="Jakarta",
                 age_days=5)
        for n in range(50)
    ]

    mesin.bot = BotPalsu({
        ("Bandung", "inventory", 1): terbaik,
        ("Jakarta", "ppic", 1): biasa,
    })

    mesin._kumpulkan_lalu_lamar()

    assert len(mesin.bot.dilamar) == 50
    assert set(f"baik-{n}" for n in range(10)) <= set(mesin.bot.dilamar)


def test_kurang_dari_50_dilamar_semua(siapkan, monkeypatch):
    mesin, _ = siapkan
    monkeypatch.setattr(config, "max_apply_per_day", 50)
    mesin.bot = BotPalsu({("Bandung", "inventory", 1): [
        lowongan("A"), lowongan("B", age_days=2), lowongan("C"),
    ]})

    mesin._kumpulkan_lalu_lamar()

    assert len(mesin.bot.dilamar) == 3


def test_research_max_jobs_menghentikan_riset(siapkan, monkeypatch):
    mesin, _ = siapkan
    monkeypatch.setattr(config, "research_max_jobs", 2)
    mesin.bot = BotPalsu({
        ("Bandung", "inventory", 1): [lowongan("A"), lowongan("B"),
                                      lowongan("C")],
    })

    kandidat = mesin._riset_lowongan()

    assert len(kandidat) == 2


def test_skor_multi_dimensi_menjumlah_ke_score():
    jobs = [
        lowongan(
            "1",
            title="Inventory Control",
            deskripsi=(
                "Minimal S1, pengalaman 2 tahun, menguasai SAP dan Excel, "
                "bertanggung jawab atas stock opname dan cycle count"
            ),
        ),
        lowongan("2", title="Staf Gudang", lokasi="Surabaya", age_days=9,
                 salary=""),
    ]

    hasil = job_filter_module.job_filter.rank_jobs(jobs, prefer_newest=False)

    for job in hasil:
        rincian = job["_skor_rincian"]
        assert set(rincian) == {
            "posisi", "lokasi", "kualifikasi", "pengalaman", "pendidikan",
            "keterampilan", "tanggal", "gaji",
        }
        assert sum(rincian.values()) == job["_score"]

    # Lowongan yang cocok di semua dimensi menang, walaupun lebih tua.
    assert hasil[0]["job_id"] == "1"
    assert hasil[0]["_skor_rincian"]["keterampilan"] > 0
    assert hasil[0]["_skor_rincian"]["pendidikan"] > 0


def test_tanggal_terbaru_dapat_skor_lebih_tinggi():
    baru = lowongan("baru", age_days=0)
    lama = lowongan("lama", age_days=9)

    rincian_baru = job_filter_module.job_filter.score_breakdown(baru)
    rincian_lama = job_filter_module.job_filter.score_breakdown(lama)

    assert rincian_baru["tanggal"] > rincian_lama["tanggal"]


def test_lokasi_di_luar_daftar_tidak_dapat_poin_lokasi(monkeypatch):
    monkeypatch.setattr(config, "locations", ["Bandung"])
    cocok = lowongan("cocok", lokasi="Bandung")
    luar = lowongan("luar", lokasi="Surabaya")

    rincian_cocok = job_filter_module.job_filter.score_breakdown(cocok)
    rincian_luar = job_filter_module.job_filter.score_breakdown(luar)

    assert rincian_cocok["lokasi"] > rincian_luar["lokasi"]


def test_dedupe_jobs_menggabungkan_data_yang_kurang():
    pertama = lowongan("A", salary="")
    kedua = dict(lowongan("A"), salary="Rp 7.000.000")

    hasil = job_filter_module.dedupe_jobs([pertama, kedua])

    assert len(hasil) == 1
    assert hasil[0]["salary"] == "Rp 7.000.000"


def test_duplikat_dihitung_untuk_laporan_riset(siapkan):
    """Duplikat yang muncul dari kata kunci/lokasi lain tetap dihitung."""
    mesin, _ = siapkan
    sama = lowongan("X")
    mesin.bot = BotPalsu({
        ("Bandung", "inventory", 1): [sama],
        ("Jakarta", "ppic", 1): [dict(sama)],
    })

    mesin._kumpulkan_lalu_lamar()

    assert mesin.duplikat_dilewati == 1
    assert mesin.bot.dilamar == ["X"]


def test_glints_dibatasi_5_muat_per_kata_kunci(monkeypatch):
    """Aturan Glints = JobStreet: maksimal 5 muat, tidak bisa dinaikkan."""
    import glints as glints_module

    monkeypatch.setattr(config, "research_max_pages", 0)

    assert glints_module.BATAS_MUAT_GLINTS == 5
    assert glints_module.halaman_per_kata_kunci(0) == 5
    assert glints_module.halaman_per_kata_kunci(20) == 5
    assert glints_module.halaman_per_kata_kunci(2) == 2

    diminta = []

    class BotGlintsPalsu:
        def cari(self, keyword, nomor=0):
            diminta.append(nomor)
            return [lowongan(f"{keyword}-{nomor}")]

    glints_module.kumpulkan_lowongan(
        BotGlintsPalsu(),
        ["inventory"],
        glints_module.halaman_per_kata_kunci(0),
    )

    # 5 muat -> cari(nomor=4), bukan nomor 5 atau 19.
    assert diminta == [4]


def test_pengukuran_waktu_dan_kemajuan_riset(siapkan):
    """Riset mencatat jumlah kombinasi, halaman, dan durasinya."""
    mesin, _ = siapkan
    mesin.bot = BotPalsu({
        ("Bandung", "inventory", 1): [lowongan("A")],
    })

    mesin._kumpulkan_lalu_lamar()

    # 2 kata kunci × 2 lokasi.
    assert mesin.riset_total == 4
    assert mesin.riset_selesai == 4
    assert mesin.jumlah_halaman >= 4
    assert mesin.durasi_riset >= 0

    assert mesin._durasi(0) == "0s"
    assert mesin._durasi(65) == "1m 05s"
    assert mesin._durasi(3725) == "1j 02m 05s"


def test_search_wait_dipakai_untuk_menunggu_kartu():
    """SEARCH_WAIT mempercepat halaman kosong (bawaan 12 detik)."""
    from config import Config, batas_halaman_riset

    assert Config().search_wait >= 3
    assert batas_halaman_riset(Config().research_max_pages) == 5
