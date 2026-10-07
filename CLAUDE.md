# bimflow — règles permanentes pour Claude Code

Dépôt d'outils pyRevit de Keovia Solutions. Ces règles valent pour toute session, quel que
soit le brief. Si un brief les contredit, signale-le avant d'agir.

## Git
- Ne jamais committer sur `dev` ni sur `main`. Toujours : branche `feature/<sujet>` depuis
  `origin/dev` à jour, puis PR vers `dev`. La fusion vers `main` est décidée par Bruno.
- Commits en français, à l'impératif, une chose logique par commit.
- Aucune mention d'IA, y compris la ligne `Co-Authored-By`.
- Le dépôt est dans Dropbox : l'index peut être verrouillé pendant la synchronisation.
  Vérifier `git show --stat` sur chaque commit avant de pousser.
- pyRevit lit le dossier de travail de ce dépôt : ne jamais changer de branche sans vérifier
  que Revit est fermé. Revit ouvert = demander à Bruno.
- Lignes de commande en PowerShell.

## Type de dépôt
- bimflow est un dépôt de type « méthode » : dérogation actée au template de dépôt logiciel.
  Pas de `pyproject.toml`, pas de packaging. Ce n'est pas un manque à signaler.
- Tests : pytest sous CPython, dans `tests\`, jeux d'essai dans `tests\fixtures\`.

## Moteur pyRevit (Revit 2026, pyRevit 6.5.5, IronPython 3.4 / IPY342)
- Pas de shebang `#! python3` : le bouton ne chargerait pas.
- Syntaxe Python 3.4 : pas de f-string, pas d'annotations de type, pas de pathlib (os.path).
- Les `dict` ne garantissent pas l'ordre d'insertion : `OrderedDict` dès que l'ordre compte.
- La logique testable va dans `bimflow.extension\lib\` (pur Python, sans Autodesk, clr ni
  pyrevit) ; le `script.py` du bouton n'est qu'un adaptateur Revit.
- Vérifier la syntaxe avec `vermin -t=3.4-`.

## API Revit
- `ElementId.Value`, jamais `.IntegerValue` (retiré en 2024+). Exception : `WorksetId.IntegerValue`.
- Ne jamais résoudre de propriété pendant qu'un `FilteredElementCollector` itère : matérialiser
  d'abord les identifiants (`ToElementIds()`), résoudre ensuite. Le contraire tue Revit
  (`AccessViolationException`, non rattrapable).
- Aucun nom de maquette en dur : lire `doc.Title` à l'exécution. Les maquettes cloud peuvent être
  renommées sur Forma à tout moment.
- Toute règle MEP se lit sur le TYPE de système, jamais sur le nom du système.

## Discipline des outils
- Lecture seule d'abord : tout outil qui écrit est précédé d'un audit en lecture seule du même
  périmètre.
- Un outil qui écrit : `SIMULATION = True` par défaut, confirmation nommant la maquette avant
  écriture, refus et exclusions affichés AVANT l'écriture, jamais une annulation silencieuse.
- Aucune indisponibilité silencieuse : une valeur illisible est écrite `NON_LU` et signalée.
- Vocabulaire : jamais « supprimable », « inutile », « en trop » ; écrire ce qui est mesuré.
- Sous-projets fermés : les détecter et le dire avant tout chiffre.

## Ruban et fichiers
- Placement des boutons : suivre `docs\organisation_ruban.md` et le `_ROLE.txt` de chaque panneau.
- Noms de dossiers de bouton en ASCII sans accent ; titre affiché par `__title__`.
- Icône bleue = lecture seule ; voir `docs\organisation_ruban.md` pour les autres.
- Sorties : dossier choisi par l'utilisateur (`forms.pick_folder` / `forms.save_file`), ou dossier
  fixe documenté et affiché en fin d'exécution ; jamais un chemin Bureau reconstruit.
  CSV en UTF-8 avec BOM, séparateur `;`, BOM écrit UNE fois (sous IronPython 3, `utf-8-sig`
  le réécrit à chaque `write()`).

## Communication avec Bruno
- Nommer les travaux par ce qu'ils font ; les numéros (PR, backlog) seulement entre parenthèses.

## Ce que la session rend
- Un compte rendu court : fichiers touchés, tests, numéro de PR, points non vérifiés sous Revit.
- Tout ce qui contredit une règle ci-dessus ou un document du dépôt est signalé, pas tranché.
