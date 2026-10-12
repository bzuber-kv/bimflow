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

À consigner ici après exécution : maquette, date, comptes par rubrique,
résidus de la transformation, signalements.

| Maquette | Date | Niveaux | Quadrillages | Volumes | Pièces | Sous-projets | Liens | Résidu (mm) | Signalements |
|---|---|---|---|---|---|---|---|---|---|
| thestudy_G_AN | — | | | | | | | | |
| thestudy_G_VZ | — | | | | | | | | |
