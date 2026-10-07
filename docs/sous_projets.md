# Sous-projets — audit (B13) et table des sous-projets

> Repo `bimflow` · extension pyRevit · créé le 2026-09-10
> **Mis à jour le 2026-10-07** : la migration B14 est remplacée par le bouton
> `Table sous-projets` (renommer et créer, sans déplacer d'élément) ; deux
> affirmations périmées corrigées sur les sous-projets imposés par Revit (§ « Un
> seul sous-projet ne se supprime jamais »).
> Portée : **générique** — toute maquette Revit en travail partagé.
> Cas d'origine : affaire **A_049_TheStudy** (étape 0 bis du plan de mise en place
> des maquettes, 50 sous-projets → 35).
> Environnement : Revit 2026, pyRevit 6.5.5, moteur **IPY342** — pas de shebang
> python3, niveau de langage Python 3.4 maximum (pas de f-strings).

---

## Pourquoi ces outils

L'opération « ranger les sous-projets » paraît anodine et ne l'est pas. Le
2026-09-10, sur The Study, une réassignation manuelle de `ZW_Défaut` vers
`Sous-projet 1` a fait passer un comptage de **3593 à 2590 objets** sans qu'aucune
erreur ne soit levée. L'écart n'a été vu que parce qu'un comptage avait été fait
avant. **Rien dans l'interface de Revit ne le signale.**

Ces outils existent pour rendre cet écart impossible à manquer — et le plus sûr
d'entre eux est celui qui **ne déplace aucun élément**.

## B13 — Audit des sous-projets (lecture seule)

Conforme à la discipline du backlog : *tout script qui écrit est précédé d'un
script d'audit en lecture seule sur le même périmètre.*

**Ce qu'il mesure.** Le nombre d'éléments par sous-projet **au niveau du
document**. C'est le point central : une sélection filtrée dans une vue 3D est un
comptage *de vue*, dépendant de la visibilité, des remplacements V/G, de la boîte
de coupe et des sous-projets ouverts. Deux comptages de vue ne sont pas
comparables ; deux comptages de document le sont.

**Ce qu'il rapporte, par sous-projet.**

| Colonne | Ce qu'elle sert |
|---|---|
| Total / Modèle / Spéc. vue | volume réel, et part d'éléments propres à une vue |
| Ouvert | un sous-projet **fermé n'est pas chargé** : il compterait zéro. Le script l'annonce en tête |
| Visible par défaut | explique une sélection vide alors que le sous-projet est plein |
| Suppression possible (colonne `Supprimable`, lue par `WorksetTable.CanDeleteWorkset`) | `Sous-projet 1` répond NON. `Vues, niveaux et grilles partagés` **peut être supprimé** (constaté le 2026-09-10) |
| Autre proprio / Qui | **le test décisif** d'un échec de réassignation en modèle Forma |

Il écrit un **CSV horodaté** sur le Bureau et imprime le **squelette de la table
de correspondance** avec les noms exacts du modèle.

**Mode d'emploi.** Ouvrir tous les sous-projets, passer le script sur la
sauvegarde datée, puis sur le modèle courant, comparer la ligne
*TOTAL instances du document*.

## Table sous-projets — renommer et créer, sans déplacer d'élément

Bouton **orange** (écrit dans la maquette), panneau `Dev` tant qu'il n'a pas
tourné dans Revit. Code : `Dev.panel\TableSousProjets.pushbutton\script.py`
(adaptateur Revit) et `lib\bimflow_sous_projets.py` (lecture et validation de la
table, plan, contrôle final — testée par `tests\test_bimflow_sous_projets.py`).
**Statut : écrit et testé hors Revit, NON ÉPROUVÉ sous Revit.**

Il remplace la migration **B14**, retirée dans `_a_supprimer\` : celle-ci portait
sa table **dans le code** et savait **vider** un sous-projet, c'est-à-dire écrire
sur chaque élément. Le nouveau bouton lit sa table dans un **fichier**, et ne
connaît que des actions qui ne touchent aucun élément.

### Deux modes

1. **Exporter la table.** Un CSV, une ligne par sous-projet **utilisateur**
   existant, trié par nom : `Action;Nom_actuel;Nouveau_nom;Nb_elements;Proprietaire`,
   `Action` pré-remplie `GARDER`. Emplacement choisi par l'utilisateur. UTF-8
   avec BOM écrit une seule fois, séparateur `;`. Un sous-projet **fermé** a
   `Nb_elements = NON_LU` : il n'est pas chargé, il compterait zéro.
2. **Appliquer une table.** Lit un CSV du même format. Accepte l'UTF-8 (avec ou
   sans BOM) et, à défaut, le `cp1252` qu'écrit Excel FR en « CSV (séparateur :
   point-virgule) » — avec un avertissement : vérifier les accents.
   `Nb_elements` et `Proprietaire` sont **informatifs**, ignorés à l'application.

| Action | Colonnes | Effet | Éléments écrits |
|---|---|---|---|
| `GARDER` | `Nom_actuel` | rien — la ligne sert de trace | 0 |
| `RENOMMER` | `Nom_actuel` → `Nouveau_nom` | renomme sur place | **0** |
| `CREER` | `Nouveau_nom` seul | crée un sous-projet | 0 |

Pas de `VIDER`, pas de suppression. Fusionner deux sous-projets reste une
opération manuelle, à encadrer par B13 avant et après.

### Validation complète, avant toute écriture

Le résultat s'affiche en tableau (niveau, ligne du fichier, constat). **Une seule
erreur bloquante = aucune écriture.**

**Erreurs bloquantes**
- en-tête différent de `Action;Nom_actuel;Nouveau_nom;Nb_elements;Proprietaire`,
  fichier vide ;
- ligne mal formée : nombre de colonnes, action inconnue, colonne obligatoire
  vide, `GARDER` avec un `Nouveau_nom` différent, `CREER` avec un `Nom_actuel` ;
- **source absente** du modèle (la casse voisine est indiquée) ;
- **cible déjà existante** dans le modèle, ou **présente deux fois** dans la table ;
- même source traitée deux fois ;
- nom contenant un caractère refusé par Revit : `` { } [ ] | ; < > ? ` ~ ``
  (liste de l'exception de `RenameWorkset` et `Workset.Create`, API 2026) ;
- `RENOMMER` d'un sous-projet **emprunté par un autre utilisateur**
  (`Workset.Owner` non vide et différent de l'utilisateur courant).

**Avertissements, non bloquants**
- nouveau nom qui n'est pas en **ASCII sans espace** ;
- table qui renomme ou crée `Sous-projet 1` ou `Vues, niveaux et grilles
  partagés` (et leurs noms anglais `Workset1`, `Shared Levels and Grids`) ;
- `RENOMMER` d'un sous-projet que l'utilisateur courant n'a pas emprunté (voir
  ci-dessous) ;
- nouveau nom qui ne diffère d'un existant que par la casse ;
- espaces en bord de cellule (retirés à la lecture) ;
- renommage vers le même nom (sans effet) ;
- sous-projets du modèle absents de la table (laissés tels quels).

**Limite assumée** : une **permutation** ou une **chaîne** (`A → B` et `B → C`)
est refusée, parce que la cible existe au moment de la validation. Elle se fait
en deux passes, par un nom intermédiaire.

### Écriture

Plan affiché (créations puis renommages), puis confirmation qui **nomme la
maquette** (`docs/organisation_ruban.md` §4, forme b). Sur une maquette
centrale non détachée, c'est la confirmation commune de `lib\bimflow_maquette.py`
(fichier nommé, case « je suis seul sur cette maquette »). **Une transaction
unique**, annulée entièrement à la moindre erreur ; aucune sortie anticipée
après son ouverture. Puis **relecture** des sous-projets du modèle et liste des
écarts avec la table.

### `RenameWorkset` et l'emprunt — ce qui est documenté

**Documenté** (référence de l'API Revit 2026, `WorksetTable.RenameWorkset`) :
pas de section *Remarks* ; exceptions : document non partagé, nom vide ou
contenant un caractère refusé, **nom déjà utilisé**, id inconnu, document en
mode d'échec, **aucune transaction ouverte**. **Rien sur l'emprunt** : la
documentation ne dit ni qu'il faut avoir emprunté le sous-projet, ni que l'API
l'emprunte, ni qu'elle refuse s'il est détenu par un autre. Par contraste,
`CanDeleteWorkset` pose explicitement ces deux conditions pour la suppression.

**Supposé** : un emprunt implicite, comme celui **mesuré le 2026-09-24** pour un
nom de famille sur une maquette centrale (`docs/ecrire_dans_revit.md` §7) —
mesure qui ne porte **pas** sur un sous-projet.

**Ce que fait l'outil** : un sous-projet détenu par **un autre** utilisateur est
une **erreur bloquante** (prudence, faute de documentation) ; un sous-projet que
personne ne détient, mais que l'utilisateur courant n'a pas emprunté, donne un
**avertissement**. L'outil n'emprunte rien lui-même. En cas de refus de Revit, la
transaction est annulée et l'erreur exacte affichée.

**À mesurer au premier passage** : renommer un sous-projet non emprunté sur une
maquette cloud, synchroniser, relancer B13.

## Un seul sous-projet ne se supprime jamais : `Sous-projet 1`

L'activation du travail partagé crée deux sous-projets utilisateur :
`Sous-projet 1` (*Workset1*) et `Vues, niveaux et grilles partagés` (*Shared
Levels and Grids*).

- **`Sous-projet 1` ne peut pas être supprimé** — Autodesk le documente ; il peut
  seulement être renommé.
- **`Vues, niveaux et grilles partagés` peut être supprimé** — constaté le
  2026-09-10. *Ce document disait jusqu'ici le contraire.*

Une recommandation communautaire ancienne déconseille de renommer Workset1
(erreurs *« deletion of non-editable workset »*) ; statut : **documenté, non
mesuré, et contesté** — Autodesk autorise le renommage.

**Position Keovia retenue le 2026-09-10 (option A)** : on ne supprime pas et on
ne renomme pas `Sous-projet 1`. Il est déclaré au BEP comme conteneur imposé,
laissé vide et jamais actif. Une liste cible de N sous-projets devient donc,
dans les faits, **N + 1 conteneur imposé**. *L'option A visait aussi `Vues,
niveaux et grilles partagés`, sur l'hypothèse qu'il était indestructible : sa
place dans la liste cible est à rejuger, la correction du constat ne la tranche
pas.*

*Candidat règle — cas d'origine A_049 : « toute maquette en travail partagé porte
un sous-projet indestructible, `Sous-projet 1` ; le standard doit lui assigner un
statut, pas tenter de le supprimer ».*

## Références

- `bimflow_BACKLOG.md` — B13, B14
- `bimflow_REVIT_FICHES.md` — fiche R14 (bordereau du 2026-09-10, en attente
  d'absorption — il porte encore « deux sous-projets indestructibles »)
- `A_049_TheStudy\context\TheStudy_PEP.md` §4.4 — liste cible des 35
- `A_049_TheStudy\actions\2026-09-01_PLAN_mise_en_place_maquettes.md` §3.2, §3.3,
  étape 0 bis — la table de correspondance de cette affaire, qui figurait dans le
  code de B14
