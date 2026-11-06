"""JobStreet, Glints, dan Indeed wajib memakai aturan Apply yang identik.

Yang dikunci di sini:
- satu fungsi kelayakan (`job_filter.alasan_tidak_layak`) untuk ketiga situs,
- tidak ada kriteria tambahan khusus Glints/Indeed (gaji Glints, lokasi wajib),
- logo/gambar perusahaan tidak pernah menjadi alasan melewati lowongan,
- batas 5 halaman riset & urutan ranking sama,
- modul kuota yang sama.
"""

import glints
import indeed
import job_filter
import kuota
import main
from config import config


def _job(**ubah):
    job = {
        "job_id": "glints:11111111-2222-3333-4444-555555555555",
        "title": "Staff Gudang",
        "company": "PT Contoh Nusantara",
        "location": "Bandung",
        "salary": "Rp 6-7jt",
        "description": "",
        "url": "https://glints.com/id/opportunities/jobs/staff-gudang/1111",
        # Bawaan: kartu berlogo. Kasus tanpa logo diuji khusus di bawah.
        "has_logo": True,
        "sudah_dilamar": False,
        "khusus_aplikasi": False,
    }
    job.update(ubah)
    return job


def _alasan_semua(job):
    return {
        "jobstreet": job_filter.alasan_tidak_layak(dict(job)),
        "glints": glints.alasan_tidak_layak(dict(job)),
        "indeed": indeed.alasan_tidak_layak(dict(job)),
    }


# ------------------------------------------------------- satu aturan ------
def test_glints_dan_indeed_memakai_fungsi_kelayakan_yang_sama():
    """Keduanya hanya meneruskan ke `job_filter.alasan_tidak_layak`."""
    import inspect

    for modul in (glints, indeed):
        kode = inspect.getsource(modul.alasan_tidak_layak)
        assert "alasan_standar(" in kode
        assert "should_apply" not in kode


def test_alasan_identik_untuk_input_yang_sama(monkeypatch):
    monkeypatch.setattr(config, "locations", ["Bandung"], raising=False)
    monkeypatch.setattr(config, "strict_location", False, raising=False)
    monkeypatch.setattr(config, "min_salary", 0, raising=False)
    monkeypatch.setattr(config, "max_age_days", 0, raising=False)
    monkeypatch.setattr(config, "require_keyword_match", True, raising=False)
    monkeypatch.setattr(
        config, "title_keywords", ["gudang", "inventory"], raising=False
    )
    monkeypatch.setattr(config, "blocked_companies", [], raising=False)
    monkeypatch.setattr(config, "blacklist_companies", [], raising=False)
    monkeypatch.setattr(config, "max_experience", 5, raising=False)

    kasus = [
        _job(),                                    # layak
        _job(title="Sales Executive"),             # judul tidak sesuai minat
        _job(company="PT Royal Abadi"),            # blacklist
        _job(title="Senior Staff Gudang"),         # terlalu senior
        _job(age_days=90),                         # umur lowongan
        _job(salary="Rp 1jt"),                     # gaji rendah (MIN_SALARY=0)
        _job(location="Surabaya"),                 # lokasi luar daftar
        _job(has_logo=False),                      # tanpa gambar/logo
    ]

    for job in kasus:
        hasil = _alasan_semua(job)
        assert len(set(hasil.values())) == 1, (job, hasil)


def test_salary_dan_lokasi_ketat_berlaku_sama_di_tiga_situs(monkeypatch):
    monkeypatch.setattr(config, "min_salary", 5_000_000, raising=False)
    monkeypatch.setattr(config, "strict_location", True, raising=False)
    monkeypatch.setattr(config, "locations", ["Bandung"], raising=False)
    monkeypatch.setattr(config, "require_keyword_match", False, raising=False)
    monkeypatch.setattr(config, "max_age_days", 0, raising=False)
    monkeypatch.setattr(config, "max_experience", 10, raising=False)
    monkeypatch.setattr(config, "blocked_companies", [], raising=False)
    monkeypatch.setattr(config, "blacklist_companies", [], raising=False)

    gaji_kecil = _alasan_semua(_job(salary="Rp 2jt"))
    lokasi_lain = _alasan_semua(_job(location="Surabaya"))

    assert set(gaji_kecil.values()) == {
        "Salary terlalu rendah: 2,000,000"
    }, gaji_kecil
    assert len(set(lokasi_lain.values())) == 1
    assert "Lokasi di luar daftar" in lokasi_lain["glints"]


# ------------------------------------------- tanpa aturan tambahan -------
def test_gaji_minimal_glints_tidak_lagi_dipakai(monkeypatch):
    """Batas gaji lama (GLINTS_MIN_SALARY) tidak boleh menolak lowongan."""
    monkeypatch.setattr(config, "min_salary", 0, raising=False)
    monkeypatch.setattr(config, "glints_min_salary", 9_000_000, raising=False)
    monkeypatch.setattr(config, "require_keyword_match", False, raising=False)
    monkeypatch.setattr(config, "strict_location", False, raising=False)
    monkeypatch.setattr(config, "max_age_days", 0, raising=False)

    job = _job(salary="Rp 4-5jt")

    assert _alasan_semua(job) == {
        "jobstreet": "", "glints": "", "indeed": "",
    }


def test_aturan_logo_jobstreet_dan_glints_sama(monkeypatch):
    """Logo wajib di JobStreet & Glints; Indeed dikecualikan (pasal 6.1)."""
    monkeypatch.setattr(config, "require_company_logo", True, raising=False)
    monkeypatch.setattr(config, "require_keyword_match", False, raising=False)
    monkeypatch.setattr(config, "strict_location", False, raising=False)
    monkeypatch.setattr(config, "min_salary", 0, raising=False)

    tanpa_gambar = _job(has_logo=False)
    hasil = _alasan_semua(tanpa_gambar)
    assert "logo" in hasil["jobstreet"].lower()
    assert "logo" in hasil["glints"].lower()

    # Kartu Indeed asli membawa penanda logo_diabaikan dari rapikan_kartu().
    kartu_indeed = dict(tanpa_gambar, logo_diabaikan=True)
    assert indeed.alasan_tidak_layak(kartu_indeed) == ""

    berlogo = _job(has_logo=True)
    assert _alasan_semua(berlogo) == {
        "jobstreet": "", "glints": "", "indeed": "",
    }


def test_khusus_aplikasi_glints_bukan_alasan_tolak(monkeypatch):
    """Lowongan "hanya via aplikasi" diperlakukan perlu manual, bukan dilewati."""
    monkeypatch.setattr(config, "require_keyword_match", False, raising=False)
    monkeypatch.setattr(config, "strict_location", False, raising=False)
    monkeypatch.setattr(config, "min_salary", 0, raising=False)

    assert glints.alasan_tidak_layak(_job(khusus_aplikasi=True)) == ""


# ------------------------------------------------- riset & peringkat ------
def test_batas_halaman_riset_sama_tiga():
    for nilai in (1, 3, 99):
        harapan = min(nilai, 3)
        assert glints.halaman_per_kata_kunci(nilai) == harapan
        assert indeed.batas_halaman_riset(nilai) == harapan


def test_peringkat_memakai_fungsi_yang_sama():
    kandidat = [
        _job(job_id="a", title="Inventory Staff", age_days=1),
        _job(job_id="b", title="Staff Gudang", age_days=10),
        _job(job_id="c", title="Warehouse Admin", age_days=2),
    ]

    harapan = [job["job_id"] for job in job_filter.job_filter.rank_jobs(
        [dict(job) for job in kandidat], prefer_newest=False
    )]

    assert [job["job_id"] for job in glints.pilih_teratas(
        [dict(job) for job in kandidat]
    )] == harapan
    assert [job["job_id"] for job in indeed.pilih_teratas(
        [dict(job) for job in kandidat]
    )] == harapan


# -------------------------------------------------------------- kuota -----
def test_satu_modul_kuota_untuk_tiga_situs():
    assert glints.kuota is kuota
    assert indeed.kuota is kuota
    assert main.kuota is kuota


def test_batas_harian_dibaca_oleh_tiga_situs(monkeypatch):
    monkeypatch.setattr(config, "max_apply_per_day", 7, raising=False)

    assert kuota.batas() == 7
    assert kuota.batas(config) == 7


def test_batas_per_sesi_dan_jeda_sama():
    """Ketiga sesi membaca setelan yang sama, tanpa nilai khusus per situs."""
    import inspect

    for modul in (main, glints, indeed):
        kode = inspect.getsource(modul)
        assert "auto_apply_max_per_session" in kode
        assert "delay_between_apply" in kode
