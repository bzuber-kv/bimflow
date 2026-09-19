# Paramètres — socle Keovia, audit, nettoyage

> Repo `bimflow` · extension pyRevit · créé le 2026-09-19
> Portée : **générique** — le socle est un objet Keovia, pas un objet d'affaire.
> Environnement : Revit 2026, pyRevit 6.5.5, moteur **IPY342** — pas de shebang
> `#! python3`, niveau de langage Python 3.4 maximum (pas de f-strings).
> Source des faits : les **six boutons ont tourné en production sur une maquette
> réelle le 2026-09-19**. *Le nom de la maquette n'est pas consigné* — à inscrire
> ici le jour où il l'est, comme `thestudy_CO_BAT` l'est dans
> [`niveaux.md`](niveaux.md).
> **Confiance : DÉCIDÉ** pour la partie 1 (le socle est une règle, pas une
> observation) · **MESURÉ** pour la partie 2 — observé, daté, et chacun de ces
> faits a changé une décision.

---

## Pourquoi ce document

Un paramètre mal placé ne se voit pas. Il se crée en trois clics, il se propage
par les gabarits, et on ne découvre qu'il était de trop — ou qu'il doublait un
paramètre que Revit fournit déjà — qu'au moment où quelqu'un l'exporte et qu'il
manque, ou qu'il sort deux fois.

Le socle existe pour que cette décision soit prise **une fois**, sur un critère
écrit, plutôt qu'à chaque maquette. Les six boutons sont ce qui rend ce socle
vérifiable : trois le mesurent, trois l'appliquent.

## Ce que le dépôt contient aujourd'hui

| Bouton | Mode | Ce qu'il fait |
|---|---|---|
| `Audit paramètres` | **bleu** — lecture seule | Mesure chaque paramètre de projet : catégories liées, portée, objets porteurs, objets réellement renseignés, valeurs distinctes. Sortie tableau + CSV |
| `Paramètres natifs` | **bleu** — lecture seule | Relève ce que Revit fournit lui-même, catégorie par catégorie, et signale les paramètres de projet qui portent le nom d'un natif |
| `Sonde vues` | **bleu** — lecture seule | Tableau de toutes les vues, croisé avec l'état du paramètre du socle — inscriptible ou en lecture seule |
| `Socle paramètres` | **orange** — écrit | Lie les paramètres partagés du socle aux catégories. Crée des champs, **n'écrit aucune valeur** |
| `Renommage paramètres` | **orange** — écrit | Renomme sur place les paramètres de projet **non partagés**. Seule écriture réversible de la série |
| `Nettoyage paramètres` | **orange** — écrit | Retire les paramètres de projet morts, après migration éventuelle des valeurs. **Irréversible** |

Discipline respectée par les trois boutons d'écriture : **le plan est calculé et
affiché avant toute écriture**, une confirmation explicite est demandée, et
l'écriture tient dans **une transaction unique**, annulée en bloc à la moindre
erreur. Aucun ne peut agir d'un simple clic.

---

# Partie 1 — Le socle

## 1. Le critère d'entrée, et il est unique

> **Quelque chose HORS DU DOCUMENT doit-il reconnaître ce champ ?**
> Export IFC, appariement Ivion ou GMAO, étiquette, nomenclature entre modèles,
> échange avec un tiers.
>
> - **oui** → paramètre **PARTAGÉ** : il entre dans le fichier de GUID et reçoit
>   un **GUID à vie** ;
> - **non** → paramètre **DE PROJET** : porté par le gabarit, absent du fichier.

La question ne porte pas sur l'importance du champ, ni sur le nombre d'objets
qui le portent. Elle porte sur **qui doit le reconnaître**. Un champ capital mais
purement interne au document reste un paramètre de projet ; un champ anodin qui
sort en IFC est partagé.

C'est ce critère, et lui seul, qui a fait sortir les trois `DOC_` du fichier
partagé le 2026-09-19 — voir §3.

## 2. Les deux étages du socle

**Partagés — GUID à vie, dans `shared_parameters/keovia_socle_parametres.txt`**

| Paramètre | Groupe | Ce qu'il désigne |
|---|---|---|
| `REF_Batiment` | RÉFÉRENCEMENT | Bâtiment auquel l'objet appartient (liste fermée par projet) |
| `REF_Etage` | RÉFÉRENCEMENT | Étage macro (`BASEMENT`, `FLOOR_1`…), **distinct du niveau Revit**, plus fin. Sur un niveau Revit, ce champ porte la matrice de passage niveau → étage |
| `REF_Id` | RÉFÉRENCEMENT | Identifiant unique du volume, `<projet>-<type>-<nn>`. **Jamais réattribué.** Clé de rapprochement avec Ivion |
| `CLS_Usage` | CLASSIFICATION | Usage du volume (`RESIDENTIEL`, `CIRCULATION`, `TECHNIQUE`, `EXTERIEUR`) |
| `CLS_Nature_volume` | CLASSIFICATION | Nature du volume (`ETAGE`, `TOITURE`, `ENTRE_TOIT`, `EXTERIEUR`) — porte la distinction que la géométrie projetée ne permet pas de faire |

**De projet — portés par le gabarit, absents du fichier**

`DOC_Classement_vue` · `DOC_Classement_feuille` · `DOC_Sous_discipline`.

Le préfixe `DOC_` dit exactement pourquoi ils sont là : ils organisent la
**documentation à l'intérieur du document**. Rien dehors ne les lit.

**Règles de nommage arrêtées le 2026-09-19.** ASCII sans accent · aucun espace,
séparateur `_` · un seul préfixe de trois lettres majuscules · première lettre du
nom en capitale, le reste en minuscules · singulier · pas d'abréviation hors
préfixe · **pas d'unité dans le nom** · **le nom dit ce que la valeur DÉSIGNE,
jamais d'où elle vient**.

## 3. Le fichier de GUID — il se versionne, il ne se régénère jamais

`shared_parameters/keovia_socle_parametres.txt` est un fichier de paramètres
partagés Revit. **Il est la source des GUID**, et à ce titre :

- **il se versionne** — il entre au dépôt et son historique est sa garantie ;
- **il ne se régénère jamais** — le régénérer fabriquerait de nouveaux GUID, et
  tous les modèles déjà renseignés cesseraient de reconnaître leurs propres
  champs ;
- **un GUID retiré n'est jamais réattribué à autre chose.** Les trois `DOC_`
  sortis du fichier le 2026-09-19 y restent **inscrits en commentaire**, avec
  leur GUID, précisément pour que personne ne les réutilise :

```
bc3f686d-c5b2-4aa5-945a-dc371dc49f44  DOC_Classement_vue
65dfba27-db46-470e-bebf-a38fbe9771b8  DOC_Classement_feuille
0f6f1a5a-8f0b-4a3e-9c2f-7d5a1b6e40c1  DOC_Sous_discipline
```

> **Pourquoi un GUID mort se garde écrit.** Un GUID n'identifie pas un nom, il
> identifie une **définition**. Réattribuer celui d'un champ retiré à un champ
> neuf ferait que deux choses différentes porteraient la même identité dans des
> modèles différents — et la collision ne se verrait qu'à l'export, chez le
> destinataire. Le fichier garde donc la trace de ce qui a existé : **ce n'est
> pas de l'historique, c'est une réservation**.

Le bouton `Socle paramètres` **ne contient aucun chemin en dur** vers ce fichier.
Il reprend le fichier de paramètres partagés déjà déclaré dans Revit si son nom
est `keovia_socle_parametres.txt`, et le demande sinon. **La copie du dépôt est
la référence** : c'est elle qu'il faut désigner.

## 4. Les liaisons — quel paramètre sur quelles catégories

| Paramètre | Catégories liées |
|---|---|
| `REF_Batiment`, `REF_Etage` | large : objets du bâtiment, **plus les Niveaux** (porteurs de la matrice de passage) et les Masses |
| `REF_Id`, `CLS_Usage`, `CLS_Nature_volume` | volumes de référence seulement : Masses et Planchers de volume |

Une liaison existante est **étendue, jamais réduite** : l'outil ajoute des
catégories, il n'en retire pas. Retirer une catégorie efface les valeurs qu'elle
portait, et cela ne se fait pas en passant.

---

# Partie 2 — Ce qui est mesuré, le 2026-09-19

## 5. Un paramètre de projet non partagé se renomme sur place · *mesuré*

**Le fait.** Un paramètre de projet **non partagé** se renomme sur place, ses
**valeurs intactes**. C'est le même élément du document : il change d'étiquette,
rien d'autre. Le classement de l'arborescence suit automatiquement.

**Un paramètre partagé, non.** Son nom vient de sa définition, identifiée par un
GUID. `Renommage paramètres` le détecte et **refuse en le disant** — il ne
contourne pas.

**Ce que ce fait a changé.** Il a remplacé une migration par un renommage. Voir
§6 : la migration coûtait 35 vues, le renommage ne coûte rien.

## 6. La migration par recopie a été abandonnée — et c'est un chiffre · *mesuré*

Première approche pour passer de `Classement Vues` à `DOC_Classement_vue` :
créer le nouveau paramètre, **recopier les valeurs**, retirer l'ancien. Résultat
mesuré :

| | Vues |
|---|---:|
| Recopiées sans incident | **171** |
| **Miroirs** — fenêtre de vue, caméra, repère, pas de vraies vues | 67 |
| **Vraies vues dont la cible restait en LECTURE SEULE**, sans explication | **35** |

Les 35 se répartissent en **16 coupes, 13 vues 3D, 6 plans**.

> **Le gain était un nom ; le risque, le classement de 35 vues.** La migration
> est abandonnée : `Classement Vues` et `Classement Feuille` **restent maîtres**.
> `MIGRATIONS` est vide dans `Nettoyage paramètres` depuis cette mesure, et les
> deux noms — l'ancien **et** le nouveau — sont inscrits dans `PROTEGES`.

C'est aussi la raison d'être de `Sonde vues` : mettre côte à côte les vues qui
acceptent l'écriture et les 35 qui la refusent, pour que la différence se voie.
**L'outil ne conclut pas** — il n'y a pas encore d'explication, seulement deux
populations et leurs colonnes.

## 7. Le doublon d'un paramètre natif est le plus coûteux · *mesuré sur un cas*

Revit fournit lui-même un grand nombre de paramètres (*built-in*). Créer un
paramètre de projet qui **porte le nom d'un natif** produit deux champs
homonymes : on renseigne l'un, on exporte l'autre, et rien ne le signale.

`Paramètres natifs` **mesure au lieu de réciter** : il ouvre les objets du modèle
et relève, catégorie par catégorie, les paramètres dont la définition porte un
`BuiltInParameter`, puis confronte cette liste aux paramètres de projet de la
maquette.

> **À relancer à chaque changement de version de Revit** : la liste des natifs
> évolue. Un relevé daté vaut pour la version où il a été pris, pas pour la
> suivante — c'est pourquoi l'outil mesure au lieu d'embarquer une table.

## 8. Ce que le nettoyage refuse de proposer — trois protections cumulées

`Nettoyage paramètres` est le seul outil **irréversible** de la série : retirer
une liaison **efface les valeurs**, sans retour. D'où trois protections qui se
cumulent — un paramètre n'est proposé que s'il passe les trois :

| # | Protection | Motif |
|---|---|---|
| 1 | Un paramètre qui **porte au moins une valeur** n'est jamais proposé | la valeur est un travail de quelqu'un |
| 2 | Un paramètre utilisé comme **champ de nomenclature ou dans un filtre de vue** n'est jamais proposé | le retirer casse un livrable, pas seulement une donnée |
| 3 | Un paramètre **nommé dans `PROTEGES`** n'est jamais proposé | le socle, et les noms d'avant le renommage |

Seuls les paramètres inscrits dans `MIGRATIONS` échappent à la protection 1 :
leurs valeurs sont d'abord **recopiées** vers le paramètre du socle, puis
l'ancien est retiré. `MIGRATIONS` est **vide** depuis le 2026-09-19 (§6).

Et la règle qui domine les trois : **`Audit paramètres` mesure, il ne conclut
pas.** « Vide partout » n'est pas « supprimable » — c'est la règle **C7** de la
fiche R16, et elle vaut ici mot pour mot : un paramètre non renseigné peut être
un champ déclaré à l'avance, pas un résidu. Le verdict appartient à celui qui
connaît l'intention.

---

## Ce qui reste ouvert

- **Pourquoi 35 vues refusent l'écriture.** Mesuré, pas expliqué. `Sonde vues`
  fournit la matière — classe, gabarit, dépendance, gabarit appliqué, feuille
  d'accueil — mais aucune colonne ne tranche encore. Tant que la cause n'est pas
  connue, **aucune migration de paramètre sur les vues** ne doit être relancée.
- **`Audit paramètres` ne voit que les paramètres de PROJET.** Un paramètre porté
  par une famille chargée ne s'y trouve pas, et se retire dans l'éditeur de
  familles, pas ici. La mesure du dépôt est donc **partielle par construction** —
  à dire à chaque lecture du rapport.
- **Le nom de la maquette d'épreuve n'est pas consigné.** Les faits du 2026-09-19
  sont reproductibles par les mêmes boutons, mais pas encore rattachés à un
  fichier nommé. À combler.
