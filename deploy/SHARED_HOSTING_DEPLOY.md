# EXPORT ZONE — cPanel / Shared Hosting Deployment Guide

cPanel-এর “Setup Django App” (Passenger) ধরে ধরে ধাপে ধাপে ডিপ্লয় করার নির্দেশনা।
প্রতিটি ধাপে “কেন” দেওয়া আছে, যাতে ভুল হলে বোঝা যায় কোথায় সমস্যা।

---

## ০. দ্রুত রেফারেন্স

| কাজ | কমান্ড |
|---|---|
| প্যাকেজ বানানো (প্রথমবার, ডাট সহ) | `.\deploy\build_shared_hosting_package.ps1 -Domain example.com` |
| প্যাকেজ বানানো (আপডেট, ডাট ছাড়া) | `.\deploy\build_shared_hosting_package.ps1 -Domain example.com -SkipData` |
| ডাট ব্যাকআপ নিন | `.\deploy\backup_data.ps1` |
| সার্ভারে মাইগ্রেট | `cd ~/exportzone && ../venv/bin/python manage.py migrate` |

---

## ১. ডাট নিরাপত্তা — সবচেয়ে গুরুত্বপূর্ণ অংশ

প্রজেক্টে ডাট দুই জায়গায় থাকে:

| জিনিস | অবস্থান | কী রাখে |
|---|---|---|
| ডাটাবেস | `exportzone/db.sqlite3` | পণ্য, অর্ডার, কাস্টমার, ঠিকানা |
| ছবি | `exportzone/media/` | ক্যাটাগরি ও পণ্যের আপলোড করা ছবি |

**আপডেটের সময় এই দুটো অবশ্যই বাদ দিতে হবে**, নইলে আপলোড করার সময় সার্ভারের ডাট
ওভাররাইট হয়ে যাবে (অথবা FTP ক্লায়েন্ট “overwrite prompt”-এ ভুলে Delete বেছে ফেলবে)।

সেজন্ই বিল্ড স্ক্রিপ্টে **`-SkipData`** সুইচ আছে:

```powershell
# প্রথমবার — ডাট অন্তর্ভুক্ত থাকবে
.\deploy\build_shared_hosting_package.ps1 -Domain example.com

# পরবর্তী সব আপডেট — ডাট বাদ, কোড আছে
.\deploy\build_shared_hosting_package.ps1 -Domain example.com -SkipData
```

`-SkipData` দিলে ZIP-এ `db.sqlite3` থাকে না এবং `media/` ফোল্ডারটি খালি অবস্থায় যায়।
FTP-এর মতো যেকোনো টুল একটি **খালি ফোল্ডার আপলোড করলে সার্ভারের ভেতরের ফাইল মুছে যায় না** —
শুধু ফোল্ডারটাই থাকে। তাই নতুন ছবি আপলোডের জায়গা হারবে না।

### আপডেটের আগে ব্যাকআপ (বাধ্যতামূলক)

```powershell
.\deploy\backup_data.ps1
```

এটি `backups/exportzone-backup-<সময়>.zip` ফাইলে ডাটাবেস, `media/`, `.env` ও `.secret_key`
রাখে। স্ক্রিপ্টটি প্রথমে **কপি** করে তারপর জিপ বানায় — মূল ফাইল কখনো মুছে বা সরায় না।
জিপ তৈরি না হলে সেটা মুছে ফেলে আবার চালালেই হবে।

সার্ভারের ডাটের ব্যাকআপ চাইলে cPanel → **phpMyAdmin** → অভিনীত ডাটাবেস নির্বাচন →
**Export → Quick** → SQL ডাউনলোড।

---

## ২. SSL ছাড়া প্রথমবার? (গুরুত্বপূর্ণ)

cPanel-এ **আগে** SSL সার্টিফিকেট চালু করে নিন (cPanel → **SSL/TLS Status** → “Run AutoSSL”)।
কারণ SSL ছাড়া অবস্থায় `SECURE_SSL_REDIRECT=True` থাকলে সব পেজ redirect হয়ে যায় এবং
secure cookie ব্রাউজারে সেভ হয় না → লগইন কাজ করবে না, redirect লুপ তৈরি হবে।

SSL এখনই না চালু করতে পারলে:

```powershell
.\deploy\build_shared_hosting_package.ps1 -Domain example.com -NoSsl -SkipData
```

`-NoSsl` দিলে স্ক্রিপ্ট স্বয়ংক্রিয়ভাবে লিখে দেবে:

```
SECURE_SSL_REDIRECT=False
SESSION_COOKIE_SECURE=False
CSRF_COOKIE_SECURE=False
CSRF_TRUSTED_ORIGINS=http://example.com,http://www.example.com
```

SSL চালু করার পরে ডোমেইন দিয়ে নতুন প্যাকেজ বানিয়ে আপলোড করলেই এগুলো `True`/`https` হয়ে যাবে।
সাইট সবসময় **পুরোনো `.env` মুছে না** বরং নতুনটি ওভাররাইট করে — সেটাই কাঙ্ক্ষিত আচরণ।

---


## ৩. প্যাকেজ বানানো (আপনার কম্পিউটারে)

```powershell
cd 'e:\django-backend\ÊXport Zøne'
.\deploy\build_shared_hosting_package.ps1 -Domain example.com
```

স্ক্রিপ্ট যা করে:

1. `manage.py collectstatic` চালায় — শেয়ার্ড হোস্টে এটি নিজে থেকে চলে না
2. ডেভ টুলিং বাদ দিয়ে শুধু দরকারি কোড কপি করে
3. প্রয়োজন হলে `db.sqlite3` ও `media/` কপি করে
4. ৬৪ বাইট র‍্যান্ডম `SECRET_KEY` তৈরি করে `.secret_key` ও `.env` লেখে (UTF-8, BOM ছাড়া)
5. ZIP বানায় এবং ভেতরের প্রতিটি জরুরি ফাইল হাজির আছে কি না যাচাই করে
6. প্লেইনটেক্সট সিক্রেট থাকা টেম্প ফোল্ডার মুছে ফেলে — শুধু ZIP থাকে

প্যাকেজ পাওয়া যাবে: `dist\exportzone-shared-hosting-<সময়>.zip`

### SMTP ইমেইল চালু করতে

```powershell
.\deploy\build_shared_hosting_package.ps1 -Domain example.com `
    -EmailHost 'mail.example.com' `
    -EmailUser 'noreply@example.com' `
    -EmailPassword 'আপনার-পাসওয়ার্ড' `
    -FromEmail 'EXPORT ZONE <noreply@example.com>'
```

`-EmailHost` না দিলে ইমেইল কনসোল ব্যাকএন্ডে থাকে (পাঠানো হয় না, শুধু Passenger লগে
দেখা যায়)। বিকল্প: প্যাকেজ বানানোর পরেও সার্ভারের `.env` ফাইলটা এডিট করে তিনটি `EMAIL_*`
লাইন পূরণ করুন।

---

## ৪. cPanel-এ প্রথমবার ডিপ্লয়

### ধাপ ১ — আপলোড

1. cPanel → **File Manager**
2. `public_html`-এর পাশের ফোল্ডারে (`home/youruser/`) ZIP আপলোড করুন
3. Extract করুন, যেন ফাইলগুলো `home/youruser/exportzone/`-এ চলে আসে

> `public_html`-এর **ভেতরে** নয়, তার **পাশে** রাখতে হবে — তাহলেই ডাটাবেস ও `.env`
> ডাউনলোডযোগ্য হবে না।

### ধাপ ২ — Python অ্যাপ তৈরি

**cPanel → Software → “Setup Django App”**

| ঘর | মান |
|---|---|
| Application URL | `example.com` (অথবা `shop.example.com`) |
| Application root | `exportzone` — **স্ল্যাশ ছাড়া, তুলনামূলক পাথ** |
| Deployment method | **Manual** (`cPanel Dispatch` নয়) |
| Python version | `runtime.txt`-এ যা আছে (`python-3.10`) |

**“Add Python App”** চাপুন। এরপর **“Run Upgrade”** চাপলে cPanel `requirements.txt` পড়ে
`venv/` ভার্চুয়াল এনভায়রন্টমেন্ট বানাবে।

> “cPanel Dispatch” বেছে নিলে cPanel প্রতি ১৫ মিনিটে `git pull` + restart করে, যা Git repo
> ছাড়া সাধারণ shared host-এ কাজ করে না। **Manual** রাখুন।

### ধাপ ৩ — কমান্ড চালানো

**cPanel → Terminal** (অথবা SSH):

```bash
cd ~/exportzone
../venv/bin/python manage.py migrate
../venv/bin/python manage.py createsuperuser
```

`collectstatic` সার্ভারে দরকার হলে একইভাবে:

```bash
../venv/bin/python manage.py collectstatic --noinput
```

### ধাপ ৪ — যাচাই

- `https://example.com/` → হোমপেজ
- `https://example.com/shop/` → প্রোডাক্ট
- `https://example.com/admin/` → অ্যাডমিন লগইন

---

## ৫. পরবর্তী আপডেট (রুটিন)

```powershell
# ১. ব্যাকআপ
.\deploy\backup_data.ps1

# ২. কোড-ওনলি প্যাকেজ বানান  ← -SkipData ছাড়া কখনো নয়
.\deploy\build_shared_hosting_package.ps1 -Domain example.com -SkipData

# ৩. ZIP আপলোড করে extract করুন (ফাইলগুলো ওভাররাইট হবে)
# ৪. cPanel → Setup Django App → "Run Upgrade"

# ৫. মাইগ্রেশন থাকলে
cd ~/exportzone && ../venv/bin/python manage.py migrate
```

`db.sqlite3` ও `media/` প্যাকেজে নেই, তাই সার্ভারের অর্ডার, কাস্টমার ও ছবি অপরিবর্তিত থাকে।

---


## ৬. `.env` ও এনভায়রনমেন্ট ভ্যারিয়েবলের অগ্রাধিকার

প্যাকেজে লেখা `.env`-এ `DOTENV_OVERRIDE=0` থাকে, অর্থাৎ
**cPanel → Application environment variables সবচেয়ে বেশি অগ্রাধিকার পায়** — ফাইল এডিট না
করেই যেকোনো একটি মান বদলানো যায়।

| পরিস্থিতি | `DOTENV_OVERRIDE` | কে জেতে |
|---|---|---|
| সার্ভার (প্যাকেজের সাথে আসে) | `0` | কন্ট্রোল প্যানেলের ভ্যারিয়েবল |
| লোকাল ডেভেলপমেন্ট | সেট করা নেই | `.env` ফাইল |

স্থানীয়ভাবে `.env`-এ `DOTENV_OVERRIDE=1` লিখে উল্টোভাবেও করা যায়।

---

## ৭. সমস্যা হলে (Troubleshooting)

### 500 Internal Server Error
- `~/exportzone/`-এ `.htaccess` আছে কি না দেখুন
- **cPanel → Errors** ট্যাবে সার্ভার লগ পড়ুন — সেখানে সত্যিকারের কারণ থাকে
- লাইন নম্বর খুঁজে বের করুন: Python এরর হলে সাধারণত `passenger_wsgi.py` বা `config/settings.py`
- “Application root” ভুল হলে Passenger ফাইলই খুঁজে পায় না — `exportzone` (স্ল্যাশ ছাড়া) আবার দেখুন

### রেডাইরেক্ট লুপ / “সাইট কাজ করছে না”
- SSL না থাকলে `-NoSsl` দিয়ে প্যাকেজ বানান, অথবা সার্ভারের `.env`-এ
  `SECURE_SSL_REDIRECT=False` করুন

### ছবি দেখাচ্ছে না, কিন্তু CSS দেখাচ্ছে
- `media/` ফোল্ডারটা সার্ভারে নেই। cPanel File Manager-এ খালি `media/` ফোল্ডার বানান
  (পরবর্তী `-SkipData` আপলোডে নিজে থেকেই তৈরি হবে)

### CSS দেখাচ্ছে না
- সার্ভারে চালান: `../venv/bin/python manage.py collectstatic --noinput`
- `staticfiles/` ফোল্ডারটা খালি হলে কোড আপডেট হয়নি

### 404 — মডিউল নেই (`No module named ...`)
- cPanel → Setup Django App → **“Run Upgrade”** চাপুন

### “no such table: accounts_customuser”
- `../venv/bin/python manage.py migrate` চালান

### ডাট অদৃশ্য / ওল্ড ডাট দেখাচ্ছে
- `DEBUG=False` হলে SQLite ফাইল খোলা ব্যর্থ হলে Django প্রায় শূন্য ফলাফল দেখায়।
  `.env`-এ `LOG_FILE=~/exportzone/django.log` দিয়ে লগ চালু করে দেখুন।
- **এটিই সবচেয়ে সাধারণ সমস্যা** — সাইট চালু থাকে কিন্তু ডাট দেখায় না

---

## ৮. কখনো যা করবেন না

- সার্ভার থেকে `db.sqlite3` মুছবেন না
- `manage.py flush` চালাবেন না (সব ডাট মুছে যায়)
- `migrate --run-syncdb` চালাবেন না
- সার্ভারে `DEBUG=True` রাখবেন না (টেমপ্লেট ও এনভ ভ্যারিয়েবল দেখা যাবে)
- ডাট সহ প্যাকেজ দিয়ে নিয়মিত আপডেট করবেন না
- `venv/`, `node_modules/` কখনো ZIP-এ দেবেন না (স্ক্রিপ্ট ইতোমধ্যেই বাদ দিয়েছে)

---

## ৯. ফাইল কাঠামো

```
e:\django-backend\ÊXport Zøne\
├── deploy\
│   ├── build_shared_hosting_package.ps1   প্যাকেজ বানায়
│   ├── backup_data.ps1                    ডাট ব্যাকআপ নেয়
│   └── New-ZipArchive.ps1                 (সহায়ক — ZIP হেল্পার)
├── dist\                                  তৈরি ZIP এখানে
├── backups\                               তৈরি ব্যাকআপ এখানে
└── exportzone\                            ← এটাই সার্ভারে যাবে
    ├── manage.py
    ├── passenger_wsgi.py                  Passenger এটাই চালায়
    ├── .htaccess                          সিক্রেট ফাইল আটকায়
    ├── runtime.txt                        Python 3.10
    ├── requirements.txt                   শুধু ৪টি রানটাইম প্যাকেজ
    ├── .env                               (স্ক্রিপ্ট তৈরি করে)
    ├── .secret_key                        (স্ক্রিপ্ট তৈরি করে)
    ├── config\  apps\  templates\  static\
    ├── staticfiles\                       (collectstatic-এর আউটপুট)
    ├── media\                             ← ছবি: আপডেটে বাদ থাকে
    ├── db.sqlite3                         ← ডাট: আপডেটে বাদ থাকে
    └── tmp\                               সেশন ফাইল
```
