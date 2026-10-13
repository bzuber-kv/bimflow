# Photo maquette — état du modèle actif en un JSON

> Repo `bimflow` · portée : **générique** (standard Keovia) · créé le 2026-10-12 · mis à jour le 2026-10-13 (version `2026-10-13b` : recette de `2026-10-13a`, message d'unicité sur maquette sans volume)
> Bouton : `bimflow.tab\Dev.panel\PhotoMaquette.pushbutton` — **bleu, lecture seule**
> Logique testable : `bimflow.extension\lib\bimflow_photo.py` · tests : `tests\test_bimflow_photo.py`
> Statut : versions `2026-10-12a` à `2026-10-13a` **éprouvées** dans Revit (§9) ; version `2026-10-13b` **non éprouvée** (§9.4).

Les exemples tirés de The Study sont marqués *spécifique The Study* ; tout le
reste vaut pour toute maquette.

## 1. Ce que fait le bouton, et pour quoi

Il lit le modèle actif et écrit **un** fichier JSON : l'état de la maquette à
un instant. Aucune transaction, aucun emprunt, aucune synchronisation : rien
n'est écrit dans la maquette.

La photo sert à **comparer** deux états (avant / après un lot de travail, deux
maquettes d'un même projet), à **rejouer** un contrôle hors Revit (le JSON se
relit en Python sans Revit) et à **documenter** l'état d'une maquette à une
date. Une photo ne se corrige pas : on en prend une autre.

## 2. Mode d'emploi

1. Ouvrir la maquette, sous-projets utiles **ouverts** (§8), puis cliquer *Photo maquette*.
2. Choisir le dossier de sortie : la boîte s'ouvre sur le dernier dossier choisi ; *Annuler* n'écrit rien.
3. Lire le rapport (§7) ; le chemin du JSON est en fin de rapport.

## 3. Contenu du JSON

Fichier `<dossier>\<modele>_<AAAA-MM-JJ_HHMM>.json`, UTF-8 sans BOM. Il
n'écrase jamais une photo précédente (`_2`, `_3`… si la minute est prise) et
s'écrit **atomiquement** : fichier temporaire du même dossier, puis renommé ;
en cas d'échec, aucun fichier partiel ne reste.

Unités : longueurs internes en **mm**, coordonnées partagées en **m**, surfaces
en **m²**, angles en **degrés**. Repères : *interne* = repère de la géométrie
du modèle ; *partagé* = coordonnées partagées (§5). `null` = absent ou sans
valeur ; `NON_LU` = la lecture a levé une exception (§4).

### 3.1 `en_tete`

| Champ | Sens | Unité / repère |
|---|---|---|
| `outil`, `version_outil` | `bimflow - Photo maquette`, version du script (ex. `2026-10-13a`) | — |
| `modele` | `doc.Title` lu à l'exécution | — |
| `chemin` | `doc.PathName`, `null` s'il est vide | — |
| `date` | instant de la photo, ISO 8601 avec fuseau (ex. `2026-10-13T00:40:12-04:00`) | heure locale du poste |
| `revit_version`, `revit_build` | version et build de Revit | — |
| `utilisateur_revit`, `utilisateur_windows` | nom d'utilisateur Revit, compte Windows | — |
| `collaboratif`, `detache` | maquette en travail partagé ; ouverte détachée (`null` si illisible) | — |
| `collaboratif_non_detache` | collaborative et pas détachée de façon certaine : on lit une **copie locale** | — |
| `source_lue` | `copie locale (…)` ou `fichier ouvert` | — |
| `avertissement` | présent si `collaboratif_non_detache` : ce que la copie locale contient ou non | — |
| `sous_projets_fermes` | noms des sous-projets fermés (§8) | — |
| `unites` | rappel des unités ci-dessus | — |
| `reperes.point_de_base`, `reperes.point_topographique` | `id`, `position_interne_mm` {x, y, z}, `position_partagee_m` {x, y, z} | mm interne ; m partagé |
| `reperes.transformation_interne_partage` | `sens_retenu` (`directe` / `inverse` / `null`), `residus_mm` par sens, `tolerance_mm`, `motif_si_absente` (§5) | mm |
| `reperes.orientation` | rappel de la convention d'azimut (§5) | — |
| `socle` | `fichier` du socle lu, GUID utilisés par nom pour `niveaux` et `volumes` (§4) | — |

### 3.2 `niveaux` — triés par élévation

| Champ | Sens | Unité / repère |
|---|---|---|
| `nom`, `id` | nom du niveau, ElementId | — |
| `elevation_pbp_mm` | `Level.ProjectElevation` − Z interne du point de base du projet : **la** valeur publiée | mm, depuis le point de base |
| `project_elevation_mm` | `Level.ProjectElevation`, pour contrôle | mm interne |
| `level_elevation_mm`, `base_elevation_type` | `Level.Elevation` et la base d'élévation du **type** de niveau dont il part (R10, `docs\niveaux.md` §1.1), pour contrôle | mm |
| `REF_Batiment`, `REF_Etage` | paramètres du socle, valeur seule (détail dans `parametres`) | — |
| `parametres` | par paramètre : `valeur`, `statut`, `porteur` (§4) | — |

### 3.3 `quadrillages` — triés par nom

| Champ | Sens | Unité / repère |
|---|---|---|
| `nom`, `id`, `type` | nom exact, ElementId, nom du type | — |
| `courbe` | `ligne` ou `arc` | — |
| `debut_partage_m`, `fin_partage_m` | extrémités {x, y, z} | m partagé |
| `debut_interne_mm`, `fin_interne_mm` | extrémités, pour contrôle | mm interne |
| `orientation_deg` | azimut début → fin, 0 = nord partagé, sens horaire, [0, 360) ; `null` pour un arc | degrés, partagé |
| `direction_deg` | orientation ramenée dans [0, 180) : c'est elle qui compare deux axes | degrés, partagé |
| `orientation_interne_deg` | même azimut dans le repère interne, pour contrôle | degrés, interne |

### 3.4 `volumes` — catégorie Volumes, triés par famille

| Champ | Sens | Unité / repère |
|---|---|---|
| `nom_type` | `Element.Name` : pour un volume in situ, c'est le nom du **type** (ex. `Volume Ivion`) | — |
| `famille` | nom de la famille : le nom **porteur de sens** (`VOL_nnn__…`) | — |
| `id` | ElementId | — |
| `REF_Zone`, `REF_Etage`, `REF_Batiment`, `CLS_Nature_volume`, `REF_Id` | paramètres du socle, valeur seule | — |
| `boite_mm` | boîte englobante {`min`, `max`} {x, y, z} | mm interne |
| `parametres` | par paramètre : `valeur`, `statut`, `porteur` (§4) | — |

Jusqu'à la version `2026-10-12c`, `nom_type` s'appelait `nom` : un programme
qui lit d'anciennes photos doit accepter les deux. Les autres rubriques gardent
`nom`.

### 3.5 `pieces` — triées par numéro

| Champ | Sens | Unité / repère |
|---|---|---|
| `id`, `numero`, `nom`, `niveau` | ElementId, numéro, nom, nom du niveau | — |
| `surface_m2` | surface | m² |
| `point_mm`, `point_partage_m` | point de localisation | mm interne ; m partagé |
| `etat` | lu sur l'API : `non placee` (sans emplacement), `surface nulle` (placée, non fermée ou redondante), `placee` | — |

### 3.6 `sous_projets` — triés par nom

`nom`, `id`, `ouvert`, `nombre_elements` (toutes les instances que Revit range
dans le sous-projet, `ElementWorksetFilter`, éléments sans catégorie compris ;
`null` si fermé). Rubrique vide pour une maquette non collaborative.

### 3.7 `liens` — triés par type puis nom

`nom`, `id`, `type` (`Revit`, `CAO`, `Nuage de points`), `epingle` ; `charge`
pour les liens Revit. Pour un lien CAO, `nom` est le nom de son type ; un
import CAO non lié n'est pas un lien et n'apparaît pas.

### 3.8 `comptes` et `signalements`

`comptes`, par rubrique : `nombre`, `champs_nuls` (champ → nombre, un `NON_LU`
compté sous `<champ> (NON_LU)`) et, pour niveaux et volumes, `parametres`
(paramètre → nombres `lu`, `vide`, `absent`, `illisible`). Pour les volumes
s'y ajoute `unicite_REF_Id` (§6) : `valeurs_controlees`, `portees_par_type`,
`doublons` (liste de {`valeur`, `nombre`, `elements` [{`id`, `nom_type`,
`famille`}]}).

`signalements` : liste de textes, tout ce qui manque ou cloche, dans l'ordre
de détection.

## 4. Règles de lecture — rien n'est déduit

- **Paramètres lus par GUID**, GUID cherchés **par nom** dans le socle versionné
  `shared_parameters\keovia_socle_parametres.txt`. Aucun GUID dans le script.
  Un nom absent du socle est signalé et le champ vaut `null` partout.
- Lecture sur l'instance, puis sur le type ; `porteur` dit lequel
  (`instance`, `type`, `null` si absent).
- Quatre statuts, tous comptés : `lu` (valeur) ; `vide` (le paramètre existe
  sans valeur) → `null` ; `absent` (ni sur l'élément ni sur son type) →
  `null` ; `illisible` (exception) → `NON_LU`, message dans `erreur`.
- Toute autre lecture qui échoue (élévation, coordonnées, famille…) vaut
  `NON_LU`, jamais un `null` silencieux.
- **Aucune donnée tirée d'un nom** : ni niveau, ni zone, ni bâtiment. Les noms
  sont publiés, jamais découpés.

## 5. Repères et transformation interne → partagé

- **Coordonnées partagées** : `ActiveProjectLocation.GetTotalTransform()`. Le
  sens (directe ou inverse) **n'est pas supposé** : il est choisi sur le point
  topographique et le point de base, dont Revit donne la position interne et la
  position partagée. Le résidu de chaque sens (pire écart sur ces deux points)
  est publié ; aucun sens sous la tolérance (1 mm) ⇒ coordonnées partagées
  `null` et signalement. *Mesuré* à la recette (§9) : sens **inverse**, résidu
  0,000 mm, contre ~9,7·10⁹ mm pour le sens direct.
- **Élévation des niveaux** : depuis le point de base du projet (§3.2).
- **Orientation d'un quadrillage** : azimut dans le repère partagé, 0 = nord
  partagé, sens horaire (§3.3).
- **Boîtes englobantes** et points de pièces : repère interne, mm.

## 6. Contrôle d'unicité a posteriori

Un copier-coller Revit (copier, réseau, miroir, groupe, « coller aligné »)
recopie toutes les valeurs d'instance, `REF_Id` compris : l'unicité d'un
identifiant écrit dans un paramètre n'est **pas** garantie par Revit. Choix
retenu (Bruno, 2026-10-12) : pas de prévention, une **unicité garantie a
posteriori**, par contrôle à chaque mise à jour régulière de la production,
quitte à tenir des matrices de passage datées.

Le bouton porte le contrôle (liste `IDENTIFIANTS_UNIQUES` de
`lib\bimflow_photo.py`, aujourd'hui `REF_Id` des volumes) :
- seules comptent les valeurs **lues sur l'instance** ; `null` et `NON_LU` ne
  sont pas des valeurs ;
- une valeur portée par le **type** est partagée par construction : elle n'est
  pas un doublon, elle est comptée à part (`portees_par_type`) et signalée ;
- la comparaison ignore casse et blancs de bord ; la valeur publiée reste
  celle lue ;
- rubrique vide (aucun volume dans la maquette) ⇒ « rien à contrôler », sans
  signalement ;
- volumes présents mais aucune valeur contrôlée ⇒ « **non contrôlée** »,
  jamais « aucun doublon » ;
- rien n'est corrigé et l'original n'est pas désigné : l'arbitrage et la
  correction relèvent d'un autre outil, à spécifier.

Règle candidate — **générique, à recadrer** ; cas d'origine : The Study,
VOL_090 / VOL_091 (2026-10-12, §9).

## 7. Rapport à l'écran

Dans l'ordre : titre (modèle) ; alerte si des sous-projets sont fermés ;
mention « copie locale » pour une maquette collaborative ; tableau des comptes
par rubrique (nombre, champs null) ; tableaux des statuts de paramètres
(niveaux, volumes) ; section *Unicité* (valeurs contrôlées, doublons et qui les
porte ; ou « non contrôlée » ; ou « rien à contrôler : aucun volume dans la
maquette ») ; états des pièces ; signalements ; sortie
(chemin du JSON, ou boîte annulée, ou échec d'écriture — sans fichier
partiel) ; rappel « lecture seule » et version.

Tout texte venu de la maquette (noms, valeurs, signalements, chemins) est
**échappé** pour le Markdown de la fenêtre pyRevit (`echapper_md` : chaque
caractère parmi `` \ ` * _ { } [ ] ( ) # + - . ! | < > & ~ `` devient une
entité HTML numérique, et ces textes ne sont plus mis entre backticks). Sans
cela, `VOL_090__SC__…` perdait ses « __ », même entre backticks (constat
rapporté par Bruno le 2026-10-13). Le JSON, lui, n'est jamais échappé.

## 8. Limites connues

- **Sous-projets fermés** : leurs éléments ne sont pas chargés et manquent à
  tous les comptes. Annoncés en tête de rapport ; leur `nombre_elements` vaut
  `null`.
- **Maquette collaborative non détachée** (toute maquette cloud) : la photo
  décrit la **copie locale** — dernière synchronisation de l'utilisateur
  **plus** ses modifications non synchronisées — et non l'état de la
  centrale ; le travail non synchronisé des autres n'y est pas.
- **Z partagé des quadrillages** : c'est la cote de l'origine interne (z = 0
  interne). Exact, mais sans signification : un quadrillage n'a pas d'altitude
  propre.
- **Quadrillages multi-segments** : chaque segment est un `Grid` et sort comme
  tel ; le regroupement n'est pas fait.
- **Liens IFC** : sortent en type `Revit` (ce sont des `RevitLinkInstance`).
  Liens de coordination (Navisworks) non couverts.
- **Boîte de dossier** : `forms.pick_folder` de pyRevit 6.5.5 n'accepte pas de
  dossier initial (lu dans `pyrevitlib\pyrevit\forms\_ipy.py`, 2026-10-13) ;
  le bouton ouvre donc `FolderBrowserDialog` sur le dernier dossier. Si cette
  boîte échoue, repli sur `pick_folder`, sans dossier initial, et le rapport
  le dit.
- **Sortie sous OneDrive** — écart signalé, non tranché : `Audit volumes` et
  `Renommer volumes` interdisent toute sortie sous OneDrive ou `WORK`
  (`FRAGMENTS_INTERDITS`) ; ce bouton écrit dans le dossier choisi, OneDrive
  compris. La règle §8g (`03_REGLES_DEV.md`) n'interdit que le *code* dans
  OneDrive, pas les données. Règle commune à décider.

Instance The Study (*spécifique The Study*) — dossier de sortie prévu :
`%USERPROFILE%\OneDrive - KEOVIA Solutions\WORK\affaires\A_049_TheStudy\context\ref\maquette_photo`

## 9. Recette

*Spécifique The Study* pour les comptes ; les constats sur l'outil sont
génériques.

### 9.1 2026-10-12 — version `2026-10-12a`, `thestudy_G_AN` et `thestudy_G_VL`

Revit 2026 (26.4.0.32), maquettes collaboratives cloud, copie locale lue,
aucun sous-projet fermé.

| Maquette | Heure | Niveaux | Quadrillages | Volumes | Pièces | Sous-projets | Liens | Résidu transformation | Signalements |
|---|---|---|---|---|---|---|---|---|---|
| `thestudy_G_AN` | 16:58 | 23 | 73 | 0 | 0 | 37 (1 753 éléments, 16 vides) | 19 (18 nuages, 1 Revit) | 0,000 mm (inverse) | 1 |
| `thestudy_G_VL` | 16:59 | 23 | 0 | 217 | 0 | 36 (2 189 éléments, 17 vides) | 1 (Revit) | 0,000 mm (inverse) | 6 |

**Ce que la recette établit sur l'outil (mesuré).**
- Sens de `GetTotalTransform` : **inverse**, résidu 0,000 mm sur le point de
  base et le point topographique, contre ~9,7·10⁹ mm pour le sens direct. Le
  choix automatique fonctionne ; les coordonnées partagées sont fiables.
- Point de base relu à (296 934,64 ; 5 038 973,46 ; 94,695 m) et point
  topographique à z = 0 : conforme au géoréférencement consigné au PEP A_049.
- `elevation_pbp_mm` = `Level.Elevation` sur les 23 niveaux, dont la base
  d'élévation de type est le point de base : contre-vérification cohérente.
- Z partagé des quadrillages = 123,76 m : la cote de l'origine interne (§8).
- Le `nom` d'un volume in situ était le **nom du type** (`Volume Ivion` pour
  210 volumes) ; le nom porteur de sens est `famille` (`VOL_nnn__…`) —
  d'où `nom_type` en version `2026-10-13a`.

**Ce que la recette fait apparaître dans les maquettes (mesuré, à traiter côté A_049).**
- `REF_Etage` vide sur les deux niveaux `Site` (`EXT_BLVD`, `EXT_PARC`) :
  vide légitime ou valeur manquante, à décider.
- Quadrillages : deux familles d'orientation — 31,34° / 121,34° (Senior
  Central, Junior, Middle, parking) et 37,94° / 127,94° (Senior East), soit
  **6,60°** entre les deux trames.
- `thestudy_G_VL` : **2 volumes sans aucun paramètre** (`Volume 1` id 5532336,
  `Volume 2` id 5530844, emprise ~36 × 67 m) — **chantier en cours** déclaré
  par Bruno (rattacher les zones extérieures aux étages), pas un défaut.
- `thestudy_G_VL` : **un `REF_Id` en double** (`dbe39340-…`) sur
  `VOL_090__SC_Bp_Amg_1p_3p__FLOOR_2__ETAGE` et
  `VOL_091__SC_Bp_Amg_1p_3p__ROOF__TOITURE` — or `REF_Id` est la clé de
  jointure vers Ivion et ne doit jamais se répéter. Cause confirmée par
  Bruno : VOL_091 obtenu par **copie de VOL_090** après écriture des
  paramètres.
- 217 volumes contre 202 au 2026-09-24. Aucune pièce dans l'une ou l'autre
  maquette.
- Les deux JSON ont été écrits dans `Downloads`, pas dans `maquette_photo`.

Le contrôle d'unicité (version `b`) a été rejoué hors dépôt sur
`thestudy_G_VL_2026-10-12_1659.json` (photo du 2026-10-12 16:59) : il trouve
VOL_090 / VOL_091.

### 9.2 2026-10-13 — version `2026-10-12c`, `thestudy_G_VL`

Exécution du 2026-10-13 à 00:40, maquette collaborative cloud, copie locale
lue. Comptes relevés sur le rapport par Bruno :

| Maquette | Heure | Niveaux | Quadrillages | Volumes | Pièces | Sous-projets | Liens | Signalements |
|---|---|---|---|---|---|---|---|---|
| `thestudy_G_VL` | 00:40 | 23 | 0 | 217 | 0 | 36 | 1 (Revit) | 7 |

| Rubrique | Paramètre | Lus | Vides |
|---|---|---|---|
| niveaux | `REF_Batiment` | 23 | 0 |
| niveaux | `REF_Etage` | 21 | 2 |
| volumes | `REF_Zone`, `REF_Etage`, `REF_Batiment`, `CLS_Nature_volume`, `REF_Id` | 215 chacun | 2 chacun |

- **Unicité** : 215 valeurs contrôlées, **1 doublon** —
  `dbe39340-81d3-4d74-9e1c-ce84a853d07d` sur VOL_090 (id 5487277) et VOL_091
  (id 5526199), le doublon déjà trouvé le 2026-10-12 (§9.1).
- **Points jusque-là non éprouvés, constatés conformes** : en-tête « copie
  locale » affiché ; boîte de dossier à chaque clic ; section *Unicité* ;
  JSON écrit.
- **Défaut constaté** : à l'écran, les « __ » des noms de famille
  disparaissent, même entre backticks (table *Unicité* et signalements) ; le
  JSON est intact. Motif de la version `2026-10-13a` (§7).
- *Mesuré* (source : `thestudy_G_VL_2026-10-13_0040.json`) : les 2 niveaux
  à `REF_Etage` vide sont `EXT_BLVD` et `EXT_PARC`, les deux niveaux `Site`
  déjà relevés au §9.1 ; les 2 volumes vides sont `Volume 1` (id 5532336) et
  `Volume 2` (id 5530844), le chantier en cours du §9.1.

### 9.3 2026-10-13 — version `2026-10-13a`, `thestudy_G_AN` et `thestudy_G_VL`

Exécution du 2026-10-13 vers 01:04, maquettes collaboratives cloud, copie
locale lue. Comptes relevés sur le rapport par Bruno :

| Maquette | Niveaux | Quadrillages | Volumes | Pièces | Sous-projets | Liens | Résidu transformation | Signalements |
|---|---|---|---|---|---|---|---|---|
| `thestudy_G_AN` | 23 | 73 | 0 | 0 | 37 | 19 | 0,000 mm | 1 |
| `thestudy_G_VL` | 23 | 0 | 217 | 0 | 36 | 1 | non relevé | 7 |

- `thestudy_G_AN`, niveaux : `REF_Batiment` 23 lus ; `REF_Etage` 21 lus /
  2 vides. Date de l'en-tête au format ISO avec fuseau : conforme.
- `thestudy_G_VL`, volumes : les 5 paramètres (`REF_Zone`, `REF_Etage`,
  `REF_Batiment`, `CLS_Nature_volume`, `REF_Id`) à 215 lus / 2 vides chacun.
  Unicité : 215 valeurs contrôlées, 1 doublon `dbe39340-…` (VOL_090 id
  5487277, VOL_091 id 5526199), le même qu'aux §9.1 et §9.2. Champ
  `nom_type` présent ; `famille` porte les noms complets.

**Vérifié à l'écran par Bruno.**
- Les noms avec « __ » s'affichent entiers : défaut de la version
  `2026-10-12c` (§9.2) corrigé.
- La boîte de dossier s'ouvre directement sur le dernier dossier
  (Téléchargements).
- Aucun fichier `.tmp` résiduel : seul le `.json` est écrit.

**Reste non éprouvé** pour cette version : le repli sur `pick_folder` (§8),
qui ne s'est pas déclenché.

**Défaut constaté** : sur `thestudy_G_AN`, qui n'a aucun volume, la section
*Unicité* affiche « Non controlee : aucune valeur lue sur l'instance » —
trompeur, il n'y avait rien à contrôler. Aucun signalement d'unicité n'est
émis dans ce cas (le seul signalement de G_AN est d'un autre ordre).
Motif de la version `2026-10-13b`.

### 9.4 Version `2026-10-13b` — non éprouvée

À vérifier dans Revit, sur une maquette sans volume (ex. `thestudy_G_AN`) :
la section *Unicité* affiche « Rien a controler : aucun volume dans la
maquette » et aucun signalement d'unicité.

## 10. Historique des versions

| Version | Date | Contenu |
|---|---|---|
| `2026-10-12a` | 2026-10-12 | Première version. Dossier de sortie lu dans un fichier du poste, Maj+clic pour le changer. Éprouvée le jour même (§9.1). |
| `2026-10-12b` | 2026-10-12 | Dossier demandé **à chaque clic** (décision Bruno), le dernier rappelé dans le titre ; réglage Maj+clic (`config.py`) et exemple de configuration retirés. Contrôle d'unicité de `REF_Id` (§6). |
| `2026-10-12c` | 2026-10-12 | Corrections d'une relecture critique indépendante, sans point bloquant : « non contrôlée » au lieu d'un faux « aucun doublon » ; en-tête « copie locale » (champ `collaboratif_non_detache`) au lieu de « état synchronisé de la centrale » ; valeurs portées par le type exclues du contrôle ; `NON_LU` sur les lectures en échec (élévation, coordonnées, famille) et import CAO illisible signalé ; messages distincts annulation / échec d'écriture, rappel mis à jour après une écriture réussie seulement ; comparaison insensible à la casse ; pièces triées. Seconde relecture le 2026-10-13 (statuts, nettoyages). Éprouvée le 2026-10-13 (§9.2). |
| `2026-10-13a` | 2026-10-13 | Finition : échappement Markdown du rapport (`echapper_md`) ; champ `nom` des volumes renommé `nom_type` ; boîte de dossier ouverte sur le dernier dossier ; écriture atomique du JSON ; date ISO avec fuseau ; ce document réécrit en référence. Éprouvée le 2026-10-13 (§9.3), hormis le repli `pick_folder`. |
| `2026-10-13b` | 2026-10-13 | Section *Unicité* : « rien à contrôler : aucun volume dans la maquette » quand la rubrique est vide, au lieu de « non contrôlée » (choix du message porté par `message_unicite`, testé). Non éprouvée (§9.4). |
