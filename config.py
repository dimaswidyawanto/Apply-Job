"""Pembacaan konfigurasi dari file .env.

Semua nilai punya default yang aman sehingga program tetap berjalan
walaupun file .env belum dibuat.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# Path absolut supaya .env dan database tetap ditemukan walaupun program
# dijalankan dari folder lain (misalnya `python /path/ke/dimastes/cli.py`).
BASE_DIR = Path(__file__).resolve().parent

# Nilai default diambil dari .env.example lebih dulu, lalu .env menimpanya.
# Dengan begitu kunci baru pada versi terbaru tetap terpakai walau .env lama
# (dari versi sebelumnya) belum memuat kunci tersebut.
load_dotenv(BASE_DIR / ".env.example")
load_dotenv(BASE_DIR / ".env", override=True)


def _list_setting(name: str, default: str) -> list[str]:
    value = os.getenv(name, default) or default
    return [item.strip() for item in value.split(",") if item.strip()]


def _int_setting(name: str, default: int) -> int:
    try:
        return int(str(os.getenv(name, str(default))).strip())
    except (TypeError, ValueError):
        return default


def _float_setting(name: str, default: float) -> float:
    try:
        teks = str(os.getenv(name, str(default))).strip().replace(",", ".")
        return float(teks)
    except (TypeError, ValueError):
        return default


def _pilihan_setting(name: str, default: str, pilihan: tuple[str, ...]) -> str:
    """Nilai teks yang dibatasi pada daftar pilihan; salah ketik -> default."""
    nilai = str(os.getenv(name, default) or default).strip().lower()
    return nilai if nilai in pilihan else default


def _bool_setting(name: str, default: bool = False) -> bool:
    value = str(os.getenv(name, str(default))).strip().lower()
    return value in ("1", "true", "yes", "y", "ya")


# Minimal satu halaman supaya perulangan pencarian tidak kosong.
_MAX_PAGES = max(1, _int_setting("MAX_PAGES", 3))

# Riset JobStreet (dan Glints): MAKSIMAL 5 halaman untuk setiap kombinasi
# kata kunci × lokasi. Batas ini tidak bisa dinaikkan lewat .env — nilai 0
# atau lebih dari 5 tetap dipakai sebagai 5. Boleh diturunkan (mis. 2).
MAKS_HALAMAN_RISET = 5


def batas_halaman_riset(nilai) -> int:
    """Halaman riset per kombinasi kata kunci × lokasi: 1 sampai 5."""
    try:
        angka = int(nilai)
    except (TypeError, ValueError):
        return MAKS_HALAMAN_RISET

    if angka <= 0:
        return MAKS_HALAMAN_RISET

    return min(MAKS_HALAMAN_RISET, angka)


@dataclass
class Config:
    # Catatan: alat ini TIDAK pernah meminta/menyimpan email & password
    # JobStreet. Login dilakukan sendiri di Chrome dan sesinya disimpan
    # pada profil Chrome (USE_PROFILE).

    keywords: list[str] = field(default_factory=lambda: _list_setting(
        "KEYWORDS",
        "inventory control,inventory controller,inventory staff,"
        "stock controller,PPIC,production planning,production planner,"
        "material control,material planner,warehouse,staff gudang,"
        "purchasing,procurement,supply chain",
    ))
    # Lokasi utama (dipertahankan untuk kompatibilitas).
    location: str = os.getenv("LOCATION", "Bandung")

    # Daftar lokasi yang dicari. Bila kosong, dipakai LOCATION saja.
    locations: list[str] = field(default_factory=lambda: _list_setting(
        "LOCATIONS", ""
    ))

    # Ikut sertakan lowongan yang sepenuhnya remote.
    allow_remote: bool = _bool_setting("ALLOW_REMOTE", False)
    min_salary: int = _int_setting("MIN_SALARY", 0)
    max_experience: int = _int_setting("MAX_EXPERIENCE_YEARS", 5)
    exclude_keywords: list[str] = field(default_factory=lambda: _list_setting(
        "EXCLUDE_KEYWORDS",
        "principal,director,head,senior,lead"
    ))
    # Nama perusahaan yang tidak ingin dilamar lagi (mantan perusahaan,
    # dsb). Dicocokkan longgar: "royal abadi" juga menangkap
    # "PT Royal Abadi Sejahtera".
    blacklist_companies: list[str] = field(
        default_factory=lambda: _list_setting("BLACKLIST_COMPANIES", "")
    )

    # Perusahaan yang selalu ditolak (tidak perlu menambah manual di .env).
    # "ifa" dicocokkan per kata, jadi "Kafifa" tidak ikut tertolak.
    blocked_companies: list[str] = field(
        default_factory=lambda: _list_setting(
            "BLOCKED_COMPANIES", "royal abadi,ifa"
        )
    )

    # Glints: lamaran hanya dikirim bila gaji bisa mencapai angka ini.
    # Gaji yang tidak dicantumkan tetap dilamar (0 = tanpa batas).
    glints_min_salary: int = _int_setting("GLINTS_MIN_SALARY", 4_500_000)

    # Tolak lowongan yang lokasinya jelas di luar LOCATION.
    strict_location: bool = _bool_setting("STRICT_LOCATION", False)

    # JobStreet: lamar hanya lowongan yang kartunya menampilkan logo
    # perusahaan. Bawaan false agar perilaku lama tidak berubah.
    require_company_logo: bool = _bool_setting("REQUIRE_COMPANY_LOGO", False)

    # Bila ada kuesioner yang tidak bisa dijawab otomatis, beri kesempatan
    # mengisinya sendiri di jendela Chrome selama ini (detik). 0 = langsung
    # dilewati seperti sebelumnya.
    auto_answer_wait: int = _int_setting("AUTO_ANSWER_WAIT", 20)

    # Hanya lamar lowongan yang judulnya cocok dengan minat.
    require_keyword_match: bool = _bool_setting("REQUIRE_KEYWORD_MATCH", True)
    # Kata kunci untuk mencocokkan judul. Kosong = pakai KEYWORDS.
    # Daftar bawaan disusun dari pengalaman CV (PPIC/inventory, gudang,
    # material/pengadaan, supply chain) dan lebih lebar dari KEYWORDS karena
    # hanya dipakai saat mencocokkan judul, bukan saat mencari.
    title_keywords: list[str] = field(default_factory=lambda: _list_setting(
        "TITLE_KEYWORDS",
        "inventory,stock,stok,persediaan,gudang,warehouse,ppic,"
        "production planning,production planner,production control,"
        "production admin,admin produksi,staf produksi,staff produksi,"
        "perencanaan produksi,demand planning,demand planner,"
        "capacity planning,material control,material planner,"
        "material controller,material handling,material management,"
        "bahan baku,pengadaan,purchasing,procurement,pembelian,"
        "supply chain,rantai pasok,logistik,logistics,distribusi,"
        "distribution,inventory analyst,inventory admin,"
        "inventory officer,admin inventory,stock opname,mrp,"
        "cycle count,project control",
    ))

    # true  = riset dulu semua kandidat, dinilai & diperingkat, baru lamar
    #         (dipakai untuk memilih TOP 50 dari seluruh kategori & lokasi).
    # false = lamar sambil mencari, per halaman (halaman 1 = terbaru).
    # Saat MAX_APPLY_PER_DAY > 0, mode riset ini tetap dipakai otomatis
    # karena tanpa riset tidak ada yang bisa dibandingkan.
    collect_before_apply: bool = _bool_setting("COLLECT_BEFORE_APPLY", True)

    # Detik menunggu kartu lowongan muncul sebelum halaman dianggap kosong.
    # Makin kecil makin cepat, tetapi halaman yang lambat bisa terlewat.
    search_wait: int = max(3, _int_setting("SEARCH_WAIT", 12))

    # --- Riset lowongan (tidak dibatasi 50) ---
    # Kata kunci yang dipakai HANYA untuk riset/pencarian. Kosong = pakai
    # KEYWORDS. Daftar ini bisa lebih lebar dari KEYWORDS supaya seluruh
    # kategori pekerjaan ikut discan tanpa mengubah aturan pencocokan judul.
    research_keywords: list[str] = field(default_factory=lambda: _list_setting(
        "RESEARCH_KEYWORDS", ""
    ))
    # Halaman riset per kombinasi kata kunci × lokasi. Maksimal 5 (batas
    # tetap); 0 atau nilai di atas 5 otomatis dipakai sebagai 5.
    research_max_pages: int = batas_halaman_riset(
        _int_setting("RESEARCH_MAX_PAGES", MAKS_HALAMAN_RISET)
    )
    # 0 = tanpa batas jumlah lowongan hasil riset (pengaman opsional).
    research_max_jobs: int = max(0, _int_setting("RESEARCH_MAX_JOBS", 0))

    # Kata kunci keterampilan untuk menilai kesesuaian keterampilan pada
    # deskripsi kartu lowongan (satu poin per keterampilan yang disebut).
    skill_keywords: list[str] = field(default_factory=lambda: _list_setting(
        "SKILL_KEYWORDS",
        "inventory,stock,stok,persediaan,gudang,warehouse,ppic,mrp,sap,erp,"
        "wms,excel,spreadsheet,forecasting,forecast,demand planning,"
        "production planning,material control,supply chain,logistik,"
        "logistics,procurement,purchasing,pengadaan,stock opname,"
        "cycle count,lean,5s,iso 9001,negosiasi,negotiation,analisis,"
        "analysis,distribusi,distribution",
    ))

    # Urutan pemilihan saat mengumpulkan dulu (COLLECT_BEFORE_APPLY=true):
    #   relevance = yang paling cocok dengan minat didahulukan (bawaan)
    #   newest    = yang paling baru didahulukan
    rank_by: str = _pilihan_setting("RANK_BY", "relevance", ("relevance", "newest"))

    # Urutkan hasil pencarian dari yang paling baru (ListedDate).
    # Kosongkan SORT_MODE untuk kembali ke urutan relevansi JobStreet.
    sort_mode: str = os.getenv("SORT_MODE", "ListedDate").strip()
    prefer_newest: bool = _bool_setting("PREFER_NEWEST", True)

    # 0 = tanpa batas umur. Nilai yang didukung JobStreet: 1, 3, 7, 14, 31.
    max_age_days: int = _int_setting("MAX_AGE_DAYS", 0)

    # 0 = tanpa batas harian.
    max_apply_per_day: int = max(0, _int_setting("MAX_APPLY_PER_DAY", 5))
    delay_between_apply: int = _int_setting("DELAY_BETWEEN_APPLY", 3)
    max_pages: int = _MAX_PAGES
    headless: bool = _bool_setting("HEADLESS_MODE", False)

    # --- Sesi Chrome (agar tidak login ulang tiap kali) ---
    use_profile: bool = _bool_setting("USE_PROFILE", True)
    # Disimpan di folder pengguna, bukan di dalam proyek.
    profile_dir: str = os.getenv(
        "CHROME_PROFILE_DIR",
        str(Path.home() / ".dimastes" / "chrome-profile"),
    )
    # false = jangan menunggu login sama sekali (untuk sesi terjadwal).
    login_wait: bool = _bool_setting("LOGIN_WAIT", True)
    # Lama menunggu Anda login di Chrome (detik), tanpa perlu tekan Enter.
    login_timeout: int = max(30, _int_setting("LOGIN_TIMEOUT", 300))

    # --- Isian lamaran otomatis ---
    # Teks yang dipakai bila formulir meminta cover letter / pesan.
    # Gunakan \n untuk baris baru.
    cover_letter: str = os.getenv("COVER_LETTER", "").replace("\\n", "\n").strip()
    # Berkas CV yang diunggah otomatis bila formulir meminta unggah.
    resume_path: str = os.getenv("RESUME_PATH", "").strip()

    # --- Lamaran otomatis ---
    # Default mati; nyalakan lewat AUTO_APPLY=true di .env atau `run --auto`.
    auto_apply: bool = _bool_setting("AUTO_APPLY", False)
    # 0 = tanpa batas per sesi: yang membatasi hanya MAX_APPLY_PER_DAY
    # (mis. 50/hari). Bila diisi lebih kecil dari batas harian, sesi akan
    # berhenti sebelum kuota harian terpakai — jadi biarkan 0 atau >= 50.
    auto_apply_max_per_session: int = max(
        0, _int_setting("AUTO_APPLY_MAX_PER_SESSION", 0)
    )
    # Batas waktu mengenali tiap langkah alur lamaran. Bila terlampaui,
    # lowongan dilewati dan lanjut ke berikutnya.
    auto_apply_step_timeout: int = max(
        1, _int_setting("AUTO_APPLY_STEP_TIMEOUT", 3)
    )
    # Halaman "Review and submit" butuh waktu lebih untuk memuat tombol kirim
    # dan menampilkan konfirmasi.
    auto_apply_submit_timeout: int = max(
        3, _int_setting("AUTO_APPLY_SUBMIT_TIMEOUT", 20)
    )
    # Simpan HTML + screenshot saat alur tidak dikenali (maks 5 berkas).
    auto_apply_debug: bool = _bool_setting("AUTO_APPLY_DEBUG", True)

    # Jawab otomatis pertanyaan pilihan (dropdown) dari perusahaan bila
    # polanya dikenali: pengalaman, gaji yang diharapkan, pendidikan.
    auto_answer_questions: bool = _bool_setting(
        "AUTO_ANSWER_QUESTIONS", True
    )
    # Target gaji dalam rupiah/juta, mis. "5000000" atau "5". Kosong = tidak
    # dijawab otomatis (pertanyaan gaji membuat lowongan dilewati).
    expected_salary: str = os.getenv("EXPECTED_SALARY", "").strip()
    # Total pengalaman kerja (tahun) untuk pertanyaan "berapa tahun ...".
    years_experience: float = _float_setting("YEARS_EXPERIENCE", 3.0)
    # Jenjang pendidikan, mis. "S1".
    # Jawab "Ya" untuk pertanyaan ya/tidak seputar kesediaan/pengalaman.
    # Pertanyaan ya/tidak lain tetap dilewati agar tidak mengarang jawaban.
    auto_answer_yes: bool = _bool_setting("AUTO_ANSWER_YES", True)
    # Bidang pengalaman yang benar-benar Anda miliki. Pertanyaan pengalaman
    # di luar daftar ini dijawab 0 / "belum ada pengalaman", bukan 3 tahun.
    experience_roles: list[str] = field(default_factory=lambda: _list_setting(
        "EXPERIENCE_ROLES",
        "inventory,stock,stok,persediaan,gudang,warehouse,ppic,production,"
        "produksi,material,perencanaan,planner,purchasing,procurement,"
        "pembelian,supply chain,logistik,logistics,distribusi,distribution,"
        "administrasi,admin,ekspor,impor,import,export,data,furniture,"
        "furnitur,manufactur,project control,quality,audit",
    ))
    education_level: str = os.getenv("EDUCATION_LEVEL", "S1").strip()

    base_url: str = "https://id.jobstreet.com"
    login_url: str = "https://id.jobstreet.com"
    search_url: str = "https://id.jobstreet.com/jobs"

    telegram_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    telegram_chat_id: str = os.getenv("TELEGRAM_CHAT_ID", "")

    db_path: str = os.getenv("DB_PATH", str(BASE_DIR / "jobstreet_auto.db"))

    @property
    def keywords_riset(self) -> list[str]:
        """Kata kunci yang dipakai fase riset (RESEARCH_KEYWORDS/KEYWORDS)."""
        return list(self.research_keywords or self.keywords)

    def __post_init__(self):
        # LOCATIONS kosong -> pakai LOCATION tunggal.
        self.locations = [loc for loc in self.locations if loc.strip()]
        if not self.locations:
            self.locations = [self.location] if self.location else []

        if not self.location and self.locations:
            self.location = self.locations[0]

        # TITLE_KEYWORDS kosong -> pakai daftar kata kunci pencarian.
        self.title_keywords = [
            kata for kata in self.title_keywords if kata.strip()
        ]
        if not self.title_keywords:
            self.title_keywords = list(self.keywords)

        # RESEARCH_KEYWORDS dirapikan & dibuang duplikatnya tanpa mengubah
        # urutan. Bila kosong, `keywords_riset` memakai KEYWORDS saat
        # dijalankan — jadi perubahan KEYWORDS langsung ikut tanpa restart.
        unik = []
        terlihat = set()
        for kata in self.research_keywords:
            kunci = kata.strip().lower()
            if kunci and kunci not in terlihat:
                terlihat.add(kunci)
                unik.append(kata.strip())
        self.research_keywords = unik

        self.skill_keywords = [
            kata.strip() for kata in self.skill_keywords if kata.strip()
        ]


# Baris ini yang dibutuhkan oleh: from config import config
config = Config()
