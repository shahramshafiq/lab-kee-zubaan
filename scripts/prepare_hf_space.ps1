# Builds a clean folder that can be uploaded to a Hugging Face Space (Docker). Run from the repo root:
#   powershell -File scripts\prepare_hf_space.ps1
# It copies only what the container needs (no keys, no tests, no private files) and adds the Space settings header
# to the README. The GitHub README stays as it is.
param([string]$Out = "C:\dev\hf-space")

$repo = (Get-Location).Path
if (-not (Test-Path (Join-Path $repo "Dockerfile"))) { Write-Error "Run this from the repo root"; exit 1 }

if (Test-Path $Out) { Remove-Item $Out -Recurse -Force }
New-Item -ItemType Directory -Force $Out | Out-Null

foreach ($item in "app", "static", "lab_reports") {
    Copy-Item (Join-Path $repo $item) (Join-Path $Out $item) -Recurse
}
Copy-Item (Join-Path $repo "Dockerfile") $Out
Copy-Item (Join-Path $repo "requirements.txt") $Out

# remove anything that should never be uploaded
Get-ChildItem $Out -Recurse -Force -Include "__pycache__", ".tts_cache", ".env", "*.pyc" | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

$header = @"
---
title: Lab Kee Zubaan
sdk: docker
app_port: 8000
pinned: false
short_description: Lab reports explained in plain words, in English and Urdu
---

"@
$readme = Get-Content (Join-Path $repo "README.md") -Raw
Set-Content (Join-Path $Out "README.md") ($header + $readme) -Encoding utf8

Write-Host "Ready: $Out"
Get-ChildItem $Out | Select-Object Name
