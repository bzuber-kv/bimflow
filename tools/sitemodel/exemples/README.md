# exemples — les sorties d'audit qui servent de référence

Ce dossier accueille des JSON **réels** produits par le bouton pyRevit
`Audit volumes`, pour que la chaîne se rejoue **sans Revit** :

```powershell
.\tools\sitemodel\run.ps1 -Audit .\tools\sitemodel\exemples\audit_volumes_zone_A_VOL_20260924_1645.json -Batiment "The Study"
```

## Ce qu'il y a ici

| Fichier | État |
|---|---|
| `audit_volumes_zone_A_VOL_20260924_1645.json` — **202 volumes, 53 zones, 4 bâtiments**, noms au motif `VOL_nnn`, paramètres écrits | **référence, versée le 2026-09-24** |
| `audit_volumes_zone_A_VOL_20260924.json` — 201 volumes, noms **d'avant** le renommage | conservé comme témoin du motif ancien |
| l'audit du 2026-09-22 — 30 volumes, 11 zones | jamais déposé ; ceux du 24 le remplacent |

## Les chiffres de régression

*Mesurés le 2026-09-24, hors Revit, sur l'audit de 16 h 45 — la chaîne
entière, `run.ps1` en une commande, code de sortie 0.*

| Contrôle | Valeur attendue |
|---|---|
| contours reconstruits | **202/202** |
| écart contour ↔ face horizontale | **0,003 m²** au pire (`VOL_142`) |
| R1, contour constant par zone | OK sur les **53** zones |
| partition en plan | **2 391,88 m²** des deux côtés, écart **0,00** |
| règle P | 53 zones → 46 signatures → **50 BUILDING** |
| site_model | **50 BUILDING**, **202 FLOOR**, 9 noms d'étage |
| C1 · C2 · C3 · C6 · C7 · C10 · 5.1 · 2a | tous **OK** |
| volume total | **36 058,1 m³** |
| `FLOOR` homonymes | **14 couples**, tous à recouvrement 3D nul, dans **12 BUILDING** |
| séparations non horizontales arbitrées | **2** (`JU_Aj-Bj-3j-5j` 1 611 mm, `JU_Gj-Hj-1j-3j` 705 mm) |

Si l'un de ces chiffres bouge sans que la maquette ait bougé, c'est le code
qui a changé. C'est à cela que sert ce dossier.

L'union des emprises sort en **MultiPolygon (2 parties)** : c'est un site à
plusieurs corps de bâtiment séparés, et la chaîne le dit sans en faire une
erreur.

Le repère est **lu dans l'audit**, jamais en dur : `entete.emplacement_partage`
donne l'angle au nord vrai et la position de l'origine interne en coordonnées
partagées. Sur cet audit : THETA **−0,5504768 rad (−31,54°)**, DX/DY/DZ
**17,521 / −1,692 / −1,240 m**. Un audit qui en serait dépourvu ferait
retomber la chaîne sur des valeurs de repli — elle le dit, mais elles ne
valent que pour The Study.

⚠️ L'audit de 13 h 11 (`..._20260924.json`) porte les noms **d'avant** le
renommage : `audit_to_zones` les refuse, et c'est correct — la chaîne vient
après le bouton `Renommer volumes`. Il ne sert qu'à vérifier que ce refus
tient.

## Pourquoi au dépôt, alors que les maquettes n'y entrent jamais

Un audit est un **JSON de géométrie déjà réduite** : quelques centaines de
kilo-octets de contours et de faces, pas une maquette. Il joue le rôle d'un
jeu d'essai — c'est lui qui permet de voir, le jour où un contrôle cesse de
rendre ses chiffres de référence, que c'est le code qui a bougé et non le
modèle.

Une règle quand même : **un audit versé ici est un instantané daté**, jamais
une source. La source reste la maquette `A_VOL`. Nommer le fichier avec la
date de l'audit, et ne jamais le retoucher à la main — un jeu d'essai
corrigé ne prouve plus rien.
