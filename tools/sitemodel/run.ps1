#Requires -Version 5.1
<#
.SYNOPSIS
    Produit un site_model Ivion a partir d'un audit de volumes de zone.
    Une seule commande : tout le reste est fabrique ici.

.DESCRIPTION
    Enchaine les deux maillons hors Revit :
        audit_to_zones.py   l'audit AuditVolumes  ->  travail\zones.json
        gen_sitemodel.py    zones.json            ->  travail\site_model_*.json

    L'environnement Python (.venv) se cree tout seul au premier lancement et
    ne se reinstalle jamais ensuite. Rien n'est ecrit dans Revit, ni dans
    OneDrive, ni ailleurs dans le depot : tout atterrit dans travail\, qui
    est ignore par git.

    Le code de sortie vaut 0 si TOUS les controles passent, 1 sinon. Un
    site_model dont un controle a echoue ne doit pas partir chez Ivion :
    l'import teste la conformite, il ne diagnostique pas.

.PARAMETER Audit
    Chemin du JSON produit par le bouton pyRevit AuditVolumes. Obligatoire.

.PARAMETER Batiment
    Nom du batiment porte par le site_model. TheStudy par defaut.

.PARAMETER Sandbox
    Sans ce commutateur, la sortie est GEOREFERENCEE (rotation puis
    translation vers le SCS Ivion). Avec, elle reste dans le repere interne
    Revit : bonne pour un bac a sable, pas pour le site reel.

.EXAMPLE
    .\run.ps1 -Audit "C:\Users\moi\Downloads\audit_volumes_zone_thestudy_A_VOL_20260922_1600.json"

.EXAMPLE
    .\run.ps1 -Audit ..\..\tools\sitemodel\exemples\audit_20260922.json -Batiment Junior -Sandbox

.NOTES
    bimflow - Keovia Solutions inc. - 2026-09-22
    Ecrit pour PowerShell 7 ; compatible 5.1 (aucune syntaxe posterieure a
    5.1 n'est employee : ni ??, ni ternaire, ni &&).
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true,
               HelpMessage = "Chemin du JSON produit par le bouton AuditVolumes")]
    [string] $Audit,

    [string] $Batiment = "TheStudy",

    [switch] $Sandbox
)

$ErrorActionPreference = "Stop"

$ICI = Split-Path -Parent $MyInvocation.MyCommand.Path
$VENV = Join-Path $ICI ".venv"
$PYVENV = Join-Path $VENV "Scripts\python.exe"
$TRAVAIL = Join-Path $ICI "travail"
$REQUIREMENTS = Join-Path $ICI "requirements.txt"

function Ecrire-Titre([string] $texte) {
    Write-Host ""
    Write-Host ("=" * 72) -ForegroundColor DarkGray
    Write-Host $texte -ForegroundColor Cyan
    Write-Host ("=" * 72) -ForegroundColor DarkGray
}

function Arreter([string] $probleme, [string] $quoiFaire) {
    Write-Host ""
    Write-Host "ARRET : $probleme" -ForegroundColor Red
    Write-Host "A faire : $quoiFaire" -ForegroundColor Yellow
    exit 1
}

# --------------------------------------------------------------------------
# 0. L'audit existe-t-il ?
# --------------------------------------------------------------------------

if (-not (Test-Path -LiteralPath $Audit)) {
    Arreter "le fichier d'audit est introuvable : $Audit" `
            ("verifier le chemin. Ce fichier est celui que le bouton " +
             "AuditVolumes ecrit dans Revit, nomme " +
             "audit_volumes_zone_<maquette>_<date>.json - par defaut dans " +
             "le dossier choisi a l'enregistrement (souvent Downloads).")
}
$AuditComplet = (Resolve-Path -LiteralPath $Audit).Path

# --------------------------------------------------------------------------
# 1. L'environnement Python - fabrique une fois, jamais reinstalle
# --------------------------------------------------------------------------

if (-not (Test-Path -LiteralPath $PYVENV)) {

    Ecrire-Titre "Premier lancement : fabrication de l'environnement Python"

    $python = $null
    foreach ($candidat in @("python", "py")) {
        $trouve = Get-Command $candidat -ErrorAction SilentlyContinue
        if ($trouve) { $python = $trouve.Source; break }
    }
    if (-not $python) {
        Arreter "aucun Python trouve sur ce poste" `
                ("installer Python 3 depuis python.org ou le Microsoft " +
                 "Store, puis relancer cette commande. Rien d'autre n'est " +
                 "a installer : le reste se fabrique ici.")
    }

    Write-Host "Python utilise pour construire l'environnement : $python"
    & $python -m venv $VENV
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $PYVENV)) {
        Arreter "la creation de l'environnement a echoue" `
                ("supprimer le dossier tools\sitemodel\.venv puis relancer. " +
                 "Si Dropbox synchronise pendant l'installation, mettre la " +
                 "synchronisation en pause le temps du premier lancement.")
    }

    Write-Host "Installation de shapely (depuis requirements.txt)..."
    & $PYVENV -m pip install --quiet --no-input -r $REQUIREMENTS
    if ($LASTEXITCODE -ne 0) {
        Arreter "l'installation des dependances a echoue" `
                ("verifier la connexion reseau, supprimer " +
                 "tools\sitemodel\.venv, puis relancer.")
    }
    Write-Host "Environnement pret. Les lancements suivants le reutiliseront." `
               -ForegroundColor Green
}

if (-not (Test-Path -LiteralPath $TRAVAIL)) {
    New-Item -ItemType Directory -Path $TRAVAIL | Out-Null
}

# --------------------------------------------------------------------------
# 2. Les deux etapes
# --------------------------------------------------------------------------

# Marqueurs d'echec imprimes par les deux scripts. "ANOMALIES" n'en est PAS
# un : gen_sitemodel y range aussi des notes sous la tolerance d'accrochage.
$MARQUEURS = @("ECHEC", "INCOMPLET", "MANQUE", "sous le metre", "NON VERIFIEE")
$echecs = @()

function Lancer-Etape([string] $titre, [string[]] $arguments) {
    Ecrire-Titre $titre
    $lignes = & $PYVENV @arguments 2>&1
    $code = $LASTEXITCODE
    foreach ($ligne in $lignes) {
        $texte = [string] $ligne
        $couleur = "Gray"
        foreach ($marqueur in $script:MARQUEURS) {
            if ($texte -like "*$marqueur*") {
                $couleur = "Red"
                $script:echecs += $texte.Trim()
                break
            }
        }
        if ($texte -like "*REFUS*") { $couleur = "Red" }
        Write-Host $texte -ForegroundColor $couleur
    }
    return $code
}

$ZONES = Join-Path $TRAVAIL "zones.json"

$code = Lancer-Etape "Etape 1 - l'audit devient des zones" `
            @((Join-Path $ICI "audit_to_zones.py"), $AuditComplet, $ZONES)

if ($code -ne 0 -or -not (Test-Path -LiteralPath $ZONES)) {
    Arreter "la conversion de l'audit a refuse d'ecrire" `
            ("lire les lignes rouges ci-dessus. Elles nomment les volumes en " +
             "cause. Un contour non refermable ou une partition qui ne ferme " +
             "pas se corrigent DANS REVIT, sur les volumes de A_VOL - ce " +
             "script ne repare jamais un contour.")
}

$argsGen = @((Join-Path $ICI "gen_sitemodel.py"), $ZONES, $Batiment)
$suffixe = "scs"
if ($Sandbox) {
    $suffixe = "sandbox"
    Write-Host ""
    Write-Host ("Mode bac a sable : AUCUNE transformation, repere interne " +
                "Revit. Cette sortie n'est pas georeferencee.") `
               -ForegroundColor Yellow
}
else {
    $argsGen += "--scs"
}

$code = Lancer-Etape "Etape 2 - les zones deviennent un site_model" $argsGen

if ($code -ne 0) {
    Arreter "le generateur de site_model s'est arrete" `
            ("lire les lignes rouges ci-dessus. Un contour non constant d'une " +
             "tranche a l'autre, ou une union d'emprises non simple, se " +
             "corrigent dans Revit sur les volumes de A_VOL.")
}

# gen_sitemodel ecrit a cote de lui-meme : on range le resultat dans travail\
$produit = Join-Path $ICI ("site_model_" + $Batiment.ToLower() + ".json")
$final = Join-Path $TRAVAIL ("site_model_" + $Batiment.ToLower() + "_" + $suffixe + ".json")

if (-not (Test-Path -LiteralPath $produit)) {
    Arreter "le site_model n'a pas ete produit" `
            ("relire la sortie de l'etape 2 ci-dessus : elle dit pourquoi.")
}
Move-Item -LiteralPath $produit -Destination $final -Force

# --------------------------------------------------------------------------
# 3. Verdict
# --------------------------------------------------------------------------

Ecrire-Titre "Verdict"

if ($echecs.Count -gt 0) {
    Write-Host ("{0} controle(s) en echec :" -f $echecs.Count) -ForegroundColor Red
    foreach ($ligne in $echecs) { Write-Host "  - $ligne" -ForegroundColor Red }
    Write-Host ""
    Write-Host ("Le fichier a ete ecrit, mais IL NE DOIT PAS PARTIR CHEZ " +
                "IVION en l'etat : l'import teste la conformite, il ne " +
                "diagnostique pas. Corriger les volumes dans Revit, " +
                "relancer l'audit, puis cette commande.") -ForegroundColor Yellow
    Write-Host ""
    Write-Host $final
    exit 1
}

Write-Host "Tous les controles sont passes." -ForegroundColor Green
Write-Host ""
Write-Host $final
exit 0
