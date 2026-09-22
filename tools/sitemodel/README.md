# sitemodel — du volume Revit au `site_model` Ivion

> Statut au 2026-09-22 : **non éprouvé de bout en bout.** `gen_sitemodel.py`
> a été écrit par Bruno et entre au dépôt tel quel (SHA-256 identique à la
> source). Le bouton `Audit volumes` qui l'alimente n'a jamais tourné dans
> Revit.

## Une chaîne en deux temps, et ce n'est pas un choix de confort

**shapely n'existe pas sous IronPython.** Le moteur pyRevit attaché à
Revit 2026 est IronPython 3.4.2, et il n'y a aucun moteur CPython en netcore.
Toute la géométrie plane du générateur — union d'emprises, test de connexité,
contrôle d'inclusion — repose sur shapely. Elle ne peut donc pas s'exécuter
dans Revit, et la chaîne reste en deux temps :

| Temps | Outil | Où | Entrée → sortie |
|---|---|---|---|
| 1 | bouton **`Audit volumes`** (`Dev.panel`) | **dans Revit**, IronPython 3.4 | maquette `A_VOL` → `audit_volumes_zone_*.json` |
| 2 | **`audit_to_zones.py`** | **hors Revit**, CPython 3 | cet audit → `*_zones.json` |
| 3 | **`gen_sitemodel.py`** | **hors Revit**, CPython 3 + shapely | ces zones → `site_model_<bâtiment>.json` |

Le JSON est le point de passage unique. Le pont ne se franchit pas dans
l'autre sens : rien ici n'écrit dans la maquette.

```bash
python tools/sitemodel/audit_to_zones.py audit_volumes_zone_thestudy_A_VOL_20260922_1600.json
python tools/sitemodel/gen_sitemodel.py audit_volumes_zone_thestudy_A_VOL_20260922_1600_zones.json Junior --scs
```

### Ce que fait le maillon 2, et ce qu'il refuse de faire

`audit_to_zones.py` reconstruit le **contour** d'une zone à partir des faces
**verticales** que l'audit a projetées en XY : il fusionne les extrémités
d'arêtes à 1 mm près, puis les chaîne en cycle. Un cycle valide a **tous ses
sommets de degré 2** et consomme **toutes** ses arêtes.

Il **ne répare jamais** un contour. Un cycle qui ne se referme pas, une zone
dont le contour varie d'une tranche à l'autre (règle R1), une partition en
plan qui ne ferme pas : c'est signalé, et rien n'est écrit pour le volume ou
la zone en cause. Un contour raccommodé en silence produirait un
`site_model` plausible et faux — qu'Ivion refuserait, ou pire, accepterait.

Quatre contrôles sont imprimés, et ce sont eux qui disent si la
reconstruction est bonne — valeurs attendues sur Junior, mesurées le
2026-09-22 : **27/27** contours reconstruits · écart contour ↔ face
horizontale **sous 0,5 m²** · contour **constant** sur toutes les tranches
d'une zone · partition en plan **326,2 m² de part et d'autre**, écart
**0,00 m²**.

Le découpage du nom `VOL__<zone>__<étage>__<attribut>` n'est pas réécrit
ici : il vient du module partagé `bimflow.extension/lib/bimflow_noms.py`,
le même que les deux boutons pyRevit utilisent dans Revit. Un seul endroit
décide de ce qu'est un nom valide.

## Dépendance

`shapely` est une dépendance de **cet outil seulement**, pas de l'extension
pyRevit, qui n'en a ni le besoin ni le moyen. Elle ne s'installe pas dans
pyRevit.

```bash
python -m pip install -r tools/sitemodel/requirements.txt
```

```bash
python tools/sitemodel/gen_sitemodel.py <audit.json> [nom_batiment] [--scs]
```

## La règle P — ce qu'est un `BUILDING`

Un `BUILDING` Ivion n'est pas un conteneur : c'est une **pile**, une suite
ordonnée de tranches partageant **une même suite d'élévations de
séparation**.

> **Règle P.** Deux zones partagent un `BUILDING` si et seulement si
> **(a)** elles ont la même signature d'élévations, à la tolérance
> d'accrochage près, **et (b)** l'union de leurs emprises est simplement
> connexe — un seul polygone.
> Sinon : un `BUILDING` par zone.

C'est l'étape 1 du générateur, et **la seule qui ne se déduise pas** de
`SITE_MODEL.md` v8 (côté `ivion_api`). Énoncé et justification :
`WORK\dev\ivion_api\actions\2026-09-22_LIAISON_bimflow_structure_pile_building.md`.

> Ce chemin est dans **OneDrive**, pas dans ce dépôt : les fiches de
> connaissance et de liaison vivent dans la zone de pilotage `WORK\`, le
> dépôt ne porte que le code et sa documentation technique (§8g). Inutile de
> chercher ce fichier sur le disque du dépôt.

Le reste des contraintes vient de cette fiche-là : emprises de `BUILDING`
d'intérieurs disjoints (C1), pile ordonnée sans chevauchement vertical (C2),
étage inclus dans son bâtiment (C3), pas de superposition 3D entre frères
(C6), tranche d'au moins un mètre pour rester éditable (C10). Le générateur
les contrôle **avant** envoi, parce que l'import Ivion teste la conformité
mais ne diagnostique pas (§5.6).

## Repère et géoréférencement

Par défaut, **aucune transformation** : la sortie est en mètres dans le
repère **interne du modèle Revit**, bonne pour un bac à sable, pas
géoréférencée. L'option `--scs` applique la rotation **−31,54°** puis la
translation **DX/DY/DZ** vers le SCS Ivion, vérifiées sur site le
2026-09-22.

L'origine du repère interne coïncide avec l'**ancien** point de base Ivion
(296952.161 ; 5038971.768 ; 123.760) : c'est de là que vient la
translation. À ne pas confondre avec `Level.Elevation`, que l'audit
n'emploie pas — cette lecture compte depuis la base d'élévation du *type*
de niveau et diffère de la géométrie de **29 065 mm** sur The Study
(R16 §1.1).

## Les deux écarts signalés le 2026-09-22 sont soldés

1. ~~Le format d'entrée ne correspond pas à la sortie de l'audit~~ →
   `audit_to_zones.py` est le maillon manquant.
2. ~~L'en-tête attribue à l'audit un `Level.Elevation` qu'il n'emploie
   pas~~ → en-tête corrigé, et l'écart de 29 065 mm y renvoie à R16 §1.1.

**Ce qui reste non éprouvé** : la chaîne n'a jamais tourné sur des données
réelles, puisque `Audit volumes` n'a jamais été exécuté dans Revit. Elle a
été éprouvée de bout en bout sur un **audit synthétique** au format exact
de l'outil (deux zones accolées, une séparation inclinée, un volume à face
manquante, un nom hors motif) : la conversion écarte les deux volumes
fautifs en les nommant, et le générateur sort deux `BUILDING` avec tous ses
contrôles au vert.
