# Install the desktop character and put it on screen (Windows).
#   powershell -ExecutionPolicy Bypass -c "irm https://raw.githubusercontent.com/EnkiHQ/awesome-desktop/main/pet/install.ps1 | iex"
$ErrorActionPreference = 'Stop'
$source = 'awesome-desktop @ https://github.com/EnkiHQ/awesome-desktop/archive/refs/heads/main.zip'
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
    $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
}
uv tool install --force $source
$bin = (uv tool dir --bin).Trim()
& (Join-Path $bin 'awesome-pet.exe') start @args
