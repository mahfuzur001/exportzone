<#
.SYNOPSIS
    Backs up the live EXPORT ZONE data: db.sqlite3 + media/ (+ secrets).

.DESCRIPTION
    Copies the database, every uploaded image and the secret files into
    backups/exportzone-backup-<timestamp>.zip. Run it before any update and
    before any risky change on the shared host.

    Everything is COPIED first and archived afterwards, so the working copy is
    never moved, truncated or deleted - a broken zip can simply be thrown away
    and the script re-run.

.PARAMETER OutputPath
    Where the ZIP is written. Defaults to <repo>/backups.

.PARAMETER SkipSecrets
    Leave .env and .secret_key out (useful when the archive is shared).

.EXAMPLE
    .\backup_data.ps1
#>
[CmdletBinding()]
param(
    [string]$OutputPath = '',
    [switch]$SkipSecrets
)

$ErrorActionPreference = 'Stop'

$DeployDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root      = Split-Path -Parent $DeployDir
$Project   = Join-Path $Root 'exportzone'

if (-not (Test-Path (Join-Path $Project 'manage.py'))) {
    throw "Could not find the Django project at '$Project'."
}

if (-not $OutputPath) { $OutputPath = Join-Path $Root 'backups' }
New-Item -ItemType Directory -Force -Path $OutputPath | Out-Null

$Stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$Build = Join-Path $OutputPath ("staging-{0}" -f $Stamp)
$Stage = Join-Path $Build  'exportzone-data'

try {
    New-Item -ItemType Directory -Force -Path $Stage | Out-Null

    Write-Host ''
    Write-Host ' EXPORT ZONE - data backup' -ForegroundColor Cyan
    Write-Host ''

    $Db = Join-Path $Project 'db.sqlite3'
    if (Test-Path $Db) {
        Copy-Item -Path $Db -Destination $Stage -Force
        Write-Host ("    db.sqlite3   {0:N0} KB" -f ((Get-Item $Db).Length / 1KB))
    } else {
        Write-Warning 'db.sqlite3 not found - the database is backed up elsewhere.'
    }

    $Media = Join-Path $Project 'media'
    if (Test-Path $Media) {
        Copy-Item -Path $Media -Destination $Stage -Recurse -Force
        $Files = @(Get-ChildItem (Join-Path $Stage 'media') -Recurse -File)
        Write-Host ("    media/       {0} file(s)" -f $Files.Count)
    } else {
        Write-Warning 'media/ not found.'
    }

    if (-not $SkipSecrets) {
        foreach ($Secret in @('.env', '.secret_key')) {
            $Source = Join-Path $Project $Secret
            if (Test-Path $Source) {
                Copy-Item -Path $Source -Destination $Stage -Force
                Write-Host ("    {0}" -f $Secret)
            }
        }
    } else {
        Write-Host '    secrets      skipped (-SkipSecrets)'
    }

    $Zip = Join-Path $OutputPath ("exportzone-backup-{0}.zip" -f $Stamp)
    . (Join-Path $DeployDir 'New-ZipArchive.ps1')
    New-NormalizedZipArchive -SourceDirectory $Build -DestinationZip $Zip

    Write-Host ''
    Write-Host (' backup : {0}' -f $Zip) -ForegroundColor Green
    Write-Host (' size   : {0:N2} MB' -f ((Get-Item $Zip).Length / 1MB))
    Write-Host ''
} finally {
    if (Test-Path $Build) { Remove-Item -Recurse -Force $Build }
}
