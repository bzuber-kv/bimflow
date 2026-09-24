# sitemodel — du volume Revit au `site_model` Ivion

> Statut au 2026-09-22 : `Audit volumes` **a tourné dans Revit** ce jour-là,
> et c'est sa sortie qui a fourni les chiffres cités plus bas — 30 volumes,
> 11 zones, trois bâtiments. `gen_sitemodel.py` a été écrit par Bruno et
> entre au dépôt tel quel.

## L'ordre des gestes, côté Revit

Le nom de famille est la **source de vérité** : il porte la zone, l'étage et
la nature. Trois boutons le lisent ou l'écrivent, et l'ordre n'est pas
indifférent — **sur copie détachée d'abord** (R17) :

| # | Bouton | Ce qu'il fait |
|---|---|---|
| 1 | **Renommer volumes** | refait le nom entier : `VOL_nnn` dans l'ordre de l'espace |
| 2 | **Audit volumes** | vérifie les noms, et produit le JSON de la chaîne |
| 3 | **MAJ params volumes** | recopie zone, étage, bâtiment, nature dans les paramètres |

On renomme **avant** d'auditer : un audit passé sur l'ancien motif décrirait
un état déjà périmé. Et on ne renomme jamais dans la même transaction qu'on
lit — c'est pourquoi le renommage est un bouton séparé.

`Renommer volumes` démarre toujours en **simulation** ; ses trois autres
modes écrivent. Le classement peut se rejouer **sans Revit**, sur un audit :

```powershell
python tools\volumes\dry_run_depuis_audit.py <audit.json>
```

C'est le même code que le bouton — `bimflow_noms.extraire()` et
`bimflow_volumes.classer()` — et c'est ce qui permet de lire les 201 noms
avant le moindre clic.

### L'ordre des numéros

`VOL_nnn` suit l'espace, sur trois niveaux : **par BAT** (préfixe de zone,
JU puis MI, SC, SE, EXT en dernier), **par colonne** (une colonne = un
`REF_Zone`, triée d'ouest en est puis du sud au nord **du projet**, sans
aucune rotation), et **par `zmin` croissant** dans la colonne. Lire une
nomenclature triée par nom, c'est descendre le bâtiment colonne par colonne.

Un nord local par groupe (`SE` est à 6,6° du nord projet) est **prévu et
non activé** : personne n'a mesuré qu'il améliore l'ordre, et changer le tri
change tous les numéros.

## Le motif de nom

```
VOL_nnn__<REF_Zone>__<REF_Etage>__<CLS_Nature_volume>[__<clé>]
ex. VOL_007__JU_Bj-Fj-1j-5j__FLOOR_3__ETAGE
    VOL_092__MI_Amg_Emg_1m_3m__ROOF__TOITURE__sup
```

Le 4e segment porte **exactement** une valeur de la liste fermée du socle —
`ETAGE`, `TOITURE`, `ENTRETOIT`, `EXTERIEUR`, `ENVELOPPE` — pour qu'aucune
table de correspondance n'existe entre le nom et le paramètre. C'est cet
arbitrage du 2026-09-22 qui a fait **abandonner le champ `CLS_Destination`** :
la destination Ivion se déduit de la nature. `ENTRETOIT` s'écrit en un mot
depuis le 2026-09-24.

Le **5e segment est optionnel**. `sup` est un simple discriminant d'unicité :
il n'alimente aucun paramètre, et ne change ni le groupe ni le nom d'étage.
`JU`, `MI`, `SC` ou `SE` donnent `REF_Batiment` et **surchargent** le préfixe
de la zone — 18 volumes sont dans ce cas au 2026-09-24.

> ⚠️ **`BAT` et `REF_Batiment` ne sont pas la même chose.** Le `BAT` qui
> **trie** est le préfixe de `REF_Zone` ; `REF_Batiment`, que la clé peut
> surcharger, dit seulement de quel bâtiment relève un volume. Trier sur
> `REF_Batiment` couperait en deux blocs les **8 zones** dont les volumes
> sont affectés à deux bâtiments — or une zone est une colonne, et c'est
> elle qui devient un `BUILDING`.

**Ce qui part vers Ivion** : `ETAGE`, `TOITURE`, `ENTRETOIT`, `EXTERIEUR`.
`ENVELOPPE` est exclue — un volume d'enveloppe LOD100 n'est ni un étage ni
une toiture — et une tranche sans nature ne l'est pas davantage : une nature
ne se devine pas. Le générateur dit combien il a écarté, et pourquoi.

## Une seule commande

```powershell
.\tools\sitemodel\run.ps1 -Audit "<le JSON qu'AuditVolumes a écrit>"
```

Le lanceur fait tout : il fabrique l'environnement Python au premier
lancement, enchaîne les deux étapes, affiche leurs contrôles, range le
résultat dans `travail\`, et **termine par le chemin du fichier à importer
dans Ivion**. Il rend un **code de sortie non nul** si un contrôle échoue —
un `site_model` dont un contrôle a échoué ne part pas chez Ivion.

| Paramètre | Effet |
|---|---|
| `-Audit <chemin>` | le JSON d'`AuditVolumes`. Obligatoire. |
| `-Batiment <nom>` | nom porté par le `site_model`. `TheStudy` par défaut. |
| `-Sandbox` | sortie **non** géoréférencée, repère interne Revit. Sans ce commutateur, la sortie est transformée vers le SCS Ivion. |

Rien n'est à déplacer à la main : `travail\` et `.venv\` sont dans le dépôt
mais ignorés par git, et aucun fichier ne part vers OneDrive.

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
reconstruction est bonne.

### Les chiffres de référence — audit réel du 2026-09-22

C'est le jeu d'essai de référence : **30 volumes, 11 zones**, trois
bâtiments (`Junior`, `SC_atelier`, `SE_office`).

| Contrôle | Valeur mesurée |
|---|---|
| contours reconstruits | **30/30** |
| écart contour ↔ face horizontale | **0,0006 m²** |
| R1, contour constant par zone | vérifiée sur **11 zones** |
| partition en plan | **408,97 m²**, écart **0,00 m²** |
| sortie | **11 BUILDING**, 6 noms d'étage, **5 185,8 m³** |
| contrôles Ivion (C1, C2, C3, C6, C10, 5.1, 2a) | **tous au vert** |

Des chiffres plus restreints ont circulé ici avant : 27 volumes, 9 zones,
partition 326,2 m². Ils portaient sur le seul `Junior` ; ce sont ceux du
tableau ci-dessus qui font foi.

Le JSON de cet audit ira dans `exemples/`, pour que ces chiffres se
rejouent sans Revit et servent de repère de régression.

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

## Une règle, payée deux fois

> **Un contrôle de recouvrement entre tranches porte sur les trois
> dimensions — ou déclare explicitement l'invariant d'emprise dont il
> dépend.**

Tester le seul recouvrement en **Z** n'est valide que **sous la garantie
R1** : si toutes les tranches d'une zone partagent leur contour, alors deux
cotes sécantes impliquent bien un recouvrement 3D. En amont de R1, cette
garantie n'existe pas — et deux volumes **côte à côte**, qui ne se touchent
pas, sont déclarés en faute.

C'est arrivé le 2026-09-24 sur `SC_Dp_Ep_4p_5p` : **3 620 mm** de
recouvrement Z annoncés, **0,000 m²** d'intersection en plan. Deux échanges
perdus, et une maquette saine à deux doigts d'être redessinée.

Deux endroits portaient ce défaut, et le second était le plus grave parce
qu'il **modifie** une cote :

| Où | Ce qui se passait | Ce qui se passe |
|---|---|---|
| rapport des `FLOOR` homonymes | « C6 ECHEC » sur un recouvrement Z seul | intersection des emprises **et** recouvrement Z ; l'étiquette C6 n'est portée que si les deux dépassent la tolérance |
| arbitrage des séparations inclinées (R‑S) | rognait la tranche basse — l'`EXTERIEUR` perdait 3 620 mm de hauteur, en silence | n'arbitre que si les emprises se recoupent ; sinon la paire est **laissée intacte** et listée comme « côtes sécantes, emprises disjointes » |

Le rapport imprime désormais, pour chaque cas, **l'aire d'intersection des
emprises et la hauteur de recouvrement Z** : le diagnostic se relit sans
avoir à y revenir.

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

## Ce qui est éprouvé, et ce qui ne l'est pas

**`AuditVolumes` a tourné dans Revit le 2026-09-22** : 30 volumes, 11 zones,
trois bâtiments, partition mesurée à **0,00 m² d'écart pour 408,97 m²**. Ce
sont les chiffres de référence des contrôles ci-dessus.

**Le JSON de cette exécution n'est pas encore au dépôt.** Il ira dans
`tools/sitemodel/exemples/`, qui existe pour l'accueillir : c'est lui qui
permettra de rejouer la chaîne sans Revit, et de voir en régression le jour
où un contrôle cesse de donner ces chiffres.

**Les deux maillons hors Revit n'ont donc pas encore tourné sur cette sortie
réelle.** Ils ont été éprouvés de bout en bout sur un **audit synthétique**
au format exact de l'outil — deux zones accolées, une séparation inclinée,
un volume à face verticale manquante, un nom hors motif : la conversion
écarte les deux volumes fautifs en les nommant, le générateur sort deux
`BUILDING` tous contrôles au vert, et le lanceur rend 1 dans le premier cas,
0 dans le second.

**`MajParamsVolumes` n'a jamais tourné** — c'est le bouton qui écrit.
