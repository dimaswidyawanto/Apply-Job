# dimastes — JobStreet Job Review Assistant

Alat bantu (Bahasa Indonesia) untuk mencari lowongan di
[id.jobstreet.com](https://id.jobstreet.com) **mulai dari yang paling baru
diposting**, menyaringnya sesuai kriteria Anda, lalu:

- **mode manual** — setiap lowongan dibuka di Chrome agar Anda tinjau dan
  kirim lamarannya sendiri, atau
- **mode otomatis** — bot menekan Lamar/Lanjutkan/Kirim lamaran sendiri.
  Bila alur tidak bisa dipastikan (lamaran lewat situs perusahaan, perlu
  unggah berkas, ada pertanyaan wajib), lowongan dikembalikan ke Anda
  sebagai daftar "perlu dilamar manual".

Program tidak menyimpan password JobStreet; login tetap Anda lakukan sendiri
di browser.

> **Penting:** melamar otomatis berarti mengirim lamaran tanpa Anda baca
> dulu. Pastikan CV dan profil JobStreet sudah benar, gunakan batas harian
> yang wajar, dan sadari bahwa otomatisasi dapat melanggar ketentuan layanan
> JobStreet (risiko akun dibatasi). Gunakan dengan tanggung jawab sendiri.

## Fitur

- Mencari lowongan berdasarkan daftar kata kunci dan **banyak lokasi**
  sekaligus (Bandung, Jakarta, Tangerang, Jababeka, Cimahi, Purwakarta,
  Bogor, dan seterusnya).
- Menyimpan lowongan ke SQLite agar tidak diproses dua kali.
- Lowongan yang sudah berlabel **"Applied"/"Anda sudah melamar"** di JobStreet
  otomatis dilewati: tidak ditampilkan lagi, tidak dilamar ulang, dan tidak
  memakan kuota harian.
- Menyaring lowongan: **judul harus cocok dengan minat**, kata kunci
  terlarang, posisi terlalu senior, gaji minimum, batas pengalaman, umur
  lowongan, dan (opsional) lokasi ketat.
- Hasil pencarian diurutkan **dari yang terbaru** (`sortmode=ListedDate`),
  dengan opsi hanya mengambil lowongan N hari terakhir.
- Memeringkat lowongan: yang terbaru didahulukan, lalu skor relevansi.
- Mode manual: halaman lowongan dibuka di Chrome, Anda yang melamar.
- Mode otomatis (`run --auto`): klik Lamar → Lanjutkan → Kirim lamaran,
  dengan pengaman dan batas per sesi.
- **Sesi login tersimpan** di profil Chrome khusus, jadi login hanya sekali
  (tidak setiap kali menjalankan).
- **Mode otomatis adalah default**: `python cli.py run` langsung melamar
  otomatis. Isian cover letter dan unggah CV juga otomatis bila
  `COVER_LETTER`/`RESUME_PATH` diisi.
- Mencatat lamaran yang sudah dikirim beserta batas harian.
- Blacklist perusahaan dan notifikasi Telegram (opsional).
- Laporan singkat di akhir sesi: `python cli.py stats`, `history`, `config`.
- Perintah `python cli.py repair` untuk merapikan data lama (judul kosong,
  status tidak seragam, baris lamaran ganda).

## Kebutuhan

- Python **3.10+**
- Google Chrome (Selenium 4.6+ mengunduh ChromeDriver otomatis)
- Koneksi internet

## Cara cepat (disarankan)

Skrip bantu sudah disiapkan: ia membuat `.venv`, memasang dependensi,
menyalin `.env.example` menjadi `.env` (sekali), lalu menjalankan perintah.

**Windows** — letakkan folder proyek di tempat biasa (misalnya
`C:\Users\NamaAnda\Documents\dimastes`, **bukan** di `C:\WINDOWS`), buka
PowerShell/Command Prompt di folder itu, lalu:

```powershell
.\jalankan.bat config
.\jalankan.bat run
```

Di Command Prompt lama, `.\` boleh dihilangkan (`jalankan.bat run`).
**Bila `tarik.bat` mencetak `'gabungan' is not recognized as an internal or
external command`**, itu bug lama pada skrip: berkas batch berakhir baris LF
sehingga `cmd.exe` melompat ke tengah baris. Sudah diperbaiki — semua `.bat`
kini memakai CRLF dan `tarik.bat` tidak lagi memakai label `goto`. Cukup tarik
versi baru sekali lagi.

**Bila `tarik.bat` berhenti dengan “Your local changes to the following
files would be overwritten by merge”**, artinya ada berkas yang kamu ubah
sendiri (mis. `.github/copilot-instructions.md`). Versi baru `tarik.bat` sudah
menyimpan perubahan itu otomatis lewat `git stash` lalu mengembalikannya.
Untuk versi lama, lakukan sekali secara manual:

```powershell
git stash push -m "sebelum tarik"
.\tarik.bat
git stash pop
```

Di **PowerShell** awalan `.\` wajib — kalau tidak, muncul
`tarik.bat : The term 'tarik.bat' is not recognized...` karena PowerShell
tidak menjalankan perintah dari folder aktif. Nama folder boleh memuat
spasi (mis. `C:\Dimas\Lamar otomatis Jobstreet dan Glints`).

**macOS / Linux**:

```bash
chmod +x jalankan.sh
./jalankan.sh config
./jalankan.sh run
```

Argumen apa pun diteruskan ke `cli.py`, misalnya
`jalankan.bat history --limit 10` atau `jalankan.bat repair`.

## Instalasi manual

```bash
git clone https://github.com/dimasw1997/dimastes.git
cd dimastes

python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

## Konfigurasi

Semua pengaturan dibaca dari file `.env` di folder proyek. Kunci yang belum
ada di `.env` (misalnya setelah pembaruan versi) otomatis memakai nilai dari
`.env.example`, jadi Anda tidak perlu menyalin ulang file contoh. Mulai dari
contoh:

```bash
cp .env.example .env
```

| Variabel | Default | Keterangan |
| --- | --- | --- |
| `KEYWORDS` | 14 kata kunci (inventory, PPIC, gudang, purchasing, ...) | Kata kunci pencarian di JobStreet, dipisah koma |
| `LOCATIONS` | kosong | Daftar lokasi dipisah koma, mis. `Bandung,Jakarta,Tangerang` |
| `LOCATION` | `Bandung` | Dipakai hanya bila `LOCATIONS` kosong |
| `ALLOW_REMOTE` | `false` | `true` = lowongan "Remote" juga diterima saat `STRICT_LOCATION` aktif |
| `REQUIRE_KEYWORD_MATCH` | `true` | Hanya lamar lowongan yang judulnya cocok dengan minat |
| `TITLE_KEYWORDS` | 43 kata kunci (inventory, gudang, ppic, logistik, ...) | Kata kunci pencocok **judul**; kosong = ikut `KEYWORDS` |
| `MIN_SALARY` | `0` | Gaji minimum (0 = tanpa filter) |
| `MAX_EXPERIENCE_YEARS` | `5` | Tolak lowongan yang minta pengalaman lebih dari ini |
| `BLACKLIST_COMPANIES` | kosong | Perusahaan yang tidak ingin dilamar (dipisah koma, cocok longgar) |
| `BLOCKED_COMPANIES` | `royal abadi,ifa` | Perusahaan yang **selalu** ditolak di JobStreet maupun Glints. Nama pendek seperti `ifa` dicocokkan per kata, jadi `Kafifa` tidak ikut tertolak |
| `GLINTS_MIN_SALARY` | `4500000` | Khusus Glints: lamar hanya bila gaji bisa mencapai angka ini. Lowongan yang tidak mencantumkan gaji **tetap** dilamar; `0` = tanpa batas |
| `EXCLUDE_KEYWORDS` | `principal,director,head,senior,lead` | Kata yang membuat judul otomatis ditolak |
| `STRICT_LOCATION` | `false` | `true` = tolak lowongan yang lokasinya di luar `LOCATION` |
| `REQUIRE_COMPANY_LOGO` | `false` | JobStreet **dan** Glints: `true` = hanya lamar lowongan yang kartunya menampilkan **logo perusahaan**; tanpa logo dilewati |
| `MAX_APPLY_PER_DAY` | `0` | Batas **lamaran yang dikirim** per hari (mis. `50`); `0` = tanpa batas. Riset & penilaian tetap tanpa batas |
| `DELAY_BETWEEN_APPLY` | `3` | Jeda (detik) antar lowongan |
| `MAX_PAGES` | `3` | Jumlah halaman per kata kunci untuk mode lama (`COLLECT_BEFORE_APPLY=false`) dan `cek-logo` |
| `RESEARCH_KEYWORDS` | kosong | Kata kunci **khusus riset** (boleh lebih lebar dari `KEYWORDS`); kosong = ikut `KEYWORDS`. Semua kata kunci dicari di semua lokasi |
| `RESEARCH_MAX_PAGES` | `5` | Halaman riset untuk **setiap kombinasi kata kunci × lokasi**: halaman 1–5 lalu berhenti. Maksimal **5** (batas tetap); `0` atau nilai di atas 5 tetap dipakai sebagai 5, boleh diturunkan |
| `RESEARCH_MAX_JOBS` | `0` | Batas jumlah lowongan hasil riset (pengaman). `0` = tanpa batas — **riset tidak dibatasi 50** |
| `SEARCH_WAIT` | `12` | Detik menunggu kartu lowongan muncul sebelum halaman dianggap kosong. Makin kecil makin cepat, tetapi halaman yang sangat lambat bisa terlewat (3–20) |
| `SKILL_KEYWORDS` | inventory, sap, erp, excel, ppic, ... | Keterampilan yang dicari di deskripsi untuk skor kesesuaian keterampilan |
| `HEADLESS_MODE` | `false` | `true` = Chrome tanpa jendela (tidak cocok untuk tinjau manual) |
| `TELEGRAM_BOT_TOKEN` | kosong | Opsional, untuk notifikasi |
| `TELEGRAM_CHAT_ID` | kosong | Opsional, untuk notifikasi |
| `COLLECT_BEFORE_APPLY` | `true` | `true` = **riset dulu**: kumpulkan → dedup → nilai → peringkat → TOP 50 → lamar. `false` = lamar sambil mencari (hanya bila `MAX_APPLY_PER_DAY=0`) |
| `RANK_BY` | `relevance` | Urutan pemilihan saat `COLLECT_BEFORE_APPLY=true`: `relevance` = kecocokan tertinggi dulu, `newest` = posting terbaru dulu |
| `SORT_MODE` | `ListedDate` | Urutan hasil; `ListedDate` = terbaru dulu, `KeywordRelevance` = relevansi |
| `PREFER_NEWEST` | `true` | Dahulukan lowongan paling baru saat antrean melamar |
| `MAX_AGE_DAYS` | `0` | Hanya lowongan N hari terakhir (0 = semua). Nilai valid JobStreet: 1, 3, 7, 14, 31 |
| `USE_PROFILE` | `true` | Simpan sesi login di profil Chrome khusus |
| `CHROME_PROFILE_DIR` | `~/.dimastes/chrome-profile` | Lokasi profil Chrome |
| `LOGIN_WAIT` | `true` | `false` = jangan menunggu; berhenti bila belum login |
| `LOGIN_TIMEOUT` | `300` | Lama menunggu login di Chrome (detik) |
| `AUTO_APPLY` | `true` | Kirim lamaran otomatis; pakai `run --manual` untuk meninjau sendiri |
| `COVER_LETTER` | kosong | Teks cover letter/pesan yang diisi otomatis |
| `RESUME_PATH` | kosong | Path berkas CV untuk unggah otomatis |
| `AUTO_APPLY_MAX_PER_SESSION` | `0` | Batas lamaran per sesi; `0` = tanpa batas |
| `AUTO_APPLY_STEP_TIMEOUT` | `3` | Batas detik mengenali tiap langkah; lewat itu lowongan dilewati |
| `AUTO_ANSWER_QUESTIONS` | `true` | Jawab otomatis pertanyaan dropdown (pengalaman, gaji, pendidikan) |
| `AUTO_ANSWER_WAIT` | `20` | Bila ada kuesioner yang tak bisa dijawab otomatis: beri waktu sekian detik agar Anda mengisi di Chrome, lalu bot melanjutkan sendiri. `0` = langsung dilewati |
| `EXPECTED_SALARY` | `5000000` | Gaji yang diharapkan (kosong = pertanyaan gaji dilewati) |
| `YEARS_EXPERIENCE` | `3` | Total pengalaman kerja (tahun) untuk pertanyaan pengalaman |
| `EXPERIENCE_ROLES` | inventory, ppic, gudang, purchasing, ... | Bidang pengalaman Anda; di luar daftar ini dijawab 0 tahun |
| `AUTO_ANSWER_YES` | `true` | Jawab **Ya** untuk pertanyaan ya/tidak seputar kesediaan/pengalaman |
| `INGAT_JAWABAN` | `true` | Ingat isian yang Anda lakukan sendiri dan pakai lagi otomatis di lamaran berikutnya |
| `EDUCATION_LEVEL` | `S1` | Jenjang pendidikan untuk pertanyaan kualifikasi |
| `AUTO_APPLY_SUBMIT_TIMEOUT` | `20` | Batas detik khusus halaman **Review and submit** (mengirim lamaran) |
| `AUTO_APPLY_DEBUG` | `true` | Simpan HTML + screenshot halaman yang tak dikenali ke folder `debug/` |
| `DB_PATH` | `jobstreet_auto.db` | Lokasi file database |

## Cara pakai

```bash
# 1. Lihat konfigurasi yang benar-benar terbaca
python cli.py config

# 2a. Jalankan pencarian + kirim lamaran otomatis (default)
python cli.py run

# 2b. Meninjau sendiri (tanpa mengirim otomatis)
python cli.py run --manual

# Hanya lowongan 3 hari terakhir, 5 halaman per kata kunci (mode lama)
python cli.py run --auto --max-age-days 3 --max-pages 5

# Riset 5 halaman per kombinasi kata kunci x lokasi (bawaan) atau 2 halaman
python cli.py run --auto --riset-pages 5
python cli.py run --auto --riset-pages 2

# Lokasi lain tanpa mengubah .env
python cli.py run --auto --locations "Bandung,Jakarta,Tangerang,Jababeka"

# 3. Lihat hasil
python cli.py stats
python cli.py history --limit 20

# 4. Blacklist perusahaan (cocok longgar, termasuk variasi nama)
python cli.py blacklist "royal abadi" --reason "mantan perusahaan"

# 5. Rapikan data lama
python cli.py repair

# 5b. Samakan kata kunci di .env dengan daftar terbaru (cadangan: .env.bak)
python cli.py perbarui-env

# 5c. Ubah nilai di .env tanpa membuka editor
python cli.py set-env MAX_APPLY_PER_DAY=0 AUTO_APPLY_MAX_PER_SESSION=0

# 5d. Kirim perubahan ke GitHub dengan satu perintah
.\simpan.bat              # Windows
./simpan.sh             # macOS/Linux

# 6. Uji alur lamaran dengan halaman palsu (tanpa Chrome, tanpa internet)
python cli.py simulasi

# 7. Uji alur lamaran pada satu lowongan (tanpa pencarian/filter)
python cli.py uji-lamar --url "https://id.jobstreet.com/job/95549275"

# 8. Periksa deteksi logo perusahaan pada kartu JobStreet
python cli.py cek-logo --limit 10
```

`uji-lamar` membuka satu lowongan, menjalankan alur lamaran otomatis, lalu
mencetak setiap langkah (tombol yang diklik, deteksi halaman "Review and
submit", status akhir). Berguna untuk memastikan lamaran benar-benar terkirim
tanpa harus menunggu ada lowongan baru yang lolos filter. Baris **Versi kode
(commit)** di `python cli.py config` menunjukkan versi kode yang sedang
dijalankan — samakan dengan commit terakhir di GitHub.

### Kirim perubahan ke GitHub (otomatis)

Perubahan dari sesi pengembangan sudah di-push otomatis ke cabang
`arena/4ab2b9fa-dimastes`. Di PC Anda cukup menariknya:

```bash
git branch --show-current     # pastikan cabangnya benar
git pull
```

Kalau `git branch --show-current` menampilkan `main` padahal pekerjaan terbaru
ada di cabang `arena/4ab2b9fa-dimastes`, `git pull` **tidak** akan menarik apa
pun. Pindah dulu: `git checkout arena/4ab2b9fa-dimastes` lalu `git pull`.

Untuk mengirim perubahan **dari PC ke GitHub** cukup satu klik:

```bash
.\simpan.bat                        # Windows
.\simpan.bat "Pesan commit sendiri" # dengan pesan sendiri
./simpan.sh                       # macOS/Linux
```

Skrip itu menjalankan: bersihkan sisa rebase → `git add -A` → `commit` →
`pull --no-rebase` → `push`. File `.env`, `jobstreet_auto.db`, `debug/`, dan
`pantau.log` otomatis tidak ikut terkirim. Kalau tidak ada perubahan, skrip
hanya menarik lalu mengirim ulang tanpa membuat commit kosong.

Penggabungan memakai *merge*, bukan *rebase*, karena riwayat memuat commit
gabungan dari `tarik.bat` — rebase pada commit gabungan sering gagal dan
meninggalkan folder `.git/rebase-merge` yang membuat semua `pull` berikutnya
ditolak. `simpan.bat`/`simpan.sh` sekarang membersihkan sisa itu otomatis di
awal, jadi kasus tersebut tidak lagi menghentikan pengiriman.

Supaya tidak diminta password setiap kali: pada Windows, Git for Windows
memakai *Git Credential Manager* — login sekali lewat jendela browser, setelah
itu tersimpan. Cek dengan `git config --global credential.helper` (harus
menampilkan `manager`). Bisa juga `gh auth login` sekali saja.

Saat `run` berjalan:

1. Chrome terbuka. Bila sesi belum ada, Anda login di Chrome — **tidak perlu
   menekan apa pun di terminal**, program mendeteksinya sendiri.
2. Setiap lowongan yang lolos filter dibuka satu per satu. Bila nama lokasi
   tidak dikenali JobStreet (mis. *Jababeka* menghasilkan halaman kosong), bot
   otomatis mencoba nama lain (*Cikarang*) dan melewati lokasi itu setelah 3
   kata kunci tanpa hasil.
3. Tinjau di browser. Setelah selesai, kembali ke terminal:
   - tekan **Enter** saja jika lamaran **tidak** dikirim (dicatat `skipped`);
   - ketik **y** jika lamaran benar-benar sudah dikirim (dicatat `applied`).

### Sinkron otomatis dua arah (kirim + tarik)

`pantau` bukan hanya mengirim: saat folder sedang **tidak** ada perubahan
lokal, ia juga menarik pembaruan supaya isi folder selalu sama dengan GitHub.

- **Ada perubahan lokal** → `git add` → commit → tarik → push (lewat `simpan`).
- **Tidak ada perubahan lokal** → periksa `origin` dan repo pengembangan;
  kalau ada commit baru, tarik otomatis (`simpan` untuk origin, `tarik` untuk
  repo pengembangan).
- **Penggabungan bentrok** → dibatalkan otomatis (`git merge --abort`), folder
  tetap utuh, dan dicatat di `pantau.log`. Selesaikan manual dengan `tarik.bat`.
- Berkas yang sedang Anda sunting **tidak** tertimpa, karena penarikan hanya
  dilakukan saat tidak ada perubahan lokal.

Jadi setelah dipasang, folder di VS Code mengikuti GitHub tanpa Anda mengetik
perintah apa pun. VS Code memuat ulang berkas otomatis; bila berkas sedang
Anda ubah dan versinya berbeda, VS Code menampilkan konflik — pilih *Keep
Yours*/*Incoming* sesuai keinginan, lalu simpan.

### Update otomatis ke GitHub setiap ada perubahan

Kalau tidak ingin mengetik perintah, jalankan pemantau di latar belakang:

```bash
.\pantau.bat          # Windows, periksa tiap 60 detik
.\pantau.bat 30       # periksa tiap 30 detik
./pantau.sh         # macOS/Linux
```

Setiap kali ada file yang berubah, `pantau.bat` memanggil `simpan.bat`
(`git add -A` → commit → tarik → push) lalu kembali memantau. Saat tidak ada
perubahan lokal, ia justru memeriksa apakah ada commit baru di GitHub atau di
repo pengembangan dan menariknya otomatis. Berhentikan dengan `Ctrl+C`. File `.env`, `jobstreet_auto.db`, dan `debug/` tetap tidak
pernah ikut terkirim karena ada di `.gitignore`.

**Otomatis penuh — cukup dipasang sekali:**

```bash
pasang-otomatis.bat      # Windows: pasang agar berjalan tiap login
matikan-otomatis.bat     # Windows: lepas lagi
```

Setelah dipasang, setiap Anda login pemantau berjalan **diam-diam tanpa
jendela**:

- perubahan file dikirim ke GitHub otomatis tiap 60 detik (cukup simpan file,
  tidak perlu mengetik perintah git apa pun),
- pembaruan dari GitHub maupun dari repo pengembangan ikut ditarik otomatis
  saat tidak ada perubahan lokal, jadi isi folder selalu terbaru,
- commit yang belum terkirim — mis. push gagal karena internet putus — ikut
  dikirim ulang pada putaran berikutnya,
- catatan aktivitasnya ada di `pantau.log`.

Ingin aktif sekarang tanpa menunggu login: `wscript pantau-diam.vbs`.

**Memeriksa pemantau benar-benar berjalan** (berguna bila folder terasa tidak
ikut berubah):

```powershell
Get-Content .\.pantau-terakhir     # diperbarui tiap putaran (±1 menit)
Get-Content .\pantau.log -Tail 15  # aktivitas terakhir
Get-CimInstance Win32_Process -Filter "Name='wscript.exe' OR Name='cmd.exe'" |
    Where-Object { $_.CommandLine -like '*pantau*' } |
    Select-Object ProcessId, CommandLine
```

Kalau `.pantau-terakhir` tidak berubah dan daftar proses kosong, pemantau
berhenti — jalankan lagi `wscript pantau-diam.vbs`. Berkas jejak ini tidak
pernah ikut ke GitHub (ada di `.gitignore`).

Cara manual (bila tidak ingin skrip): tekan `Win+R`, ketik `shell:startup`,
lalu buat pintasan ke `pantau.bat`.

**Identitas commit.** Supaya commit tercatat atas nama Anda:

```bash
git config user.name "Dimas Widyawanto"
git config user.email "widyawantod@gmail.com"
```

Alamat email itu harus sudah ditambahkan dan **diverifikasi** di
<https://github.com/settings/emails>, kalau tidak commit-nya tidak akan
terhubung ke profil GitHub. Bila ingin menyembunyikan email asli dari riwayat
publik, pakai alamat `...@users.noreply.github.com` yang diberikan GitHub
(hanya commit berikutnya yang berubah; commit lama tetap seperti semula).

### Memakai repo GitHub sendiri (mis. `dimaswidyawanto/Apply-Job`)

Kode ini juga bisa disimpan di repo Anda sendiri. Setelah repo tujuan dibuat
(mis. `https://github.com/<akun>/Apply-Job.git`):

```bash
# 1. Arahkan origin ke repo Anda, lalu kirim seluruh riwayat sebagai main
git remote set-url origin https://github.com/<akun>/Apply-Job.git
git push -u origin arena/4ab2b9fa-dimastes:main

# 2. Pindah ke cabang main yang tadi dikirim
git checkout -B main origin/main
```

Sejak itu `main` adalah salinan penuh di repo Anda, dan `simpan.bat` /
`pantau.bat` mengirim perubahan ke sana.

**Menarik pembaruan dari repo pengembangan** (akun `dimasw1997`) dilakukan
dengan satu perintah; remote `arena` ditambahkan otomatis:

```bash
.\tarik.bat        # Windows
./tarik.sh       # macOS/Linux
```

Alurnya jadi dua arah: `tarik.bat` untuk mengambil pembaruan, `pantau.bat`
untuk mengirim pekerjaan Anda sendiri ke repo Anda.

Bila muncul permintaan login saat push, masuk dengan akun pemilik repo tujuan
(mis. `dimaswidyawanto`). Bila Windows menyimpan kredensial akun lama:

```bash
cmdkey /delete:git:https://github.com
```

lalu push sekali lagi dan ikuti jendela login.

### Uji cepat tanpa Chrome

`python cli.py simulasi` menjalankan enam skenario halaman JobStreet palsu:
lamaran sederhana, pertanyaan pilihan (gaji/pengalaman/pendidikan), langkah
terakhir *Review and submit*, pengalihan ke situs perusahaan, pertanyaan yang
tidak dikenal, dan alur yang tidak dikenali. Hasilnya berupa tabel OK/GAGAL,
selesai dalam hitungan detik, tanpa membuka Chrome dan tanpa internet.

Gunakan ini untuk memastikan pembaruan kode berjalan benar sebelum sesi
lamaran sungguhan.

### Login sekali saja (sesi tersimpan)

Secara default program memakai profil Chrome sendiri di
`~/.dimastes/chrome-profile` (Windows: `C:\Users\NamaAnda\.dimastes\chrome-profile`).
Jadi:

1. Jalankan pertama kali: `python cli.py run --auto`
2. Login di jendela Chrome yang terbuka. Program menunggu dan mendeteksinya
   otomatis (tanpa Enter), maksimal `LOGIN_TIMEOUT` detik.
3. Sesi disimpan. Sesi berikutnya program mendeteksi sudah login dan
   **tidak menanyakan apa pun**.

Program **tidak pernah meminta email atau password JobStreet** — tidak ada
formulir kredensial di mana pun. Semua login terjadi di jendela Chrome milik
Anda, dan hasilnya disimpan sebagai cookie di profil tersebut.

Untuk sesi terjadwal/tanpa orang di depan komputer:

```bash
python cli.py run --auto --no-login-wait
```

Perintah itu langsung berhenti dengan pesan jelas bila sesi sudah kedaluwarsa
(sehingga Anda tahu perlu login sekali lagi), bukan menggantung menunggu.

Opsi lain: `--profile-dir "D:\chrome-dimastes"` untuk lokasi profil lain, dan
`--no-profile` untuk kembali ke profil sementara (selalu login ulang).

Pastikan Chrome lain tidak memakai folder profil yang sama; bila terkunci,
tutup Chrome tersebut atau pakai `--profile-dir` yang berbeda.

Bila sesi JobStreet kedaluwarsa di tengah sesi, program mendeteksinya
(halaman dialihkan ke Sign in) lalu **berhenti** dengan pesan jelas, bukan
mengulang-ulang error. Login sekali lagi, sesi tersimpan kembali.

Ingin memaksa login ulang dari nol? Hapus folder profil:

```powershell
Remove-Item -Recurse -Force "$HOME\.dimastes\chrome-profile"
```

atau jalankan sekali dengan `--no-profile`.

### Banyak lokasi

Isi `.env`:

```
LOCATIONS=Bandung,Jakarta,Tangerang,Jababeka,Cimahi,Purwakarta,Bogor
STRICT_LOCATION=true
```

Pencarian dijalankan **per lokasi** (bukan digabung), lalu hasilnya
digabung dan diurutkan dari yang terbaru. Karena itu:

- Jumlah pencarian = lokasi × kata kunci × halaman. Dengan 7 lokasi,
  8 kata kunci, dan `MAX_PAGES=3` ada 168 pemuatan halaman. Kurangi
  `MAX_PAGES` (mis. 2) atau pakai `--max-age-days 3` agar lebih cepat.
- `STRICT_LOCATION=true` membuang lowongan di luar daftar lokasi. Nama
  wilayah dicocokkan dengan beberapa alias, misalnya **Jababeka** juga
  menerima lokasi *Cikarang* dan *Bekasi*, **Tangerang** menerima
  *Tangerang Selatan/BSD/Serpong*, **Jakarta** menerima *Jakarta
  Selatan/Pusat/Barat/Timur/Utara*.
- Bila JobStreet tidak mengenali nama lokasi (mis. "Jababeka"), hasilnya
  bisa kosong. Coba `--locations "Bandung,Cikarang,Bekasi,..."` atau cek
  sendiri di situs: `https://id.jobstreet.com/jobs?where=Jababeka`.

### Hanya melamar yang Anda minati

Secara default program **hanya melamar lowongan yang judulnya memuat salah
satu `TITLE_KEYWORDS`**. Judul yang nyasar di hasil pencarian — misalnya
"Sales Executive" atau "Staff Accounting" — otomatis dilewati, tidak dilamar.

Ada dua daftar yang dipakai:

| Pengaturan | Fungsi | Pengaruh ke waktu |
| --- | --- | --- |
| `KEYWORDS` | query yang diketik ke pencarian JobStreet | **menambah** waktu (dijalankan per lokasi, per halaman) |
| `TITLE_KEYWORDS` | hanya mencocokkan judul hasil pencarian | tidak menambah waktu sama sekali |

Karena itu daftar bawaan dibuat dua lapis: `KEYWORDS` 14 istilah pencarian,
`TITLE_KEYWORDS` 43 istilah pencocok judul yang disusun dari pengalaman
PPIC/inventory, gudang, material/pengadaan, dan supply chain — termasuk versi
bahasa Indonesia (`staf gudang`, `admin inventory`, `persediaan`,
`perencanaan produksi`, `pengadaan`, `logistik`, ...). Contoh judul yang lolos:
*Staff PPIC*, *Staf Gudang*, *Warehouse Supervisor*, *Production Planner*,
*Material Control Staff*, *Purchasing Staff*, *Demand Planner*,
*Project Control*. Yang tetap ditolak: *Operator Produksi*,
*Financial Planner*, *Media Buyer*, *Quantity Surveyor*.

Setelah `git pull`, samakan kata kunci di `.env` Anda dengan daftar terbaru:

```bash
python cli.py perbarui-env
```

Perintah itu hanya mengganti baris `KEYWORDS` dan `TITLE_KEYWORDS` di `.env`
(cadangan otomatis di `.env.bak`); cover letter, path CV, token Telegram, dan
isian lain tidak disentuh. Setelah itu jalankan ulang program.

Ingin menambah sendiri? Tambahkan istilah dipisah koma, mis.
`TITLE_KEYWORDS=...,staf gudang,admin produksi,persediaan`.
Ingin mematikan filter ini (lamar semua yang muncul)?
`REQUIRE_KEYWORD_MATCH=false`.

### Hanya perusahaan yang menampilkan logo (JobStreet)

Sebagian lowongan di JobStreet menampilkan **logo perusahaan** di kanan atas
kartu; sebagian lagi tidak. Bila ingin hanya melamar lowongan yang ada
logonya:

```bash
python cli.py cek-logo            # periksa dulu apa yang terdeteksi
python cli.py cek-logo --limit 20 --keywords "ppic,inventory"
python cli.py set-env REQUIRE_COMPANY_LOGO=true
```

Aturan ini berlaku untuk **JobStreet maupun Glints** — keduanya memakai
penilai logo yang sama (`logo_perusahaan`), hanya sumber gambarnya berbeda
(kartu JobStreet vs kartu Glints). Untuk Glints, deteksinya bisa dilihat
langsung lewat kolom **Logo** pada `python cli.py glints cari`; tambahkan
`--semua` bila ingin melihat kartu yang tersaring oleh aturan ini.

`cek-logo` membuka pencarian JobStreet seperti biasa (perlu login, sama seperti
`run`),
lalu menampilkan tabel: judul, perusahaan, **ada logo atau tidak**, dan
keterangan cara deteksinya. Contoh keluaran:

```
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━┳━━━━━━┳━━━━━━━━━━━━━━━━━━━━━┓
┃ Judul                        ┃ Perusahaan      ┃ Logo ┃ Keterangan          ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━╇━━━━━━╇━━━━━━━━━━━━━━━━━━━━━┩
│ Admin PPIC GARMENT           │ Trackerindo ... │  ya  │ penanda 'company... │
│ Staf Gudang                  │ PT Tanpa Logo   │ tidak│ 2 gambar tanpa logo │
└──────────────────────────────┴━━━━━━━━━━━━━━━━━┵──────┴─────────────────────┘
2 dari 12 kartu terdeteksi berlogo perusahaan.
```

Deteksinya berlapis, karena JobStreet bisa mengubah penanda HTML-nya:
penanda `data-automation`/`data-testid`/`alt` yang memuat kata *logo*, URL
gambar yang memuat *logo*/*brand*, atau teks alternatif gambar yang memuat
**nama perusahaan**. Gambar yang jelas ikon/placeholder (mis. `icon`,
`placeholder`, `sprite`) tidak dihitung logo.

Dengan `REQUIRE_COMPANY_LOGO=true`, lowongan tanpa logo **dilewati** dan
alasannya tampil di terminal (`Dilewati: … — Tanpa logo perusahaan`). Situs
lain — Glints — tidak terpengaruh karena tidak mengisi informasi logo.

Bila `cek-logo` menampilkan **tidak** untuk semua kartu padahal di situs
logonya terlihat, berarti aturan perlu disesuaikan: kirimkan tabel itu (kolom
*Keterangan* yang penting). Saat `run` berjalan, program juga memberi
peringatan sekali bila satu halaman penuh kartu terbaca tanpa logo, supaya
filter tidak diam-diam membuang semua lowongan.

### Pertanyaan pilihan dari perusahaan

Banyak lowongan menambahkan pertanyaan wajib: dropdown, radio ya/tidak, atau
kolom isian. Bot membacanya dari label/aria/legend di sekitar kolom — **bukan**
dari atribut `name` yang hanya berisi ID internal seperti
`questionnaire.ID_Q_...`.

| Pertanyaan | Jawaban bot |
| --- | --- |
| Gaji ("berapa gaji yang diharapkan?") | opsi/kolom terdekat dengan `EXPECTED_SALARY` |
| Pengalaman pada jabatan yang pernah dipegang (staff, inventory controller, PPIC, planner) | opsi berisi `YEARS_EXPERIENCE`, atau angka itu pada kolom isian |
| Pengalaman jabatan lebih tinggi (Kepala/Head/Manager/Supervisor) | 0 tahun / belum ada pengalaman |
| Pengalaman di bidang di luar `EXPERIENCE_ROLES` (mis. *Pharmacist in Charge*, *Recruitment*) | 0 tahun / *No experience* — tidak diklaim 3 tahun |
| Pendidikan/kualifikasi | opsi sesuai `EDUCATION_LEVEL` (mis. *Sarjana (S1)*) |
| Ya/tidak seputar kesediaan atau pengalaman ("apakah kamu bersedia…", "have you…") | **Ya** (matikan dengan `AUTO_ANSWER_YES=false`) |
| Pola lain | tidak ditebak — lowongan dilewati, alasannya ditulis apa adanya |

Setiap jawaban tercetak di terminal, misalnya
`jawab "3 years" untuk: Berapa tahun pengalaman kerjamu sebagai Inventory Controller?`.
Bila formulir tetap ditolak, bot berhenti setelah 2 kali klik **Lanjutkan** pada
halaman yang sama dan menampilkan pesan validasi dari JobStreet (tanpa ID
internal).

Matikan semuanya dengan `AUTO_ANSWER_QUESTIONS=false` bila ingin semua
pertanyaan dilewati.

### Kuesioner yang belum terisi: bot menunggu Anda

Tidak semua pertanyaan perusahaan bisa dijawab bot (mis. *"Warna favorit?"*,
atau pertanyaan pilihan yang polanya tidak dikenali). Dulu lowongan seperti itu
langsung dilewati. Sekarang bot memberi Anda waktu untuk mengisinya sendiri:

```
[dim]   belum bisa dijawab otomatis: Warna favorit kamu?
Ada pertanyaan yang belum terisi: Warna favorit kamu?
   Silakan isi di jendela Chrome sekarang — menunggu sampai 20 detik...
   menunggu... sisa 15 detik
   isian sudah lengkap — melanjutkan pengiriman lamaran.
[dim]   klik tombol kirim "Kirim lamaran" (percobaan 1)
Status: applied — Terkirim otomatis
```

Cara kerjanya:

1. Bot mendeteksi ada pertanyaan wajib yang belum terisi (atau formulir menolak
   dikirim karena isian wajib).
2. Pesan muncul di terminal dan bot menunggu sampai `AUTO_ANSWER_WAIT` detik
   (bawaan **20**). Terminal **tidak** meminta Anda menekan apa pun.
3. Isi kuesionernya di jendela Chrome yang sedang terbuka.
4. Bot memeriksa ulang setiap detik: begitu tidak ada pertanyaan tersisa dan
   peringatan validasi hilang, ia melanjutkan sendiri — mengklik **Kirim**.
5. Bila waktu habis dan isian masih kurang, lowongan dilewati seperti biasa
   dan masuk daftar "perlu dilamar manual" di akhir sesi.

Atur lamanya:

```bash
python cli.py set-env AUTO_ANSWER_WAIT=45    # lebih lega, sesi lebih lambat
python cli.py set-env AUTO_ANSWER_WAIT=0     # kembali ke perilaku lama: langsung lewati
```

Tips: jalankan tanpa `HEADLESS_MODE` (bawaan) supaya jendela Chrome terlihat
dan bisa Anda isi. Di mode headless tidak ada yang bisa diklik, jadi biarkan
`AUTO_ANSWER_WAIT=0`.

### Ingatan jawaban: sekali diisi, selamanya otomatis

Setiap isian yang **Anda** lakukan sendiri di formulir dicatat, lalu dipakai
otomatis pada lamaran berikutnya. Jadi kuesioner berulang seperti ini:

> *Seberapa mahir kamu dengan keahlian berikut ini?* — Manajemen Rantai
> Pasokan, Microsoft Excel, Manajemen Persediaan
> (Tidak Berpengalaman / Dasar / Menengah / Ahli)

cukup Anda jawab **sekali**. Lamaran Glints/JobStreet berikutnya terisi sendiri,
dan bot hanya berhenti bertanya untuk pertanyaan yang benar-benar baru.

Yang dicatat: pilihan ganda (radio), dropdown, dan kolom teks — termasuk kolom
gaji, tahun pengalaman, dan pendidikan bila Anda mengubahnya.

Yang **tidak** dicatat: tebakan bot sendiri. Bila bot memilih "Dasar" lalu Anda
mengubahnya menjadi "Ahli", yang diingat adalah "Ahli" (keadaan akhir formulir).

Perubahan Anda juga diingat **walau lamaran tidak selesai**: alur yang berakhir
"perlu manual", galat, atau waktu tunggu habis tetap merekam isian yang sempat
Anda ubah. Begitu juga di mode manual `AUTO_APPLY=false` — setelah Anda meninjau
halaman lowongan dan menekan Enter di terminal, isian yang Anda lakukan ikut
disimpan.

Kelola ingatannya:

```bash
python cli.py jawaban                                  # lihat semua
python cli.py jawaban --isi "Microsoft Excel=Ahli"     # isi manual
python cli.py jawaban --hapus "Microsoft Excel"        # hapus satu
python cli.py jawaban --reset                          # kosongkan
```

Matikan fitur ini dengan `python cli.py set-env INGAT_JAWABAN=false` bila ingin
bot kembali menebak dari aturan bawaan setiap kali.

Pencocokan pertanyaan tidak peka huruf besar/kecil, spasi ganda, atau tanda
baca, dan masih mengenali pertanyaan yang berubah sedikit (kemiripan teks
≥ 86%). Pertanyaan berbeda tetap dianggap berbeda — "Manajemen Rantai Pasokan"
tidak akan memakai jawaban "Manajemen Persediaan".

### Isian lamaran otomatis

Bila formulir meminta cover letter atau berkas CV, isi dulu di `.env`:

```
COVER_LETTER=Saya tertarik pada posisi ini dan siap bergabung.\nTerima kasih.
RESUME_PATH=C:\Users\NAMA\Documents\cv.pdf
```

Program akan mengisi textarea kosong dan mengunggah berkas tersebut secara
otomatis, lalu melanjutkan klik Kirim lamaran. Tanpa konfigurasi ini,
lowongan yang meminta isian khusus akan **dilewati** (bukan diminta dikerjakan
manual).

Pertanyaan pilihan wajib dari perusahaan (radio/select) **tidak** ditebak
jawabannya, karena salah jawab lebih merugikan daripada tidak melamar.
Lowongan seperti itu dilewati otomatis dan hanya dicatat di akhir sesi.

### Mode otomatis (default)

`python cli.py run` sudah otomatis. Gunakan `run --manual` hanya bila ingin
meninjau sendiri.

1. Bot membuka halaman lowongan, lalu mencari tombol **Lamar**.
2. Bila muncul langkah berikutnya (**Lanjutkan/Kirim lamaran**), bot menekan
   otomatis sampai muncul konfirmasi "lamaran telah dikirim". Di halaman
   terakhir **Review and submit** bot mencari tombol kirim dengan cakupan lebih
   luas dan memberi waktu `AUTO_APPLY_SUBMIT_TIMEOUT` detik (default **20**),
   jadi langkah final ini tidak ikut dibatalkan oleh batas 3 detik.
3. Lamaran hanya dicatat `applied` **setelah** konfirmasi itu terlihat.
4. Lowongan **dilewati** (tanpa jeda, langsung lanjut ke berikutnya) bila:
   - lamaran **dialihkan ke situs lain** — baik lewat tombol
     "Lamar di situs perusahaan", tab baru, maupun tab yang sama berpindah
     domain ke ATS perusahaan (Workday, Lever, dll.);
   - alur tidak dikenali dalam `AUTO_APPLY_STEP_TIMEOUT` detik (default **3**);
   - formulir meminta unggah berkas **wajib** (`required`), pertanyaan pilihan
     yang polanya tidak dikenali (lihat *Pertanyaan pilihan dari perusahaan*),
     atau pertanyaan wajib yang belum diisi otomatis (`COVER_LETTER`/`RESUME_PATH` kosong),
     atau pertanyaan pilihan dari perusahaan yang jawabannya tidak boleh
     ditebak. Bagian "Documents included" yang sifatnya opsional tidak
     menghalangi pengiriman.
5. Di akhir sesi muncul daftar lowongan yang dilewati beserta alasannya —
   hanya informasi, tidak perlu Anda kerjakan.

Batas pengaman: `MAX_APPLY_PER_DAY` (harian, bawaan **0** = tanpa batas),
`AUTO_APPLY_MAX_PER_SESSION` (per sesi, bawaan **0** = tanpa batas), dan
`DELAY_BETWEEN_APPLY` (jeda antar lamaran, tetap **3** detik agar tidak
terlihat seperti bot).

Dengan kedua batas `0`, sesi berjalan sampai lowongan habis atau Anda
menghentikannya (Ctrl+C). Untuk memasang batas lagi:

```bash
python cli.py set-env MAX_APPLY_PER_DAY=100 AUTO_APPLY_MAX_PER_SESSION=50
```

### Riset sebanyak mungkin → nilai → peringkat → TOP 50 → apply

**50 adalah batas lamaran per hari, bukan batas riset.** Riset dibatasi
**halaman**, bukan jumlah lowongan: maksimal 5 halaman untuk setiap kombinasi
kata kunci × lokasi. Alur yang dijalankan setiap `run`:

```
Riset sebanyak mungkin → gabung semua hasil → hapus duplikat →
nilai kecocokan → peringkat → ambil TOP 50 → apply maksimal 50/hari
```

1. **Riset.** Setiap kata kunci (`RESEARCH_KEYWORDS`, atau `KEYWORDS` bila
   kosong) dicari di **setiap** lokasi (`LOCATIONS`). Untuk setiap kombinasi
   kata kunci × lokasi dibuka **halaman 1 → 5 berurutan, lalu berhenti** —
   halaman 6 dan seterusnya tidak pernah dibuka, langsung lanjut ke kata
   kunci/lokasi berikutnya. Batas 5 halaman berlaku **independen** untuk tiap
   kombinasi dan tidak bisa dinaikkan (`RESEARCH_MAX_PAGES` hanya boleh
   menurunkan). `SORT_MODE=ListedDate` membuat yang **paling baru** muncul
   lebih dulu. Pencarian satu kombinasi berhenti lebih awal bila halamannya
   kosong / tidak ada lowongan baru, atau bila `RESEARCH_MAX_JOBS` (opsional)
   tercapai.
2. **Gabung & hapus duplikat.** Hasil semua kategori dan lokasi digabung;
   lowongan yang sama (ID/URL sama, atau judul + perusahaan + lokasi sama)
   hanya dihitung sekali. Yang sudah pernah dilamar juga dilewati.
3. **Penilaian.** Setiap lowongan dinilai per dimensi:
   `posisi` (kata kunci di judul), `lokasi`, `kualifikasi` (bidang yang
   diminta), `pengalaman`, `pendidikan`, `keterampilan` (`SKILL_KEYWORDS`),
   `tanggal` (makin baru makin tinggi), dan `gaji`. Data yang tidak tercantum
   di kartu tidak dihukum.
4. **Peringkat.** `RANK_BY=relevance` (bawaan) = skor tertinggi dulu, bila
   sama yang paling baru. `RANK_BY=newest` = tanggal terbaru dulu.
5. **TOP 50.** Sisa kuota hari ini = `MAX_APPLY_PER_DAY` − lamaran yang sudah
   terkirim hari ini. Hanya **sebanyak sisa kuota** kandidat teratas yang
   dilamar — dipilih **global** dari seluruh kategori dan lokasi, bukan 50 per
   kategori/lokasi. Bila kandidat yang memenuhi kriteria kurang dari 50,
   semuanya dilamar.

```bash
python cli.py set-env MAX_APPLY_PER_DAY=50 COLLECT_BEFORE_APPLY=true RANK_BY=relevance
python cli.py run
```

Contoh keluaran:

```
RISET LOWONGAN — 14 kata kunci × 7 lokasi, maksimal 5 halaman per kombinasi kata kunci & lokasi (batas tetap 5), urut tanggal terbaru.
Riset selesai: 412 lowongan terbaca dari 14 kategori × 7 lokasi → 187 unik (225 duplikat dibuang).
Penilaian selesai: 187 lowongan dinilai (posisi, lokasi, kualifikasi, pengalaman,
pendidikan, keterampilan, tanggal, gaji) dan diurutkan dari kecocokan tertinggi.
Kuota harian: 12 sudah dilamar hari ini, sisa 38 dari 50.
187 kandidat (dari seluruh kategori & lokasi) bersaing untuk 38 slot — diambil 38 yang paling cocok.
      Kandidat yang akan dilamar (dibandingkan dari 38)
┏━━━┳━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━┓
┃ # ┃ Skor ┃ Judul                 ┃ Perusahaan    ┃ Umur        ┃
┡━━━╇━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━┩
│ 1 │   42 │ Inventory Controller  │ PT A          │ hari ini    │
│ 2 │   38 │ Staff PPIC            │ PT B          │ 1 hari lalu │
└───┴──────┴───────────────────────┴───────────────┴─────────────┘
            Rincian skor kandidat teratas
┏━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━┳━━━━━━┳━━━━━━┳━━━━━━┳━━━━━━┳━━━━━━┳━━━━━┳━━━━┳━━━━━┓
┃ Judul                ┃ Pos. ┃ Lok. ┃ Kual ┃ Peng ┃ Pend ┃ Kete ┃ Tgl ┃ Gj ┃ Tot ┃
┡━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━╇━━━━━━╇━━━━━━╇━━━━━━╇━━━━━━╇━━━━━━╇━━━━━╇━━━━╇━━━━━┩
│ Inventory Controller │   14 │    8 │    4 │    6 │    4 │    2 │   5 │  5 │  42 │
└──────────────────────┴──────┴──────┴──────┴──────┴──────┴──────┴─────┴────┴─────┘
```

### Berapa lama risetnya, dan cara mempercepat

Waktu riset = **jumlah kombinasi × halaman × biaya per halaman**:

- Jumlah kombinasi = jumlah kata kunci × jumlah lokasi. Bawaannya 14 × 7 = **98 kombinasi**, masing-masing maksimal **5 halaman** → maksimal **490 pemuatan halaman**.
- Biaya satu halaman: buka URL + tunggu kartu muncul (`SEARCH_WAIT`, bawaan 12 detik bila kosong) + 1 detik + pembacaan kartu. Normalnya **4–12 detik** per halaman, jadi sesi penuh biasanya **35–80 menit**.
- Kombinasi yang tidak punya lowongan tetap memakan ±12 detik per halaman (halaman 1 saja, lalu berhenti).
- Fase lamaran menambah: jeda `DELAY_BETWEEN_APPLY` (3 detik) × 50 lamaran, waktu formulir (`AUTO_APPLY_STEP_TIMEOUT` 3 detik per langkah), dan `AUTO_ANSWER_WAIT` (20 detik) setiap kali ada kuesioner yang harus Anda isi sendiri.

Selama riset, kemajuannya dicetak setelah setiap kombinasi sehingga kelihatan sisa waktunya:

```
Kemajuan riset: 12/98 kombinasi, 87 lowongan terkumpul, 6m 20s berlalu — perkiraan sisa 41m 05s.
```

Di akhir riset muncul ringkasan biaya per halaman, untuk mengetahui apakah yang lambat itu situsnya atau jumlah halamannya:

```
Waktu riset: 42m 18s untuk 392 halaman (rata-rata 6,5 detik/halaman, 98 kombinasi kata kunci × lokasi).
```

Cara mempercepat (pilih sesuai kebutuhan):

| Cara | Efek |
| --- | --- |
| `.\jalankan.bat run --riset-pages 3` | 5 → 3 halaman per kombinasi: **−40%** waktu riset |
| Persempit `RESEARCH_KEYWORDS` (mis. 6 kata kunci inti) | 98 → 42 kombinasi: **−55%**, dan karena ada deduplikasi, lowongan unik yang didapat biasanya tidak banyak berkurang |
| `.\jalankan.bat set-env SEARCH_WAIT=8` | Memotong waktu tunggu halaman kosong 12 → 8 detik |
| `.\jalankan.bat set-env HEADLESS_MODE=true` | Chrome tanpa jendela; lebih ringan, cocok untuk sesi panjang |
| `.\jalankan.bat set-env AUTO_ANSWER_WAIT=10` | Memotong waktu tunggu kuesioner per lowongan (20 → 10 detik) |
| `.\jalankan.bat set-env DELAY_BETWEEN_APPLY=2` | Menghemat ±50 detik untuk 50 lamaran |

Catatan: `MAX_APPLY_PER_DAY` adalah batas **per hari kalender** yang dihitung
dari database, jadi menjalankan `run` dua kali dalam sehari tidak menambah
kuota — sisanya yang dipakai. Bila kuota habis, program berhenti dengan pesan
`Kuota lamaran hari ini sudah habis` dan tidak mengirim apa pun.

Ingin kembali melamar sambil mencari (lebih cepat, tanpa perbandingan)?
Itu hanya berlaku bila tidak ada batas harian:
`python cli.py set-env COLLECT_BEFORE_APPLY=false MAX_APPLY_PER_DAY=0`.

Aturan yang sama berlaku di Glints: `jalankan.bat glints run` juga meriset
semua kartu (mengklik "Muat lebih banyak" maksimal 5 kali per kata kunci),
menghapus duplikat,
menilai dengan skor yang sama, menampilkan tabel perbandingan + rincian skor,
lalu hanya melamar sebanyak sisa kuota `MAX_APPLY_PER_DAY` — memakai kuota
yang sama dengan JobStreet karena keduanya menulis ke database yang sama.

### Glints (glints.com)

#### Aturan Glints = aturan JobStreet

JobStreet dipakai sebagai acuan; Glints mengikuti aturan yang sama:

| Aturan | JobStreet | Glints |
|---|---|---|
| Riset semua kata kunci, maks 5 halaman per kombinasi | ya | ya (5 kali muat "Muat lebih banyak") |
| Urut posting terbaru | ya | ya ("Baru Ditambahkan") |
| Dedupe lintas kata kunci | ya | ya |
| Saring judul/lokasi/gaji/kualifikasi | `JobFilter` | `JobFilter` yang sama |
| Wajib logo perusahaan (`REQUIRE_COMPANY_LOGO`) | ya | ya |
| Skor 8 dimensi + ranking global | ya | ya |
| TOP 50 global per hari, kuota dipakai bersama | ya (`kuota.py`) | ya (`kuota.py`) |
| Lewati yang sudah pernah dilamar (situs **dan** database) | ya | ya |
| Lewati lowongan yang hanya bisa dilamar via aplikasi | tidak berlaku | ya (khusus Glints) |
| `AUTO_APPLY_MAX_PER_SESSION` | ya | ya |
| `DELAY_BETWEEN_APPLY` (hanya setelah lamaran/error) | ya | ya |
| Mode manual `AUTO_APPLY=false` (tinjau lalu konfirmasi) | ya | ya |
| Login habis → sesi berhenti + notifikasi Telegram | ya | ya |
| Laporan harian Telegram di akhir sesi | ya | ya |
| Pencarian per lokasi | `LOCATIONS` × kata kunci | satu pencarian nasional per kata kunci, hasil disaring `LOCATIONS` |

Dua perbedaan yang memang disengaja:

1. **Glints selalu riset dulu** (tidak ada mode "lamar sambil mencari"),
   karena TOP 50 global hanya bisa ditentukan setelah semua hasil dinilai.
2. **Pencarian Glints tidak per lokasi** — alamat explore-nya nasional
   (`countryCode=ID`), jadi hasilnya lebih luas lalu disaring dengan
   `LOCATIONS`. Aturan "semua lokasi tercakup" tetap terpenuhi.

### Indeed (id.indeed.com)

Indeed memakai **aturan yang sama persis** dengan JobStreet:

| Aturan | Nilai di Indeed |
|---|---|
| Riset | semua `KEYWORDS` × semua `LOCATIONS`, maksimal 5 halaman per kombinasi |
| Urutan | tanggal terbaru (`sort=date`) |
| Dedupe | lintas kata kunci × lokasi |
| Saringan | `JobFilter` yang sama (judul, lokasi, gaji `MIN_SALARY`, kualifikasi) |
| Logo perusahaan | `REQUIRE_COMPANY_LOGO` (aturan deteksi yang sama) |
| Skor & ranking | 8 dimensi, ranking global, ambil yang terbaik dulu |
| Kuota harian | `kuota.py` — 50/hari, **dipakai bersama** JobStreet & Glints |
| Batas per sesi | `AUTO_APPLY_MAX_PER_SESSION` |
| Sudah pernah dilamar | dilewati (tanda situs + catatan database) |
| Mode manual | `AUTO_APPLY=false` → buka lowongan, Anda kirim sendiri |
| Login habis | sesi berhenti + notifikasi Telegram |
| Notifikasi | per lamaran + laporan harian |
| Ingatan jawaban | `jawaban.py` — sekali diisi, terisi otomatis |

Lamaran Indeed yang dialihkan ke situs perusahaan (`Apply on company site`)
dilewati sebagai *perlu manual* — sama seperti JobStreet.

```powershell
.\jalankan.bat indeed run
.\jalankan.bat indeed run --max-pages 2 --limit 10
.\jalankan.bat indeed cari --keywords "inventory staff" --limit 10
.\jalankan.bat indeed diagnosa --keyword "inventory staff"
```

#### Batas harian: satu aturan untuk dua situs

Batas `MAX_APPLY_PER_DAY` dihitung di satu tempat (`kuota.py`) dan dipakai
**bersama** oleh JobStreet dan Glints:

* lamaran yang terkirim lewat JobStreet mengurangi jatah Glints, dan sebaliknya;
* `0` berarti tanpa batas;
* kandidat dipotong menurut sisa kuota **setelah** dinilai dan diperingkat,
  jadi slot dipakai untuk lowongan yang paling cocok;
* pesan yang dicetak kedua situs identik:
  `Kuota harian: 4 sudah dilamar hari ini, sisa 46 dari 50.`

#### "Terbaca 0 lowongan" di Glints

Kalau `glints run`/`glints cari` melaporkan tidak ada lowongan padahal di
Chrome terlihat ada, jalankan diagnosa:

```bash
python cli.py glints diagnosa                 # kata kunci pertama .env
python cli.py glints diagnosa --keyword PPIC  # kata kunci tertentu
```

Perintah itu membuka satu halaman pencarian, mencoba **semua bentuk URL
pencarian Glints**, lalu mencetak:

```
Diagnosa halaman Glints:
  URL          : https://glints.com/id/opportunities/jobs?keyword=PPIC
  Judul halaman: Lowongan Kerja ...
  Tautan lowongan ditemukan: 0, kartu terbaca: 0
  HTML        : ...\debug\diagnosa-20261105-101500-ppic.html
  Screenshot  : ...\debug\diagnosa-20261105-101500-ppic.png
```

Kirimkan dua berkas itu (atau tempelkan 30 baris keluarannya) supaya pola
tautan/pembacaan kartunya bisa disesuaikan. Hal yang biasanya terlihat:

- `meminta login` → login dulu di jendela Chrome, jalankan lagi.
- `captcha` → selesaikan verifikasi di Chrome, jalankan lagi.
- `Tautan lowongan ditemukan: 0` tetapi halaman berisi lowongan → struktur
  halaman berubah; berkas HTML-nya yang diperlukan untuk memperbaiki pola.

Kalau skrip pembaca kartu tidak menemukan apa pun, bot otomatis mencoba
**pembaca cadangan** yang membaca elemen `<a>` langsung (tanpa JavaScript)
dan mencatatnya di log.

Versi Glints memakai mesin lamaran yang sama, tetapi dengan peta situsnya
sendiri: pencarian `/id/opportunities/jobs/explore`, tautan lowongan
`/id/opportunities/jobs/<slug>/<uuid>`, tombol **Lamar** lalu **Lamar
Sekarang**, dan urutan **Baru Ditambahkan** untuk lowongan terbaru.

```bash
python cli.py glints simulasi                # uji alur tanpa Chrome (7 skenario)
python cli.py glints cari --limit 10         # daftar lowongan layak + URL-nya
python cli.py glints uji                     # uji lamar: lowongan dipilih sendiri
python cli.py glints run                     # semua kata kunci di .env
python cli.py glints run --keywords "warehouse,PPIC" --max-pages 1
python cli.py glints run --limit 10         # batasi 10 lamaran sesi ini
python cli.py glints uji --url "https://glints.com/id/opportunities/jobs/staff-gudang/11111111-2222-3333-4444-555555555555"
```

Lewat skrip bantu: `jalankan.bat glints run` (Windows) atau
`./jalankan.sh glints run`.

Yang dipakai bersama dengan versi JobStreet: `LOCATIONS`, `KEYWORDS`,
`TITLE_KEYWORDS`, `EXCLUDE_KEYWORDS`, blacklist, `MIN_SALARY`, `COVER_LETTER`,
`RESUME_PATH`, `DELAY_BETWEEN_APPLY`, `MAX_APPLY_PER_DAY`,
`AUTO_APPLY_MAX_PER_SESSION`, dan folder `debug/`. Riwayat lamaran masuk ke
database yang sama dengan awalan ID `glints:`, jadi lowongan yang sudah
dilamar tidak akan dilamar dua kali.

Perbedaan yang perlu diketahui:

| Hal | JobStreet | Glints |
| --- | --- | --- |
| Filter lokasi | lewat pencarian situs | disaring dari teks lokasi kartu |
| Urutan terbaru | parameter `sortmode=ListedDate` | klik tombol *Baru Ditambahkan* |
| Umur lowongan | terbaca ("3 hari yang lalu") | tidak ditampilkan Glints |
| Lowongan khusus HP | — | *"Lamar & chat di aplikasi"* dilewati otomatis |
| Batas gaji | `MIN_SALARY` (batas bawah) | `GLINTS_MIN_SALARY` (gaji tertinggi di rentang) |
| Logo perusahaan | `REQUIRE_COMPANY_LOGO` | `REQUIRE_COMPANY_LOGO` (aturan sama) |
| Kuota harian & pilih yang paling cocok | `MAX_APPLY_PER_DAY` + `RANK_BY` | sama |
| Menunggu kuesioner diisi | `AUTO_ANSWER_WAIT` | sama |

Karena Glints tidak menampilkan tanggal tayang di kartu, urutan "terbaru"
mengandalkan urutan situs, bukan `MAX_AGE_DAYS`.

Aturan gaji di Glints: lowongan dengan gaji di bawah `GLINTS_MIN_SALARY`
(bawaan **Rp4.500.000**) dilewati. Untuk rentang seperti *Rp 4-4,5jt* dipakai
angka tertinggi — jadi masih dilamar karena bisa mencapai 4,5 juta. Lowongan
yang menulis *"Gaji Tidak Ditampilkan"* atau tanpa info gaji **tetap dilamar**.

### Versi ringan tanpa Selenium

```bash
python buka_pencarian.py
```

Perintah ini membuka tab pencarian JobStreet untuk setiap lokasi × kata
kunci (default maksimal 24 tab) dan menyiapkan `catatan_lamaran.csv` sebagai
pelacak manual.

```bash
python buka_pencarian.py --locations "Bandung,Jakarta,Bekasi" --max-tabs 12
```

## Struktur proyek

| File | Isi |
| --- | --- |
| `config.py` | Membaca `.env` dan menyediakan objek `config` |
| `database.py` | Skema dan operasi SQLite (`jobs`, `applications`, `blacklist`) |
| `scraper.py` | Selenium: buka Chrome, cari lowongan, baca kartu lowongan |
| `job_filter.py` | Aturan lolos/tidak dan pemeringkatan |
| `main.py` | Alur sesi: login → cari → saring → tinjau |
| `cli.py` | Perintah `run`, `stats`, `history`, `config`, `repair`, `blacklist`, `cek-logo`, dan `glints` |
| `notifier.py` | Notifikasi Telegram (opsional) |
| `auto_apply.py` | Alur klik Lamar → Lanjutkan → Kirim + deteksi pengaman |
| `glints.py` | Situs Glints: pencarian, kartu lowongan, dan pelamaran |
| `simulasi_glints.py` | Simulasi alur lamaran Glints tanpa Chrome |
| `buka_pencarian.py` | Pembuka tab pencarian tanpa Selenium |
| `jalankan.bat` / `jalankan.sh` | Skrip bantu: siapkan `.venv`, pasang dependensi, jalankan CLI |
| `simpan.bat` / `simpan.sh` | Kirim perubahan ke GitHub sekali jalan |
| `pantau.bat` / `pantau.sh` | Pemantau: kirim otomatis setiap ada perubahan |
| `pasang-otomatis.bat` / `matikan-otomatis.bat` | Pasang/lepas pemantau saat login |
| `pantau-diam.vbs` | Menjalankan pemantau tanpa jendela (log: `pantau.log`) |
| `tarik.bat` / `tarik.sh` | Tarik pembaruan dari repo pengembangan (dipakai juga oleh `pantau` secara otomatis) |
| `tests/` | Unit test untuk filter dan database |

## Seberapa otomatis alat ini?

| Langkah | Status |
|---|---|
| Mencari lowongan di 7 kota | otomatis |
| Urut dari posting terbaru | otomatis |
| Menyaring (senior, gaji, pengalaman, lokasi) | otomatis |
| Login JobStreet | **sekali saja**, lalu tersimpan — satu-satunya langkah yang melibatkan Anda (tanpa Enter) |
| Klik Lamar → Lanjutkan → Kirim | otomatis (`--auto`) |
| Lowongan lewat situs perusahaan (ATS) | **manual** — JobStreet mengalihkan keluar |
| Lowongan berlabel "You applied"/sudah pernah dilamar | otomatis dilewati (tidak ditampilkan) |
| Lowongan yang minta cover letter/unggah CV | otomatis diisi bila `COVER_LETTER`/`RESUME_PATH` disetel; jika tidak, dilewati otomatis |
| Pertanyaan pilihan wajib dari perusahaan | dilewati otomatis (jawaban tidak ditebak) |
| Captcha/OTP saat login | **manual** (tidak bisa dilewati) |
| Menaikkan batas harian, memilih kota | Anda (lewat `.env`/flag) |

Lowongan yang tidak bisa diproses otomatis hanya **dicatat** di akhir sesi
(lengkap dengan tautan) — Anda tidak perlu mengerjakan apa pun agar sesi
selesai.

## Menjalankan test

```bash
pip install pytest
pytest -q
```

Test tidak membutuhkan Chrome maupun koneksi internet.

## Troubleshooting

**Muncul "Tidak ada lowongan yang berhasil dibaca".**
JobStreet kadang mengubah struktur HTML. Pastikan Anda sudah login, halaman
hasil pencarian terbuka normal di Chrome, lalu periksa selector di
`scraper.py` (`CARD_SELECTORS` dan `_parse_job_card`).

**Chrome tidak bisa dibuka.**
Pastikan Google Chrome terpasang dan bukan versi portabel. Bila unduhan
ChromeDriver otomatis gagal, program mencoba `webdriver-manager`; Anda juga
bisa memasang ChromeDriver manual dan menaruhnya di `PATH`.

**`session not created: Chrome failed to start ... DevToolsActivePort file
doesn't exist`.**
Profil Chrome masih dipakai proses Chrome lain atau profilnya rusak. Program
sudah otomatis mencoba: (1) profil tersimpan, (2) profil tersimpan setelah
berkas kunci sisa Chrome (`SingletonLock`, dll.) dibersihkan, (3) profil
sementara, (4) tanpa mode headless. Bila semuanya gagal:

```powershell
# 1) tutup semua Chrome, lalu cek Task Manager (Ctrl+Shift+Esc) -> chrome.exe -> End task
# 2) buat profil Chrome baru (sesi login lama tidak terbawa)
.\jalankan.bat perbaiki-chrome
# 3) jalankan lagi; login sekali di jendela yang terbuka
.\jalankan.bat glints diagnosa --keyword "inventory staff"
```

Bila muncul peringatan “Chrome terbuka TANPA profil tersimpan”, itu tanda
profil masih terkunci oleh Chrome lain: tutup semua Chrome, lalu jalankan
lagi agar sesi login tersimpan kembali. Bila tetap gagal, bot otomatis
memakai profil cadangan (`~/.dimastes/chrome-profile-baru`) yang tetap
menyimpan sesi login.

**Cek cepat: apakah Glints sudah berfungsi?**
Satu perintah memeriksa semuanya berurutan — baca kartu → saring kandidat
(logo & duplikat) → simulasi alur lamaran → catatan database:

```powershell
.\cek-glints.bat          # aman: hanya membaca, tidak melamar
.\cek-glints.bat 3        # ikut mengirim maksimal 3 lamaran uji (minta konfirmasi)
```

Setara dengan `jalankan.bat glints cek --lamar 3`. Setiap tahap ditandai
`OK` / `GAGAL` beserta alasannya, dan perintah berhenti dengan kode keluar 1
bila ada tahap gagal sehingga bisa dipakai di skrip.

**Situs menampilkan “Just a moment...” (verifikasi Cloudflare).**
Glints dilindungi Cloudflare, sehingga Chrome yang dijalankan otomatis bisa
diminta verifikasi. Dua cara:

1. Selesaikan verifikasinya di jendela Chrome yang bot buka, lalu jalankan
   lagi (cookie verifikasi tersimpan di profil bila profil tersimpan dipakai).
2. Paling stabil — pakai Chrome Anda sendiri, lalu bot menempel ke situ:

```powershell
# buka Chrome khusus bot (port debug 9222) + halaman Glints
.\chrome-debug.bat
# selesaikan "Just a moment..." di jendela itu (sekali saja)

# suruh bot menempel, bukan membuka Chrome sendiri
.\jalankan.bat set-env CHROME_DEBUG_PORT=9222
.\jalankan.bat glints diagnosa --keyword "inventory staff"
.\jalankan.bat glints run
```

Setelah selesai, kembalikan ke mode biasa dengan
`set-env CHROME_DEBUG_PORT=0`. Jangan tutup jendela Chrome dari
`chrome-debug.bat` selama bot berjalan.

**Riwayat menampilkan posisi kosong.**
Itu data lama dari versi sebelumnya yang menyimpan judul kosong. Jalankan
`python cli.py repair`; data lama tidak dihapus, hanya diisi teks pengganti.

**Lowongan muncul tapi lokasinya bukan Kota Anda.**
Aktifkan `STRICT_LOCATION=true` di `.env`.

**Diminta login setiap kali menjalankan.**
Pastikan `USE_PROFILE=true` (default), tidak memakai `--no-profile`, dan
folder profil (`~/.dimastes/chrome-profile` di Windows
`C:\Users\NamaAnda\.dimastes\chrome-profile`) tidak dihapus. Permintaan
login di layar hanya muncul bila cookie sesi benar-benar sudah tidak ada —
program tidak pernah menanyakan email/password.

**Lowongan yang menurut saya relevan malah dilewati.**
Judulnya tidak memuat kata kunci minat. Tambahkan istilahnya ke
`TITLE_KEYWORDS` di `.env` (mis. `gudang`, `stok`, `production planning`) —
atau jalankan `python cli.py perbarui-env` untuk memakai daftar terbaru,
atau set `REQUIRE_KEYWORD_MATCH=false`.

**Lowongan yang sudah saya lamar masih muncul.**
Pastikan JobStreet sudah menampilkan label "Applied" pada kartu lowongan
tersebut. Bila labelnya tidak terdeteksi, jalankan mode manual sekali dan
kirimkan potongan HTML kartunya agar selector
`APPLIED_CARD_SELECTORS`/`APPLIED_CARD_TEXTS` di `scraper.py` disesuaikan.
Lowongan yang sudah tercatat di database tetap dilewati walau tanpa label.

**Program berhenti dengan pesan "Login dibatalkan" atau "Batas waktu login habis".**
Sesi belum ada dan login tidak terdeteksi. Jalankan lagi, login di Chrome, dan
biarkan jendela Chrome terbuka — program melanjutkan sendiri. Bila Anda memang
tidak ingin menunggu, set `LOGIN_WAIT=false`.

**Terlalu banyak lowongan dilewati dengan alasan "alur tidak dikenali".**
Koneksi/laman JobStreet bisa lambat. Naikkan batasnya, mis. `AUTO_APPLY_STEP_TIMEOUT=8`
di `.env`, lalu jalankan lagi. Untuk halaman terakhir pakai
`AUTO_APPLY_SUBMIT_TIMEOUT` (default **20** detik).

**Halaman "Review and submit" tidak terkirim / lowongan dilewati di langkah akhir.**
Bot mengenali halaman review lewat URL (`/apply/review`) maupun teks halaman,
lalu mengklik tombol kirim apa pun yang tersedia (termasuk
`button[type=submit]`) dengan batas waktu 20 detik. Ada tiga sebab yang dibedakan
sekarang:

1. **Isian wajib kurang** — muncul banner "please address the following issues".
   Bot berhenti setelah satu klik dan menuliskan isian mana yang kurang.
2. **Galat server JobStreet** — banner merah *"Something has gone wrong. Please
   try again or contact Customer Service"*. Bot memuat ulang halaman sekali dan
   mencoba kirim lagi; kalau tetap gagal, lowongan dilewati (tidak lagi menunggu
   20 detik lalu mengklik 3 kali).
3. **Halaman lambat dimuat** — bot menunggu 1,5 detik sebelum klik pertama dan
   tidak mengklik ganda.

Bila masih gagal, buka folder `debug/`. Sekarang ada dua berkas per lowongan:
`*.txt` (URL, isi modal, banner galat server, dan label tombol yang terlihat) dan
`*.html`/`*.png` untuk pemeriksaan lebih dalam. Kirimkan `*.txt`-nya — biasanya
sudah cukup untuk tahu penyebabnya.

**Muncul "It seems that there is already a rebase-merge directory".**
Ada sisa rebase yang gagal di `.git/`. `simpan.bat`/`simpan.sh` versi baru
membersihkannya sendiri; kalau masih muncul, jalankan sekali:

```bash
git rebase --abort
```

lalu `simpan.bat` lagi.

**`pantau.log` ikut ter-commit.**
Catatan aktivitas pemantau tidak perlu masuk repo; sejak `.gitignore` memuat
`pantau.log` dan `*.log`, skrip simpan juga mengeluarkannya dari daftar berkas
Git secara otomatis (berkas di disk tetap ada).

**Program masih menunggu Enter saat lowongan dibuka.**
Berarti mode manual aktif. Pastikan `AUTO_APPLY=true` di `.env` (atau jalankan
`run --auto`). Di mode otomatis tidak ada permintaan Enter.

**Semua lowongan masuk "perlu dilamar manual".**
Penyebab yang paling sering: lowongan memakai "Lamar di situs perusahaan",
meminta unggah berkas, atau punya pertanyaan wajib. Bot sengaja tidak menebak
jawaban. Selesaikan lewat tautan di daftar akhir sesi.

**Lowongan Jakarta/Tangerang tidak muncul.**
Pastikan `LOCATIONS` berisi kota itu (bukan hanya `LOCATION`), dan
`STRICT_LOCATION` tidak memakai daftar lama. Cek juga nama lokasi yang
dipakai JobStreet; "Jababeka" sering tampil sebagai *Cikarang* atau *Bekasi*.

**Ingin hanya lowongan yang baru tayang.**
Tambahkan `--max-age-days 3` (atau `1`) saat menjalankan `run`, atau isi
`MAX_AGE_DAYS` di `.env`. Hasil sudah otomatis diurutkan dari yang terbaru.

**Tombol Lamar tidak ditemukan.**
JobStreet memakai beberapa variasi tombol. Jalankan sekali dengan mode manual
(`run --manual`) di jendela Chrome yang terlihat, lalu kirimkan potongan HTML
tombol Lamar agar selector di `auto_apply.py` bisa disesuaikan.

**Lamaran tidak bertambah padahal sudah melamar.**
Pastikan Anda mengetik `y` saat terminal bertanya, bukan hanya Enter. Lamaran
tanpa konfirmasi dicatat sebagai `skipped` dan tidak dihitung di batas harian.

## Catatan

Gunakan alat ini dengan wajar dan sesuai ketentuan layanan JobStreet. Program
hanya membantu proses penelusuran; keputusan melamar tetap milik Anda.
