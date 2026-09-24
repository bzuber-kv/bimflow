# exemples — les sorties d'audit qui servent de référence

Ce dossier accueille des JSON **réels** produits par le bouton pyRevit
`Audit volumes`, pour que la chaîne se rejoue **sans Revit** :

```powershell
.\tools\sitemodel\run.ps1 -Audit .\tools\sitemodel\exemples\<fichier>.json -Batiment Junior
```

## Ce qu'on attend ici

| Fichier | État |
|---|---|
| `audit_volumes_zone_A_VOL_20260924.json` — **201 volumes, 53 zones, 4 bâtiments**, copie détachée, 0 erreur de lecture | **versé le 2026-09-24** |
| l'audit du 2026-09-22 — 30 volumes, 11 zones | jamais déposé ; celui du 24 le remplace |

Ce que cet audit donne, et qui sert de repère de régression *(mesuré le
2026-09-24, hors Revit)* : **201/201** contours reconstruits · écart contour
↔ face horizontale **0,003 m²** au pire · partition **2 391,88 m²** des deux
côtés, écart **0,00** · **2 zones** écartées par R1 (contour variable) ·
**48 BUILDING**, **192 FLOOR**, tous les contrôles Ivion au vert ·
**14 couples** de `FLOOR` homonymes, tous contigus en Z.

⚠️ Il porte les noms **d'avant** le renommage `VOL_nnn` : la chaîne
`audit_to_zones` les refuse donc, et c'est correct — elle vient après le
bouton `Renommer volumes`. Pour rejouer la chaîne dessus, il faut d'abord
appliquer le dry-run, ou déposer un audit postérieur au renommage.

Il doit porter son `entete.emplacement_partage` : c'est de là que
`gen_sitemodel` tire l'angle au nord vrai et la translation vers le SCS.
Un audit qui en serait dépourvu ferait retomber la chaîne sur les valeurs
de repli — elle le dit, mais elles ne valent que pour The Study.

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
