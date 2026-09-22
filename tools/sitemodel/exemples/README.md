# exemples — les sorties d'audit qui servent de référence

Ce dossier accueille des JSON **réels** produits par le bouton pyRevit
`Audit volumes`, pour que la chaîne se rejoue **sans Revit** :

```powershell
.\tools\sitemodel\run.ps1 -Audit .\tools\sitemodel\exemples\<fichier>.json -Batiment Junior
```

## Ce qu'on attend ici

| Fichier | État |
|---|---|
| l'audit du **2026-09-22** — 30 volumes, 11 zones, trois bâtiments, partition 408,97 m² à 0,00 m² d'écart | **à déposer** — il existe, il n'est pas encore versé |

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
