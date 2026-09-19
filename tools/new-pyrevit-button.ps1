#requires -Version 7
<#
    Cree un nouveau bouton pyRevit conforme au gabarit Keovia.
    Depannage en attendant B19 (interface dans le ruban).

    Exemple :
      .\new-pyrevit-button.ps1 -Nom "B18a_AuditNiveaux" -Titre "Audit des niveaux" `
          -Tooltip "Liste toutes les references de niveau du modele. Lecture seule."
#>
param(
    [Parameter(Mandatory)][string]$Nom,      # interne : sans espace ni accent
    [Parameter(Mandatory)][string]$Titre,    # affiche dans le ruban
    [string]$Panneau = "Calage projet",      # panneau existant, ou nouveau : il est cree
    [string]$Tooltip,
    [switch]$Ecriture,                       # ajoute le squelette transaction + simulation
    # Racine du depot : deduite de l'emplacement du script (tools\ est sous la
    # racine). Aucun chemin de poste en dur - le script suit le depot, ou qu'il
    # soit clone. A ne renseigner que pour viser un autre depot.
    [string]$Depot = (Split-Path $PSScriptRoot -Parent)
)

if ($Nom -match '[^A-Za-z0-9_\-]') { throw "Nom interne : lettres, chiffres, _ et - uniquement." }

if (-not (Test-Path (Join-Path $Depot "bimflow.extension"))) {
    throw "Depot bimflow introuvable : '$Depot' ne contient pas bimflow.extension. Lancer le script depuis tools\ du depot, ou passer -Depot."
}

$panneauDir = Join-Path $Depot "bimflow.extension\bimflow.tab\$Panneau.panel"
if (-not (Test-Path $panneauDir)) {
    New-Item -ItemType Directory -Path $panneauDir -Force | Out-Null
    Write-Host "Nouveau panneau : $Panneau"
}

$btn = Join-Path $panneauDir "$Nom.pushbutton"
if (Test-Path $btn) { throw "Ce bouton existe deja : $btn" }
New-Item -ItemType Directory -Path $btn -Force | Out-Null

# NB : ne jamais nommer ces gabarits $lecture / $ecriture. Les noms de variables
# PowerShell sont insensibles a la casse : $ecriture designerait le parametre
# [switch]$Ecriture, l'affectation echouerait et le squelette d'ecriture ne serait
# jamais ajoute au script genere.
$gabaritLecture = @'
# -*- coding: utf-8 -*-
"""__DOC__"""
__title__ = "__TITRE__"
__author__ = "Keovia Solutions inc."

from Autodesk.Revit.DB import FilteredElementCollector
doc = __revit__.ActiveUIDocument.Document

def val(i):                      # Revit 2024+ : ElementId.Value (fiche R15)
    return i.Value if hasattr(i, "Value") else i.IntegerValue

# --- LECTURE SEULE ---------------------------------------------------------
print(u"Modele : %s" % doc.Title)
'@

$gabaritEcriture = @'

# --- ECRITURE : simulation par defaut (decision 2026-09-10) ----------------
SIMULATION = True                # passer a False apres lecture du rapport
from Autodesk.Revit.DB import Transaction

refus = []                       # ce qui ne peut pas passer : affiche AVANT d ecrire
if refus:
    print(u"%d element(s) hors de portee, rien n a ete ecrit :" % len(refus))
    for r in refus:
        print(u"  %s" % r)

if not SIMULATION and not refus:
    t = Transaction(doc, __title__)
    t.Start()
    try:
        pass                     # les ecritures ici, avec controle avant/apres
        t.Commit()
    except Exception as e:
        t.RollBack()
        print(u"ANNULE, modele intact : %s" % e)
'@

$doc = if ($Tooltip) { $Tooltip } else { $Titre }
$py = $gabaritLecture -replace '__TITRE__', $Titre -replace '__DOC__', $doc
if ($Ecriture) { $py += $gabaritEcriture }

$script = Join-Path $btn "script.py"
Set-Content -Path $script -Value $py -Encoding utf8NoBOM   # sans BOM : IronPython
Write-Host "Cree : $script"
Write-Host "Puis dans Revit : onglet pyRevit > Reload"
if (Get-Command code -ErrorAction SilentlyContinue) { code $script }