# Inventaire systèmes — photographie des réseaux MEP d'une maquette

> Repo `bimflow` · extension pyRevit · créé le 2026-10-07
> Portée : **générique — famille A** (marche à l'identique sur toute maquette).
> Cas d'origine : `thestudy_CO_EQU` (A_049) et maquettes McGill — chantier
> « réseaux et systèmes » ; spec : `WORK\dev\bimflow\actions\2026-10-07_SPEC_inventaire_systemes_equipements_v0.md` (v0.1).
> Environnement : Revit 2026, pyRevit 6.5.5, moteur **IPY342** — pas de shebang
> python3, niveau de langage Python 3.4 maximum (pas de f-strings).
> **Statut : recette faite par Bruno le 2026-10-07 sur une copie détachée de
> `thestudy_ME_EX` — outil fonctionnel.** Quatre corrections en ont résulté
> (version `2026-10-07b`, schéma `0.2`) : catégories lues comme catégories,
> réseau des systèmes, equipement de base dit `AUCUN`, nature des anomalies.
> Ces corrections ne sont **pas encore repassées** sous Revit (§6).

---

## 1. Ce que fait le bouton

`Conformité ▸ Inventaire systèmes` — icône **bleue** : lecture seule, rien
n'est écrit dans la maquette, aucun emprunt, aucune synchronisation.

Il relève, **tels qu'ils sont**, les noms, codes, classifications, couleurs et
matériaux de :

- types de système de tuyauterie et de gaine, et systèmes ;
- éléments MEP rattachés à aucun système ;
- types de canalisation et de gaine (segments) ;
- électricité : systèmes de distribution, tableaux, circuits ;
- filtres de vue : règles, catégories, application et remplacements graphiques ;
- familles d'équipement des catégories cibles et leurs paramètres ;
- paramètres de projet, paramètres partagés, champs des nomenclatures.

**Il mesure, il ne conclut pas.** Aucune sortie ne qualifie un objet : on lit
« 0 occurrence », « n'est appliqué à aucune vue », jamais un verdict. Les
décisions (table nom → code → couleur, paramètres partagés, nettoyage des
familles) se prennent **hors de l'outil**, sur ses sorties.

## 2. Mode d'emploi

1. Ouvrir la maquette (locale, détachée ou centrale cloud — lecture identique).
2. Cliquer **Inventaire systèmes**.
3. S'il y a des liens chargés : cocher ceux à inventorier. **Rien coché ou
   fenêtre fermée = hôte seul** (défaut). Une maquette liée plusieurs fois est
   lue une fois ; les liens imbriqués ne sont pas lus (v0).
4. Si des **sous-projets sont fermés** (hôte ou liens choisis), l'outil les
   liste et demande de continuer : leurs éléments ne sont pas chargés et
   compteraient zéro sans le dire.
5. Choisir le dossier de dépôt. L'outil y crée
   `inventaire_<titre_hote>_<AAAAMMJJ_HHMM>\` (suffixe `_2`… si le dossier
   existe déjà). Aucun chemin n'est construit à la place de l'utilisateur.
6. Barre de progression, **annulable** : une annulation n'écrit aucun fichier.
7. En fin d'exécution, l'écran affiche les maquettes lues, les **contrôles 99**
   et le **nombre d'anomalies**, `ERREUR` et `NON_APPLICABLE` séparées.

Sur une maquette centrale non détachée, l'inventaire décrit l'état
**synchronisé** à l'instant de la lecture : le travail non synchronisé des
autres n'y figure pas.

## 3. Les 19 fichiers

Tous en **UTF-8 avec BOM**, écrits **en une seule fois** (sous IronPython 3, le
codec `utf-8-sig` réécrit le BOM à chaque `write()` ; la lib ajoute le BOM au
texte complet). CSV : séparateur `;`, fins de ligne CRLF, guillemets RFC 4180,
booléens `OUI`/`NON`, **virgule décimale** (Excel FR lit `12,5` comme un
nombre). JSON : décimale point — à lire avec `utf-8-sig`.

Chaque ligne commence par `Source_modele` (titre de la maquette, suffixé `#2`
en cas d'homonymie).

| Fichier | Une ligne = |
|---|---|
| `inventaire.json` | tout : `schema` (`bimflow.inventaire/0.2`), `outil`, `modeles`, puis un tableau par CSV, mêmes colonnes |
| `10_types_systeme.csv` | type de système (tuyauterie ou gaine) |
| `11_systemes.csv` | système (réseau) |
| `12_systemes_categories.csv` | (système, catégorie) — compté côté élément |
| `13_elements_sans_systeme.csv` | élément MEP sans nom de système |
| `14_types_canalisation_gaine.csv` | type de canalisation, de gaine, ou souple |
| `20_elec_distribution.csv` | système de distribution |
| `21_elec_tableaux.csv` | tableau : occurrence dont le `MEPModel` est un `ElectricalEquipment` portant un nom de tableau (les autres équipements électriques sont comptés dans une anomalie `NON_APPLICABLE`) |
| `22_elec_circuits.csv` | circuit |
| `30_filtres.csv` | filtre (à règles ou de sélection) |
| `31_filtres_regles.csv` | règle élémentaire, avec son chemin dans l'arbre |
| `32_filtres_application.csv` | (gabarit ou vue sans gabarit, filtre) |
| `40_familles.csv` | famille des catégories cibles |
| `41_familles_parametres.csv` | (famille, paramètre, portée) |
| `50_parametres_projet.csv` | paramètre lié au projet |
| `51_parametres_partages.csv` | `SharedParameterElement` du document |
| `60_nomenclatures_champs.csv` | champ de nomenclature |
| `90_anomalies.csv` | lecture échouée ou objet non lu, avec sa `Nature` (`ERREUR` ou `NON_APPLICABLE`) |
| `99_controles.csv` | contrôle arithmétique |

Colonnes exactes : constante `TABLES` de `bimflow.extension\lib\bimflow_inventaire.py`
— c'est la source, ce tableau n'en est qu'un résumé.

`modeles[].statut_lecture` : `LU`, `NON_CHARGE` (lien déchargé, introuvable ou
sans document), `IMBRIQUE_NON_LU`, `ERREUR` (une phase a échoué : l'anomalie la
nomme, les autres phases ont tourné). `modeles[].comptes` : lignes par table,
plus les compteurs des contrôles.

## 4. Définitions

- **NON_LU** — propriété illisible : la cellule vaut `NON_LU` **et** une ligne
  part dans `90_anomalies.csv`. Aucune indisponibilité silencieuse (ACT-054).
  Une cellule **vide** veut dire *sans objet* (fluide d'une gaine, forme d'une
  canalisation) ou *valeur vide dans Revit*, jamais *pas lu*. Les lectures
  répétées par élément (valeurs de paramètres de famille) sont regroupées :
  une anomalie par (famille, paramètre), avec le nombre d'échecs.
- **Nature d'une anomalie** — `ERREUR` : une lecture a échoué, ou une maquette
  n'a pas pu être lue (lien déchargé). `NON_APPLICABLE` : **limite de lecture
  prévue** — famille sans occurrence (paramètres d'occurrence non lus),
  propriété d'un circuit de réserve ou d'espace (`CircuitType` = `Spare` ou
  `Space`), tension et nombre de pôles d'un circuit autre que de puissance
  (`SystemType` ≠ `PowerCircuit`), lien lu avec des sous-projets fermés
  (« inventaire partiel »), équipement électrique
  qui n'est pas un tableau, « Alimenté par » absent d'un tableau, catégorie inconnue de la version ou absente du document, lien
  imbriqué (v0). Les deux sont publiées ; seules les `ERREUR` font un écart au
  contrôle 99. Dans les deux cas la cellule concernée vaut `NON_LU`.
- **Equipement_base** — `MEPSystem.BaseEquipment` ; `AUCUN` quand l'API rend
  null (le système n'a pas d'équipement de base). Une cellule vide n'y apparaît
  plus.
- **Code_nom** — segment du nom avant le premier `_`, espace ou `-`.
- **Code_coherent / Prefixe_coherent** — `OUI` si le code du nom égale
  l'abréviation du type, sans tenir compte de la casse ni des accents ; `NON`
  sinon ; `INDETERMINE` si l'un des deux manque. Le **type** fait foi, pas le
  nom (R15 fait 5) : les deux sont publiés côte à côte.
- **Renseigné** — texte : non vide après `strip()` et différent de `-` (le `-`
  est compté dans `Nb_tiret`, règle Pomerleau). Numérique, Oui/Non,
  identifiant : `HasValue`. `Taux_remplissage` = renseignés / porteurs, fraction
  0–1 ; vide quand il n'y a aucun porteur.
- **Origine d'un paramètre** — `INTEGRE` (natif), `PARTAGE` (`IsShared`),
  `PROJET` (non partagé, nom lié au projet), `FAMILLE` (sinon),
  `INDETERMINE` (lecture manquante, ou nom lié au projet mais identifiant qui
  n'est pas un paramètre du document). Heuristique **à éprouver**. Table 60 :
  `CALCULE` pour un champ sans paramètre (formule, compte).
- **Couleur** — `R G B` et `#RRGGBB` ; couleur invalide (pas de remplacement) :
  cellules vides et `Remplace = NON`.
- **Systèmes, trois comptes** — `Nb_elements_parametre` est compté **côté
  élément** (paramètre natif *Nom du système*, découpé aux virgules : un
  élément peut appartenir à plusieurs systèmes). Côté **système**, deux
  propriétés de l'API, que la recette a montrées distinctes :
  `Nb_terminaux_api` = `MEPSystem.Elements` (« Terminal elements in the
  system » : terminaux et équipements seulement) et `Nb_elements_reseau` =
  `PipingSystem.PipingNetwork` (« Pipes and fittings which are contained in
  this system ») ou `MechanicalSystem.DuctNetwork` (« The ducts and fittings
  contained within the system »). Tous sont publiés, jamais soustraits : un
  écart ne prouve rien (R15 fait 3). Les tables 11 à 13 couvrent le domaine
  tuyauterie et gaine (constante `CATEGORIES_SYSTEME`).
- **Catégories cibles (40, 41)** — constante `CATEGORIES_CIBLES` : équipements
  mécaniques, de plomberie, électriques ; appareils sanitaires ; luminaires ;
  appareils électriques ; accessoires et raccords de canalisation et de gaine ;
  bouches d'aération ; gicleurs ; dispositifs d'alarme incendie, communication,
  données, sécurité, appel infirmier, téléphoniques. Une catégorie inconnue de
  la version donne une anomalie, pas un plantage.
- **Filtres** — l'arbre de `GetElementFilter()` est descendu (ET, OU,
  `ElementParameterFilter`, règles inverses) : `GetRules()` du filtre est retiré
  en 2024+. `Chemin` donne la position (`ET/NON OU[2]/PARAM[1]/R1`) ; `NON`
  devant un nœud = nœud inversé ; `Inverse = OUI` = règle enveloppée dans
  `FilterInverseRule`. Valeurs numériques **brutes**, en unités internes
  (`Valeur_unites_internes = OUI`). Paramètre identifié par son id et, s'il est
  partagé, son **GUID** — l'identité d'un paramètre partagé (R08).
- **Unités** — SI : mm, °C (conversion par `UnitUtils` dans le bouton), V.
  **Tensions** : `VoltageType.ActualValue` est **déjà en volts** (doc API 2026 :
  « the unit is volt ») — la convertir donnait 21,4 pour « 230V AC » (recette
  McGill, 2026-10-07 ; corrigé en `2026-10-07c`). `ElectricalSystem.Voltage`
  (tension d'un circuit) : unité non documentée, **supposée interne**
  (1 V = 10,7639 unités internes) — à vérifier sur un circuit connu.
  La tension et le nombre de pôles d'un circuit qui n'est pas de puissance
  sont `NON_APPLICABLE` (la doc annonce une exception pour la tension ;
  `Nb_poles` : 9 `ERREUR` sur des circuits Data / Communication de
  `1981McGill_M_CH_Global`, corrigé en `2026-10-07d`).

## 5. Contrôles (99)

Par maquette lue :

0. **Prérequis (liens seulement) : aucun sous-projet fermé dans le lien.**
   Écart s'il y en a ; la mesure les nomme, et une anomalie `NON_APPLICABLE`
   « inventaire partiel : N sous-projets fermes dans <lien> » part dans
   `90_anomalies.csv`. Pour l'hôte, l'alerte est à l'écran avant la lecture.
1. **Éléments par système (côté élément) + éléments sans système ≥ éléments
   MEP lus.** La mesure détaille l'écart : affectations supplémentaires des
   éléments multi-systèmes, éléments au nom de système `NON_LU`, noms lus sans
   système de ce nom dans le document.
2. **Σ occurrences des familles = occurrences des catégories cibles.** Un écart
   signale des occurrences qui ne sont pas des `FamilyInstance`.
1 bis. **Côté système : terminaux et réseau lus pour chaque système.** La
   mesure met la somme côté système à côté de la somme côté élément, sans les
   comparer : ce sont deux instruments. Écart seulement si un compte est
   `NON_LU`.
3. **Chaque filtre appliqué existe dans la table 30.**
4. **Anomalies de nature `ERREUR`** (une ligne par maquette, total rappelé). Les
   `NON_APPLICABLE` sont comptées dans la mesure, hors écart.

## 6. Recette dans Revit — à passer avant tout usage

| # | Vérification | Résultat |
|---|---|---|
Première recette : Bruno, le 2026-10-07, copie détachée de `thestudy_ME_EX`,
version `2026-10-07a` — outil fonctionnel, quatre corrections demandées
(48 anomalies de catégorie, compte côté système limité aux terminaux,
`Equipement_base` vide pour les 168 systèmes, anomalies prévues mêlées aux
erreurs). Le détail point par point de cette recette n'est pas reporté ici.

À repasser sur la version `2026-10-07b` :

| # | Vérification | Résultat |
|---|---|---|
| R1 | Plus aucune anomalie « element -2000xxx introuvable » ; colonnes `Categories` (30) et `Categorie` (60) renseignées | à faire |
| R2 | `11_systemes` : `Nb_terminaux_api` et `Nb_elements_reseau` renseignés ; contrôle 1 bis à OK | à faire |
| R3 | `Equipement_base` : `AUCUN` ou une famille, jamais vide ; vérifier à la main sur deux systèmes (navigateur de systèmes ▸ propriétés) | à faire |
| R4 | `90_anomalies` : colonne `Nature` ; contrôle 4 n'en compte que les `ERREUR` | à faire |
| R5 | `2026-10-07c` : « 230V AC » sort 230 en `20_elec_distribution` ; `Tension_V` d'un circuit connu juste en `22` | à faire |
| R6 | `2026-10-07c` : sur `1981McGill_E_EL_Global`, plus d'`ERREUR` de nom de tableau ou de système de distribution (705 en `b`) | à faire |
| R7 | `2026-10-07d` : sur `1981McGill_M_CH_Global`, `Nb_poles` des circuits Data / Communication en `NON_APPLICABLE` (9 `ERREUR` en `c`) | à faire |
| R8 | `2026-10-07d` : un lien lu avec un sous-projet fermé donne l'anomalie « inventaire partiel » et le contrôle prérequis en écart | à faire |

Lire aussi `90_anomalies.csv` de la première exécution : chaque ligne
`AttributeError` y désigne une propriété d'API supposée et absente (§7).

## 7. Points d'API non vérifiés sous Revit 2026

Écrits d'après la documentation, **non mesurés**. Chacun, s'il est faux, donne
`NON_LU` + anomalie (ou une phase en `ERREUR`), pas un plantage :

- `OST_PlumbingEquipment` (catégorie récente) — résolue par nom, anomalie si absente ;
- `RevitLinkType.IsNestedLink` ; `FilteredWorksetCollector` et `Workset.IsOpen`
  sur le document d'un lien ;
- `FilterRule.GetRuleParameter()` sur toutes les classes de règle (dont
  `HasValueFilterRule`) ; `ElementFilter.Inverted` ;
  `LabelUtils.GetLabelFor(BuiltInParameter)` via `System.Enum.ToObject` ;
- paramètres natifs : `RBS_SYSTEM_NAME_PARAM` (séparateur virgule pour les
  éléments multi-systèmes), `RBS_PIPING_SYSTEM_TYPE_PARAM` /
  `RBS_DUCT_SYSTEM_TYPE_PARAM` sur raccords et équipements,
  `RBS_SYSTEM_CLASSIFICATION_PARAM` sur un type de système,
  `RBS_ELEC_PANEL_NAME`, `RBS_ELEC_PANEL_SUPPLY_FROM_PARAM`,
  `RBS_FAMILY_CONTENT_DISTRIBUTION_SYSTEM` ;
- `MEPSystemType` : `Abbreviation`, `SystemClassification`, `LineColor`,
  `LinePatternId`, `LineWeight`, `MaterialId` ; `PipingSystemType.FluidType`,
  `FluidTemperature` (interne en kelvins, converti en °C) ;
  `MEPSystem.BaseEquipment` (la documentation ne dit pas quand il est null) ;
  `PipingSystem.PipingNetwork`, `MechanicalSystem.DuctNetwork` (documentés,
  `ElementSet`, non mesurés) ; `PipingSystem.SystemType`,
  `MechanicalSystem.SystemType` ;
- `Category.GetCategory(Document, ElementId)` pour les ids de `BuiltInCategory` ;
- `PipeType.RoutingPreferenceManager` (règles de segments) ;
  `DuctType.Shape`, `FlexDuctType.Shape` ;
- `ElectricalSystem` : `CircuitType`, `Voltage`, `PolesNumber`, `LoadName`,
  `PanelName` ; `DistributionSysType` : `ElectricalPhase`,
  `ElectricalPhaseConfiguration`, `NumWires`, `VoltageLineToLine`,
  `VoltageLineToGround` (`VoltageType.ActualValue`) ;
- `View.AreGraphicsOverridesAllowed()`, `GetIsFilterEnabled`,
  `GetFilterVisibility`, `GetFilterOverrides` ; `OverrideGraphicSettings` :
  `ProjectionLineColor`, `SurfaceForegroundPatternColor`, `CutLineColor`,
  `CutForegroundPatternColor`, `Transparency`, `Halftone` ;
- `InternalDefinition.Id` (pour départager un nom partagé ambigu) ;
  `Definition.GetGroupTypeId()` + `LabelUtils.GetLabelForGroup` ;
  `GetDataType().TypeId` ;
- `ViewSchedule.IsTitleblockRevisionSchedule`, `ScheduleField.ParameterId`,
  `GetName()` ;
- `Document.IsDetached`, `IsModelInCloud`, `GetCloudModelPath()` ;
- moteur : `unicodedata` sous IPY342 (repli intégré s'il manque),
  `DB.Element.Name.__get__` en repli de `.Name` ;
- pyRevit : `forms.SelectFromList.show(multiselect=True)`, annulation de
  `forms.ProgressBar`.

## 8. Limites (v0)

- **Familles non ouvertes** (`EditFamily` exclu) : ni formules, ni paramètres
  d'étiquette, ni paramètres d'occurrence d'une famille **sans occurrence** —
  dit en anomalie.
- Paramètres sans stockage (`StorageType.None`) ignorés en table 41.
- Liens imbriqués non lus ; variantes et phases lues sans filtrage.
- Une vue pilotée par un gabarit est ignorée en table 32 (ses filtres viennent
  du gabarit), même si le gabarit ne contrôle pas les filtres.
- Deux systèmes homonymes reçoivent chacun le compte côté élément du nom —
  signalé en anomalie.
- Grandes maquettes : la table 41 lit tous les paramètres de chaque occurrence
  des catégories cibles ; c'est la phase la plus longue. Durée en méta
  (`outil.duree_s`).

## 9. Code et tests

| Fichier | Rôle |
|---|---|
| `bimflow.extension\lib\bimflow_inventaire.py` | logique pure (schéma, codes, cohérences, remplissage, arbre de filtre, répartition, contrôles, CSV/JSON) — IronPython 3.4 **et** CPython 3, sans `Autodesk`, `clr` ni `pyrevit` |
| `bimflow.extension\bimflow.tab\Conformite.panel\InventaireSystemes.pushbutton\script.py` | adaptateur Revit : lecture par l'API, conversion en dictionnaires, unités SI |
| `tests\test_bimflow_inventaire.py`, `tests\fixtures\inventaire\*.json` | tests pytest de la lib, et relecture statique du bouton |

```powershell
python -m pip install pytest vermin
python -m pytest
vermin -t='3.4-' --no-tips --violations bimflow.extension\lib\bimflow_inventaire.py "bimflow.extension\bimflow.tab\Conformite.panel\InventaireSystemes.pushbutton\script.py"
```
