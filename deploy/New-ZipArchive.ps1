<#
.SYNOPSIS
    Creates a spec-compliant ZIP with forward-slash entry names.

.DESCRIPTION
    .NET Framework's ZipFile::CreateFromDirectory writes entry names with
    Windows backslashes on some runtimes. Linux tools (unzip, cPanel's file
    manager, Passenger) treat the backslash as part of the file name, so the
    archive would explode into files literally called "exportzone\manage.py"
    and the site would break. This helper walks the directory itself and
    always writes proper "exportzone/manage.py" entries, including an entry for
    every directory so that empty folders such as media/ survive the round trip.
#>
function New-NormalizedZipArchive {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][string]$SourceDirectory,
        [Parameter(Mandatory = $true)][string]$DestinationZip
    )

    Add-Type -AssemblyName System.IO.Compression | Out-Null
    Add-Type -AssemblyName System.IO.Compression.FileSystem | Out-Null

    $Root = (Resolve-Path -LiteralPath $SourceDirectory).Path.TrimEnd('\', '/')

    if (Test-Path -LiteralPath $DestinationZip) {
        Remove-Item -Force -LiteralPath $DestinationZip
    }

    $Stream = [System.IO.File]::Open($DestinationZip, [System.IO.FileMode]::CreateNew)
    try {
        $Archive = New-Object System.IO.Compression.ZipArchive(
            $Stream, [System.IO.Compression.ZipArchiveMode]::Create
        )
        try {
            foreach ($Dir in @(Get-ChildItem -LiteralPath $Root -Recurse -Directory -Force)) {
                $Relative = $Dir.FullName.Substring($Root.Length).TrimStart('\', '/').Replace('\', '/')
                $null = $Archive.CreateEntry($Relative + '/')
            }

            foreach ($File in @(Get-ChildItem -LiteralPath $Root -Recurse -File -Force)) {
                $Relative = $File.FullName.Substring($Root.Length).TrimStart('\', '/').Replace('\', '/')
                $Entry = $Archive.CreateEntry(
                    $Relative, [System.IO.Compression.CompressionLevel]::Optimal
                )
                $Entry.LastWriteTime = $File.LastWriteTime

                $Input = [System.IO.File]::OpenRead($File.FullName)
                $Output = $Entry.Open()
                try {
                    $Input.CopyTo($Output)
                } finally {
                    $Output.Dispose()
                    $Input.Dispose()
                }
            }
        } finally {
            $Archive.Dispose()
        }
    } finally {
        $Stream.Dispose()
    }
}
