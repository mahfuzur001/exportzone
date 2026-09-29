<#
.SYNOPSIS
    Builds a clean, upload-ready EXPORT ZONE package for cPanel / shared hosting.

.DESCRIPTION
    Collects only what a shared host actually needs (no .venv, no __pycache__,
    no tests, no dev docs) and zips it together with a production .env.

    The live data is handled explicitly:
      * default     -> db.sqlite3 and media/ are INCLUDED (first deploy)
      * -SkipData   -> both are left OUT of the package, so uploading it can
                       never overwrite the database or the uploaded images that
                       already live on the server.

    The script only ever reads from the working copy; it never deletes or moves
    anything inside the project.

.PARAMETER Domain
    The live domain, e.g. exportzone.com. Used for ALLOWED_HOSTS,
    CSRF_TRUSTED_ORIGINS, SITE_URL and the default from-address.

.PARAMETER NoWww
    Do not add www.<domain> to the host list.

.PARAMETER NoSsl
    The host has no SSL certificate yet: forces http and turns the secure
    cookie / redirect switches off so the site stays reachable.

.PARAMETER BehindTlsProxy
    The host terminates TLS in front of Django (cPanel + nginx, Cloudflare, a
    load balancer). This is the correct mode for cPanel: it trusts
    X-Forwarded-Proto so request.is_secure() is accurate, and it leaves
    SECURE_SSL_REDIRECT off, because with a proxy in front that redirect is the
    classic way to end up in an endless http/https bounce.
    Secure cookies stay on, so a certificate really is required.

.PARAMETER EmailHost
    SMTP host. Either the account's own mail server (cPanel > Email Accounts
    shows it, e.g. mail.example.com) or a third-party relay such as
    smtp.gmail.com. Omit it to keep email on the console backend (messages are
    printed to the Passenger log, not sent).

.PARAMETER EmailUser
    The mailbox or Gmail address that authenticates against EmailHost. For
    Gmail this must be the account the app password belongs to.

.PARAMETER EmailPassword
    The password or app password. Surrounding and inner whitespace is stripped
    automatically, because Google displays app passwords in groups of four
    ("abcd efgh ijkl mnop") and the spaces must not reach the login.

.PARAMETER FromEmail
    The From: address, e.g. "EXPORT ZONE <orders@example.com>". Defaults to
    "EXPORT ZONE <noreply@DOMAIN>". Gmail refuses to send when this differs
    from EmailUser, so pass the Gmail address itself when using Gmail.

.PARAMETER SkipData
    Build a code-only update package. db.sqlite3 and media/ are excluded, so
    uploading it cannot wipe the shop's data.

.PARAMETER SkipCollectStatic
    Reuse the existing staticfiles/ folder instead of re-running collectstatic.

.PARAMETER Flat
    Write every ZIP entry at the archive root instead of nesting everything
    inside an "exportzone/" folder. cPanel's "Setup Django App" already creates
    the application folder, so the archive is uploaded INTO it and extracted
    there; without this switch the files would land in
    ~/export-zone/exportzone/ and the site would not boot.

.PARAMETER SkipDeployDirs
    Leave out tmp/ (and mention nothing else). Use it when cPanel manages the
    deployment folders itself. public/ is never packaged, because overwriting
    cPanel's own public/.htaccess breaks the Passenger rewrite.

.EXAMPLE
    .\build_shared_hosting_package.ps1 -Domain exportzone.com

.EXAMPLE
    .\build_shared_hosting_package.ps1 -Domain exportzone.com -SkipData
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string]$Domain,

    [switch]$NoWww,
    [switch]$NoSsl,
    [switch]$BehindTlsProxy,

    [string]$EmailHost = '',
    [string]$EmailUser = '',
    [string]$EmailPassword = '',
    [string]$FromEmail = '',
    [string]$EmailPort = '587',

    [string]$OutputPath = '',
    [switch]$SkipData,
    [switch]$SkipCollectStatic,
    [switch]$Flat,
    [switch]$SkipDeployDirs,
    [string]$Python = 'python'
)

$ErrorActionPreference = 'Stop'

# Windows PowerShell 5.1 reads .ps1 files as ANSI unless they carry a BOM, so
# this file is deliberately pure ASCII. Every text file written by the script
# is emitted as UTF-8 WITHOUT a BOM: a BOM would corrupt the first key of .env.
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)

$DeployDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root      = Split-Path -Parent $DeployDir
$Project   = Join-Path $Root 'exportzone'

if (-not (Test-Path (Join-Path $Project 'manage.py'))) {
    throw "Could not find the Django project at '$Project'. Run this script from the repository's deploy folder."
}

if (-not $OutputPath) { $OutputPath = Join-Path $Root 'dist' }
New-Item -ItemType Directory -Force -Path $OutputPath | Out-Null

$Stamp  = Get-Date -Format 'yyyyMMdd-HHmmss'
$Build  = Join-Path $OutputPath ("build-{0}" -f $Stamp)
$Stage  = Join-Path $Build  'exportzone'
New-Item -ItemType Directory -Force -Path $Stage | Out-Null

Write-Host ''
Write-Host ' EXPORT ZONE - shared hosting package' -ForegroundColor Cyan
Write-Host (' domain : {0}{1}' -f $Domain, $(if ($NoWww) { '  (www excluded)' } else { '  (+ www)' }))
Write-Host (' ssl    : {0}' -f $(if ($NoSsl) { 'NO (http only)' } else { 'yes' }))
Write-Host (' data   : {0}' -f $(if ($SkipData) { 'CODE ONLY - db/media excluded' } else { 'db.sqlite3 + media INCLUDED' }))
Write-Host (' layout : {0}' -f $(if ($Flat) { 'FLAT - extract straight into the application folder' } else { 'nested in exportzone/' }))
Write-Host ''

# ---------------------------------------------------------------------------
# 1. collectstatic - the host usually cannot run it itself
# ---------------------------------------------------------------------------
if (-not $SkipCollectStatic) {
    Write-Host '> collectstatic ...' -ForegroundColor Yellow
    Push-Location $Project
    try {
        # collectstatic prints one "Deleting ..." line per stale file, which is
        # hundreds of lines of noise here and floods the cPanel log. Only the
        # summary line matters, so the output is captured and re-emitted.
        $StaticOutput = & $Python manage.py collectstatic --noinput --clear 2>&1
        if ($LASTEXITCODE -ne 0) {
            $StaticOutput | Select-Object -Last 20 | ForEach-Object { Write-Host "    $_" -ForegroundColor Red }
            throw "collectstatic failed (exit code $LASTEXITCODE). Fix the error or re-run with -SkipCollectStatic."
        }
        $StaticOutput |
            Where-Object { $_ -match 'static file' -or $_ -match 'Found another file' } |
            ForEach-Object { Write-Host "    $_" -ForegroundColor DarkGray }
    } finally {
        Pop-Location
    }
} else {
    Write-Host '> collectstatic skipped (-SkipCollectStatic)' -ForegroundColor DarkGray
}

# ---------------------------------------------------------------------------
# 2. copy the application code
# ---------------------------------------------------------------------------
Write-Host '> copying application files ...' -ForegroundColor Yellow

$CodeItems = @(
    'manage.py',
    'passenger_wsgi.py',
    'requirements.txt',
    'runtime.txt',
    '.htaccess',
    'config',
    'apps',
    'templates',
    'static'
)

# cPanel creates tmp/ (and public/) itself when the Python application is set
# up. Re-uploading tmp/ is harmless but pointless, and public/ must never be in
# the package at all - cPanel's own public/.htaccess is what routes the domain
# to Passenger, and replacing it takes the whole site down.
if (-not $SkipDeployDirs) {
    $CodeItems += 'tmp'
}

foreach ($Item in $CodeItems) {
    $Source = Join-Path $Project $Item
    if (-not (Test-Path $Source)) {
        Write-Warning "Missing '$Item' - skipped."
        continue
    }
    Copy-Item -Path $Source -Destination $Stage -Recurse -Force
}

# Compiled assets are only useful when collectstatic produced them.
$StaticFiles = Join-Path $Project 'staticfiles'
if (Test-Path $StaticFiles) {
    Copy-Item -Path $StaticFiles -Destination $Stage -Recurse -Force
} else {
    Write-Warning 'staticfiles/ not found - the site will have no CSS. Run collectstatic or drop -SkipCollectStatic.'
}

# Empty Python caches would only slow the upload down.
Get-ChildItem -Path $Stage -Recurse -Directory -Force -Filter '__pycache__' -ErrorAction SilentlyContinue |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
Get-ChildItem -Path $Stage -Recurse -File -Force -Filter '*.pyc' -ErrorAction SilentlyContinue |
    Remove-Item -Force -ErrorAction SilentlyContinue

# Django's test suite. It never runs on the host (no pytest/unittest is executed
# there) so it is dead weight, and shipping it means shipping the shop's order and
# customer fixtures to a public server. apps/core/management/commands/test_email.py
# is deliberately KEPT - that one is a management command run from the terminal.
$TestModules = @('tests.py', 'test_*.py')
foreach ($Pattern in $TestModules) {
    Get-ChildItem -Path $Stage -Recurse -File -Force -Filter $Pattern -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -notmatch '[\\/]management[\\/]commands[\\/]' } |
        Remove-Item -Force -ErrorAction SilentlyContinue
}

# ---------------------------------------------------------------------------
# 3. live data
# ---------------------------------------------------------------------------
if ($SkipData) {
    Write-Host '> data excluded on purpose (-SkipData): the server keeps its db.sqlite3 and media/' -ForegroundColor Green
    # The directory still has to exist, otherwise uploaded images have nowhere
    # to go. Uploading an empty folder never deletes the server's files.
    New-Item -ItemType Directory -Force -Path (Join-Path $Stage 'media') | Out-Null
} else {
    Write-Host '> copying data (db.sqlite3 + media) ...' -ForegroundColor Yellow

    $Db = Join-Path $Project 'db.sqlite3'
    if (Test-Path $Db) {
        Copy-Item -Path $Db -Destination $Stage -Force
    } else {
        Write-Warning 'db.sqlite3 not found in the project - the package will start with an empty database.'
    }

    $Media = Join-Path $Project 'media'
    if (Test-Path $Media) {
        Copy-Item -Path $Media -Destination $Stage -Recurse -Force
    } else {
        New-Item -ItemType Directory -Force -Path (Join-Path $Stage 'media') | Out-Null
    }
}

# ---------------------------------------------------------------------------
# 4. secret key + production .env
# ---------------------------------------------------------------------------
function New-SecretKey {
    $Bytes = New-Object byte[] 64
    $Rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $Rng.GetBytes($Bytes) } finally { $Rng.Dispose() }
    $Text = [Convert]::ToBase64String($Bytes)
    return $Text.Replace('+', '-').Replace('/', '_').TrimEnd('=')
}

$Secret = New-SecretKey
[System.IO.File]::WriteAllText((Join-Path $Stage '.secret_key'), $Secret, $Utf8NoBom)

$HostList = @($Domain)
if (-not $NoWww) { $HostList += "www.$Domain" }
$HostsJoined   = $HostList -join ','
$Scheme        = if ($NoSsl) { 'http' } else { 'https' }
# Braces are required: PowerShell reads "$Scheme:" as a scoped variable.
$OriginsJoined = (($HostList | ForEach-Object { '{0}://{1}' -f $Scheme, $_ }) -join ',')
$Flag          = if ($NoSsl) { 'False' } else { 'True' }
$SiteUrl       = '{0}://{1}' -f $Scheme, $Domain
$FromAddress   = if ($FromEmail) { $FromEmail } else { "EXPORT ZONE <noreply@$Domain>" }
$EmailBackend  = if ($EmailHost) { 'django.core.mail.backends.smtp.EmailBackend' } else { 'django.core.mail.backends.console.EmailBackend' }

# Google shows an app password as four space-separated groups ("abcd efgh ijkl
# mnop"). The spaces are only display, so they must be removed or the login is
# rejected. Trimming only the ends would leave "abcd efgh" and fail silently.
$EmailPassword = ($EmailPassword -replace '\s+', '').Trim()
$EmailUser     = $EmailUser.Trim()

if ($EmailHost -and -not $EmailUser) {
    throw "EMAIL_HOST was given but -EmailUser is empty. Without a login the relay would reject every message."
}
if ($EmailHost -and -not $EmailPassword) {
    throw "EMAIL_HOST was given but -EmailPassword is empty. Drop -EmailHost entirely to stay on the console backend."
}

# Redirect to HTTPS and forward http to https are two different decisions.
#   -NoSsl         : no certificate at all -> no redirect, no secure cookies.
#   -BehindTlsProxy: TLS is terminated upstream -> the app must NOT redirect
#                    (it cannot know the browser is already on https, and a
#                    wrong guess bounces the visitor forever), but cookies are
#                    still marked Secure because the public URL really is https.
#   default        : plain HTTPS everywhere -> redirect.
$SslRedirect   = if ($NoSsl) { 'False' } elseif ($BehindTlsProxy) { 'False' } else { 'True' }
$TrustProxy    = if ($BehindTlsProxy -and -not $NoSsl) { 'True' } else { 'False' }

$SslNote = ''
if ($BehindTlsProxy -and -not $NoSsl) {
    $SslNote = @'
# TLS is terminated by the web server in front of Django (cPanel/nginx).
# SECURE_SSL_REDIRECT is intentionally OFF: Django only sees the internal
# http hop, so redirecting would bounce the visitor between http and https
# forever. TRUST_X_FORWARDED_PROTO tells Django to read the real scheme from
# the X-Forwarded-Proto header instead, which keeps request.is_secure() and
# the secure cookies correct.
'@
}

$EnvLines = @(
    '# EXPORT ZONE - generated by deploy/build_shared_hosting_package.ps1'
    "# Built: $Stamp"
    '# Precedence: 0 = the control panel environment variables win, 1 = this'
    '# file wins. 0 is correct on a shared host, where no unrelated machine-wide'
    '# variable can interfere.'
    'DOTENV_OVERRIDE=0'
    ''
    "SECRET_KEY=$Secret"
    'DEBUG=False'
    "ALLOWED_HOSTS=$HostsJoined"
    "CSRF_TRUSTED_ORIGINS=$OriginsJoined"
    ''
    $SslNote
    "SECURE_SSL_REDIRECT=$SslRedirect"
    "SESSION_COOKIE_SECURE=$Flag"
    "CSRF_COOKIE_SECURE=$Flag"
    'SECURE_HSTS_SECONDS=0'
    'SECURE_HSTS_INCLUDE_SUBDOMAINS=False'
    'SECURE_HSTS_PRELOAD=False'
    "TRUST_X_FORWARDED_PROTO=$TrustProxy"
    ''
    'SQLITE_TIMEOUT=20'
    'SERVE_STATIC_WITH_DJANGO=True'
    'LOG_LEVEL=INFO'
    'LOG_FILE='
    ''
    "EMAIL_BACKEND=$EmailBackend"
    "EMAIL_HOST=$EmailHost"
    "EMAIL_PORT=$EmailPort"
    "EMAIL_HOST_USER=$EmailUser"
    "EMAIL_HOST_PASSWORD=$EmailPassword"
    'EMAIL_USE_TLS=True'
    "EMAIL_TIMEOUT=15"
    'EMAIL_FALLBACK_TO_CONSOLE=True'
    "DEFAULT_FROM_EMAIL=$FromAddress"
    "SITE_URL=$SiteUrl"
)

[System.IO.File]::WriteAllText(
    (Join-Path $Stage '.env'),
    (($EnvLines -join "`n") + "`n"),
    $Utf8NoBom
)

# ---------------------------------------------------------------------------
# 5. in-package cheat sheet (English so it survives any FTP client encoding)
# ---------------------------------------------------------------------------
$DataNote = 'media/  (empty placeholder - your server database and images are untouched)'
if (-not $SkipData) { $DataNote = 'db.sqlite3  media/   <-- THE LIVE DATA' }

if ($EmailHost) {
    $MailNote  = ''
    $MailNote2 = ''
    $MailCheck = @"
EMAIL - CONFIGURED ($EmailHost`:$EmailPort as $EmailUser)
  Prove it from the server (the server's firewall is what matters, not
  your computer's):
       $PyPath manage.py test_email
  It reports the exact reason if it fails. Read cPanel > Errors for the
  Passenger log; when the host blocks outbound SMTP the message is printed
  there instead of being lost.
"@
} else {
    $MailNote  = '  - email is on the console backend: nothing is delivered. To enable it,'
    $MailNote2 = '    rebuild with -EmailHost/-EmailUser/-EmailPassword, then run'
    $MailCheck = @'
  EMAIL - NOT CONFIGURED
     No customer mail can be sent. The quickest fix is an account mailbox:
       cPanel > Email Accounts > create one, then rebuild with
         -EmailHost mail.YOURDOMAIN -EmailUser that@address
         -EmailPassword the-mailbox-password
       An account mailbox always works; a third-party relay such as
       smtp.gmail.com is usually blocked by the host's firewall.
'@
}

# The virtualenv path differs between hosts: cPanel uses
# ~/virtualenv/<app>/<ver>/bin/python, while older documentation assumed
# ../venv/bin/python. The package states cPanel's layout and tells the reader
# where to confirm it.
$PyPath = '../virtualenv/export-zone/3.10/bin/python'

$UpdateCommand = ".\deploy\build_shared_hosting_package.ps1 -Domain $Domain -SkipData"
if ($Flat) { $UpdateCommand += ' -Flat -SkipDeployDirs' }

if ($Flat) {
    $LayoutNote = @'
  NOTE: this ZIP has NO wrapper folder. Extract it directly INSIDE the
  application folder, so manage.py sits next to public/ and tmp/.
'@
} else {
    $LayoutNote = ''
}

$FirstStep1 = '  1. cPanel > Software > "Setup Django App" has already created the'
$FirstStep2 = '     application folder (the one holding public/ and tmp/).'
$FirstStep3 = '  2. Upload this ZIP INTO that folder, then Extract it there.'
$FirstStep4 = ''
$FirstStep5 = '  3. cPanel > Software > "Setup Django App":'
$FirstStep6 = "       Application URL    : $Domain"
$FirstStep7 = '       Application root   : export-zone        (relative, no leading slash)'
$FirstStep8 = '       Deployment method  : Manual      (NOT "cPanel Dispatch")'
$FirstStep9 = '       Python version     : 3.10'
if (-not $Flat) {
    $FirstStep1 = '  1. Upload this ZIP to your home directory (the folder that holds public_html).'
    $FirstStep2 = '  2. Extract it so the files end up in  ~/exportzone/'
    $FirstStep3 = '  3. cPanel > Software > "Setup Django App":'
    $FirstStep4 = "       Application URL    : $Domain"
    $FirstStep5 = '       Application root   : exportzone         (relative, no leading slash)'
    $FirstStep6 = '       Deployment method  : Manual      (NOT "cPanel Dispatch")'
    $FirstStep7 = '       Python version     : 3.10'
    $FirstStep8 = '     Press "Add Python App", then "Run Upgrade" next to it.'
    $FirstStep9 = ''
}

$Readme = @"
EXPORT ZONE - shared hosting package
Built: $Stamp
$LayoutNote
WHAT IS INSIDE
  manage.py  passenger_wsgi.py  .htaccess  runtime.txt  requirements.txt
  config/  apps/  templates/  static/  staticfiles/
  .env  .secret_key
  $DataNote

  public/ and tmp/ are NOT in this ZIP on purpose - cPanel created them and
  cPanel's own public/.htaccess is what routes the domain to Passenger.
  Never overwrite it.

FIRST DEPLOY
$FirstStep1
$FirstStep2
$FirstStep3
$FirstStep4
$FirstStep5
$FirstStep6
$FirstStep7
$FirstStep8
$FirstStep9
  4. Press "Run Upgrade" next to the app so requirements.txt gets installed.
  5. cPanel > Terminal (or SSH) - the virtualenv path is shown in cPanel:
       cd ~/export-zone
       $PyPath manage.py migrate
       $PyPath manage.py createsuperuser
     (migrate is optional the first time: the package already carries a
      migrated db.sqlite3, but it must never be skipped on a later update.)
  6. Open https://$Domain/admin/ and sign in.
     The account is already in db.sqlite3: exportmp2015@gmail.com
     (forgot the password? delete that user in the admin, then re-create it)
  7. Check that mail really leaves the server:
       $PyPath manage.py test_email

LATER UPDATES - IMPORTANT
  Rebuild a code-only package on your computer:
       $UpdateCommand
  Upload it and overwrite the files. db.sqlite3 and media/ are NOT in that
  package, so the orders, customers and uploaded images on the server stay
  exactly as they are.

  Take a backup before any update:
       .\deploy\backup_data.ps1

NEVER
  - do not delete db.sqlite3 on the server
  - do not delete or overwrite the public/ folder
  - do not run "manage.py flush" or "migrate --run-syncdb"
  - do not set DEBUG=True on a public host
$MailNote
$MailNote2

$MailCheck
"@

[System.IO.File]::WriteAllText(
    (Join-Path $Stage 'DEPLOY-README.txt'),
    ((($Readme -replace "`r`n", "`n").TrimStart()) + "`n"),
    $Utf8NoBom
)

# ---------------------------------------------------------------------------
# 6. zip and verify
# ---------------------------------------------------------------------------
$Zip = Join-Path $OutputPath ("exportzone-shared-hosting-{0}.zip" -f $Stamp)

# -Flat zips the stage itself (entries at the archive root); otherwise the
# wrapper folder is included, so extracting into a home directory produces
# ~/exportzone/. New-NormalizedZipArchive always writes forward slashes.
$ZipRoot = if ($Flat) { $Stage } else { $Build }
$Prefix  = if ($Flat) { '' } else { 'exportzone/' }

. (Join-Path $DeployDir 'New-ZipArchive.ps1')
New-NormalizedZipArchive -SourceDirectory $ZipRoot -DestinationZip $Zip

Write-Host ''
Write-Host '> verifying package ...' -ForegroundColor Yellow
$Archive = [System.IO.Compression.ZipFile]::OpenRead($Zip)
try {
    $Entries = @($Archive.Entries | ForEach-Object { $_.FullName })
} finally {
    $Archive.Dispose()
}

$Checks = @(
    @{ Name = 'manage.py';                 Expected = $true },
    @{ Name = 'passenger_wsgi.py';         Expected = $true },
    @{ Name = '.htaccess';                 Expected = $true },
    @{ Name = '.env';                      Expected = $true },
    @{ Name = '.secret_key';               Expected = $true },
    @{ Name = 'requirements.txt';          Expected = $true },
    @{ Name = 'runtime.txt';               Expected = $true },
    @{ Name = 'staticfiles/admin/css/base.css'; Expected = $true },
    @{ Name = 'apps/store/models.py';      Expected = $true },
    @{ Name = 'db.sqlite3';                Expected = (-not $SkipData) },
    # cPanel owns the document root; shipping one would break Passenger.
    @{ Name = 'public';                    Expected = $false },
    # No test code, no compiled caches: neither is ever used on the host.
    @{ Name = 'apps/store/tests.py';       Expected = $false },
    @{ Name = 'apps/core/test_seo.py';     Expected = $false },
    @{ Name = '__pycache__';               Expected = $false }
)
if ($SkipData) {
    $Checks += @{ Name = 'media'; Expected = $true }
}
if (-not $SkipDeployDirs) {
    $Checks += @{ Name = 'tmp'; Expected = $true }
}

$Failed = $false
foreach ($Check in $Checks) {
    $Needle = $Prefix + $Check.Name
    $Found = [bool]($Entries | Where-Object { $_ -eq $Needle -or $_ -like ($Needle + '*') })
    if ($Found -eq $Check.Expected) {
        Write-Host ("    OK      {0}" -f $Needle)
    } else {
        $Failed = $true
        Write-Host ("    {0} {1}   (expected: {2})" -f $(if ($Check.Expected) { 'MISSING' } else { 'ABSENT ' }), $Needle, $Check.Expected) -ForegroundColor $(if ($Check.Expected) { 'Red' } else { 'DarkGray' })
    }
}

# The build folder holds the plaintext .env and secret key - keep only the ZIP.
Remove-Item -Recurse -Force $Build

Write-Host ''
Write-Host (' package : {0}' -f $Zip) -ForegroundColor Green
Write-Host (' size    : {0:N2} MB' -f ((Get-Item $Zip).Length / 1MB))
if ($SkipData) {
    Write-Host ' data    : excluded - the server keeps its own db.sqlite3 and media/'
} else {
    Write-Host ' data    : db.sqlite3 + media/ are INSIDE the ZIP'
}
Write-Host ''
if ($Failed) {
    Write-Warning 'Some expected files are missing - read the list above before uploading.'
} else {
    Write-Host ' Next: read deploy/SHARED_HOSTING_DEPLOY.md' -ForegroundColor Cyan
}
Write-Host ''
