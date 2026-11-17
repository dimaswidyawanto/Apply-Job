from pathlib import Path

import pytest

import job_filter as job_filter_module
from config import config
from database import Database
from job_filter import JobFilter


@pytest.fixture
def filter_baru(tmp_path, monkeypatch):
    """JobFilter dengan database kosong supaya hasil test deterministik."""
    database = Database(str(tmp_path / "filter.db"))
    monkeypatch.setattr(job_filter_module, "db", database)
    return JobFilter()


def make_job(**overrides):
    job = {
        "job_id": "123",
        "title": "Inventory Control",
        "company": "PT Contoh",
        "location": "Bandung, West Java",
        "salary": "Rp 8.000.000 per month",
        "description": "Mengelola stok gudang.",
        "url": "https://id.jobstreet.com/job/123",
        "date_posted": "Hari ini",
    }
    job.update(overrides)
    return job


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Rp 7.000.000 – Rp 10.500.000 per month", 7_000_000),
        ("Rp 8.000.000", 8_000_000),
        ("8500000", 8_500_000),
        ("Rp 5 juta", 5_000_000),
        ("7,5 juta", 7_500_000),
        ("Rp 900 ribu", 900_000),
        ("Tidak disebutkan", 0),
        ("", 0),
    ],
)
def test_parse_salary(filter_baru, text, expected):
    assert filter_baru._parse_salary(text) == expected


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Minimal 3 tahun pengalaman", 3),
        ("5+ years of experience required", 5),
        ("2-4 tahun", 2),
        ("Tanpa pengalaman", None),
    ],
)
def test_extract_experience(filter_baru, text, expected):
    assert filter_baru._extract_experience(text) == expected


def test_lolos_untuk_lowongan_biasa(filter_baru):
    lolos, alasan = filter_baru.should_apply(make_job())
    assert lolos is True
    assert alasan == "OK"


def test_tolak_judul_kosong(filter_baru):
    lolos, alasan = filter_baru.should_apply(make_job(title="   "))
    assert lolos is False
    assert "judul" in alasan.lower()


def test_tolak_kata_kunci_terlarang(filter_baru):
    lolos, alasan = filter_baru.should_apply(
        make_job(title="Senior Inventory Control")
    )
    assert lolos is False
    assert "senior" in alasan.lower() or "excluded" in alasan.lower()


def test_tolak_perusahaan_blacklist(filter_baru, tmp_path):
    job_filter_module.db.add_blacklist("PT Contoh", "tidak sesuai")
    lolos, alasan = filter_baru.should_apply(make_job())
    assert lolos is False
    assert "blacklist" in alasan.lower()


def test_tolak_job_yang_sudah_dilamar(filter_baru):
    job_filter_module.db.record_application("123", "applied")
    lolos, alasan = filter_baru.should_apply(make_job())
    assert lolos is False
    assert "sudah" in alasan.lower()


def test_tolak_pengalaman_berlebih(filter_baru, monkeypatch):
    monkeypatch.setattr(config, "max_experience", 5)
    lolos, alasan = filter_baru.should_apply(
        make_job(description="Minimal 8 tahun pengalaman di bidang PPIC.")
    )
    assert lolos is False
    assert "pengalaman" in alasan.lower() or "experience" in alasan.lower()


def test_tolak_gaji_di_bawah_minimum(filter_baru, monkeypatch):
    monkeypatch.setattr(config, "min_salary", 5_000_000)
    lolos, alasan = filter_baru.should_apply(
        make_job(salary="Rp 3.000.000 per month")
    )
    assert lolos is False
    assert "salary" in alasan.lower() or "gaji" in alasan.lower()


def test_strict_location(filter_baru, monkeypatch):
    monkeypatch.setattr(config, "strict_location", True)
    monkeypatch.setattr(config, "location", "Bandung")
    monkeypatch.setattr(config, "locations", ["Bandung"])

    lolos, alasan = filter_baru.should_apply(
        make_job(location="Jakarta Selatan")
    )
    assert lolos is False
    assert "lokasi" in alasan.lower()

    lolos, _ = filter_baru.should_apply(make_job(location="Cimahi, Bandung"))
    assert lolos is True


def test_job_tanpa_job_id_tidak_error(filter_baru):
    job = make_job()
    job.pop("job_id")
    assert filter_baru.should_apply(job)[0] is True


def test_rank_jobs_aman_untuk_salary_none(filter_baru):
    jobs = [
        make_job(job_id="1", salary=None),
        make_job(job_id="2", salary="Rp 9.000.000"),
    ]
    hasil = filter_baru.rank_jobs(jobs)

    assert len(hasil) == 2
    assert hasil[0]["salary"] == "Rp 9.000.000"


def test_tolak_lowongan_terlalu_lama(filter_baru, monkeypatch):
    monkeypatch.setattr(config, "max_age_days", 3)

    lolos, alasan = filter_baru.should_apply(make_job(age_days=5))
    assert lolos is False
    # Alasan kini menyebut umur lowongan DAN batasnya (audit #26).
    assert "5 hari" in alasan
    assert "MAX_AGE_DAYS=3" in alasan

    assert filter_baru.should_apply(make_job(age_days=1))[0] is True
    # Umur tidak diketahui -> jangan dibuang.
    assert filter_baru.should_apply(make_job(age_days=None))[0] is True


def test_rank_jobs_utamakan_yang_terbaru(filter_baru):
    jobs = [
        make_job(job_id="1", title="Inventory Control", age_days=6),
        make_job(job_id="2", title="Stok Controller", age_days=0),
        make_job(job_id="3", title="PPIC", age_days=None),
    ]

    hasil = filter_baru.rank_jobs(jobs, prefer_newest=True)

    assert [job["job_id"] for job in hasil] == ["2", "1", "3"]


def test_rank_jobs_mode_skor(filter_baru):
    jobs = [
        make_job(job_id="1", title="Stok Controller", age_days=0),
        make_job(job_id="2", title="Inventory Control", age_days=9),
    ]

    hasil = filter_baru.rank_jobs(jobs, prefer_newest=False)

    # Judul yang persis cocok dengan kata kunci mendapat skor lebih tinggi.
    assert hasil[0]["job_id"] == "2"


def test_tolak_judul_di_luar_minat(filter_baru):
    lolos, alasan = filter_baru.should_apply(
        make_job(title="Marketing Communication Staff")
    )
    assert lolos is False
    assert "minat" in alasan.lower()


@pytest.mark.parametrize(
    "judul",
    [
        "Inventory Control Staff",
        "Inventory Controller",
        "Staff PPIC",
        "Production Planner",
        "Material Planner",
        "Stock Controller",
        "Inventory Analyst",
    ],
)
def test_judul_sesuai_minat_diterima(filter_baru, judul):
    assert filter_baru.should_apply(make_job(title=judul))[0] is True


def test_filter_judul_bisa_dimatikan(filter_baru, monkeypatch):
    monkeypatch.setattr(config, "require_keyword_match", False)

    assert filter_baru.should_apply(
        make_job(title="Marketing Communication Staff")
    )[0] is True


def test_kata_kunci_judul_bisa_ditambah(filter_baru, monkeypatch):
    monkeypatch.setattr(config, "title_keywords", ["inventory control", "gudang"])

    assert filter_baru.should_apply(make_job(title="Staff Gudang"))[0] is True
    assert filter_baru.should_apply(make_job(title="Staff PPIC"))[0] is False


ROOT = Path(__file__).resolve().parent.parent


def _kata_kunci_judul() -> list:
    """Daftar TITLE_KEYWORDS bawaan, dibaca dari .env.example."""
    from env_tools import baca_baku

    isi = baca_baku((ROOT / ".env.example").read_text(encoding="utf-8"))
    return [
        item.strip()
        for item in isi.get("TITLE_KEYWORDS", "").split(",")
        if item.strip()
    ]


@pytest.mark.parametrize(
    "judul",
    [
        "Inventory Control Staff",
        "Staf Inventory",
        "Stock Controller",
        "Staf Gudang",
        "Admin Gudang",
        "Warehouse Supervisor",
        "Staff PPIC",
        "Production Planning & Inventory Control",
        "Production Planner",
        "Staf Produksi",
        "Material Control Staff",
        "Material Planner",
        "Purchasing Staff",
        "Procurement Officer",
        "Supply Chain Staff",
        "Logistik Staff",
        "Demand Planner",
        "Inventory Analyst",
        "Project Control",
    ],
)
def test_judul_sesuai_pengalaman_cv_lolos(monkeypatch, judul):
    monkeypatch.setattr(config, "title_keywords", _kata_kunci_judul())

    assert JobFilter._matches_interest(judul.lower()) is True


@pytest.mark.parametrize(
    "judul",
    [
        "Staff Accounting",
        "Sales Executive",
        "Operator Produksi",
        "Financial Planner",
        "Media Buyer",
        "Quantity Surveyor",
        "Income Auditor",
        "IT Support & Asset Management",
    ],
)
def test_judul_di_luar_pengalaman_cv_tetap_ditolak(monkeypatch, judul):
    monkeypatch.setattr(config, "title_keywords", _kata_kunci_judul())

    assert JobFilter._matches_interest(judul.lower()) is False


@pytest.mark.parametrize(
    "company",
    [
        "PT Royal Abadi Sejahtera",
        "PT. ROYAL ABADI SEJAHTERA",
        "Royal Abadi Sejahtera",
        "PT Royal Abadi",
    ],
)
def test_blacklist_cocok_longgar(filter_baru, monkeypatch, company):
    monkeypatch.setattr(
        config, "blacklist_companies", ["royal abadi"]
    )

    lolos, alasan = filter_baru.should_apply(make_job(company=company))

    assert lolos is False
    assert "blacklist" in alasan.lower()


def test_blacklist_tidak_menolak_perusahaan_lain(filter_baru, monkeypatch):
    monkeypatch.setattr(config, "blacklist_companies", ["royal abadi"])

    lolos, _ = filter_baru.should_apply(
        make_job(company="PT Sinar Abadi Nusantara")
    )

    assert lolos is True


def test_blacklist_dari_daftar_tersimpan(filter_baru, monkeypatch):
    monkeypatch.setattr(config, "blacklist_companies", [])
    filter_baru.__class__  # noqa: B018 - hanya memastikan filter siap
    job_filter_module.db.add_blacklist("Royal Abadi", "mantan perusahaan")

    lolos, alasan = filter_baru.should_apply(
        make_job(company="PT Royal Abadi Sejahtera")
    )

    assert lolos is False
    assert "blacklist" in alasan.lower()


# ----------------------------------------------------------------------
# Rentang gaji (dipakai aturan minimal gaji Glints)
# ----------------------------------------------------------------------
@pytest.mark.parametrize(
    "teks, expected",
    [
        ("Rp 2-3jt", (2_000_000, 3_000_000)),
        ("Rp 4-4,5jt", (4_000_000, 4_500_000)),
        ("Rp 4,2jt", (4_200_000, 4_200_000)),
        ("Rp 5jt", (5_000_000, 5_000_000)),
        ("Rp2.000.000 - 3.000.000/Bulan", (2_000_000, 3_000_000)),
        ("Rp 4.500.000 - 6.000.000", (4_500_000, 6_000_000)),
        ("Rp 1-2,5jt", (1_000_000, 2_500_000)),
        ("Gaji Tidak Ditampilkan", (0, 0)),
        ("", (0, 0)),
    ],
)
def test_rentang_gaji(teks, expected):
    assert job_filter_module.rentang_gaji(teks) == expected


# ----------------------------------------------------------------------
# Perusahaan yang selalu ditolak
# ----------------------------------------------------------------------
@pytest.mark.parametrize(
    "company",
    [
        "PT IFA Indonesia",
        "IFA",
        "PT IFA",
        "ifa group",
        "PT Royal Abadi Sejahtera",
        "ROYAL ABADI",
    ],
)
def test_blocked_companies_selalu_ditolak(filter_baru, monkeypatch, company):
    monkeypatch.setattr(config, "blacklist_companies", [])
    monkeypatch.setattr(config, "blocked_companies", ["royal abadi", "ifa"])

    lolos, alasan = filter_baru.should_apply(make_job(company=company))

    assert lolos is False
    assert "blacklist" in alasan.lower()


@pytest.mark.parametrize(
    "company",
    ["PT Kafifa Nusantara", "PT Sinar Abadi Nusantara", "PT Ifana Jaya"],
)
def test_blocked_companies_tidak_menolak_nama_mirip(
    filter_baru, monkeypatch, company
):
    monkeypatch.setattr(config, "blacklist_companies", [])
    monkeypatch.setattr(config, "blocked_companies", ["royal abadi", "ifa"])

    lolos, _ = filter_baru.should_apply(make_job(company=company))

    assert lolos is True
