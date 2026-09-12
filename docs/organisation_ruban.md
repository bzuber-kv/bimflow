# G03 — Organisation du ruban bimflow

> Repo `bimflow` · créé le 2026-09-10 · portée : **générique**, gouvernance du repo
> Statut : décidé (Bruno, 2026-09-10). Réversible à coût nul — un panneau est un
> nom de dossier, le renommer ne casse aucune référence.
> **Complété le 2026-09-12** : code couleur des icônes (§4, orientation O7) et état
> réel du panneau `Calage projet` (§3), tous deux déjà appliqués au dépôt mais non
> écrits ici.

---

## 1. Les deux niveaux, et ce que chacun porte

| Niveau | Ce qu'il exprime | Coût |
|---|---|---|
| `.tab` | **la famille d'usage** — deux à terme, voir §2 | occupe du ruban en permanence |
| `.panel` | **le domaine** — 4 à 8 boutons | l'unité de « ce que je vois d'un coup » |
| bouton | **le mode** — `Audit …` en lecture, verbe d'action en écriture ; la **couleur de l'icône** le redit avant le clic (§4) | — |

**Règle : par domaine au panneau, par mode au bouton.**
La tentation d'un panneau `Audit` et d'un panneau `Écriture` est à écarter : la
discipline du backlog impose que *tout script qui écrit soit précédé d'un audit en
lecture seule sur le même périmètre*. La paire audit + écriture est **l'unité
d'usage** — B13 prépare B14, B10 prépare B09. Les séparer éloignerait deux boutons
qu'on enchaîne et effacerait visuellement le couplage qui est justement la règle.

Le ruban Revit est fini horizontalement : un panneau qui grossit sans limite
repousse les autres dans le débordement. D'où le grain de 4 à 8 boutons.

## 2. Les deux familles

La ligne de partage est **le contenant et le contenu** :

**Famille A — le fichier.** Les outils s'intéressent à *comment le projet est
rangé* : sous-projets, niveaux, vues, feuilles, unités, normes, coordonnées. Ils
ne savent pas ce que le bâtiment est, et n'ont pas besoin de le savoir. C'est
l'objet de `bimflow.tab` aujourd'hui, et des cinq panneaux du §3.

**Famille B — le modèle.** Les outils s'intéressent à *ce que le bâtiment est* :
reconnaissance de formes, détection d'objets, création de géométrie, quantitatifs,
écart maquette ↔ nuage. Rien de tout cela n'existe encore.

**Test d'appartenance, pour tout script à venir :**
> Le script marcherait-il à l'identique sur n'importe quelle maquette, sans rien
> savoir du bâtiment ? → **famille A**. Sinon → **famille B**.

Exemples de frontière : l'audit d'écart maquette ↔ nuage relève de B (il parle du
bâtiment réel) ; l'audit du nommage des liens relève de A (il parle du fichier).

**Quand créer le second onglet.** Pas maintenant. Un onglet Revit coûte de la
place en permanence, et cinq panneaux tiennent largement dans un seul. Le critère
est **mesurable, pas esthétique** : le jour où `bimflow.tab` déborde à l'écran de
travail, la famille B part dans son propre `.tab`. Comme la famille de chaque
script est déjà inscrite ici, ce jour-là le découpage est un déplacement de
dossiers, pas une refonte.

## 3. Les cinq panneaux de la famille A

Noms de dossiers en **ASCII, sans accent** — même esprit que la règle sur les
sous-projets (accents et mots de liaison supprimés partout : exports, scripts,
IFC), et pas de surprise Git entre postes.

### `Calage projet.panel`
**Rôle.** Mettre le fichier d'aplomb : ce qui définit l'organisation du projet,
indépendamment de ce qu'il contient. Sous-projets, propagation des normes,
cartouche et identité, paramètres partagés.
**Installés — 5 boutons** : **B13** (audit sous-projets), **B15** (export de
l'inventaire), **B16** (inventaire détaillé), **B17** (reclassement sous-projets),
**B18a** (audit des références de niveau, lecture seule).
**Attendus — 5 autres** : B06 (propagation des normes), B08 (cartouche /
rebranding), B14 (migration sous-projets), B18b (contrôle de zone), B18c (niveaux,
mode écriture).

> ⚠ **5 boutons sur les 8 du grain, et 5 en attente : le seuil sera franchi.**
> C'est le **déclencheur d'O1**, à rejuger à la **révision mensuelle** et non au
> fil de l'eau. Le jour venu le découpage reste un déplacement de dossiers, pas
> une refonte — chaque bouton sait déjà de quel domaine il relève.

*Arbitrage tracé* : B08 touche un objet documentaire (le cartouche) mais c'est une
**normalisation ponctuelle d'un fichier repris**, pas de la production de
documents — il reste ici, pas dans `Vues et feuilles`.

### `Georeferencement.panel`
**Rôle.** La position du modèle dans le monde : repères, origine interne,
altitudes et niveaux, insertion des nuages, export géolocalisé.
**Y va** : B09 (paramètre `Altitude_Absolue`), B10 (audit des altitudes),
B11 (lecture de l'origine interne), B12 (recalage — suspendu).
⚠ **Domaine partagé** avec `dev\ivion_api` (section Passerelle du hub) : tout
script touchant aux coordonnées se lit des deux côtés avant d'être écrit.

### `Vues et feuilles.panel`
**Rôle.** La couche documentaire : arborescence et classement des vues, gabarits
de vue, feuilles, export et nommage des livrables.
**Y va** : B01 (planche-contact), B04 (audit du classement des vues),
B07 (export batch et nommage).

### `Unites.panel`
**Rôle.** Valeurs et arrondis : détection des valeurs qui ne tombent pas sur la
trame, conversions.
**Y va** : B02 (audit des valeurs impériales non-propres), B03 (convertisseur).
*Portée réduite* depuis la décision mm/SI : l'impérial n'est plus une unité de
travail mais de sortie. Ce panneau sert surtout aux **fichiers repris de tiers** et
aux familles héritées.

### `Conformite.panel`
**Rôle.** Vérifier une maquette contre le plan qualité : nommage, sous-projets,
filtres, valeurs de paramètres, cohérence de la fédérée.
**Y va** : B05 (audit de conformité fédérée).
*Particularité* : seul panneau dont la sortie est **aussi un livrable client
potentiel**, et pas seulement un outil interne. Bloqué par S1 — sans règles
écrites, il n'y a rien à auditer.

## 4. Le code couleur des icônes — orientation O7

Posé le 2026-09-10, en réponse à un irritant d'usage : *« en cliquant sur un bouton
on engage une action sans pouvoir décider de l'annuler »*. La couleur de l'icône
dit **ce que le bouton fait au modèle**, et elle le dit **avant le clic**.

| Couleur | Sens |
|---|---|
| **Bleu** — `#195DB1` | **lecture seule**, aucune transaction |
| **Orange** | **écrit dans le modèle** (une fois désarmé) |
| **Violet** | ouvre une transaction **mais l'annule toujours** |

*Seul le bleu a sa valeur relevée comme référence (au dépôt, le 2026-09-12).
Orange et violet sont désignés par leur nom tant qu'une valeur n'a pas été relevée
de la même façon.*

**Complément indissociable.** Tout script d'écriture **démarre en simulation** et
demande une **confirmation nommant la maquette**. C'est le sens de « une fois
désarmé » : un bouton d'écriture ne doit jamais pouvoir agir d'un simple clic.

**L'icône fait partie du livrable, pas de la finition.** Un bundle sans `icon.png`
s'affiche **en texte nu** et **sort du code couleur** — il perd exactement
l'information que le code couleur existe pour donner, et rien à l'écran ne signale
le manque. Un bouton sans icône n'est pas fini.

**Format.** **96×96, ARGB** — fond transparent, jamais un aplat opaque — et une
**carte arrondie à fond clair** bordée de la couleur du mode. C'est cette forme
commune, et pas le seul pictogramme, qui rend la famille reconnaissable à la
taille où le ruban l'affiche réellement.

## 5. Ce qui reste ouvert

- L'ordre d'affichage des panneaux et des boutons suit l'alphabet par défaut.
  pyRevit expose une clé `layout` dans un `bundle.yaml` pour le forcer.
  *Statut : documenté, syntaxe non vérifiée.* À regarder le jour où l'alphabet ne
  suffit plus — aujourd'hui il donne le bon ordre (`Audit` avant `Migration`).
- Les panneaux de la famille B ne sont pas nommés : ils le seront quand le premier
  script métier arrivera, sur la même méthode — nommer au niveau du groupe qui
  tiendra 4 à 8 boutons, jamais au niveau d'un objet isolé.
- **Le déclencheur d'O7 est atteint** *(2026-09-12)*. Un **quatrième mode d'action**
  est apparu : **B19 écrit des fichiers, pas le modèle**. Trois couleurs ne
  suffisent plus à décrire ce qu'un bouton fait. À rejuger à la révision mensuelle
  — en attendant, **aucune quatrième couleur n'est inventée ici**.
