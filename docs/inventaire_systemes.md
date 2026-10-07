# Inventaire systèmes — photographie des réseaux MEP d'une maquette

> Repo `bimflow` · extension pyRevit · créé le 2026-10-07
> Portée : **générique — famille A** (marche à l'identique sur toute maquette).
> Cas d'origine : `thestudy_CO_EQU` (A_049) et maquettes McGill — chantier
> « réseaux et systèmes » ; spec : `WORK\dev\bimflow\actions\2026-10-07_SPEC_inventaire_systemes_equipements_v0.md` (v0.1).
> Environnement : Revit 2026, pyRevit 6.5.5, moteur **IPY342** — pas de shebang
> python3, niveau de langage Python 3.4 maximum (pas de f-strings).
> **Statut : écrit et testé hors Revit, NON ÉPROUVÉ sous Revit.** Tant que la
> recette (§6) n'est pas passée, rien de ce qui touche l'API n'est mesuré.

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
   et le **nombre d'anomalies**.

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
| `inventaire.json` | tout : `schema` (`bimflow.inventaire/0.1`), `outil`, `modeles`, puis un tableau par CSV, mêmes colonnes |
| `10_types_systeme.csv` | type de système (tuyauterie ou gaine) |
| `11_systemes.csv` | système (réseau) |
| `12_systemes_categories.csv` | (système, catégorie) — compté côté élément |
| `13_elements_sans_systeme.csv` | élément MEP sans nom de système |
| `14_types_canalisation_gaine.csv` | type de canalisation, de gaine, ou souple |
| `20_elec_distribution.csv` | système de distribution |
| `21_elec_tableaux.csv` | occurrence d'équipement électrique |
| `22_elec_circuits.csv` | circuit |
| `30_filtres.csv` | filtre (à règles ou de sélection) |
| `31_filtres_regles.csv` | règle élémentaire, avec son chemin dans l'arbre |
| `32_filtres_application.csv` | (gabarit ou vue sans gabarit, filtre) |
| `40_familles.csv` | famille des catégories cibles |
| `41_familles_parametres.csv` | (famille, paramètre, portée) |
| `50_parametres_projet.csv` | paramètre lié au projet |
| `51_parametres_partages.csv` | `SharedParameterElement` du document |
| `60_nomenclatures_champs.csv` | champ de nomenclature |
| `90_anomalies.csv` | lecture échouée ou objet non lu |
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
- **Systèmes, deux instruments** — `Nb_elements_parametre` est compté **côté
  élément** (paramètre natif *Nom du système*, découpé aux virgules : un
  élément peut appartenir à plusieurs systèmes) ; `Nb_elements_api` **côté
  système** (`MEPSystem.Elements`). Les deux sont publiés, jamais soustraits :
  un écart ne prouve rien (R15 fait 3). Les tables 11 à 13 couvrent le domaine
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
- **Unités** — SI : mm, °C, V (conversion par `UnitUtils` dans le bouton).

## 5. Contrôles (99)

Par maquette lue :

1. **Éléments par système (côté élément) + éléments sans système ≥ éléments
   MEP lus.** La mesure détaille l'écart : affectations supplémentaires des
   éléments multi-systèmes, éléments au nom de système `NON_LU`, noms lus sans
   système de ce nom dans le document.
2. **Σ occurrences des familles = occurrences des catégories cibles.** Un écart
   signale des occurrences qui ne sont pas des `FamilyInstance`.
3. **Chaque filtre appliqué existe dans la table 30.**
4. **Nombre d'anomalies** (une ligne par maquette, total rappelé).

## 6. Recette dans Revit — à passer avant tout usage

| # | Vérification | Résultat |
|---|---|---|
| 8 | `pyRevit ▸ Recharger` : bouton **bleu** dans le panneau `Conformité` (premier bouton du panneau, qui devient visible) | à faire |
| 9 | Sur une maquette **cloud workshared** : la liste **Annuler** de Revit reste vide, aucun élément emprunté | à faire |
| 10 | Les 19 fichiers sont produits ; dans Excel FR, accents corrects, colonnes séparées, nombres à virgule reconnus | à faire |
| 11 | Un lien **déchargé** donne `NON_CHARGE` + une anomalie, sans plantage | à faire |
| 12 | Contrôles 99 et nombre d'anomalies affichés à l'écran en fin d'exécution | à faire |

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
  `MEPSystem.BaseEquipment`, `.Elements` ; `PipingSystem.SystemType`,
  `MechanicalSystem.SystemType` ;
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
