# Passation — volumes de zone → site_model Ivion

> Repo `bimflow` · branche `feat/audit-volumes-zone`, **17 commits, non poussée**
> Affaire **A_049_TheStudy** · rédigé le 2026-09-24
> Environnement : Revit 2026, pyRevit 6.5.5, moteur **IPY342** (Python 3.4,
> pas de f-strings, pas de shebang python3) · PowerShell 7 · code dans
> `D:\Dropbox\Dev\bimflow`, **jamais dans OneDrive**

Ce document est une passation. Il dit ce qui **est mesuré**, ce qui est
**documenté**, ce qui reste **hypothèse**, et ne mélange jamais les trois.
Un chiffre sans étiquette n'a pas sa place ici.

---

## 1. De quoi il s'agit

The Study est décrite par des **volumes in situ** (catégorie `Volumes`,
`OST_Mass`) qui découpent le bâti en zones et en tranches d'étage. Ivion
attend un `site_model` : une hiérarchie `SITE → BUILDING → FLOOR`, chaque
`FLOOR` portant un contour 2D et deux cotes, en **coordonnées partagées**.

La chaîne va des uns à l'autre, en deux temps nettement séparés :

1. **dans Revit** — nommer les volumes, puis recopier le nom dans les
   paramètres partagés ;
2. **hors Revit** — lire l'audit JSON, reconstruire les contours, assembler
   le `site_model`.

Le **nom de famille est la source de vérité**. Les paramètres en sont la
copie, pas l'inverse. C'est pour cela que renommer et paramétrer sont deux
boutons : on n'écrit pas la source dans la transaction qui la lit.

---

## 2. État au soir du 2026-09-24

| Maillon | État | Sur quoi c'est mesuré |
|---|---|---|
| `Audit volumes` (pyRevit, lecture seule) | **éprouvé** | 4 exécutions, la dernière sur 202 volumes / 53 zones |
| `Renommer volumes` (pyRevit, écriture) | **éprouvé** | 202 familles + 202 types renommés |
| `MAJ params volumes` (pyRevit, écriture) | **éprouvé** | 1010 valeurs sur 202 volumes, 0 paramètre absent |
| `audit_to_zones.py` (hors Revit) | **éprouvé** | 202/202 contours reconstruits |
| `gen_sitemodel.py` (hors Revit) | **éprouvé** | 50 BUILDING, 202 FLOOR, tous contrôles au vert |
| `run.ps1` (la commande unique) | **éprouvé** | chaîne entière, code de sortie 0 |
| **import dans Ivion** | **jamais fait** | — |

**Chacune de ces validations vient d'un audit relancé après coup**, pas du
rapport du script. Ce point n'est pas de la prudence rhétorique : c'est la
leçon la plus chère de la journée (§7.1).

---

## 3. La chaîne, maillon par maillon

### 3.1 Dans Revit — trois boutons, panneau `Dev`

Ordre d'emploi, et il n'est pas interchangeable :

```
Renommer volumes  →  Audit volumes  →  MAJ params volumes  →  Audit volumes
   (écrit le nom)      (vérifie)        (recopie le nom)        (vérifie)
```

On renomme **avant** d'auditer : un audit passé sur l'ancien motif décrirait
un état déjà périmé.

**`Renommer volumes`** — trois modes, choisis au lancement par une fenêtre
`CommandSwitchWindow`. La simulation est le défaut, et **aucune transaction
n'existe avant un choix explicite**.

| Mode | Effet | CSV |
|---|---|---|
| 1 — Simuler | lecture seule | avant/après |
| 2 — Renommer les familles | écrit, en **deux passes** | avant/après |
| 3 — Noms de type | écrit, une passe | — |

**`MAJ params volumes`** — recopie les segments du nom dans les paramètres
partagés, un seul commit pour tout le lot.

**`Audit volumes`** — lecture seule stricte, aucune transaction ouverte. Sort
un JSON daté hors du modèle. C'est **lui le vérificateur** des deux autres.

### 3.2 Hors Revit — une seule commande

```powershell
.\tools\sitemodel\run.ps1 -Audit <chemin du JSON d'audit> -Batiment "The Study"
```

`run.ps1` construit son venv une fois (`tools\sitemodel\.venv`, gitignoré),
enchaîne les deux étapes, rend **1** si un contrôle échoue, et **sa dernière
ligne est le chemin absolu du fichier à importer**. Bruno n'a pas de
tuyauterie Python à gérer : c'est la seule commande à taper.

Les deux maillons, si on veut les appeler séparément :
`tools\sitemodel\audit_to_zones.py` puis `tools\sitemodel\gen_sitemodel.py`.
`shapely` n'est déclaré que pour cet outil, pas pour l'extension.

---

## 4. Le nommage

### 4.1 Le motif

```
VOL_nnn__<REF_Zone>__<REF_Etage>__<CLS_Nature_volume>[__<clé>]
ex.  VOL_007__JU_Bj-Fj-1j-5j__FLOOR_3__ETAGE
```

Le séparateur est un **double underscore**. Un underscore simple à
l'intérieur d'un segment (`JU_Bj-Fj-1j-5j`, `FLOOR_2_Mezzanine`) n'est
**jamais** un séparateur. Le découpage doit rendre **4 ou 5 segments**.

`CLS_Nature_volume` est une **liste fermée** : `ETAGE`, `TOITURE`,
`ENTRETOIT`, `EXTERIEUR`, `ENVELOPPE`. `ENVELOPPE` est un volume LOD100, ni
étage ni toiture : **exclu de l'export** vers Ivion.

La clé optionnelle vaut `sup`, ou un code bâtiment (`JU`, `MI`, `SC`, `SE`).
Quand elle désigne un bâtiment, **elle l'emporte** sur le préfixe de la zone
pour déterminer `REF_Batiment` — c'est ce qui permet à un escalier mitoyen
(`JU_esc-MI`) d'être rattaché où il faut.

**Tout le découpage vit à un seul endroit** : `bimflow.extension\lib\bimflow_noms.py`.
Pur Python, il tourne sous IronPython 3.4 **et** sous CPython 3 — c'est
exactement pour cela que le classement a pu être rejoué hors Revit avant
d'être exécuté dedans, avec **le même code**.

### 4.2 La numérotation `nnn`, trois niveaux

Le numéro suit **l'espace**, pour qu'une nomenclature triée par nom se lise
comme une descente du bâtiment :

1. **bâtiment** — `JU`, `MI`, `SC`, `SE`, puis `EXT` ;
2. **colonne** — regroupement par centre `(xc, yc)` arrondi, trié d'ouest en
   est puis du sud au nord ;
3. **altitude** — du bas vers le haut dans la colonne.

⚠️ **Deux pièges, tous deux payés** :

- Le niveau 1 se prend sur le **préfixe de `REF_Zone`**, pas sur
  `REF_Batiment`. Trier sur `REF_Batiment` éclate 8 zones sur deux bâtiments
  et donne des numéros non contigus *[mesuré]*. `classer()` dérive donc le
  bâtiment **lui-même** : aucun appelant ne peut se tromper de champ.
- Le niveau 2 travaille en **coordonnées internes Revit**, pas partagées.

`--nord-local SE=6.6` est **prévu et inactif** : personne n'a mesuré que
faire pivoter les centres de SE améliore l'ordre, et changer le tri change
tous les numéros.

### 4.3 Renommer en lot : deux passes, obligatoirement

Une renumérotation **redistribue** les noms : un nom final peut être déjà
porté par une autre famille au moment où on veut le poser, et Revit refuse
le doublon. D'où : passe 1, chacun prend `TMP_<id>` ; passe 2, chacun prend
son nom final ; les deux dans un `TransactionGroup`, pour que la maquette ne
reste jamais avec des familles nommées `TMP_...`.

---

## 5. Les paramètres

Écrits par `MAJ params volumes`, **identifiés par GUID, jamais par nom**
(fiche R08 — un nom se renomme, se traduit, se duplique ; le GUID *est* le
paramètre).

| Paramètre | GUID | Valeur |
|---|---|---|
| `REF_Zone` | `499a73ab-e323-42bf-807b-465c9165e62b` | segment 2, rafraîchi |
| `REF_Etage` | `d7971f4d-dab0-4a07-bf53-df011895c4e4` | segment 3, rafraîchi |
| `CLS_Nature_volume` | `ba2e6c9e-506e-4b97-95aa-a5e3c10cbc40` | segment 4, rafraîchi |
| `REF_Batiment` | `9b48114b-33fe-4eee-97ef-2369b17ea6ce` | clé si bâtiment, sinon préfixe de zone |
| `REF_Id` | `7414d6b1-6083-4145-9c1c-784e03243895` | uuid4, **une seule fois** |
| `CLS_Usage` | `e3e496bc-5c59-4d02-b914-428692662dc7` | **jamais écrit** (saisie métier) |

`REF_Zone` a été **ajouté au socle** ce jour (Texte, instance, Volumes), avec
un GUID neuf — jamais recyclé, y compris depuis les trois GUID `DOC_` retirés
le 2026-09-19, qui sont consignés dans le fichier précisément pour ne jamais
être réattribués.

`REF_Id` est la **clé de jointure vers Ivion**. Écrit une fois si le champ est
vide, jamais réécrit, jamais régénéré : il doit survivre aux renommages.

`REF_Batiment` porte les **valeurs longues** (`VALEURS_LONGUES = True`,
décision du 19b, maintenue).

Un paramètre local qui porterait le même *nom* sans le bon GUID n'est **pas**
reconnu : le volume sort en « paramètre absent » plutôt que de recevoir une
valeur dans le mauvais champ.

Registre : `shared_parameters\keovia_socle_parametres.txt`. Il se versionne,
il ne se régénère jamais.

---

## 6. Le repère, et le site_model

### 6.1 Coordonnées

Trois repères, à ne jamais confondre :

- **géométrie interne Revit** — ce que l'audit publie, toujours ;
- **coordonnées partagées** — ce qu'Ivion attend ;
- **`Level.Elevation`** — à ne **jamais** utiliser pour une altitude : sur
  The Study, il diffère de la géométrie de **29 065 mm** *[mesuré, R16 §1.1]*.
  L'audit publie les deux lectures pour contrôle, mais ne calcule que sur
  `ProjectElevation`.

La transformation est **lue dans l'audit**, plus jamais en dur :
`entete.emplacement_partage` donne l'angle au nord vrai et la position de
l'origine interne en coordonnées partagées. Seule constante fournie de
l'extérieur : le point de base Ivion.

Valeurs pour The Study *[mesurées par Revit, lues dans l'audit]* :
THETA **−0,5504768 rad (−31,54°)**, DX/DY/DZ **17,521 / −1,692 / −1,240 m**.

Un audit dépourvu de cette section fait retomber la chaîne sur des valeurs de
repli — elle le dit, mais elles ne valent que pour The Study.

### 6.2 Règle P — ce qui fait un BUILDING

Un `BUILDING` est **une pile**. Deux zones fusionnent si elles ont la **même
signature d'élévations** *et* une **union d'emprises connexe**. Les deux
conditions, pas l'une des deux.

Sur The Study : 53 zones → 46 signatures → **50 BUILDING**.

L'union globale des emprises sort en **MultiPolygon (2 parties)** : c'est un
site à plusieurs corps séparés, et ce n'est **pas une erreur**. Ce contrôle
était bloquant, il est devenu informatif.

### 6.3 Le défaut de recouvrement, et sa règle

*C'est le défaut le plus instructif de la chaîne.*

Un « recouvrement » de 3620 mm avait été annoncé entre deux tranches. Bruno
l'a contesté. **Mesure** : intersection des emprises en plan = **0,000 m²**.
Le test ne portait que sur l'intervalle Z.

Le même invariant manquait dans **l'arbitrage R‑S**, qui aurait silencieusement
rogné un volume valide de 3620 mm.

> **Règle consignée** : deux tranches se recouvrent si et seulement si elles
> se recouvrent **en plan ET en Z**. Un intervalle Z commun sans intersection
> d'emprise n'est pas un recouvrement. Un test qui ne regarde qu'une dimension
> ne mesure rien.

---

## 7. Ce qui a été mesuré sur Revit

Détail complet, avec dates et volumétrie : **`docs\ecrire_dans_revit.md`**.
Les cinq qui comptent :

### 7.1 Aucun `script.exit()` après une écriture

`script.exit()` appelle `sys.exit()`, lève `SystemExit`, la commande rend
`Cancelled` — et **Revit annule tout ce qu'elle a modifié, transactions
committées comprises**. Sans exception, sans message, sans trace.

Ce qu'on voyait : 202 renommages committés, relus 202/202 au nom voulu, et
tout revenu à l'ancien nom au clic suivant. **Six hypothèses sont mortes
avant la bonne** — document actif, élément `Family` remplacé, porteur de nom
désynchronisé, `TransactionGroup`, passe temporaire, travail partagé. Une
sonde a été écrite pour la troisième. J'étais à une réponse d'écrire en fiche
que *renommer une famille in situ par l'API ne persiste pas*, ce qui est faux.

Contrôle : `tools\volumes\verifier_sorties_apres_ecriture.py`.

### 7.2 Caractères interdits dans un nom Revit

`\ : { } [ ] | ; < > ? \` ~` — le **tilde** en fait partie. Le nom temporaire
valait `~TMP_<id>` : le lot entier a échoué sur *Name cannot include
prohibited characters*. Bénéfice : le `TransactionGroup` a été éprouvé pour
de vrai, la maquette n'est pas restée à moitié renommée.

### 7.3 `forms.alert` plafonne à quatre options

Une cinquième option est **silencieusement ignorée** — pas d'erreur, le
bouton n'existe pas. Vérifié dans le code pyRevit installé : les options
mappent sur les `TaskDialogCommandLinkId`, il y en a quatre. Au-delà,
`forms.CommandSwitchWindow`.

### 7.4 Les types homonymes sont acceptés

Chaque volume in situ est **sa propre famille** : 202 types nommés
`Volume Ivion` dans 202 familles distinctes, acceptés sans réserve. Ce
n'était pas acquis ; l'essai sur 3 volumes qui protégeait l'inconnue a été
retiré une fois la mesure faite.

### 7.5 Vérifier depuis l'extérieur

Un rapport de script dit ce que le script **croit** avoir fait. C'est ce qui
a masqué 7.1 pendant six exécutions. La vérification se fait par un audit
relancé, ou une nomenclature.

**Corollaire** : ne jamais rendre deux sorties indiscernables. Un CSV de
simulation et un CSV d'après-exécution portant le même nom ne permettent plus
de dire lequel on lit — et on finit par déduire une écriture qui n'a pas eu
lieu. C'est arrivé, et ça a fait relancer une écriture pour rien.

---

## 8. Mes erreurs de la journée

Elles sont ici parce qu'elles sont instructives, et parce qu'une passation
qui ne dirait que les succès serait fausse.

| Erreur | Ce qu'elle a coûté |
|---|---|
| Affirmer « le CSV confirme le mode 2 » alors que les deux CSV étaient indiscernables | Bruno a relancé une écriture inutilement |
| Attribuer au script le renommage de `VOL_202`, qui était un clic droit de Bruno | Une piste de diagnostic fausse |
| Annoncer 3620 mm de recouvrement sans tester le plan | Corrigé avant toute modification, sur la demande de mesure de Bruno |
| Trier le niveau 1 sur `REF_Batiment` | 8 zones éclatées, numéros non contigus |
| Utiliser `Family` sans l'importer | Un clic perdu ; d'où `verifier_noms_non_definis.py` |

Le point commun des trois premières : **j'ai affirmé sans mesurer**. Les deux
contrôles automatiques écrits ce jour (`verifier_noms_non_definis.py`,
`verifier_sorties_apres_ecriture.py`) sont la réponse durable aux deux
dernières.

---

## 9. Ce que la chaîne produit, et le jeu d'essai

Versé : `tools\sitemodel\exemples\audit_volumes_zone_A_VOL_20260924_1645.json`
— 202 volumes, noms au motif, paramètres écrits. C'est le **jeu de
régression**.

Chaîne entière rejouée dessus, hors Revit, en une commande, code de sortie 0
*[mesuré le 2026-09-24]* :

| Contrôle | Valeur |
|---|---|
| contours reconstruits | **202/202** |
| écart contour ↔ face horizontale | **0,003 m²** au pire |
| R1 (contour constant par zone) | OK sur 53 zones |
| partition en plan | **2 391,88 m²** des deux côtés, écart **0,00** |
| site_model | **50 BUILDING**, **202 FLOOR**, 9 noms d'étage |
| C1 · C2 · C3 · C6 · C7 · C10 · 5.1 · 2a | tous **OK** |
| volume total | **36 058,1 m³** |
| séparations non horizontales arbitrées | 2 (1 611 mm et 705 mm, vers le haut) |

Si l'un de ces chiffres bouge sans que la maquette ait bougé, **c'est le code
qui a changé**.

---

## 10. Ce qui reste ouvert

1. **L'import dans Ivion n'a jamais été fait.** Tous les contrôles amont sont
   au vert, ce qui n'est pas la même chose : l'import d'Ivion teste la
   conformité mais **ne diagnostique pas**. À faire sur un site brouillon.
2. **La carte 2D et les `FLOOR` homonymes.** 14 couples, dans 12 BUILDING,
   tous `ENTRETOIT` + `TOITURE` empilés sous le même nom `ROOF`. Bruno a
   confirmé qu'Ivion **les accepte** ; ce que la minimap de navigation en
   fait reste **inconnu**. `--suffixer-doublons` les distingue si nécessaire
   — à décider après l'essai, pas avant.
3. **Panneau définitif des trois boutons.** Ils ont tourné, la règle de sortie
   du panneau `Dev` leur est acquise ; leur destination relève de B25.
4. **`ControleZoneNiveau` (B18b)** est dans la même situation que l'était
   `audit_volumes_zone` : signalé, non traité.
5. **La branche n'est pas poussée**, et il n'y a pas eu de merge vers `main`.

---

## 11. Discipline — ce qui ne se négocie pas

- **Statuts** *mesuré* / *documenté* / *hypothèse*, jamais confondus. Ne rien
  affirmer d'un comportement Revit sans l'avoir observé **sur Revit**.
- Tout script qui écrit est précédé d'un **audit en lecture seule** sur le
  même périmètre.
- Les trois boutons ne tournent que sur **copie détachée** (R17).
  `IsWorkshared` reste vrai après un détachement conservant les sous-projets ;
  c'est **`IsDetached`** qui décide.
- Un script d'écriture : simulation d'abord, confirmation **nommant la
  maquette**, **un seul commit**, aucun `script.exit()` après la première
  écriture.
- Code dans `D:\Dropbox\Dev\bimflow`, **jamais dans OneDrive**. La fiche de
  liaison, elle, vit dans OneDrive (§8g) — c'est le seul document qui y reste.
- **PowerShell 7** uniquement.
- Un audit versé au dépôt est un **instantané daté**, jamais une source, et ne
  se retouche jamais à la main.

---

## 12. Où est quoi

```
bimflow.extension\lib\
    bimflow_noms.py            découpage et composition du nom — seul endroit
    bimflow_volumes.py         classement spatial et numérotation
bimflow.extension\bimflow.tab\Dev.panel\
    AuditVolumes.pushbutton\        lecture seule — le vérificateur
    RenommerVolumes.pushbutton\     écriture — 3 modes
    MajParamsVolumes.pushbutton\    écriture — par GUID
    SondeNomsFamille.pushbutton\    lecture seule — diagnostic conservé
    _ROLE.txt                       état réel de chaque bouton
tools\sitemodel\
    run.ps1                    LA commande
    audit_to_zones.py          audit JSON → zones + contours
    gen_sitemodel.py           zones → site_model Ivion
    exemples\                  le jeu de régression et ses chiffres
    README.md                  la chaîne en deux étapes, règle P
tools\volumes\
    dry_run_depuis_audit.py            rejoue le classement hors Revit
    verifier_noms_non_definis.py       noms utilisés jamais définis
    verifier_sorties_apres_ecriture.py script.exit() après un Commit()
docs\
    ecrire_dans_revit.md       les faits Revit mesurés
    passation_volumes_ivion_20260924.md   ce document
shared_parameters\
    keovia_socle_parametres.txt   la source des GUID
```
