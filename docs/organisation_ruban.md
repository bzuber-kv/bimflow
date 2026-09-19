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
**Installés — 11 boutons.**
*Sous-projets et niveaux* : **B13** (audit sous-projets), **B15** (export de
l'inventaire), **B16** (inventaire détaillé), **B17** (reclassement sous-projets),
**B18a** (audit des références de niveau).
*Paramètres, versés le 2026-09-19* : `Audit paramètres`, `Paramètres natifs`,
`Sonde vues` (lecture seule) · `Socle paramètres`, `Renommage paramètres`,
`Nettoyage paramètres` (écriture).
**Attendus — 5 autres** : B06 (propagation des normes), B08 (cartouche /
rebranding), B14 (migration sous-projets), B18b (contrôle de zone), B18c (niveaux,
mode écriture).

> ⚠ **Le seuil d'O1 n'est plus à venir : il est franchi.** 11 boutons installés
> pour un grain de 4 à 8, et 5 attendus. Les six outils de paramètres relèvent
> bien du domaine — le rôle du panneau nomme les paramètres partagés — donc ce
> n'est pas une erreur d'affectation, c'est **un domaine devenu trop gros pour un
> panneau**.
>
> La coupure naturelle se lit dans la liste ci-dessus : *sous-projets et niveaux*
> d'un côté, *paramètres* de l'autre. **À trancher à la révision mensuelle**, pas
> au fil de l'eau. Le découpage reste un déplacement de dossiers.

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
| **Orange** — `#C55901` | **écrit dans le modèle** (une fois désarmé) |
| **Violet** | ouvre une transaction **mais l'annule toujours** |

*Valeurs relevées au dépôt : le **bleu le 2026-09-12**, l'**orange le 2026-09-19**
— une seule valeur pour l'orange, celle de B17, à laquelle les trois boutons
d'écriture du socle de paramètres ont été ramenés le même jour. Le violet est
désigné par son nom tant qu'une valeur n'a pas été relevée de la même façon.*

**Complément indissociable — deux formes admises.** Un bouton d'écriture ne doit
**jamais pouvoir agir d'un simple clic**. C'est l'exigence ; elle se tient de deux
façons, et **les deux satisfont O7** :

**(a) Désarmement par constante.** Le script porte `SIMULATION = True` en tête de
fichier ; passer en mode réel demande d'éditer le script, geste délibéré qui ne
s'accomplit pas par inadvertance. *Forme de B17.*

**(b) Plan affiché avant écriture, puis confirmation nommant la maquette.** Le
script calcule ce qu'il ferait, l'**affiche en entier**, puis demande une
confirmation dont le texte **nomme la maquette** — `Maquette : <titre>`. Rien
n'est écrit avant ce oui. *Forme des trois boutons d'écriture du socle de
paramètres.*

Ce que la couleur orange annonce, c'est donc ce que le bouton **peut** faire,
jamais ce qu'il fait au premier clic.

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
