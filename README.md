# pantau

Pelacak kode promo / voucher / kuota gratis layanan AI di mesin pencari.
Tanpa API key: Bing RSS, Google News RSS, Hacker News (Algolia), GitHub Search,
dev.to, Lemmy, dan umpan Reddit/HN.

Sumber yang dites dari jaringan Indonesia: DDG (html/lite) dan Brave kena
connection-reset, Reddit `.json` kena 403 — keduanya sudah diganti:
Reddit lewat `.rss` (atom) dan sisanya lewat daftar engine di bawah.
Ekstrak kode dari judul + cuplikan + isi halaman, skor kelayakan, simpan ke SQLite,
kirim yang bagus ke Discord/Telegram, dan tampilkan di panel web lokal.

## pasang

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
```

## pakai

```bash
python -m pantau.cli run --deep --show     # satu putaran, cari kode di dalam halaman
python -m pantau.cli codes --days 3        # kode baru 3 hari terakhir
python -m pantau.cli export                # JSON + CSV ke data/export/
python -m pantau.cli stats                 # ringkasan DB
python -m pantau.server --port 8000        # panel web
```

Atur kueri, umpan, dan webhook di `config.yaml`.

## jadwalkan (cron, tiap 6 jam)

```
0 */6 * * * cd /path/promo-tracker && .venv/bin/python -m pantau.cli run --deep
```

## deploy online (gratis)

### A. GitHub Actions — paling pas, kode Python dipakai apa adanya

1. buat repo (private juga boleh), push folder ini.
2. Settings → Secrets and variables → Actions → New secret:
   - `TELEGRAM_TOKEN` = token bot
   - `TELEGRAM_CHAT` = chat id (lihat cara ambil di bawah)
3. `.github/workflows/pantau.yml` sudah ada; jadwalnya `17 */4 * * *` (tiap 4 jam).
3. Actions → pantau → Run workflow, untuk uji sekali jalan.

SQLite disimpan antar-run lewat cache GitHub, jadi kode yang sudah pernah
dilaporkan tidak dikirim ulang. Hasil CSV/JSON diunggah sebagai artifact 30 hari.

Biaya: repo publik gratis tanpa batas; privat dapat 2.000 menit/bulan
(1 run ≈ 3–5 menit → masih muat ~400 run).

### B. Cloudflare Worker + D1 — SUDAH DIPASANG

```
https://pantau.dalimuntheferdi5.workers.dev
cron */2 * * * *   (tiap 2 menit)
D1 : pantau / cc450152-b228-400e-b4ae-05990e07b7a8 (region APAC)
```

Endpoint: `/scan` paksa putaran, `/top` 30 temuan teratas, `/pipeline` hitung
tahap filter, `/` ringkasan.

Catatan jaringan: `*.workers.dev` diblokir DNS ISP Indonesia (resolv ke
`blockpage.xlaxiata.id`). Cron tetap jalan di sisi Cloudflare; untuk membuka
`/top` dari HP pakai DNS 1.1.1.1 atau VPN.

Sumber yang hidup dari egress Cloudflare: **Bing News**, **Hacker News**.
Yang mati: Google News (503), Reddit RSS (403/429), dev.to (403), DuckDuckGo
(challenge). Karena itu worker hanya pelengkap; pemindaian lengkap tetap di
GitHub Actions.

#### memasang dari nol (kalau perlu ulang)

```bash
cd worker
npm i -D wrangler
npx wrangler login
npx wrangler d1 create pantau          # salin database_id ke wrangler.toml
npx wrangler d1 execute pantau --file=schema.sql --remote
npx wrangler secret put TELEGRAM_TOKEN
npx wrangler secret put TELEGRAM_CHAT
npx wrangler deploy                     # cron 23 */6 * * *
curl https://pantau.<akun>.workers.dev/scan   # uji manual
curl https://pantau.<akun>.workers.dev/top    # 30 temuan teratas
```

Catatan jujur: plan gratis Worker dibatasi 10 ms CPU per invocation. I/O
(fetch) tidak dihitung, tapi parsing RSS 12 kueri bisa menyentuh batas itu.
Kalau log menunjukkan "exceeded CPU", turunkan `QUERIES` jadi 3 atau naik ke
plan berbayar $5/bulan. D1 gratis 5 GB, cukup untuk ratusan ribu baris.

### C. Oracle Cloud Always Free — VM kecil, cron biasa

Ambil VM Ampere/AMD always-free, pasang Python, taruh folder ini, lalu crontab
seperti di atas. Paling bebas (tidak ada batas CPU), tapi harus urus VM sendiri.

### yang tidak cocok

| layanan | alasan |
|---|---|
| Vercel Hobby | cron hanya 1×/hari, function max 10 s |
| Netlify | cron terjadwal hanya di plan berbayar |
| Render free | service tidur setelah idle, cron job berbayar |
| Railway / Fly.io | tidak ada tier gratis yang benar-benar gratis sekarang |

## ambil chat_id Telegram

Kirim `/start` ke bot, lalu:

```bash
python -m pantau.cli telegram --wait 30
```

Perintah itu mencetak `chat_id`, menyimpannya ke DB, dan mengirim satu pesan tes.
Kalau `TELEGRAM_CHAT` kosong, putaran cron berikutnya juga akan menebak sendiri
dari pesan terakhir yang masuk ke bot.

## Reddit lewat OAuth

JSON Reddit tanpa auth diblokir (`403 Blocked`) dari IP datacenter, sedangkan
endpoint token tetap terbuka. Jadi pakai aplikasi OAuth sendiri:

1. buka https://www.reddit.com/prefs/apps (akun harus punya email terverifikasi)
2. klik **create another app**
3. isi: name `pantau`, type **script**, redirect uri `http://localhost:8080`
4. setelah dibuat, ambil dua nilai:
   - **client id** = teks pendek tepat di bawah "personal use script"
   - **secret** = baris berlabel `secret`
5. isi `.env`:

```
REDDIT_CLIENT_ID=xxxxx
REDDIT_CLIENT_SECRET=yyyyy
```

6. uji:

```bash
python -m pantau.cli reddit
# token  : abc123...
# akun   : u/...
```

Kalau berhasil, `config.yaml` otomatis memakai `engine: reddit` dan membaca
`subreddits` (100 pos terakhir per sub, disaring 24 jam). Kalau kredensial
kosong, blok itu dilewati tanpa error.

Batas Reddit: 100 request/menit. Satu putaran memakai ~10.

## jendela waktu

`max_age_hours: 24` di `config.yaml`. Hasil tanpa tanggal terbit dibuang, karena
tidak bisa dipastikan masih baru. Konsekuensinya sumber yang tidak mengirim
`pubDate` tidak akan pernah lolos.

Google News dibatasi `when:1d`, Bing `filters=ex1:"ez1"`, HN
`created_at_i > now-24h`, Reddit `t=day`.

Kalau ingin lebih longgar, naikkan ke `48` atau `72`.

## sumber komunitas / forum

Selain mesin pencari, ada tiga jalur komunitas yang sudah tersambung:

| jalur | cara | status |
|---|---|---|
| Forum Discourse | `search.json?q=... after:YYYY-MM-DD` — server yang menyaring tanggal | ✅ community.openai.com, forum.cursor.com, community.n8n.io, discuss.huggingface.co, community.vercel.com |
| Reddit | OAuth (`/search`, `/r/<sub>/new`) atau fallback `/r/<sub>/new/.rss` | ✅ (RSS kena jeda 20 s/host) |
| Lemmy | `/api/v3/search` | ✅ lemmy.world |
| Mastodon | `/api/v2/search?type=statuses` | ⚠️ sering kosong untuk kueri promo |
| Telegram | `t.me/s/<kanal>` lewat pencarian `site:t.me` | ✅ tidak langsung |
| HN / GitHub / dev.to | Algolia, Search API, artikel terbaru | ✅ |

Menambah forum baru: cari di `config.yaml` bagian `forums`, tempel URL basis forum
(harus Discourse — cirinya ada `/search.json`). Contoh tambahan:

```yaml
forums:
  - "https://community.openai.com"
  - "https://discuss.huggingface.co"
  - "https://forum.cursor.com"
```

Kuota sumber berbagi satu pool: `max_queries` mengatur berapa kueri mesin pencari
per putaran (bergiliran), sementara forum selalu jalan penuh.

## catatan teknis

- `rate.delay_min/max` + `retries` dengan backoff — jangan turunkan ke bawah 2 detik.
- Skor 0–100: kode konkret (+40), sinyal promo (+20), kesegaran tahun (+8),
  kepercayaan domain (+), tanda kedaluwarsa (−35), URL jualan/login (−25).
- Dedupe lewat uid = sha1(url ternormalisasi + judul).
- Notifikasi dikirim kalau skor ≥ `min_notify` (45) **atau** ada kode konkret
  dengan skor ≥ `min_notify_coded` (28). Tanpa aturan kedua, temuan seperti
  "kode CLAUDE50" bisa tidak pernah dikirim hanya karena judulnya pendek.
- Kode wajib memuat angka; token tanpa angka hanya lolos kalau dikutip dan
  berada dekat frasa "kode promo / voucher code / redeem code". Ini yang
  menyaring nama variabel dan akronim dari hasil GitHub.
- Hasil wajib menyentuh salah satu istilah AI (claude, chatgpt, gemini, llm,
  kuota api, dst). "kode pos", "kode wilayah", "kode bank" otomatis dibuang.
- GitHub tanpa kode konkret dipotong 22 poin: commit/PR sering menyebut
  "promo" tanpa voucher apa pun.
- Notifikasi hanya untuk temuan `notified=0` dengan skor ≥ `score.min_notify`.
