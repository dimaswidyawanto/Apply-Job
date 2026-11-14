# Audit: Master Prompt vs Kondisi Kode Sekarang

Dibuat: 2026-11-06 · Cabang `arena/4ab2b9fa-dimastes`
Metode: pembacaan langsung kode (`config.py`, `job_filter.py`, `database.py`,
`main.py`, `glints.py`, `indeed.py`, `auto_apply.py`, `kuota.py`, `jawaban.py`),
bukan asumsi. Setiap baris menyebut letak buktinya.

Ringkasan: **fondasi pencarian–saring–peringkat–apply sudah ada dan berjalan**,
tetapi spesifikasi ini meminta beberapa lapisan yang **belum ada sama sekali**
(antrean 12 status, dashboard, pembacaan CV, skor berbobot persen, pembelajaran).

---

## 1. Konflik dengan aturan yang sudah ditetapkan lebih dulu

Tiga hal di spesifikasi ini **berlawanan langsung** dengan instruksi Anda
sebelumnya. Perlu keputusan Anda sebelum saya mengubah kode.

| # | Topik | Aturan Anda sebelumnya | Spesifikasi baru | Dampak bila diubah |
|---|---|---|---|---|
| K1 | Logo/gambar perusahaan | "Logo tidak dijadikan syarat; ada/tidaknya gambar tidak boleh menggagalkan lowongan" (diterapkan di JobStreet, Glints, Indeed) | Pasal 6.1: logo **wajib**; tanpa logo dikeluarkan dari klasifikasi; tidak pasti → `REVIEW_REQUIRED` | Lowongan tanpa logo kembali di-skip, termasuk di Indeed yang kartunya tidak memuat logo → nol lamaran di Indeed |
| K2 | Batas halaman riset | "Maksimal **5** halaman per kombinasi kata kunci × lokasi, tidak boleh lebih" (`config.MAKS_HALAMAN_RISET = 5`) | Pasal 3.2: maksimal **3** halaman | Riset turun ±40%, lowongan terkumpul lebih sedikit |
| K3 | Aturan gaji | `MIN_SALARY` (bawaan `0`), batas bawah rentang; `GLINTS_MIN_SALARY` sudah dihapus agar ketiga situs sama | Pasal 6.2: hanya gaji ≥ Rp4.500.000; rentang 4,0–6,0 jt **tidak** memenuhi | Bila `MIN_SALARY=4500000` diset, aturan berlaku otomatis tanpa ubah kode (sudah pakai batas bawah) |

---

## 2. Yang SUDAH ada dan berfungsi

| Pasal | Kebutuhan | Status | Bukti |
|---|---|---|---|
| 2.1 | Lokasi jamak lewat setelan | Ada | `config.locations`, `.env` `LOCATION` |
| 2.2 | Kategori dari daftar kata kunci | Sebagian | `config.keywords`, `title_keywords`, `research_keywords` |
| 3.1 | Urut terbaru | Ada | `sort=date` (Indeed), `sortmode=ListedDate` (JobStreet), "Baru Ditambahkan" (Glints) |
| 3.3 | Kumpulkan >50 tanpa batas | Ada | `research_max_jobs=0`; kuota hanya memotong saat apply (`kuota.py`) |
| 4.1 | Simpan data lowongan | Sebagian | tabel `jobs` (`database.py`:82) — tanpa kolom status antrean & alasan lolos/tidak |
| 4.2 | Status antrean | **Sebagian** | hanya status lamaran: `applied/already_applied/error/manual/failed`; belum ada FOUND→READY_TO_APPLY |
| 5 | Deteksi duplikat | Ada (dasar) | `kunci_duplikat` + `dedupe_jobs` (job_id, judul+perusahaan ternormalisasi) |
| 6.3 | Baca CV | **Belum** | tidak ada modul CV; profil diisi manual (`education_level`, `skill_keywords`, `max_experience`) |
| 7 | Skor kecocokan | Sebagian | 8 dimensi aditif (`job_filter.py`: skor posisi/lokasi/kualifikasi/pengalaman/pendidikan/keterampilan/tanggal/gaji), **bukan** 6 parameter berbobot persen |
| 8 | Ingatan formulir | Ada | `jawaban.py` (kunci normalisasi + `SequenceMatcher` 0.86, riwayat perubahan) |
| 9.1–9.2 | Batas 50/hari, lintas situs & lokasi | Ada | `kuota.py` (`MAX_APPLY_PER_DAY`), reset per tanggal lokal (`database.py`:363 `localtime` = WIB di PC Anda) |
| 9.3 | Verifikasi pengiriman | Sebagian | `auto_apply.py` mencocokkan teks sukses; ragu → `manual_required` |
| 9.4 | Isi formulir dari data valid | Ada | `auto_apply.py` + `jawaban.py` |
| 10 | Pemulihan otomatis | Sebagian | 4 percobaan driver, failover Chrome debug→profil, cek `already_applied` sebelum kirim |
| 13 | Keamanan data | Ada (dasar) | SQLite lokal, tanpa password tersimpan |
| 16.1 | Tes otomatis | Ada | `pytest` 452 tes hijau, `ruff` bersih |

---

## 3. Yang BELUM ada (pekerjaan baru)

| Pasal | Kebutuhan | Kondisi | Perkiraan usaha |
|---|---|---|---|
| 2.3 | Prioritas **lokasi × kategori** (tabel 5 baris contoh) | Tidak ada struktur data maupun urutan proses | Sedang — modul `prioritas.py` + dipakai 3 situs |
| 2.1 | Aktif/nonaktif lokasi tanpa hapus riwayat | Tidak ada | Kecil |
| 4.2 | 12 status antrean persisten | Tidak ada | Besar — tabel `queue` + migrasi + 3 situs |
| 4.3 | Antrean persisten, klaim worker, resume | Tidak ada | Besar |
| 5.1 | Fuzzy/similarity deskripsi untuk duplikat | Hanya exact/ternormalisasi | Sedang |
| 6.1 | `REVIEW_REQUIRED` untuk logo tak pasti | Tidak ada | Kecil (bila K1 diputuskan) |
| 7.1 | Skor 6 parameter berbobot 30/25/20/10/10/5 (0–100) | Skor aditif internal | Sedang–besar (ganti mesin skor, jaga filter wajib) |
| 7.2 | Kategori skor 90/80/70 | Tidak ada | Kecil |
| 7.3 | Alasan cocok/tidak per parameter | Sebagian (`_skor_rincian`) | Kecil |
| 11 | Dashboard real-time + kontrol Start/Pause/Stop/Clear/Retry | **Tidak ada** | Besar |
| 12 | Continuous improvement + laporan berkala | Tidak ada | Besar |
| 14 | Optimasi (async, worker, cache) | Sebagian (browser tunggal, tanpa cache) | Sedang |

---

## 4. Bug/risiko yang ditemukan saat audit

1. **Batas harian memakai `localtime`** (`database.py`:363). Benar selama PC di
   WIB; bila PC diubah ke zona lain, reset kuota ikut bergeser. Spesifikasi
   meminta WIB eksplisit → perlu `Asia/Jakarta` tetap, bukan zona PC.
2. **`jobs` tidak menyimpan alasan lolos/tidak** (pasal 4.1). Sekarang alasan
   hanya dicetak ke layar, hilang setelah sesi.
3. **Tidak ada kolom "tanggal publikasi asli" vs "diperbarui"** (pasal 3.1);
   hanya `age_days` hasil teks relatif.
4. **Tidak ada penanda proses berjalan** (pasal 4.3): dua peluncur yang dibuka
   bersamaan bisa mengklaim lowongan yang sama karena tidak ada lock.
5. **Dashboard tidak ada**, sehingga pasal 11.5 (kontrol nyata) belum bisa
   diuji.

---

## 5. Usulan urutan pengerjaan

Fase 1 — **Aturan & data inti** (tanpa UI):
- putuskan K1/K2/K3, lalu terapkan seragam di 3 situs;
- kolom `jobs`: alasan, status antrean, tanggal publikasi asli;
- lock proses (satu sesi) + reset kuota WIB eksplisit.

Fase 2 — **Antrean 12 status** + resume:
- tabel `queue`, migrasi aman, `READY_TO_APPLY`, `REVIEW_REQUIRED`, `EXPIRED`;
- klaim worker + lanjut dari progres terakhir.

Fase 3 — **Skor berbobot + CV**:
- pembacaan CV (PDF/DOCX) → profil terstruktur;
- skor 6 parameter berbobot, kategori 90/80/70, alasan per parameter.

Fase 4 — **Dashboard + pembelajaran**:
- dashboard lokal (kontrol Start/Pause/Resume/Stop/Clear/Retry);
- statistik per lokasi/kategori, laporan berkala, evaluasi strategi.

Fase 1 dan 2 wajib lebih dulu: dashboard tanpa status antrean hanya akan
menampilkan data yang tidak lengkap.

---

## 5a. Status pelaksanaan

Keputusan Anda: logo wajib di JobStreet & Glints (Indeed dikecualikan),
3 halaman per kombinasi, lowongan tanpa info gaji tetap boleh dilamar,
dan semua fase dikerjakan berurutan.

**Fase 1 — selesai (`96dc574` → commit sesudahnya):**
- Batas riset 5 → **3 halaman** (`config.MAKS_HALAMAN_RISET`), seragam 3 situs.
- Logo **wajib lagi** di JobStreet & Glints; Indeed tetap dikecualikan
  (`logo_diabaikan`).
- `MIN_SALARY` bawaan **4.500.000**; lowongan tanpa info gaji tetap layak.
- Kolom baru `jobs`: `status_antrean`, `alasan`, `posted_at`,
  `dikumpulkan_at`, `diperbarui_at`, `skor` + `set_status_antrean()` dan
  `hitung_status_antrean()`.
- Kuota harian memakai **batas hari WIB** eksplisit (`rentang_hari_wib`),
  bukan zona waktu komputer.
- **Kunci sesi tunggal** (`kunci.py`) mencegah dua peluncur melamar bersamaan.
- Tes: `tests/test_antrean.py` (12) + penyesuaian tes aturan; 465 tes hijau.

**Fase 2 — selesai (`7e448b2`):**
- `antrean.py`: pemetaan alasan → status, `klaim()` idempoten sebelum melamar,
  `selesai()` untuk applied/failed/review_required/expired.
- Dipakai di **ketiga** alur (`main.py`, `glints.py`, `indeed.py`), termasuk
  status penolakan, `applying` sebelum kirim, dan `expired` bila situs
  menyatakan lowongan tutup.
- `kendali.py`: berkas perintah `jeda`/`stop` yang diperiksa sesi di antara
  lowongan dan kata kunci — dasar tombol Pause/Stop dashboard.
- `REVIEW_REQUIRED` untuk logo yang **tidak dapat dipastikan** (pasal 6.1),
  bukan hanya tanpa logo.

**Fase 3 — selesai (`73f34b6`):**
- `cv.py`: baca `.docx` (zip+XML, tanpa dependensi), `.txt`/`.md`, dan `.pdf`
  (opsional lewat `pypdf`); profil berisi pengalaman, pendidikan, bidang,
  keterampilan, sertifikasi.
- `skor_cv.py`: skor 0–100 berbobot 30/25/20/10/10/5 + kategori 90/80/70 +
  rincian per parameter + alasan cocok/kurang. `MIN_SKOR_CV` memotong kandidat
  sebelum antrean apply. Tanpa CV, perilaku lama tidak berubah.

**Fase 4 — selesai:**
- `dashboard.py`: server HTTP pustaka standar (tanpa dependensi) di
  `http://127.0.0.1:8765`, JSON status, log aktivitas, dan kontrol nyata
  Start/Pause/Resume/Stop/Retry/Clear (Clear berkonfirmasi, dan tidak
  menghapus lowongan yang pernah dilamar). Diuji live di sandbox.
- `laporan.py` + `jalankan.bat laporan`: angka kinerja nyata dari database,
  sebaran status, per lokasi/kategori, alasan penolakan tersering, tingkat
  keberhasilan, serta saran yang **tidak** mengubah aturan otomatis.
- `log_aktivitas.py`: log harian WIB di `logs/aktivitas.log`.
- Perintah CLI baru: `cv`, `dashboard`, `laporan`, `antrean`; berkas
  `Dashboard.bat`.

**Uji 15 skenario wajib (pasal 14) — `tests/test_skenario_wajib.py`:**

| # | Skenario | Hasil |
|---|---|---|
| 1 | 200 lowongan sekaligus | 200 diproses & terurut, tanpa gagal |
| 2 | duplikat lintas sumber | digabung; satu baris per lowongan |
| 3 | tanpa logo | ditolak, kecuali Indeed |
| 4 | gaji Rp4,0 jt vs Rp4,5 jt | 4,0 jt ditolak (termasuk rentang 4,0–6,0 jt), 4,5 jt lolos |
| 5 | tanpa info gaji | tetap boleh dilamar |
| 6 | tidak relevan CV | tersaring `MIN_SKOR_CV` |
| 7 | batas 50/hari | dipotong tepat sesuai sisa kuota |
| 8 | kuota habis | berhenti, tidak melebihi batas |
| 9 | aplikasi dimatikan | sesi kedua ditolak; Stop menghentikan sesi |
| 10 | internet putus | dicatat `failed`, riwayat tetap, bisa diulang |
| 11 | resume setelah ditutup | status tersimpan & dibaca ulang |
| 12 | pertanyaan berulang | dijawab dari ingatan |
| 13 | bahasa berbeda | "Full Name" → jawaban "Nama Lengkap" |
| 14 | status kirim tidak pasti | `review_required`, bukan "berhasil" |
| 15 | klik dua kali | satu lamaran saja |

**Pelengkap setelah Fase 4 (revisi ini):**
- **Prioritas lokasi × kategori** (`PRIORITAS_LOKASI`, `PRIORITAS_KATEGORI`):
  mengatur urutan saat skor sama; tidak pernah menolak lowongan.
- **Dashboard lengkap**: detail satu lowongan + riwayat lamaran, tabel riwayat,
  dan edit konfigurasi dengan validasi (`.env` dicadangkan ke `.env.bak`,
  berlaku pada sesi berikutnya).
- **Backup & restore** database (`backup.py`, `jalankan.bat backup`): memakai
  API backup SQLite (aman saat sesi berjalan), `integrity_check` sebelum
  pemulihan, database lama disimpan `.db.bak`, 20 backup terbaru disimpan.
- **Laporan berkala**: `laporan.teks_markdown()` + `laporan.simpan()` menulis
  `reports/laporan-YYYY-MM-DD.md`, otomatis setelah sesi `lamar` selesai dan
  bisa dijadwalkan lewat Task Scheduler (`jalankan.bat laporan --simpan`).
- **Evaluasi kata kunci & sumber**: tabel `jobs` menyimpan `sumber` (dibaca
  dari URL, dengan pengisian otomatis untuk database lama) dan `kata_kunci`
  yang menemukan lowongan. Laporan, dashboard, dan berkas harian menampilkan
  jumlah lowongan + lamaran per kata kunci dan per sumber, lalu menyarankan
  kata kunci yang tidak produktif.

**Optimasi kecepatan (revisi ini):**
- `jalankan.bat` memakai jalur cepat: bila `.venv` siap (penanda
  `.venv\.python-baik` + `.deps-terpasang`), pencarian `py -3.13/3.12/...`
  dilewati sehingga setiap perintah tidak lagi menunggu beberapa detik.
- Dashboard tidak merender ulang bila datanya sama dan menyegarkan tiap 3 detik
  (sebelumnya 2 detik, selalu render).
- Port 8765 yang masih dipakai memberi pesan jelas (bukan layar memuat terus).
- Perintah baru `performa`: mengukur database, tulis berkas, dashboard, dan
  jaringan ke tiga situs, lalu memberi saran (folder OneDrive, antivirus,
  ukuran database).

**Hasil audit menyeluruh (revisi ini):** empat cacat nyata ditemukan dan
diperbaiki, semuanya dengan tes:

| Temuan | Dampak bila dibiarkan | Perbaikan |
|---|---|---|
| `DB_PATH=` kosong/relatif di `.env` | SQLite membuat database sementara → riwayat lamaran seolah hilang | `Config` selalu menjadikan path absolut; kosong → `jobstreet_auto.db` di folder proyek |
| Database lama: `status_antrean` NULL | total status di dashboard tidak sama dengan jumlah lowongan | migrasi mengisi `found` untuk baris lama |
| `MAX_APPLY_PER_DAY=0` di template | aturan "maks 50/hari" tidak berlaku untuk pemasangan baru | template memakai 50 (batas tetap, tetap bisa diubah lewat `.env`) |
| `submit_texts` didefinisikan dua kali di `glints.py` | definisi pertama mati, membingungkan saat dirawat | definisi mati dihapus (perilaku tidak berubah) |

**Revisi 10/10 — tiga celah terakhir ditutup:**

| Celah | Sebelum | Sesudah |
|---|---|---|
| Persetujuan/hukum dijawab dari ingatan | bot bisa mencentang "saya setuju" atas nama Anda | `jawaban.perlu_konfirmasi()` memblokir pernyataan/persetujuan/privasi/narkoba/background check di jalur teks **dan** radio; lowongan dikembalikan ke daftar manual + catatan di log |
| Galat sementara langsung membuang lowongan | satu timeout = lowongan dicatat `failed` | `antrean.ulang_berbatas()` + `perlu_konfirmasi`-independen: timeout/jaringan/Chrome diulang `MAKS_ULANG` (bawaan 2) dengan jeda `JEDA_ULANG`; kesalahan permanen (login habis) tidak diulang. Berlaku di JobStreet, Glints, dan Indeed |
| Statistik sesi hilang saat program ditutup | hanya tampil di terminal | tabel `sesi` di database (ditemukan, baru, duplikat, dilamar, gagal, diulang, durasi) → laporan memuat **Sesi terakhir** + rasio duplikat dan saran bila ≥ 30%; dashboard punya panel **Sesi terakhir** |

Tambahan kecil pada revisi ini: indeks `jobs(status_antrean/sumber/kata_kunci)`
untuk filter yang makin sering dipakai, backup harian otomatis di awal sesi
(`backup.pastikan_harian()`, sekali per hari), template `LOCATIONS` berisi 7 kota
sesuai pasal lokasi, dan `tests/conftest.py` yang mengarahkan database tes ke
berkas sementara sehingga **menjalankan tes tidak pernah mengubah data Anda**.

**Batas yang perlu diketahui (jujur):**
- Uji browser nyata (Selenium) tetap hanya bisa di PC Anda; semua tes di sini
  memakai bot/driver palsu.
- Atribusi kata kunci mencatat **kata kunci pertama** yang menemukan sebuah
  lowongan (bukan semua kata kunci yang juga menemukannya).
- Jumlah duplikat yang dibuang tercatat di konsol setiap riset, tetapi belum
  disimpan sebagai angka di laporan.
- Laporan berkala berbentuk berkas harian + panduan Task Scheduler; tidak ada
  penjadwal bawaan di dalam aplikasi.
- Uji end-to-end di browser sungguhan (JobStreet/Glints/Indeed) tetap harus
  dijalankan di PC pengguna.
- Klaim worker memakai status di database + kunci sesi tunggal, bukan antrean
  multi-mesin.

## 6. Yang TIDAK akan saya ubah tanpa persetujuan Anda

Sesuai pasal 12.5: batas gaji, batas 50/hari, kriteria logo, daftar lokasi,
daftar kategori, data pribadi/CV, dan ketentuan inti apply.

---

## 7. Audit lanjutan 2026-11-03 — temuan E-1…E-13

Audit ini dijalankan atas kode `ca1b5b5` (setelah PR #4). Setiap perbaikan
disertai tes baru; angka di bawah diambil dari eksekusi nyata, bukan perkiraan.

### 7.1 Ringkasan angka

| Ukuran | Sebelum | Sesudah |
|---|---|---|
| `pytest -q` | 595 passed, 1 skipped | **615 passed, 1 skipped** |
| Temuan `ruff check .` | 424 | **151** (semuanya pola pertahanan yang disengaja) |
| Gate `ruff --select E9,F,E501,I,B,SIM,ISC` | bersih | bersih |
| CI otomatis | tidak ada | `.github/workflows/uji.yml` |

### 7.2 P1 — lamaran gagal terkirim (FIXED + TESTED)

| ID | Temuan | Perbaikan | Tes |
|---|---|---|---|
| E-1 | Beberapa tombol cocok; yang diklik tombol atas (mis. "Review"), bukan tombol kirim di ujung formulir. Label navigasi seperti "Lanjut"/"Kembali"/"Batal" juga bisa terpilih. | `AutoApplier._kandidat_tombol_kirim()` mengumpulkan semua kandidat layak lalu **memilih yang paling bawah** di halaman review; `LABEL_BUKAN_KIRIM` + `_boleh_jadi_tombol_kirim()` menolak tombol navigasi. | `test_tombol_kirim_pilih_paling_bawah`, `test_tombol_navigasi_ditolak_sebagai_tombol_kirim` |
| E-2 | Label berisi karakter tak terlihat (U+2060, U+001B…), NBSP, dan spasi ganda sehingga "Submit application" tidak dikenali. | `jawaban.bersihkan_teks()` membuang karakter tak terlihat, mengubah NBSP menjadi spasi, dan merapikan spasi; dipakai `kunci_pertanyaan()`, `_norm()`, dan `_text()`. | `test_karakter_tak_terlihat_dibuang_dari_label_tombol`, `test_kunci_pertanyaan_abaikan_karakter_tak_terlihat` |
| E-3 | `input[type=checkbox]` tidak ditangani sama sekali → formulir skill multi-pilih selalu kosong. | `_jawab_checkbox()` + `_centang()`: centang opsi yang cocok dengan `SKILL_KEYWORDS`/`TITLE_KEYWORDS`; bila tidak ada yang cocok, centang opsi jujur ("None of the above"/"Tidak ada"); bila tetap tidak ada, lowongan masuk daftar manual (tidak menebak). Pertanyaan persetujuan tetap diblokir `jawaban.perlu_konfirmasi()`. | `test_checkbox_skill_pengguna_dicentang`, `test_checkbox_tanpa_kecocokan_pilih_none`, `test_checkbox_tak_dikenal_masuk_manual` |
| E-4 | Pertanyaan berskala ("how would you rate…") tidak dijawab; varian "Yes, I have"/"Ya, benar" tidak dikenali; radio tanpa atribut `name` diabaikan total. | `SKALA_KATA` + `SKALA_URUT` + `_pilih_skala_terendah()` menjawab dengan tingkat **terendah** (jujur, tanpa melebihkan); regex Ya/Tidak menerima varian dan menolak yang memuat "belum"/"not"; radio tanpa `name` dikelompokkan menurut teks pertanyaannya (kelompok < 2 radio dilewati). | `test_skala_dijawab_tingkat_terendah`, `test_ya_tidak_varian_dikenali`, `test_radio_tanpa_name_dikelompokkan_per_pertanyaan` |

### 7.3 P2 — ketahanan & pemeliharaan

| ID | Temuan | Perbaikan | Status |
|---|---|---|---|
| E-5 | `PRAGMA foreign_keys` mati (0). | `Database._koneksi()` menjalankan `PRAGMA foreign_keys=ON`. Skema sekarang memang belum memakai `FOREIGN KEY`, jadi efeknya nol sampai relasi ditambahkan — tetapi biayanya juga nol. | FIXED + TESTED (`test_foreign_key_dipaksa_aktif`) |
| E-6 | Log hanya dipangkas jumlah baris; setiap penulisan membaca ulang seluruh berkas, dan berkas tumbuh tanpa batas ukuran. | `log_aktivitas._rotasi()`: berkas > 512 KB diganti nama menjadi `aktivitas.log.1` (satu arsip, bukan menumpuk). Pemangkasan 2.000 baris tetap ada. | FIXED + TESTED (4 tes di `tests/test_log_aktivitas.py`) |
| E-7 | Tidak ada CI; regresi hanya ketahuan saat dijalankan manual. | `.github/workflows/uji.yml`: pasang dependensi → gate ruff → `pytest -q` pada setiap push/PR. | FIXED (belum pernah berjalan di GitHub — lihat 7.5) |
| E-8 | `DB_PATH` ada di `.env.example` tetapi tanpa penjelasan. | Komentar ditambahkan: lokasi database, arti nilai kosong, path relatif otomatis absolut. | FIXED (dokumentasi) |
| E-9 | 424 temuan gaya `ruff`. | 272 diperbaiki (`--fix` yang aman + perbaikan manual); sisa 152: `BLE001` 124, `S112` 12, `S110` 7, `RUF100` 9. Semuanya **disengaja**: `except Exception` luas pada pembacaan DOM/tombol memang diperlukan agar perubahan HTML satu situs tidak menghentikan sesi, dan `# noqa` dipertahankan sebagai penanda alasan. | PARTIAL (disengaja) |
| E-10 | Perintah uji Telegram tidak ada. | **Tidak diubah** — Anda sudah menetapkan agar kode/`.env` notifikasi Telegram tidak diutak-atik. | DITUNDA (sesuai instruksi) |
| E-11 | Skor inventori/persediaan. | **Tidak diubah** — bagian dari prioritas stock/inventory yang Anda batalkan. | DITUNDA (sesuai instruksi) |

### 7.4 P3 — perapian (sudah dikerjakan, lihat bagian 12)

| ID | Temuan | Perbaikan | Status |
|---|---|---|---|
| E-12 | Normalisasi teks tersebar di beberapa modul. | `teks.py` menjadi satu tempat: `bersihkan()` (buang karakter tak terlihat, rapikan spasi) dan `kunci_nama()` (huruf kecil tanpa tanda baca). `jawaban.bersihkan_teks` dan `scraper._norm_teks` kini hanya nama lama yang menunjuk ke sana, jadi perilaku pengenalan logo tidak berubah. | FIXED + TESTED (`tests/test_teks.py`) |
| E-13 | Riset memanggil situs berulang tanpa cache. | `cache_riset.py` + tabel `riset_cache`: hasil satu kombinasi situs + kata kunci + lokasi + halaman dipakai ulang selama `CACHE_RISET_MENIT` (bawaan 60 menit), `0` = mati, `--segar` = ambil ulang. Lamaran tetap membuka halaman lowongannya sendiri. | FIXED + TESTED (`tests/test_cache_riset.py`) |

### 7.5 Batas yang perlu diketahui (jujur)

- Perbaikan E-1…E-4 **teruji dengan driver/tiruan**, bukan di JobStreet/Glints
  sungguhan. Uji browser nyata tetap harus dijalankan di PC Anda dengan
  `.\jalankan.bat run --auto`.
- Workflow CI baru ditulis; hasil pertama baru terlihat setelah ada push ke
  GitHub.
- E-3 memakai `SKILL_KEYWORDS`/`TITLE_KEYWORDS`. Bila formulir menanyakan
  keahlian yang tidak ada di daftar itu, bot **tidak menebak** — lowongan masuk
  daftar manual. Itu disengaja agar tidak ada klaim palsu di lamaran.

### 7.6 Temuan dari sesi nyata 2026-11-11 (E-14, E-15)

Bukti: tangkapan layar sesi `run --auto` pada Glints (PPIC, Megacon Bangun
Perkasa). Terminal menulis `klik tombol kirim "kirim" (percobaan 1)` lalu
`Dilewati: Tombol Kirim sudah diklik, tetapi konfirmasi tidak muncul dalam 45
detik`, sementara halaman Glints menampilkan **"Kamu sudah melamar pekerjaan
ini. Silakan cek aplikasi…"**.

| ID | Temuan | Perbaikan | Tes |
|---|---|---|---|
| E-14 | Setelah Kirim diklik, Glints kembali ke halaman lowongan dengan banner "sudah melamar". Teks itu tidak ada di `SUKSES_GLINTS`, dan pemeriksaan `is_already_applied()` hanya berjalan **sebelum** tombol Lamar diklik — jadi bot menunggu 45 detik lalu menandai lowongan "perlu manual" padahal lamaran sudah masuk. | `SUKSES_GLINTS` + `SIBUK_TEXTS` memuat "kamu sudah melamar", "sudah melamar pekerjaan ini", "cek lamaran saya", "you have already applied". Setelah Kirim diklik, `is_already_applied()` kini juga dihitung sebagai **terkirim**. Banner yang sudah ada sejak awal tetap dianggap `already_applied` (tidak melamar dua kali). | `test_banner_sudah_melamar_dihitung_terkirim`, `test_banner_sudah_melamar_dikenali_sebagai_sukses`, `test_already_applied_tetap_dilewati_sebelum_klik` |
| E-15 | Dump debug Glints **tidak pernah tersimpan**: `job_id` berbentuk `glints:<uuid>` dan titik dua tidak sah pada nama berkas Windows. Konsol tetap mengaku "debug disimpan di …", sehingga berkas yang diminta untuk diagnosa tidak ada. | `nama_berkas_aman()` mengganti karakter terlarang dengan `-`; pesan baru dicetak setelah berkas benar-benar tertulis, dan kegagalan menulis dilaporkan (dulu ditelan `except: pass`). | `test_nama_berkas_debug_aman_untuk_glints`, `test_dump_debug_tersimpan_untuk_job_id_glints` |

Catatan jujur: E-14 menutup gejala yang terlihat, tetapi keadaan halaman tepat
sebelum waktu tunggu habis tidak bisa saya periksa karena dump debug-nya (akibat
E-15) tidak pernah ada di disk. Bila masih muncul, jalankan lagi setelah
pembaruan ini — kini berkas `debug\*.html/.txt` benar-benar tersimpan.

---

## 8. Pemisahan situs (2026-11-11)

Keluhan pemakai: `run --auto` membuka JobStreet padahal JobStreet sudah selesai
dan yang ingin dikerjakan adalah Glints.

**Sebabnya bukan bug:** perintah `run` memang mesin JobStreet sejak awal,
sedangkan `lamar`/`Lamar *.bat` adalah jalur semua situs. Yang kurang adalah
penanda yang jelas dan cara melihat data per situs. Perbaikannya:

| Perubahan | Keterangan |
|---|---|
| `run --situs {jobstreet,glints,indeed,semua}` | bawaan tetap **jobstreet**; situs lain dijalankan lewat jalur `lamar_semua` yang sama dengan `Lamar Glints.bat` |
| Baris `Situs: … — situs lain tidak dibuka` | tercetak setiap `run`, menghilangkan salah sangka |
| Perintah baru `status` | tabel per situs: lowongan, terkirim, perlu manual, gagal, ditolak, kedaluwarsa |
| `history --situs` dan `antrean --situs` | data per situs tidak lagi tercampur di layar |
| `stats` | menampilkan total keseluruhan **dan** tabel per situs |
| `Database.ringkasan_per_situs()`, `hitung_status_antrean(situs)`, `get_recent_applications(situs)` | dasar angkanya; situs lama ditebak dari URL bila kolom `sumber` kosong |

Data JobStreet tidak diubah sama sekali: tidak ada migrasi, penghapusan, atau
penulisan ulang baris. Semua penyaringan hanya `SELECT`.

Tes: `tests/test_situs_terpisah.py` (17 tes) — pilihan situs, ringkasan per
situs, tebakan situs dari URL, filter riwayat/antrean, dan routing `run`
(JobStreet tetap bawaan; `--situs glints` tidak memanggil mesin JobStreet).

---

## 9. Ingatan jawaban formulir (2026-11-11)

Keluhan pemakai: "setiap jawaban yang pernah saya isi kenapa tidak diingat,
harus memasukkan lagi" — pada formulir Glints *Seberapa mahir kamu dengan
keahlian berikut ini?* (Pelayanan Pelanggan / Kerja Tim / Microsoft Excel).

| ID | Sebab | Perbaikan |
|---|---|---|
| E-16 | `_potret_jawaban()` (pencatat isian) hanya melihat radio yang **terlihat** dan punya atribut `name`. Input asli Glints tersembunyi di balik label, dan sebagian tanpa `name` → jawaban pengguna tidak pernah terekam, sehingga setiap lowongan menanyakannya lagi. | Pengelompokan disamakan dengan `_jawab_radio()`: menerima input tersembunyi selama labelnya terlihat, dan mengelompokkan yang tanpa `name` menurut wadahnya (`_kunci_grup_tanpa_nama`). |
| E-17 | Satu judul skala dipakai untuk banyak keahlian, sehingga kunci ingatan sama untuk semuanya — jawaban keahlian A menimpa B (dan jawaban tersimpan bisa terpakai di keahlian yang salah). | `_pertanyaan_grup()` menambahkan pembeda (nama keahlian) pada kunci, mis. `Seberapa mahir … — Microsoft Excel`. Pembeda hanya dipakai untuk kelompok berskala (≥ 3 opsi, ≥ 2 tingkat), jadi pertanyaan ya/tidak tidak berubah kuncinya. |
| E-18 | Kotak centang tidak pernah dicatat maupun dipakai ulang. | `_kelompok_checkbox()` dipakai bersama oleh `_jawab_checkbox()` dan `_potret_jawaban()`; jawaban disimpan sebagai `Excel; SAP` dan diisi ulang lewat `_dari_ingatan_banyak()`. |
| E-19 | Sulit memastikan ingatan aktif. | `status` menampilkan "Ingatan jawaban: N tersimpan"; `jawaban` tetap bisa melihat/menghapus. |

Tes: `tests/test_jawaban.py` (+4) — radio tersembunyi tanpa `name` terekam,
dua keahlian tersimpan terpisah, pengisian ulang dari ingatan pada lamaran
berikutnya, dan kotak centang dari ingatan. Suite penuh **636 passed, 1
skipped**.

Batas jujur: pengujian memakai elemen tiruan (HTML asli Glints tidak tersedia
di sesi ini). Bila masih ada pertanyaan yang tidak terisi, jalankan sesi lagi
setelah pembaruan; sekarang berkas `debug\*.html` benar-benar tersimpan
(perbaikan E-15), dan kirimkan satu berkas itu untuk penyetelan selector.

---

## 10. Kuota harian per situs: 50 wajib, bukan batas bersama (2026-11-11)

Permintaan pemakai: "JobStreet, Glints, dan Indeed wajib apply 50 lowongan
setiap hari, bukan batas maksimal 50". Pilihan yang dipilih saat ditanya:
**50 untuk tiap situs**, dan **berhenti di 50** (bukan terus melamar).

| Sebelum | Sesudah |
|---|---|
| Satu hitungan 50 dipakai bersama; JobStreet 50 berarti Glints 0 | Tiap situs punya hitungan sendiri: JobStreet 50, Glints 50, Indeed 50 |
| `get_today_apply_count()` tanpa parameter | `get_today_apply_count(situs)` dengan cadangan dari URL dan awalan `job_id` (`glints:…`, `indeed:…`) |
| `kuota.sisa/habis/potong/ringkasan` global | menerima `situs=`; ditambah `target()`, `kurang()`, `ringkasan_situs()` |
| Pesan "kuota habis" tanpa nama situs | "Kuota Glints hari ini sudah habis…" dan situs lain tetap jalan |
| `MAX_APPLY_PER_DAY` bawaan kode 5 | 50 (sama dengan `.env.example`) |

Tambahan supaya angka 50 benar-benar dikejar, bukan sekadar dibatasi:

- akhir sesi `lamar` menampilkan `JobStreet: 12/50`, `Glints: 50/50`, dst. dan
  peringatan "Target harian belum tercapai: JobStreet kurang 38";
- perintah `status` punya tabel target per situs (hari ini / target / sisa /
  status tercapai);
- laporan harian (layar, Markdown, dashboard) menampilkan kuota per situs.

Tes: `tests/test_kuota_situs.py` (10 tes) + penyesuaian
`test_glints_aturan.py`, `test_laporan_harian.py`, `test_rank_kuota.py`.
Suite penuh: **646 passed, 1 skipped**. Gate ruff bersih.

Batas jujur: 50 per situs hanya bisa tercapai bila kandidatnya ada. Bila hasil
riset habis sebelum 50 (mis. kata kunci terlalu sempit), sesi berhenti dan
melaporkan kekurangannya — bukan memaksakan lowongan yang tidak memenuhi
syarat.

---

## 11. Kuota 50 per situs dalam siklus 24 jam bergulir (2026-11-11)

Klarifikasi pemakai atas permintaan sebelumnya: "50 itu per hari yah, karena
batas maksimum setiap aplikasi 50 per hari; apabila sudah lewat 24 jam dari
pengiriman pertama maka bisa lagi 50 apply; wajib setiap 50 harus tercapai".

| Sebelum (PR #8) | Sesudah (PR #9) |
|---|---|
| 50 per situs per **hari kalender WIB** — reset pukul 00:00 | 50 per situs per **siklus 24 jam** — reset 24 jam sejak lamaran pertama |
| Dimulai 20:30 → 00:00 sudah dapat 50 slot baru | Dimulai 20:30 → slot baru besok 20:30 |
| Tidak ada info kapan kuota kembali | `status`/laporan/akhir sesi menampilkan "Reset berikutnya: besok 20:30" |

Cara kerjanya (tanpa tabel baru, dihitung dari `applications`):

1. `Database.bentuk_siklus()` mengurutkan waktu lamaran, memulai siklus baru
   setiap kali jarak ke lamaran pertama siklus berjalan ≥ 24 jam.
2. `Database.siklus_kuota(situs)` membatasi hitungan pada satu situs.
3. Bila siklus terakhir sudah lewat dan belum ada lamaran baru, hitungan
   kembali 0 (slot penuh 50) dan siklus baru dimulai pada lamaran berikutnya.
4. `kuota.py` memakai siklus itu untuk `terpakai/sisa/habis/kurang/ringkasan/
   ringkasan_situs`, lengkap dengan `berakhir` dan `sisa_waktu`.

Contoh keluaran `status`:

| Situs | Siklus ini | Target | Sisa | Reset berikutnya |
|---|---|---|---|---|
| JobStreet | 47 | 50 | 3 | hari ini 23:37 |
| Glints | 12 | 50 | 38 | hari ini 23:37 |
| Indeed | 0 | 50 | 50 | - |

Tes: `tests/test_siklus_kuota.py` (13 tes) — batas 24 jam, bukan tengah malam,
situs terpisah, status gagal tidak memakai kuota, siklus kemarin tidak menahan
kuota hari ini, teks ringkasan. Suite penuh **659 passed, 1 skipped**, gate
ruff bersih.

Batas jujur: sisa slot yang tidak terpakai **hangus** saat siklus berganti
(mulai 50 baru). Bila Anda ingin sisanya dibawa ke siklus berikutnya, itu
perubahan kecil di `bentuk_siklus()` — beri tahu saja.

---

## 12. P3: normalisasi teks & cache riset (2026-11-03)

Permintaan pemakai: "lanjutkan semua pr" → pilih "kerjakan temuan audit yang
ditunda (E-12, E-13)". E-10 (Telegram) dan E-11 (skor inventori) tetap tidak
disentuh sesuai instruksi.

### E-12 — normalisasi teks

Sebelumnya dua fungsi normalisasi terpisah, masing-masing membuang karakter
tak terlihat dengan daftar sendiri:

| Sebelum | Sesudah |
|---|---|
| `jawaban.bersihkan_teks()` — buang karakter tak terlihat, rapikan spasi | `teks.bersihkan()` |
| `scraper._norm_teks()` — huruf kecil tanpa non-alfanumerik | `teks.kunci_nama()` |

Nama lama tetap ada sebagai alias, jadi `logo_perusahaan()` dan pencocokan
pertanyaan formulir berperilaku persis sama (dijaga oleh `tests/test_teks.py`,
termasuk tiga kasus `logo_perusahaan`).

### E-13 — cache riset

| Hal | Nilai |
|---|---|
| Cakupan | satu kombinasi situs + kata kunci + lokasi + halaman |
| Penyimpanan | tabel `riset_cache` (kunci, situs, jumlah, isi JSON, dibuat_at) |
| Masa berlaku | `CACHE_RISET_MENIT` (bawaan 60 menit); `0` = mati |
| Paksa ambil ulang | `--segar` pada `jalankan.bat run` / `lamar_semua.py` |
| Pembersihan | baris > 3 hari dibuang setiap kali menyimpan |
| Lamaran | **tidak** memakai cache — selalu buka halaman lowongannya sendiri |

Alasan desain: risiko utama cache adalah menyajikan lowongan yang sudah tutup.
Karena pengiriman lamaran tetap membuka halaman aslinya, lowongan tutup gagal
dengan aman dan tidak pernah terkirim dua kali. Yang dihemat hanya pembacaan
daftar lowongan (bagian terlama dari riset).

Keluaran saat cache dipakai: `Halaman 1 diambil dari cache riset (24 lowongan).`
dan di akhir riset: `Cache riset: 12 kombinasi dipakai ulang, 5 disimpan
(berlaku 60 menit; pakai --segar untuk ambil ulang dari situs).`

Tes: `tests/test_teks.py` (7) + `tests/test_cache_riset.py` (12) — kunci cache
tidak tercampur antar situs, TTL, `--segar`, cache mati, pembersihan baris lama,
dan pembuktian bahwa bot tidak dipanggil dua kali untuk kombinasi yang sama
(Glints, Indeed, JobStreet). Suite penuh: **678 passed, 1 skipped**; gate ruff
bersih.

Batas jujur: semuanya teruji dengan objek tiruan (tanpa Chrome). Perilaku di
situs sungguhan — terutama apakah cache 60 menit cukup segar untuk lowongan
baru — baru ketahuan setelah dijalankan di PC Anda.

---

## 13. Perbaikan dari sesi nyata 12 Nov 2026 (JobStreet 2 lamaran dari 28 kandidat)

Log sesi nyata dikirim pemakai. Tiga penyebab utama 50 lamaran/situs tidak
tercapai, semuanya diperbaiki di sini.

| Gejala di log | Penyebab | Perbaikan | Status |
|---|---|---|---|
| 26 dari 28 kandidat dilewati: "please address the following issues: how many years' experience …" | Ingatan jawaban hanya mencocokkan kalimat yang mirip ≥ 86%; JobStreet menanyakan hal sama dengan kalimat berbeda ("as a Purchasing Specialist" vs "in a Purchasing role") | `jawaban.maksud()` + `_cari_berdasarkan_maksud()`: cocokkan jenis pertanyaan (pengalaman/gaji/pendidikan/bahasa/hak kerja/industri/ketersediaan/SIM) + subjeknya, tanpa mengarang jawaban baru | FIXED + TESTED (`tests/test_jawaban_maksud.py`) |
| Pertanyaan gaji tetap kosong walau ingatan berisi "Rp 5 Jt" | Pilihan formulir berbunyi "Rp 5 jt"/"Rp 5 million"/"Rp 5.000.000", pencocokan hanya berbasis teks | `jawaban.angka_dari_teks()` + `sama_nilai()`; `AutoApplier._dari_ingatan` memilih opsi dengan nilai yang sama | FIXED + TESTED |
| Indeed: captcha di setiap pencarian, 3 jam untuk 0 lowongan | Setelah menunggu 60 detik, bot tetap melanjutkan 180 kombinasi | `IndeedBot.captcha_berturut`; riset berhenti setelah 2 captcha berturut-turut dengan pesan yang jelas | FIXED + TESTED (`tests/test_indeed_captcha.py`) |
| Glints: "Chrome instance exited" → profil baru → login diminta → 0 lamaran | Profil Chrome situs sebelumnya belum dilepas | `browser.profil_terkunci()` + `tunggu_profil_bebas()` (maks 8 detik) dan pesan agar menutup Chrome | FIXED + TESTED (`tests/test_profil_chrome.py`) |

Keputusan pemakai pada sesi ini:
- pencocokan jawaban: **berdasarkan maksud, tanpa mengarang jawaban baru**;
- panjang riset: **tidak diubah** (tetap menyeluruh), jadi riset masih bisa
  memakan 2+ jam bila kata kunci × lokasi banyak.

Tes: 678 → **694 passed, 1 skipped** (+16: 8 maksud/angka, 2 captcha Indeed,
6 profil Chrome). Gate ruff bersih.

Batas jujur: semua diuji dengan objek tiruan. Efek nyata — berapa kandidat yang
berhasil dikirim setelah pencocokan maksud — hanya ketahuan dari sesi
berikutnya di PC Anda; kirimkan log lagi bila angkanya belum membaik.

---

## 14. Sesi 12 Nov 2026 (lanjutan): jawaban bertentangan & Indeed 0 terkirim

Angka sesi nyata yang dilaporkan pemakai: JobStreet 68 terkirim, Glints 38,
**Indeed 0 dari 381** (297 disaring filter, 84 "perlu manual", 0 gagal).

### 14.1 Jawaban bertentangan (prasyarat sebelum menelusuri Indeed)

| Gejala | Penyebab | Perbaikan | Status |
|---|---|---|---|
| Pertanyaan pengalaman purchasing dijawab berbeda-beda: "Less than 1 year", "1 year", "2 tahun", "3 years" | Ingatan menyimpan satu nilai per kalimat; kalimat berbeda = baris berbeda | `jawaban.konflik()` mengelompokkan per jenis+subjek (tanpa kata tingkat jabatan, jadi purchasing staff/specialist ikut satu kelompok) | FIXED + TESTED (`tests/test_jawaban_konflik.py`) |
| Nilai terpilih berubah-ubah antar lamaran | `_cari_berdasarkan_maksud` memakai kemiripan teks; selisih kata "staff"/"specialist" menentukan pemenang | Subjek dibandingkan tanpa kata jabatan + tie-break `min(dipakai,20)/1000`; pencocokan maksud didahulukan sebelum kemiripan teks | FIXED + TESTED |
| "Rp 5 Jt" dan "Rp 5 million" dulu dianggap sama, **tetapi** "2 tahun" juga dianggap sama dengan "3 tahun" | `sama_nilai` punya toleransi absolut 1 | Toleransi jadi relatif 1%; "kurang dari/less than" tidak disamakan dengan angka polos | FIXED + TESTED |
| Tidak ada cara menyamakan jawaban tanpa mengarang | — | `jawaban.tetapkan()` + `cli.py jawaban --tetapkan "subjek=nilai"`, dan `--rapikan` untuk tabel konflik | FIXED + TESTED |

**Nilai resmi per subjek belum ditetapkan** — itu keputusan pemakai. `--rapikan`
hanya menampilkan usulan (nilai yang paling sering dipakai), bukan memilih
sendiri.

### 14.2 Indeed 0 terkirim

| Gejala | Penyebab yang bisa dipastikan dari kode | Perbaikan | Status |
|---|---|---|---|
| 84 lamaran Indeed berakhir "perlu manual", 0 terkirim | Indeed Apply menaruh formulir di iframe `smartapply.indeed.com`; `AutoApplier` hanya mencari tombol/isian di dokumen utama, jadi alur tidak pernah dikenali | Hook aditif `_masuk_kerangka_lamaran()` (default kosong → JobStreet tidak berubah) + selector iframe Indeed; `_keluar_kerangka()` sebelum tiap lowongan | FIXED + TESTED (driver tiruan, `tests/test_indeed_kerangka.py`) |
| Penyebab pasti per lowongan tidak terlihat dari `history` | Riwayat hanya menampilkan status, bukan `applications.notes` | `history --alasan` menampilkan kolom Alasan | FIXED + TESTED (`tests/test_riwayat_alasan.py`) |

Batas jujur: perbaikan iframe **belum teruji di situs sungguhan**. Bila Indeed
masih 0 setelah sesi berikutnya, jalankan
`python cli.py history --situs indeed --alasan --limit 20` dan kirimkan
hasilnya — kolom Alasan menyebut penyebabnya apa adanya (mis. "Tombol Lamar
tidak ditemukan", "Lamar di situs perusahaan", atau "Formulir meminta isian
yang belum bisa dijawab otomatis: …").

Tes: 694 → **731 passed, 1 skipped** (+37: 23 konflik jawaban, 10 kerangka
iframe, 4 riwayat alasan). Gate ruff `E9,F,E501,I,B,SIM,ISC` bersih untuk
`jawaban.py`, `auto_apply.py`, `indeed.py`, `cli.py`, `database.py`, dan tes
baru.

---

## 15. Sesi lanjutan: Indeed "tombol Lamar tidak ditemukan" (data nyata)

Data dari PC pemakai (`history --situs indeed --alasan`, kode `cd18f62`):
**20 dari 20** lamaran Indeed gagal dengan alasan yang persis sama —
"Tombol Lamar tidak ditemukan di halaman". Tidak ada satu pun pesan
"dialihkan ke situs lain", jadi halaman lowongan memang terbuka normal tetapi
tidak menawarkan tombol Lamar.

Koreksi: perbaikan iframe (bagian 14.2) **bukan penghalang pertama** — iframe
baru relevan setelah tombol Lamar diklik. Dua penyebab yang tersisa: sesi
login Indeed habis (ajakan "Masuk untuk melamar") atau halaman verifikasi.

| Gejala | Penyebab | Perbaikan | Status |
|---|---|---|---|
| 84 lamaran Indeed "perlu manual", alasan selalu "tombol tidak ditemukan" | Ajakan masuk / halaman verifikasi tidak dikenali sebagai penyebab, jadi alur berjalan 12 detik lalu menyerah dengan pesan generik | `IndeedApplier._is_login_page()` mendeteksi ajakan masuk (sesi dihentikan, `login_required`) dan `_blocker()` memberi alasan spesifik untuk verifikasi/login | FIXED + TESTED (`tests/test_indeed_login_verifikasi.py`) |
| Penyebab tidak bisa dibuktikan | Jalur "tombol tidak ditemukan" satu-satunya yang **tidak** menyimpan `debug/` | `_dump_debug(job, paksa=True)` di jalur itu; batas 5 berkas/sesi, tetap menghormati `AUTO_APPLY_DEBUG` untuk jalur lain | FIXED + TESTED |
| Risiko lowongan baru dicap "sudah dilamar" | `SUDAH_DILAMAR_TEXTS` memuat kata "applied" sendirian, yang muncul di banyak tempat di halaman Indeed | Token itu dibuang; frasa panjang dipertahankan | FIXED + TESTED |

Batas jujur: penyebab sebenarnya (login habis vs verifikasi) **belum
terkonfirmasi** — tes memakai driver tiruan. Bukti akan tersedia otomatis di
`debug/*.txt` pada sesi Indeed berikutnya; dari berkas itu selector bisa
diperbaiki berdasarkan HTML asli.

Tes: 731 → **746 passed, 1 skipped** (+15), gate ruff bersih.

---

## 16. Blokir Cloudflare pada Indeed (bukti layar, 2026-11-08)

Pemakai mengirim tangkapan layar: jendela Chrome bot menampilkan
**"Diperlukan Verifikasi Tambahan"** milik Cloudflare (ID Ray
`a5956cc5fbed9fad`) dengan *spinner* "Melakukan verifikasi…", sementara
terminal mencatat `Indeed menampilkan verifikasi/captcha` pada setiap
kombinasi (1/180, 0 lowongan, perkiraan sisa ±5943 detik).

Dua koreksi penting atas analisis sebelumnya:

1. Dugaan "sesi login habis" **tidak terbukti** — pada layar, Indeed
   menampilkan tombol "Masuk", jadi memang tidak login; tetapi penyebab
   kegagalan 84 lamaran adalah **halaman tantangan Cloudflare** yang tidak
   punya tombol Lamar sama sekali, bukan tombol yang salah selector.
2. Perbaikan deteksi verifikasi (`28ed3e2`) **tidak mengenali** halaman ini:
   tokennya `"verifikasi anda"`, sedangkan halaman berbunyi
   *"Diperlukan Verifikasi Tambahan"*. Celah ini ditutup di bagian ini.

| Gejala | Penyebab | Perbaikan | Status |
|---|---|---|---|
| Riset Indeed 1/180, 0 lowongan, ±5943 detik | Bot menunggu 60 detik lalu lanjut ke kombinasi berikutnya; tantangan Cloudflare muncul di semua kombinasi | `PENANDA_BLOKIR_CLOUDFLARE` (teks + judul tab) dan `_laporkan_blokir()`; blokir dihitung sebagai captcha yang sudah mencapai batas sehingga riset berhenti **seketika** | FIXED + TESTED (`tests/test_indeed_blokir_cloudflare.py`) |
| Alasan "tombol Lamar tidak ditemukan" menyesatkan | Halaman lowongan juga halaman tantangan | `IndeedApplier._blocker()` mendeteksi Cloudflare lebih dulu dan melaporkan penyebab sebenarnya | FIXED + TESTED |
| Tidak ada bukti saat diblokir | Tidak ada penyimpanan pada jalur blokir | `simpan_diagnosa("blokir-cloudflare", …)` sekali per sesi (HTML + PNG) | FIXED + TESTED |

Batas jujur: blokir Cloudflare **tidak bisa dilewati kode**. Yang dijamin di
sini hanya: dikenali dengan benar, berhenti cepat, bukti tersimpan, dan
instruksi jelas. Lolos/tidaknya bergantung pada reputasi IP dan profil Chrome —
bila verifikasi berulang di Chrome biasa sekalipun, itu penilaian jaringan,
bukan bug aplikasi.

Tes: 746 → **757 passed, 1 skipped** (+11), gate ruff bersih.

---

## 17. Paritas kombinasi riset Glints = JobStreet

Permintaan pemakai: jumlah kombinasi riset Glints disamakan dengan JobStreet.
Sebelumnya Glints hanya mencari per kata kunci (URL explore tanpa lokasi),
jadi 20 kata kunci = 20 pencarian, sementara JobStreet 20 kata kunci x
9 lokasi = 180 kombinasi. Itu juga sebabnya JobStreet mengumpulkan 3304
lowongan dan Glints 1059.

| Perubahan | Rincian |
|---|---|
| URL per lokasi | `.../explore?keyword=…&countryCode=ID&location=…` (plus satu bentuk cadangan) dicoba lebih dulu |
| Kombinasi | `kumpulkan_lowongan()` dan loop riset `jalankan_glints()` kini `kata kunci × lokasi`, sama seperti JobStreet |
| Cache | kunci cache membedakan lokasi, jadi hasil satu kota tidak menimpa kota lain |
| Fallback aman | bila Glints mengabaikan `location` (tidak ada kartu), bot menandai `lokasi_didukung = False`, kembali ke pencarian nasional per kata kunci, dan **melewati sisa lokasi** supaya tidak mengulang kartu yang sama (bukan 9x kerja sia-sia) |
| Tampilan | `glints run` mencetak "X kata kunci x Y lokasi = Z kombinasi" dan memberi tahu bila lokasi diabaikan |

Batas jujur: dukungan parameter `location` di Glints **belum diuji di situs
sungguhan** (tes memakai driver tiruan). Bila diabaikan, perilaku kembali
seperti sebelumnya tanpa kerugian — hanya satu pesan tambahan di terminal.

Tes: 757 → **767 passed, 1 skipped** (+10 di `tests/test_glints_lokasi.py`),
ditambah penyesuaian 6 tes lama yang memakai bot tiruan (tanda tangan
`cari()` kini menerima `location`). Gate ruff bersih.

---

## 18. Profil Chrome terkunci: Chrome bot dibiarkan hidup, dua situs hangus

Gejala dari log sesi 2026-11-13 (`run --situs semua`, versi `f1e04f0`):

- JobStreet selesai: 24 terkirim dari kuota 50.
- Glints: "Profil masih terkunci setelah 8 detik" (2x), "Chrome instance
  exited", lalu pindah ke `chrome-profile-baru` dan berhenti dengan
  "Login Glints belum selesai" → **0 lamaran**.
- Indeed: memakai profil baru yang sama (belum login), lalu diblokir
  Cloudflare pada kombinasi 1/180 → **0 lowongan**.

Penyebabnya bukan login, bukan selector, melainkan satu baris di
`browser.tutup_chrome()`:

| Gejala | Penyebab | Perbaikan |
|---|---|---|
| Chrome buatan bot dibiarkan hidup setelah JobStreet | `tutup_chrome()` memutuskan "jangan tutup" dari **nilai** `CHROME_DEBUG_PORT`, bukan dari **hasil** menempel. Menempel gagal (Chrome debug belum jalan) → bot membuka Chrome sendiri → Chrome itu tetap hidup dan memegang `chrome-profile` | Driver hasil menempel ditandai `_dimastes_tertempel`; `tutup_chrome()` memakai tanda itu. Hasil fungsi kini `bool` |
| Pesan "Chrome ditutup." walau Chrome hidup | `scraper.close()` mencetak pesan tanpa memeriksa hasil | Pesan hanya dicetak bila Chrome benar-benar ditutup |
| Profil tetap terkunci walau Chrome sudah ditutup | Batas tunggu 8 detik terlalu pendek | Batas 20 detik |
| Chrome sisa sesi lama (zombie) memegang profil | Tidak ada pembersihan | `tutup_chrome_bot_tertinggal()`: di Windows mencari `chrome.exe` yang **baris perintahnya memuat folder profil bot** lalu `taskkill /F`. Chrome pribadi pengguna (profil lain) tidak tersentuh |
| Situs berikutnya langsung jalan tanpa memeriksa | `lamar_semua.jalankan()` tidak menjeda | `_lepas_profil_sebelum_situs_berikut()`: tunggu 20 dtk → bila masih terkunci, tutup Chrome sisa → tunggu 10 dtk |

Batas jujur: bagian `taskkill` hanya aktif di Windows dan hanya menyasar
proses yang memakai folder profil bot; di Linux/macOS fungsi pembersih itu
mengembalikan 0 (tidak melakukan apa pun). Semua di atas teruji unit dengan
driver tiruan — **belum** diuji pada sesi `run --situs semua` sungguhan.

Tes: 767 → **777 passed, 1 skipped** (+10), gate ruff bersih.

---

## 19. `tarik.bat` menarik cabang lama → perbaikan tidak pernah sampai

Gejala dari terminal pengguna (2026-11-13, sesudah PR #16 di-merge):

```
[2/2] Menggabungkan arena/arena/4ab2b9fa-dimastes ke cabang ini...
Already up to date.
```

`4ab2b9fa` adalah cabang sesi pengembangan lama yang **sudah dihapus** di
GitHub. Variabel `ARENA_CABANG` di terminal pengguna masih menunjuk ke sana
(bawaannya di `pantau.bat`, `pantau.sh`, dan `tarik.sh` juga cabang itu), jadi
`git merge` menjawab "Already up to date" selamanya: PC pengguna tetap
menjalankan kode lama meski semua perbaikan sudah masuk `main`.

| Gejala | Penyebab | Perbaikan |
|---|---|---|
| "Already up to date" padahal ada perbaikan | Bawaan `ARENA_CABANG` = cabang sesi lama | Bawaan diganti `main` di `tarik.bat`, `tarik.sh`, `pantau.bat`, `pantau.sh`, dan `lamar_semua.CABANG_BAKU` |
| Nilai lama masih terpasang di terminal pengguna | Tidak ada pemeriksaan | Jaring pengaman: bila `HEAD` tertinggal dari `arena/main`, `main` ikut digabung |
| Pengguna tidak tahu versi yang dipakai | Skrip tidak mencetak commit | `tarik.bat` mencetak `Versi sekarang: <commit> - <judul>`; `perbarui_kode()` mengembalikan commit yang sama |

Selain itu, log menunjukkan pengguna menekan Ctrl+C saat
`[2/3] Memasang dependensi (sekali saja, mohon tunggu)...` karena layar diam
(pip dijalankan dengan `--quiet`). Sekarang pip menampilkan progres, ditambah
peringatan "2-5 menit, JANGAN tekan Ctrl+C".

Batas jujur: venv di PC pengguna memakai **Python 3.15**, di luar dukungan
resmi skrip (3.10-3.13). Instalasi berhasil atau tidak pada 3.15 belum
terverifikasi; disarankan memasang Python 3.12.

Tes: 777 → **784 passed, 1 skipped**, gate ruff bersih.

---

## 20. `chrome-debug.bat` selalu membuka Glints

Gejala: pengguna menjalankan `chrome-debug.bat` untuk menguji **Indeed**, tetapi
jendela Chrome yang terbuka memuat halaman Glints. URL-nya memang ditulis tetap
di skrip (`glints.com/id/opportunities/jobs/explore?...`), sisa dari saat skrip
ini dibuat khusus untuk Glints.

| Perubahan | Rincian |
|---|---|
| Argumen situs | `chrome-debug.bat [port] [situs]`, bawaan **indeed** |
| Pilihan | `indeed`, `glints`, `jobstreet`, `kosong` (about:blank), atau URL penuh |
| Petunjuk ikut situs | Perintah `diagnosa`/`run` yang dicetak menyesuaikan situs |
| Tetap sama | Port debug (bawaan 9222) dan profil `~/.dimastes/chrome-debug` yang terpisah dari profil bot |

Tes: `tests/test_skrip_windows.py` +4 (bawaan Indeed, situs lain, URL penuh,
perintah uji per situs). Gate ruff bersih.
