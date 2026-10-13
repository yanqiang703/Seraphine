<#
.SYNOPSIS
    This script is used to package "Seraphine".

.PARAMETER dest
    The target output path. Default is the current directory.

.PARAMETER dbg
    Whether to enable debug mode. If enabled, the `.\dist` directory will not be deleted and no 7z file will be created.

.EXAMPLE
    .\make.ps1 -dbg
#>

param(
    [Parameter()]
    [String]$dest = ".",
    [Switch]$dbg
)

# 打包前必须关闭所有运行中的实例，否则旧 dist 无法删除，会产出损坏的包
if (Get-Process Seraphine, main -ErrorAction SilentlyContinue) {
    Write-Error "检测到 Seraphine/main 进程正在运行，请先关闭再打包"
    exit 1
}

if ($dbg -and (Test-Path .\dist)) {
    # 删除失败（文件被占用等）直接中止，避免新旧文件混合产出损坏的包
    # 注意: PS5.1 的 Remove-Item 遇到占用文件时 -ErrorAction Stop 不一定可靠, 删完后必须复查
    rm -r -Force .\dist -ErrorAction SilentlyContinue
    if (Test-Path .\dist) {
        Write-Error "旧 dist 目录未删干净（可能有文件被占用或资源管理器打开了该目录），请关闭后重试"
        exit 1
    }
}

# Garante que o PyInstaller resolva as DLLs (libssl/libcrypto) do ambiente
# Python ATIVO, e nao de outro ambiente conda que apareca antes no PATH -- By Claude
# (isso causava "RuntimeError: SSL is not supported" no executavel empacotado)
$pythonExe = (Get-Command python).Source
$envRoot = Split-Path $pythonExe -Parent
$env:PATH = "$envRoot;$envRoot\Library\bin;$envRoot\Scripts;$env:PATH"

# Usa o layout padrao do PyInstaller 6 (tudo dentro de `_internal`, deixando
# so o Seraphine.exe visivel na raiz da pasta) -- By Claude
python -m PyInstaller -w -i .\app\resource\images\logo.ico main.py
rm -r -fo .\build
rm -r -fo .\main.spec
rni -path .\dist\main -newName Seraphine
rni -path .\dist\Seraphine\main.exe -newName Seraphine.exe

# app/resource precisa ficar dentro de `_internal`: e' para la' que o
# os.chdir(dirname(__file__)) do main.py aponta dentro do executavel
# empacotado, entao e' onde os caminhos relativos "app/resource/..." resolvem -- By Claude
cpi .\app -destination .\dist\Seraphine\_internal -recurse
rm -r .\dist\Seraphine\_internal\app\common
rm -r .\dist\Seraphine\_internal\app\components
rm -r .\dist\Seraphine\_internal\app\lol
rm -Path .\dist\Seraphine\_internal\app\resource\game* -r
rm -r .\dist\Seraphine\_internal\app\resource\i18n\Seraphine.zh_CN.ts
rm -r .\dist\Seraphine\_internal\app\resource\bin\fix_lcu_window.c
rm -r .\dist\Seraphine\_internal\app\resource\bin\readme.md
rm -r .\dist\Seraphine\_internal\app\view

$files = Get-ChildItem -Path ".\dist\Seraphine\*" -Recurse |
    Select-Object -ExpandProperty FullName |
    ForEach-Object { $_.Replace((Resolve-Path ".\dist\Seraphine").Path + "\", "") }

$files | Out-File -FilePath ".\dist\Seraphine\filelist.txt" -Encoding UTF8

if (! $dbg) {
    7z a $dest\Seraphine.7z .\dist\Seraphine\* -r
    rm -r .\dist
}
