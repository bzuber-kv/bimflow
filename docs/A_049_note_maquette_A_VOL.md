# A_049 The Study — note pour les infos du projet

> État de la maquette **`thestudy_A_VOL`** au **2026-09-24**, après la mise en
> place du nommage des volumes de zone et la mise à jour du `site_model` Ivion.
> Texte destiné aux informations du projet A_049 (OneDrive).

---

## Ce qui a changé dans la maquette

La maquette **centrale** `thestudy_A_VOL` porte désormais, sur ses **202
volumes de zone** (familles in situ, catégorie `Volumes`) :

**1. Un nom de famille au motif fermé**

```
VOL_nnn__<REF_Zone>__<REF_Etage>__<CLS_Nature_volume>[__<clé>]
ex.  VOL_001__JU_Cj-Dj-1j-1j__FLOOR_3__ETAGE
```

Le séparateur est un **double underscore**. Un underscore simple à
l'intérieur d'un segment (`JU_Bj-Fj-1j-5j`, `FLOOR_2_Mezzanine`) n'est jamais
un séparateur.

Le numéro `nnn` suit **l'espace**, pas l'ordre de création : par bâtiment
(`JU`, `MI`, `SC`, `SE`, puis `EXT`), puis par colonne d'ouest en est puis du
sud au nord, puis du bas vers le haut. Une nomenclature triée par nom se lit
donc comme une descente du bâtiment. Répartition actuelle :

| BAT | Colonnes | Volumes | Plage |
|---|---|---|---|
| JU | 9 | 27 | `VOL_001` → `VOL_027` |
| MI | 13 | 48 | `VOL_028` → `VOL_075` |
| SC | 15 | 69 | `VOL_076` → `VOL_144` |
| SE | 16 | 58 | `VOL_145` → `VOL_202` |

**2. Un nom de type unique** — tous les volumes portent le type
`Volume Ivion`.

**3. Cinq paramètres partagés**, recopiés depuis le nom :

| Paramètre | Contenu |
|---|---|
| `REF_Zone` | segment 2 — la zone de découpage |
| `REF_Etage` | segment 3 — l'étage macro (`BASEMENT`, `FLOOR_1`, `ROOF`…) |
| `CLS_Nature_volume` | segment 4 — liste fermée : `ETAGE`, `TOITURE`, `ENTRETOIT`, `EXTERIEUR`, `ENVELOPPE` |
| `REF_Batiment` | la clé si elle désigne un bâtiment, sinon le préfixe de la zone |
| `REF_Id` | **uuid4 — clé de jointure vers Ivion** |

`CLS_Usage` n'est **pas** écrit : c'est une saisie métier.

---

## Trois règles à ne pas perdre

1. **Le NOM de famille est la source de vérité.** Les paramètres en sont la
   copie, jamais l'inverse. Renommer un volume à la main sans relancer
   l'outil met les deux en désaccord, et c'est le nom qui a raison.
2. **`REF_Id` ne se régénère jamais.** C'est ce qui rattache un volume à son
   objet dans Ivion. Il est écrit une seule fois, et il doit survivre aux
   renommages, aux copier-coller et aux reprises.
3. **L'identité d'un paramètre est son GUID**, pas son nom. Un champ portant
   le même nom avec un autre GUID n'est pas le même paramètre. Source des
   GUID : `shared_parameters\keovia_socle_parametres.txt` du dépôt bimflow.

---

## Le `site_model` Ivion

Produit depuis la maquette et **mis à jour dans Ivion le 2026-09-24**.

- **50 `BUILDING`**, **202 `FLOOR`**, 9 noms d'étage distincts.
- Un `BUILDING` est **une pile** : deux zones fusionnent si elles ont la même
  signature d'élévations **et** une union d'emprises connexe.
- Le géoréférencement est **lu dans la maquette**, jamais saisi : angle au
  nord vrai et position de l'origine interne en coordonnées partagées. Seule
  constante extérieure, le point de base Ivion.
- Les volumes de nature `ENVELOPPE` sont **exclus** de l'export.

**Point ouvert.** 14 couples de `FLOOR` homonymes (un `ENTRETOIT` et une
`TOITURE` empilés sous le même nom `ROOF`), répartis dans 12 `BUILDING`.
Ivion les **accepte** ; ce que la **minimap de navigation 2D** en fait n'a pas
été regardé. Si l'affichage gêne, la chaîne sait les distinguer
(`--suffixer-doublons`) — mais cela change les noms d'étage côté Ivion, donc
à décider sur ce qu'on voit, pas par précaution.

---

## Comment on refait la chaîne

Dans Revit, ruban **bimflow → Dev**, un palier à la fois, **en synchronisant
et en relançant l'audit entre chacun** :

1. **Renommer volumes** — mode 1 pour simuler, mode 2 pour l'essai sur un
   seul volume (à faire en premier sur une maquette centrale), mode 3 pour
   les familles, mode 4 pour les types.
2. **MAJ params volumes**.
3. **Audit volumes** — c'est lui qui produit le JSON d'export, et c'est lui
   qui **vérifie** : un rapport de script dit ce que le script croit avoir
   fait, l'audit dit ce que la maquette porte.

Puis, hors Revit, une seule commande :

```powershell
D:\Dropbox\Dev\bimflow\tools\sitemodel\run.ps1 -Audit <le JSON d'audit> -Batiment TheStudy
```

Sa dernière ligne est le chemin du fichier à importer dans Ivion. Code de
sortie non nul si un contrôle échoue.

**Sur la maquette centrale** : être **seul dessus**, et synchroniser à chaque
palier. Les boutons le demandent et font cocher une case avant d'écrire.

---

## Où sont les outils

Dépôt **`bimflow`**, `D:\Dropbox\Dev\bimflow` — jamais dans OneDrive.

| | |
|---|---|
| boutons pyRevit | `bimflow.extension\bimflow.tab\Dev.panel\` |
| chaîne site_model | `tools\sitemodel\` (`run.ps1`, README) |
| règles Revit mesurées | `docs\ecrire_dans_revit.md` |
| passation complète | `docs\passation_volumes_ivion_20260924.md` |
| source des GUID | `shared_parameters\keovia_socle_parametres.txt` |
