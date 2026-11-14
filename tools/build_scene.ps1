# Builds static/scene.js (the 3D background) from tools/scene.src.js. Needs Node.js. Run from the repo root:
#   powershell -File tools\build_scene.ps1
# esbuild keeps only the parts of three.js that the scene uses, so the file is small for phones.
$repo = (Get-Location).Path
$alias = "three=" + (Join-Path $repo "tools\vendor\three\three.module.js")
npx --yes esbuild (Join-Path $repo "tools\scene.src.js") --bundle --minify --format=esm --target=es2020 "--alias:$alias" "--outfile=$(Join-Path $repo 'static\scene.js')" --legal-comments=none
Get-Item (Join-Path $repo "static\scene.js") | Select-Object Name, @{n = "KB"; e = { [math]::Round($_.Length / 1KB) } }
