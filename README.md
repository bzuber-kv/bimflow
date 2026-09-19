# bimflow

Outils d'automatisation Revit/BIM Keovia (pyRevit) + plan qualité BIM.

> ### ⚠ RecalageGlobal — toujours passer par « Essai de stratégies » avant d'appliquer
>
> Constat du 2026-08-27, sept stratégies mesurées : sur un modèle contenant des
> objets à **géométrie redéfinie**, le recalage détruit des éléments. **C'est une
> limite de Revit, documentée par Autodesk** — les forums Dynamo rapportent les
> mêmes échecs.
>
> Mais l'essai de stratégies **nomme les éléments qui seraient détruits, sans
> rien modifier**. L'outil garde donc deux usages : sur un **modèle propre**
> (non testé, voie plausible de mise au propre en début de projet), et quand le
> recalage est **critique pour la livraison** — on budgète alors la reprise au
> lieu de la subir.
>
> Conséquence de portée générale : **la position de l'origine interne se décide
> à l'ouverture du modèle, et très difficilement après.** À faire remonter au
> plan qualité BIM. Détail : `docs/recalage_global.md` §5 ter.

Version Revit de référence : **2026**.

pyRevit installé sur le poste (KS101) au 2026-08-27 : **v6.5.5**, clone unique en
`%APPDATA%\pyRevit-Master`. Moteur attaché à Revit 2026 : **IronPython 3.4.2**
(`IPY342`), soit un niveau de langage **Python 3.4**.

> ⚠️ **Interop .NET — la règle qui casse le plus souvent.**
> Sous IronPython 3, toute méthode de l'API attendant `ICollection` / `IList` /
> `ISet` **refuse une liste Python** (`TypeError`). IronPython 2 tolérait la
> coercion implicite ; ce n'est plus le cas. Conversion obligatoire :
>
> ```python
> from System.Collections.Generic import List
> ids = List[DB.ElementId]()
> for e in elements:
>     ids.Add(e.Id)
> ```
>
> Concerne notamment `MoveElements`, `CopyElements`, `RotateElements`,
> `doc.Delete`, `Selection.SetElementIds`, `NewGroup`.

> ⚠️ Il n'existe **pas** de moteur CPython pour netcore : `CPY3123` n'est déployé
> qu'en netfx. Un script portant le shebang `#! python3` ne se chargerait donc
> pas sous Revit 2026. Ne pas en ajouter.

**Vérifier le moteur, la bonne commande.** `pyrevit clones engines` liste les
déploiements *disponibles* — dont un qui s'appelle littéralement `DEFAULT`, ce
qui induit en erreur. Seul l'**attachement** dit lequel tourne :

```bash
pyrevit attached
```

Plus sûr encore, le manifeste que Revit lit au démarrage nomme le moteur dans le
chemin du DLL : `%APPDATA%\Autodesk\Revit\Addins\2026\pyRevit.addin`.

**Nommage des bundles.** Dossier sans espace ni accent ; libellé affiché porté
par `__title__` dans le script ou `title:` dans `bundle.yaml` (accents et `\n`
autorisés).

## Installation

Enregistrer le dossier d'extensions auprès de pyRevit, une fois :

```bash
pyrevit extend path "D:\Dropbox\Dev\bimflow"
```

Puis recharger depuis Revit : onglet **pyRevit** ▸ **Reload**. L'onglet
`bimflow` apparaît dans le ruban.

Variante sans CLI : pyRevit ▸ Settings ▸ *Custom Extension Directories* ▸
ajouter `D:\Dropbox\Dev\bimflow` ▸ Save Settings and Reload.

## Contenu

```
bimflow.extension/
└── bimflow.tab/
    ├── Calage projet.panel/             Sous-projets, niveaux, paramètres
    └── Georeferencement.panel/
        └── RecalageGlobal.pushbutton/    Recalage global du modèle
docs/
├── recalage_global.md                    Mode d'emploi et protocole de test
├── niveaux.md                            Ancrage aux niveaux (B18a)
└── parametres.md                         Socle Keovia, audit et nettoyage
shared_parameters/
└── keovia_socle_parametres.txt           Source des GUID — voir ci-dessous
```

| Outil | État | Documentation |
|---|---|---|
| Recalage global | Écrit, **non exécuté sur Revit** | [docs/recalage_global.md](docs/recalage_global.md) |
| Socle de paramètres (6 boutons) | **Éprouvés en production le 2026-09-19** | [docs/parametres.md](docs/parametres.md) |

*Tableau non exhaustif : il précède les outils sous-projets et niveaux, qui sont
documentés dans `docs/`.*

## Discipline

- Tout script qui écrit dans le modèle est précédé d'un script d'audit en
  lecture seule sur le même périmètre — ou embarque un mode simulation
  obligatoire, comme le recalage global.
- Tout test se fait sur une **copie détachée**.
- Un comportement Revit s'observe sur Revit avant de s'écrire en fiche.
  Tant qu'un protocole de test n'est pas passé, la documentation le dit.

## Paramètres partagés — `shared_parameters/keovia_socle_parametres.txt`

Ce fichier est la **source des GUID** du socle Keovia. Trois règles, et elles ne
souffrent pas d'exception :

- **Il se versionne.** Il entre au dépôt, et son historique est sa garantie.
- **Il ne se régénère jamais.** Le régénérer fabriquerait de nouveaux GUID, et
  tous les modèles déjà renseignés cesseraient de reconnaître leurs propres
  champs.
- **Un GUID retiré n'est jamais réattribué à autre chose.** Les GUID sortis du
  socle restent **inscrits en commentaire en tête du fichier**, avec le nom
  qu'ils portaient. Ce n'est pas de l'historique, c'est une **réservation** : un
  GUID identifie une définition, pas un nom, et le réattribuer ferait que deux
  choses différentes porteraient la même identité d'un modèle à l'autre — une
  collision qui ne se verrait qu'à l'export, chez le destinataire.

**Critère d'entrée, unique.** Quelque chose **hors du document** doit-il
reconnaître ce champ — export IFC, appariement Ivion ou GMAO, étiquette,
nomenclature entre modèles, échange avec un tiers ? Oui → paramètre **partagé**,
il entre ici et reçoit un GUID à vie. Non → paramètre **de projet**, porté par le
gabarit, absent de ce fichier.

**Source et copie.** `shared_parameters/keovia_socle_parametres.txt` est **LA
source** : elle se modifie ici, dans le dépôt, et par PR. La copie que Revit lit
sera déposée dans le **dossier ACC du projet** — *chemin à fixer* — et **ne
s'édite jamais** : on la redépose entière depuis la source.

Ne pas éditer à la main dans un tableur : passer par Revit ▸ *Gérer les
paramètres partagés*. Détail et liaisons : [docs/parametres.md](docs/parametres.md).

## Zones

| Zone | Contenu |
|---|---|
| `D:\Dropbox\Dev\bimflow\` (ce repo) | Code pyRevit, documentation technique |
| `WORK\dev\bimflow\` (OneDrive) | Pilotage projet, fiches de connaissance Revit (Rnn), plan qualité BIM |

Conventions : `WORK\_CONTEXT\03_REGLES_DEV.md`. Dérogations en vigueur pour ce
repo : voir `docs/recalage_global.md` §9 (contraintes IronPython 3.4 / IPY342).
