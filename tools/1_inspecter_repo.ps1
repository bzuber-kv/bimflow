# 1_inspecter_repo.ps1 — ETAPE 0 : etat des lieux du repo bimflow
#
# LECTURE SEULE. Ne cree, ne modifie, ne supprime rien.
# A lancer en premier, avant toute autre chose.
#
# Keovia Solutions inc. - 2026-09-10 - cible pwsh 7, compatible 5.1

param(
    [string]$Repo = "D:\Dropbox\Dev\bimflow"
)

function Titre($t) {
    Write-Host ""
    Write-Host ("=" * 70) -ForegroundColor Cyan
    Write-Host "  $t" -ForegroundColor Cyan
    Write-Host ("=" * 70) -ForegroundColor Cyan
}

Titre "0. Le dossier existe-t-il ?"
if (-not (Test-Path $Repo)) {
    Write-Host "INTROUVABLE : $Repo" -ForegroundColor Red
    Write-Host ""
    Write-Host "Cherchons ou il est reellement :" -ForegroundColor Yellow
    foreach ($racine in @("D:\Dropbox\Dev", "D:\Dev", "D:\")) {
        if (Test-Path $racine) {
            Get-ChildItem $racine -Directory -Filter "*bimflow*" -ErrorAction SilentlyContinue |
                ForEach-Object { Write-Host ("  trouve -> " + $_.FullName) -ForegroundColor Green }
        }
    }
    Write-Host ""
    Write-Host "Relance avec le bon chemin :" -ForegroundColor Yellow
    Write-Host '  pwsh -File .\1_inspecter_repo.ps1 -Repo "D:\le\bon\chemin"' -ForegroundColor Yellow
    return
}
Write-Host "OK : $Repo" -ForegroundColor Green

Titre "1. Arborescence du repo (2 niveaux)"
Get-ChildItem $Repo -Directory | ForEach-Object {
    Write-Host ("  " + $_.Name)
    Get-ChildItem $_.FullName -Directory -ErrorAction SilentlyContinue |
        ForEach-Object { Write-Host ("      " + $_.Name) -ForegroundColor DarkGray }
}
Get-ChildItem $Repo -File | ForEach-Object { Write-Host ("  [f] " + $_.Name) -ForegroundColor DarkGray }

Titre "2. Extension pyRevit : onglets, panneaux, boutons"
$ext = Join-Path $Repo "bimflow.extension"
if (-not (Test-Path $ext)) {
    Write-Host "  Pas de bimflow.extension a cet endroit." -ForegroundColor Yellow
} else {
    Get-ChildItem $ext -Directory -Filter "*.tab" | ForEach-Object {
        Write-Host ("  ONGLET  " + $_.Name) -ForegroundColor White
        Get-ChildItem $_.FullName -Directory -Filter "*.panel" | ForEach-Object {
            Write-Host ("     PANNEAU  " + $_.Name) -ForegroundColor Green
            Get-ChildItem $_.FullName -Directory | ForEach-Object {
                Write-Host ("         bouton  " + $_.Name) -ForegroundColor DarkGray
            }
            Get-ChildItem $_.FullName -File | ForEach-Object {
                Write-Host ("         [f] " + $_.Name) -ForegroundColor DarkGray
            }
        }
    }
}

Titre "3. Dossier docs\"
$docs = Join-Path $Repo "docs"
if (Test-Path $docs) {
    Get-ChildItem $docs -File | ForEach-Object { Write-Host ("  " + $_.Name) }
} else {
    Write-Host "  Pas de dossier docs\ (il sera cree a l'etape 3)." -ForegroundColor Yellow
}

Titre "4. .gitignore"
$gi = Join-Path $Repo ".gitignore"
if (Test-Path $gi) {
    Write-Host "  Present. Contenu :" -ForegroundColor Green
    Get-Content $gi | ForEach-Object { Write-Host ("    " + $_) -ForegroundColor DarkGray }
} else {
    Write-Host "  ABSENT — sera cree a l'etape 3." -ForegroundColor Yellow
}

Titre "5. Etat Git"
Push-Location $Repo
try {
    if (-not (Test-Path (Join-Path $Repo ".git"))) {
        Write-Host "  Ce dossier n'est PAS un depot Git." -ForegroundColor Yellow
        Write-Host "  -> il faudra 'git init' puis rattacher le remote GitHub." -ForegroundColor Yellow
    } else {
        Write-Host "  -- git remote -v --" -ForegroundColor White
        git remote -v
        Write-Host ""
        Write-Host "  -- branche courante --" -ForegroundColor White
        git branch --show-current
        Write-Host ""
        Write-Host "  -- git log (5 derniers) --" -ForegroundColor White
        git log --oneline -5 2>&1
        Write-Host ""
        Write-Host "  -- git status --" -ForegroundColor White
        git status --short
        Write-Host ""
        $n = (git status --porcelain | Measure-Object).Count
        Write-Host ("  Fichiers non commites : {0}" -f $n) -ForegroundColor White
    }
} finally {
    Pop-Location
}

Titre "FIN — rien n'a ete modifie"
Write-Host "Copie-colle cette sortie a Claude si quelque chose te surprend." -ForegroundColor Cyan
Write-Host ""
