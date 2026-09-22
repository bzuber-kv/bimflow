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
| 2 | **`gen_sitemodel.py`** | **hors Revit**, CPython 3 + shapely | ce JSON → `site_model_<bâtiment>.json` |

Le JSON est le point de passage unique entre les deux. Le pont ne se
franchit pas dans l'autre sens : rien ici n'écrit dans la maquette.

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

Le reste des contraintes vient de cette fiche-là : emprises de `BUILDING`
d'intérieurs disjoints (C1), pile ordonnée sans chevauchement vertical (C2),
étage inclus dans son bâtiment (C3), pas de superposition 3D entre frères
(C6), tranche d'au moins un mètre pour rester éditable (C10). Le générateur
les contrôle **avant** envoi, parce que l'import Ivion teste la conformité
mais ne diagnostique pas (§5.6).

## Deux écarts connus, à traiter avant la première exécution réelle

1. **Le format d'entrée ne correspond pas encore à la sortie de l'audit.**
   `gen_sitemodel.py` attend `{"zones": {nom_zone: [{etage, coords, zmin,
   zmax, ...}]}}`. `Audit volumes` écrit `{"entete", "volumes", "mass_floors",
   "constats", "erreurs"}`, avec les faces classées et les segments projetés.
   Il manque l'étape qui replie l'un sur l'autre : reconstruire le contour
   d'une zone à partir de ses faces verticales, et grouper par `REF_Etage`.
2. **L'en-tête du générateur dit que l'audit écrit `Level.Elevation`.**
   Ce n'est pas le cas : l'audit publie les altitudes de la **géométrie**, et
   ne se sert jamais de `Level.Elevation` — l'écart entre les deux vaut
   29 065 mm sur The Study (R16 §1.1). Le repère de sortie décrit dans
   l'en-tête, lui, reste juste : origine interne Revit, en mètres, sans
   transformation tant que `THETA` n'est pas mesuré.

Ces deux points sont laissés tels quels : le fichier entre au dépôt **dans
l'état où Bruno l'a écrit**, et se corrigera par un commit qui porte son
motif.
