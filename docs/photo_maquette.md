# Photo maquette — état du modèle actif en un JSON

> Repo `bimflow` · créé le 2026-10-12 · portée : **générique** (standard Keovia)
> Bouton : `Dev.panel\PhotoMaquette.pushbutton` — **bleu, lecture seule, NON ÉPROUVÉ**
> Logique testable : `bimflow.extension\lib\bimflow_photo.py` · tests : `tests\test_bimflow_photo.py`

## 1. Ce que fait le bouton

Il lit le modèle actif et écrit **un** fichier JSON. Aucune transaction, aucun
emprunt, aucune synchronisation. Le JSON est une photo datée : on la compare à
une autre photo, on la rejoue hors Revit, on ne la corrige pas.

| Rubrique | Champs |
|---|---|
| `en_tete` | modèle (`doc.Title`), chemin, date, version et build Revit, utilisateur Revit et Windows, état collaboratif / détaché / centrale, sous-projets fermés, repères (point de base, point topographique), transformation interne → partagé retenue, GUID utilisés |
| `niveaux` | nom, Id, `elevation_pbp_mm`, `REF_Batiment`, `REF_Etage` ; pour contrôle : `project_elevation_mm`, `level_elevation_mm`, base d'élévation du type |
| `quadrillages` | nom exact, Id, `debut_partage_m` / `fin_partage_m`, `orientation_deg`, `direction_deg`, type, courbe (ligne/arc) ; extrémités internes en mm et orientation interne pour contrôle |
| `volumes` | nom, famille, Id, `REF_Zone`, `REF_Etage`, `REF_Batiment`, `CLS_Nature_volume`, `REF_Id`, `boite_mm` (min/max) |
| `pieces` | numéro, nom, niveau, surface (m²), point de localisation (mm interne + m partagé), état (placée / non placée / surface nulle) |
| `sous_projets` | nom, Id, ouvert, nombre d'éléments |
| `liens` | nom, Id, type (Revit / CAO / Nuage de points), épinglé ; `charge` pour les liens Revit |
| `comptes`, `signalements` | bilan par rubrique : nombre, champs null, statut de chaque paramètre |

Chaque paramètre REF_/CLS_ est recopié au premier niveau (valeur seule) et
détaillé dans `parametres` : `valeur`, `statut`, `porteur` (instance ou type).

## 2. Règles de lecture — rien n'est déduit

- **Paramètres lus par GUID**, GUID cherchés **par nom** dans le socle versionné
  `shared_parameters\keovia_socle_parametres.txt`. Aucun GUID dans le script. Un
  nom absent du socle est signalé et le champ vaut null partout.
- Trois cas distincts, tous comptés au rapport : `absent` (le paramètre n'existe
  pas sur l'élément ni sur son type) → null ; `vide` (il existe sans valeur) →
  null ; `illisible` (exception) → `NON_LU`.
- **Aucune donnée tirée d'un nom** : ni le niveau, ni la zone, ni le bâtiment.
  Le nom d'un volume est publié, jamais découpé.

## 3. Repères

- **Élévation des niveaux** : `elevation_pbp_mm = Level.ProjectElevation − Z
  interne du point de base du projet`. `Level.Elevation` compte depuis la base
  d'élévation du **type** (R10, `docs\niveaux.md` §1.1) ; il est publié à côté,
  avec cette base, pour contrôle.
- **Coordonnées partagées** : `ActiveProjectLocation.GetTotalTransform()`. Le
  sens (directe ou inverse) **n'est pas supposé** : il est choisi sur le point
  topographique et le point de base, dont Revit donne la position interne et la
  position partagée. Résidus publiés dans l'en-tête ; aucun sens sous 1 mm ⇒
  coordonnées partagées null et signalement. *Statut : hypothèse de
  conception, à confirmer par la recette (résidus lus dans le JSON).*
- **Orientation d'un quadrillage** : azimut début → fin dans le repère partagé,
  0 = nord partagé, sens horaire, [0, 360). `direction_deg` la ramène dans
  [0, 180) — c'est elle qui compare deux axes. Arc : orientation null.
- **Boîtes englobantes** et points de pièces : coordonnées **internes**, mm.

## 4. Sortie

`<dossier>\<modele>_<AAAA-MM-JJ_HHMM>.json`, UTF-8 sans BOM, jamais écrasé
(`_2`, `_3`… si la minute est prise). Le chemin s'affiche en fin de rapport.

Le dossier est **demandé à chaque clic** (décision Bruno, 2026-10-12) : une
photo se range dans l'affaire de la maquette photographiée, et un dossier
retenu d'une fois sur l'autre finirait par en ranger une dans la mauvaise
affaire. Le dernier dossier choisi est rappelé dans le titre de la boîte
(lu dans `%APPDATA%\bimflow\photo_maquette.json`), jamais utilisé sans être
choisi. Boîte annulée : rien n'est écrit, et le rapport le dit.

Instance The Study (portée : spécifique The Study) :
`%USERPROFILE%\OneDrive - KEOVIA Solutions\WORK\affaires\A_049_TheStudy\context\ref\maquette_photo`

⚠ **Écart signalé, non tranché** : `Audit volumes` et `Renommer volumes`
interdisent toute sortie sous OneDrive ou `WORK` (`FRAGMENTS_INTERDITS`). Ce
bouton, à la demande du brief du 2026-10-12, écrit dans le dossier choisi —
y compris OneDrive. La règle §8g (`03_REGLES_DEV.md`) n'interdit que le
*code* dans OneDrive, pas les données. Règle commune à décider.

## 5. Limites connues

- Sous-projets fermés : leurs éléments ne sont pas chargés et manquent à tous
  les comptes. Annoncés en tête de rapport ; leur nombre d'éléments vaut null.
- `nombre_elements` d'un sous-projet compte toutes les instances que Revit y
  range (`ElementWorksetFilter`), éléments sans catégorie compris.
- Maquette centrale : la photo décrit l'état synchronisé à l'instant de la
  lecture.
- Quadrillages multi-segments : chaque segment est un `Grid` et sort comme tel ;
  le regroupement n'est pas fait.
- Liens IFC : sortent en type `Revit` (ce sont des `RevitLinkInstance`).

## 6. Recette

Première exécution le **2026-10-12**, version `2026-10-12a`, Revit 2026
(26.4.0.32), maquettes **centrales** cloud de The Study, aucun sous-projet
fermé. Portée des comptes : **spécifique The Study** ; portée des constats
sur l'outil : générique.

| Maquette | Heure | Niveaux | Quadrillages | Volumes | Pièces | Sous-projets | Liens | Résidu transformation | Signalements |
|---|---|---|---|---|---|---|---|---|---|
| `thestudy_G_AN` | 16:58 | 23 | 73 | 0 | 0 | 37 (1 753 éléments, 16 vides) | 19 (18 nuages, 1 Revit) | 0,000 mm (inverse) | 1 |
| `thestudy_G_VL` | 16:59 | 23 | 0 | 217 | 0 | 36 (2 189 éléments, 17 vides) | 1 (Revit) | 0,000 mm (inverse) | 6 |

**Ce que la recette établit sur l'outil (mesuré).**
- Le sens de `GetTotalTransform` est l'**inverse** : résidu 0,000 mm sur le
  point de base et le point topographique, contre ~9,7·10⁹ mm pour le sens
  direct. Le choix automatique fonctionne ; les coordonnées partagées sont
  fiables.
- Point de base relu à (296 934,64 ; 5 038 973,46 ; 94,695 m) et point
  topographique à z = 0 : conforme au géoréférencement consigné au PEP A_049.
- `elevation_pbp_mm` = `Level.Elevation` sur les 23 niveaux, dont la base
  d'élévation de type est le point de base : contre-vérification cohérente.
- Z partagé des quadrillages = 123,76 m : c'est le z = 0 interne, donc la
  cote de l'origine interne. Exact, mais **sans signification** pour un
  quadrillage, qui n'a pas d'altitude propre.
- Le champ `nom` d'un volume in situ est le **nom du type**
  (`Volume Ivion` pour 210 volumes) ; le nom porteur de sens est `famille`
  (`VOL_nnn__…`). À clarifier dans le JSON (point ouvert ci-dessous).

**Ce que la recette fait apparaître dans les maquettes (mesuré, à traiter côté A_049).**
- `REF_Etage` vide sur les deux niveaux `Site` (`EXT_BLVD`, `EXT_PARC`) :
  vide légitime ou valeur manquante, à décider.
- Quadrillages : deux familles d'orientation — 31,34° / 121,34° (Senior
  Central, Junior, Middle, parking) et 37,94° / 127,94° (Senior East),
  soit **6,60°** entre les deux trames.
- `thestudy_G_VL` : **2 volumes sans aucun paramètre** (`Volume 1`
  id 5532336, `Volume 2` id 5530844, emprise ~36 × 67 m) et **un `REF_Id`
  en double** (`dbe39340-…`) sur `VOL_090__SC_Bp_Amg_1p_3p__FLOOR_2__ETAGE`
  et `VOL_091__SC_Bp_Amg_1p_3p__ROOF__TOITURE` — or `REF_Id` est la clé de
  jointure vers Ivion et ne doit jamais se répéter. 217 volumes contre 202
  au 2026-09-24.
- Aucune pièce dans l'une ou l'autre maquette.

**Points ouverts sur l'outil.**
1. `nom` d'un volume : publier aussi le nom de famille en tête, ou renommer
   le champ `nom_type`.
2. Doublons de `REF_Id` : les compter au bilan (c'est une mesure, pas une
   déduction) — à décider.
3. Les deux JSON ont été écrits dans `Downloads`, pas dans `maquette_photo`.
