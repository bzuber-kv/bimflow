# Niveaux — audit de l'ancrage (B18a) et mode écriture (B18c)

> Repo `bimflow` · extension pyRevit · créé le 2026-09-12
> Portée : **générique** — toute maquette Revit.
> Cas d'origine : affaire **A_049_TheStudy**, maquette `thestudy_CO_BAT`,
> Revit 2026, ACC, 6 187 éléments porteurs d'une référence de niveau.
> Environnement : Revit 2026, pyRevit 6.5.5, moteur **IPY342** — pas de shebang
> python3, niveau de langage Python 3.4 maximum (pas de f-strings).
> Sources : fiche **R16** §1 et §2 (faits mesurés) et **spécification B18 mode
> écriture** v2, toutes deux du 2026-09-12.
> **Confiance : MESURÉ** pour la partie 1 — observé, daté, reproductible par le
> même bouton. **SPÉCIFICATION, aucun code écrit** pour la partie 2.

---

## Pourquoi ce document

Corriger à la main le niveau de rattachement d'un objet **le déplace** : Revit
conserve le décalage, pas l'altitude. Autour de ce fait unique gravitait une
demi-douzaine d'affirmations jamais mesurées. Trois exécutions de l'outil d'audit
en ont tranché quatre, et en ont invalidé deux qui circulaient comme acquises.

Ce document porte les deux moitiés de l'opération : **ce qui est mesuré**
(partie 1, matière du bouton livré) et **ce que le mode écriture devra faire**
(partie 2, spécification — rien n'est écrit).

## Ce que le dépôt contient aujourd'hui

| Bouton | Panneau | Mode | État |
|---|---|---|---|
| `Audit niveaux` (B18a) | `Calage projet` | lecture seule, aucune transaction — icône **bleue** | **éprouvé** le 2026-09-12, trois exécutions, deux défauts trouvés et corrigés |
| `Controle zone` (B18b) | `Calage projet` | lecture seule — icône **bleue** | écrit, **jamais exécuté — hors dépôt** |
| Mode écriture (B18c) | — | écriture — icône **orange** | **spécifié, pas écrit** — voir §9 |

`Audit niveaux` sort **une ligne par référence** de niveau (22 colonnes) et une
synthèse à l'écran. Regrouper le CSV par `Id` donne la **signature d'ancrage
complète** d'un objet : c'est cette signature, et jamais une ligne isolée, qui est
l'unité de travail. La colonne `Niveau_cible` sort **vide** — elle est le point
d'entrée de la boucle semi-automatique du §3 de la partie 2.

---

# Partie 1 — Ce qui est mesuré

## 1. Trois faits Revit mesurés — et non documentés ailleurs

### 1.1 `Level.Elevation` n'est pas un repère géométrique · *mesuré*

Sur `thestudy_CO_BAT`, en comparant sur 361 murs le `Zmin` de la boîte englobante
à `altitude du niveau + décalage inférieur` :

| Lecture d'altitude | Écart médian | Dispersion |
|---|---:|---|
| **`Level.ProjectElevation`** | **0,0 mm** | 99 % à ±5 mm |
| `Level.Elevation` | **−29 065 mm** | 99 % à ±5 mm |

Les 29 065 mm ne sont pas un hasard : c'est **exactement** l'écart entre l'origine
interne (123,760 m) et le point de base (94,695 m) relevés au géoréférencement du
2026-09-11.

**`Level.Elevation` compte depuis la base d'élévation du TYPE de niveau** — ici le
point de base du projet. **`Level.ProjectElevation` compte depuis l'origine
interne**, comme toute la géométrie. Le nommage est trompeur : c'est
`ProjectElevation`, et non `Elevation`, qui est dans le repère du modèle.

> **Règle.** Toute comparaison géométrique se fait sur `ProjectElevation`.
> `Level.Elevation` dépend d'un réglage de type (R10) et n'est pas un repère
> fiable.

Et surtout : **un outil ne suppose pas le repère, il le mesure.** B18a essaie les
deux lectures, retient celle qui annule l'écart, et s'il reste une constante il la
retranche — à condition que la dispersion prouve qu'elle est bien constante. Sans
ce contrôle, la première exécution annonçait **6 602** écarts « supérieurs à 3 m »
qui étaient tous le même décalage de 29 m.

### 1.2 Un paramètre de niveau HAUT ne se compare pas à `Zmin` · *mesuré*

Deuxième cause de faux positifs, et la plus coûteuse : comparer `Zmin` au niveau
désigné par la **contrainte supérieure** d'un objet. Tout mur de 3 m sort alors à
−3 m.

Vérification sur les murs incriminés : leur `Zmax` tombe sur leur niveau supérieur
à la valeur du `Décalage supérieur` près — médiane **−100 mm**. Ils étaient
corrects.

| Règle de comparaison | Références | Objets |
|---|---:|---:|
| `Zmin` partout | 286 | **243** |
| `Zmin`, ou `Zmax` si le paramètre désigne un niveau haut | 118 | **114** |

> **153 faux positifs sur 286.** Le chiffre de **243 objets** publié dans
> l'affaire A_049 provient du prototype, qui appliquait la même règle — la
> coïncidence au chiffre près le confirme. **Il est surestimé d'un facteur 2,1.**

### 1.3 Revit expose les paramètres de niveau EN DOUBLE · *mesuré*

La plupart des occurrences de famille portent leur paramètre de niveau **deux
fois** — paramètre d'instance et paramètre de nomenclature, même nom affiché, même
valeur. Le phénomène est général, pas marginal :

| Catégorie | Références brutes | Après dédoublonnage |
|---|---:|---:|
| Raccords de canalisation | 2 476 | 1 238 |
| Poteaux porteurs | 345 | 207 |
| Modèles génériques | 288 | 144 |
| Équipement de génie climatique | 222 | 111 |
| Sols · Plafonds · Portes · Fenêtres | ×2 | ÷2 |
| **Total modèle** | **8 584** | **6 601** |

Les poteaux porteurs atteignent **cinq** références (`Niveau de base` ×2,
`Niveau supérieur` ×2, `Niveau` ×1).

> **Règle.** Même nom de paramètre + même niveau = **un seul fait d'ancrage**.
> Tout dénombrement de références sans dédoublonnage est surévalué d'environ 30 %
> sur l'ensemble d'un modèle, et du double sur les catégories concernées.

## 2. L'état mesuré de `thestudy_CO_BAT` au 2026-09-12

### 2.1 Ce que l'altimétrie tranche

| | Objets |
|---|---:|
| Écart franc (> 3 m), **total** | **114** |
| dont **actionnables** (paramètre modifiable) | **88** |
| dont **suiveurs** (paramètre en lecture seule — ils suivent leur hôte) | 26 |

Composition des 88 actionnables : 45 lignes d'axe · 22 canalisations · **20 murs**
· 4 éléments d'ossature · 1 escalier. Les 26 suiveurs sont 23 raccords de
canalisation, 1 équipement CVC, 1 plafond, 1 sol — **les raccords suivront les
canalisations qui les portent**.

Autrement dit : **une vingtaine d'objets de bâtiment, et un réseau**. Le problème
est nettement plus petit qu'annoncé, et concentré.

**86 % des références en écart sont sur `SC_N00` ou `SC_N01`**, le niveau de la vue
de travail. Signature de l'objet créé au niveau par défaut, pas d'une erreur de
jugement.

### 2.2 Ce que l'altimétrie ne tranche pas — et c'est le chiffre qui compte

**5 015 objets** (dont 3 598 modifiables) ont un écart compris entre **800 mm** —
l'intervalle médian entre niveaux consécutifs — et 3 000 mm.

Ce ne sont pas 5 015 suspects : un plafond à 2,7 m ou une canalisation sous dalle
sont normalement dans cette bande. C'est la mesure de ce sur quoi l'altimétrie
**s'abstient**.

> **L'altimétrie décide sur 114 objets et se tait sur 5 015. Rapport de 1 à 44.**
> C'est l'argument chiffré du contrôle de ZONE, qui ne reposait jusqu'ici que sur
> un raisonnement sur l'intervalle de 790 mm.

### 2.3 Les niveaux, et ce que l'audit ne dit pas

26 niveaux. Intervalle médian **800 mm**, 15 intervalles sur 25 sous le mètre.

Huit niveaux ne portent **aucune référence** : `MI_N05`, `EXT_PARC`, `SE_N01_S`,
`SE_TOIT`, `SC_TOIT`, `MI_EQU`, `MI_TOIT`, `JU_TOIT`.

> ⚠ **Une référence nulle n'est pas un verdict de suppression.** Sur A_049, six de
> ces huit niveaux (toitures, extérieur, équipement) sont **déclarés à l'avance**,
> avant que la modélisation les atteigne. C'est un état normal d'une maquette en
> cours. Seuls trois niveaux sont effectivement visés par les décisions du 12/09,
> et deux d'entre eux figurent dans cette liste par coïncidence.
>
> **Un audit mesure des références ; il ne connaît pas l'intention.** Un outil, et
> le commentaire qui l'accompagne, écrivent *« n'est référencé par rien »*, jamais
> *« supprimable »*. Le verdict appartient à celui qui connaît l'intention. La
> distinction résidu / déclaré-à-l'avance **n'est pas dans le modèle** — elle est
> dans le PEP et dans la tête de celui qui a créé l'objet. *(Erreur commise et
> corrigée le 2026-09-12 ; vaut aussi pour les sous-projets vides, les types non
> instanciés, les paramètres non renseignés, les vues sans feuille.)*

Ce que la mesure apporte réellement : **le coût de suppression des trois niveaux
visés**.

| Niveau visé | Objets à redistribuer | Vues détruites |
|---|---:|---:|
| `NS_0-1` | **43** (dont 20 lignes d'axe suiveuses → 23 réels) | **0** |
| `SE_N01_S` | 0 | 0 |
| `SE_N02_S` | 3 | 0 |

**Ces chiffres confirment indépendamment les décisions de l'affaire** : la note du
12/09 annonçait « les décrochés en portent 0 et 3 », l'audit mesure 0 et 3, par un
tout autre chemin.

Les **28 vues en plan** du modèle se répartissent sur huit niveaux, dont **14 sur
`SC_N00`**. Aucune n'est menacée par les trois suppressions visées ; la vigilance
porte sur d'éventuelles fusions à `SC`.

### 2.4 Les ancrages multiples

| Références par objet | Objets |
|---:|---:|
| 1 | 5 828 |
| 2 | 283 |
| 3 | 69 (poteaux porteurs) |

Paramètres porteurs recensés : `Niveau` (3 181) · `Niveau de référence` (2 613,
MEP) · `Contrainte inférieure` (376) · `Contrainte supérieure` (274) ·
`Niveau de base` (76) · `Niveau supérieur` (74) · `Niveau à la pointe` ·
`Niveau au bas de la flèche` · `Niveau de nomenclature` · la propriété `.LevelId`
(1 cas non couvert par un paramètre).

**352 objets ont deux ou trois niveaux.** Ce sont ceux pour lesquels « un ancrage
se transforme en entier, ou pas du tout » n'est pas une précaution théorique.

---

# Partie 2 — Le mode écriture (B18c) : spécification

> **Statut : spécification, aucun code écrit.** Le mode lecture, lui, est livré.
> Les six points du §9 ne sont pas tous tranchés : écrire ce mode avant de les
> avoir mesurés, c'est remettre au dépôt du code non éprouvé sur un outil qui
> modifie le modèle.

## 0. Le problème, tel qu'il se pose réellement

Il a **deux entrées** et **une seule sortie**.

**(a) Un objet mal ancré.** Un objet a été créé avec un mauvais niveau de
rattachement — et, avec lui, de mauvaises contraintes de position et de dimension :
niveau bas, niveau haut, élévation par rapport à une référence, décalages. Comment
corriger tout cela **sans rien casser**, et idéalement **en semi-automatique** ?

**(b) Un niveau à supprimer.** Supprimer un niveau emporte ce qui lui est rattaché
— géométrie **et** vues en plan. Il faut donc d'abord **redistribuer** ce qu'il
porte sur d'autres niveaux. Ce qui est exactement le problème (a), appliqué à un
lot d'objets désigné par leur niveau commun.

**(b) = (a) + un audit exhaustif des références + une séquence.** L'outil est un
seul : il déplace l'ancrage. Ce qui change, c'est qui désigne les objets à traiter
et ce qu'il faut vérifier avant de supprimer.

### Ce qu'on déplace n'est pas « le niveau », c'est l'ANCRAGE

Le mot compte, parce qu'il change le périmètre de l'opération. Un objet n'est pas
ancré par un paramètre mais par un **jeu cohérent** :

- un ou deux niveaux (base, sommet — murs, poteaux, escaliers, pièces) ;
- le ou les décalages associés (inférieur, supérieur, élévation par rapport au
  niveau, décalage de milieu) ;
- éventuellement une contrainte de hauteur (« hauteur non connectée » vs
  « jusqu'au niveau ») ;
- pour les réseaux, un niveau de référence qui n'a pas le même rôle qu'un niveau
  de base.

**Règle qui en découle : un ancrage se transforme en entier, ou pas du tout.**
Traiter le niveau bas sans le haut change la hauteur de l'objet ; corriger le
niveau sans le décalage le déplace ; corriger le décalage sans le niveau laisse une
incohérence documentaire. Les trois sont des façons différentes de casser quelque
chose.

*Conséquence pour le mode lecture : le CSV d'audit sort **une ligne par
référence**. Regrouper par `Id` donne la **signature d'ancrage complète** d'un
objet — c'est cette signature, pas une ligne isolée, qui est l'unité de travail.*

## 1. Ce que l'outil fait, en une phrase

Il transporte l'**ancrage** d'un élément d'un jeu de niveaux vers un autre **sans
déplacer l'élément** — et il le prouve, élément par élément, en re-mesurant après
l'écriture.

## 2. Pourquoi une boucle fermée, et pas une table de comportements

Changer le niveau d'un élément à la main le déplace : Revit conserve le
**décalage**, pas l'altitude. On pourrait croire qu'il suffit de connaître,
catégorie par catégorie, ce que Revit conserve — et d'appliquer la compensation
correspondante. C'est une impasse, pour deux raisons.

1. **Les catégories ne se comportent pas pareil** (constat A_049, à confirmer par
   le protocole R16) : les canalisations paraissent conserver l'altitude, les murs,
   poteaux et dalles le décalage.
2. **Aucune table figée ne survivra aux versions.** Une table est une hypothèse
   écrite une fois et jamais rejugée ; c'est exactement la forme d'erreur que la
   maison s'interdit ailleurs.

D'où le principe : **l'outil ne sait rien du comportement de Revit, il le mesure à
chaque élément.**

```
pour chaque ELEMENT (et non pour chaque parametre) :
    z0   <- altitude absolue mesuree                 (avant)
    h0   <- hauteur mesuree, si l'objet en a une     (avant)
    ecrire le nouvel ancrage COMPLET (niveaux base et sommet)
    z1, h1 <- RE-MESURE
    si |z1 - z0| > 0,1 mm : compenser par les decalages, RE-MESURER
    si |z2 - z0| > 0,1 mm  ou  |h2 - h0| > 0,1 mm :
        ANNULER la transaction, inscrire l'element en echec, continuer
```

**Trois points de vigilance.**

- **La mesure d'altitude n'est pas triviale.** `Zmin` de la boîte englobante suffit
  au diagnostic, mais la boîte d'un objet joint ou attaché peut bouger pour
  d'autres raisons que le niveau. **Mesure retenue : le point caractéristique** —
  origine de `LocationPoint`, ou premier point de `LocationCurve` — avec `Zmin` en
  repli, en journalisant laquelle a servi. Le contrôle de cadre de référence
  intégré au bouton d'audit doit être **passé avant toute écriture**.
- **Le paramètre de décalage n'a pas le même nom partout.** L'outil ne les cherche
  pas par nom : il **repère, avant l'écriture, quel paramètre de longueur
  modifiable change quand le niveau change**, en comparant l'état avant/après. Si
  aucun ne change, l'élément part en refus — on ne devine pas.
- **La hauteur est un invariant au même titre que l'altitude.** Elle se mesure et
  se vérifie comme elle.

## 3. La boucle semi-automatique — le CSV est le lieu de l'arbitrage

La forme retenue n'ajoute aucun outil : elle réutilise le CSV d'audit comme
**support d'échange**.

```
1. AUDIT      le bouton "Audit niveaux" produit un CSV, une ligne par reference,
              avec une colonne "Niveau_cible" VIDE
2. PROPOSITION le bouton "Controle zone" remplit "Niveau_cible" pour ce qu'il sait
              trancher (INFRACTION -> niveau admissible le plus proche dans la
              bonne zone) et laisse VIDE ce qu'il ne sait pas (ARBITRAGE, AMBIGU)
3. ARBITRAGE  l'humain ouvre le CSV, relit les propositions, remplit les vides,
              efface ce qu'il refuse. C'est lui qui decide, dans un tableur,
              pas dans une boite de dialogue
4. EXECUTION  le mode ecriture relit le MEME CSV : il ne traite que les lignes
              dont "Niveau_cible" est renseigne, et rien d'autre
5. PREUVE     nouvel audit + comparaison d'identifiants (B15)
```

**Trois propriétés de cette boucle, et c'est pour elles qu'elle est retenue.**

- **Une ligne vide ne fait rien.** L'inaction est l'état par défaut : oublier une
  ligne n'écrit pas, ne déplace pas, ne casse pas.
- **L'arbitrage est relisible et archivable.** Le CSV validé est la trace de ce qui
  a été décidé, et par qui. Une boîte de dialogue ne laisse rien.
- **L'outil ne propose jamais ce qu'il ne sait pas.** `ARBITRAGE` et `AMBIGU`
  sortent vides, par construction — pas de suggestion « au plus probable ».

**Contrainte d'intégrité** : la cohérence d'ancrage se vérifie **avant**
l'exécution. Si un objet à deux niveaux n'a qu'une de ses deux lignes renseignée,
l'objet entier est refusé, avec son motif.

## 4. Ce qui ne peut pas passer — affiché AVANT l'écriture

Décision du 2026-09-10, reprise sans amendement : **aucune annulation silencieuse**.
Un traitement partiel non signalé produit une dette qu'on redécouvre des mois plus
tard sans en connaître l'origine.

| Motif | Origine | Source |
|---|---|---|
| Paramètre de niveau en **lecture seule** | l'élément suit son hôte, il se déplacera tout seul | colonne `Verrou` du CSV — R15 fait 4 |
| **Hébergé par une face** | son ancrage est celui de son hôte | `FamilyInstance.HostFace` |
| **Épinglé** | verrou explicite posé par quelqu'un | `Element.Pinned` |
| **En groupe** | modifier un membre modifie toutes les occurrences | `Element.GroupId` |
| **Attaché / contraint** | murs attachés, contraintes de cotation | à détecter, voir §9 |
| **Possédé par un autre utilisateur** | travail partagé | `WorksharingUtils.GetCheckoutStatus` |
| **Réseau connecté à cibles différentes** | séparerait un réseau | R15 fait 6, voir §5 |
| **Ancrage incomplet** | une seule des deux lignes d'un objet à deux niveaux | §3 |
| **Ambigu / arbitrage** de zone | à moins de 300 mm d'une frontière, ou à cheval | contrôle de zone |
| **Compensation impossible** | aucun paramètre de décalage n'a bougé | mesuré dans la boucle |

**Contrôle arithmétique de complétude**, comme pour B17 :
`planifiés + refusés + verrouillés = total examiné`. Aucun élément ne tombe entre
deux règles. C'est ce contrôle, et non la liste, qui donne confiance au plan.

## 5. Réseaux : en bloc, jamais élément par élément

R15 fait 6, payé une journée sur A_049. Quelques éléments sont à la frontière de
deux réseaux (vanne entre alimentation et retour, té reliant deux systèmes) ; les
séparer de leurs voisins casse la connectivité et Revit refuse par un dialogue
« impossible d'ignorer ».

1. avant d'écrire, l'outil **reconstitue les composantes connexes** (parcours des
   `ConnectorManager` de proche en proche) ;
2. si tous les éléments d'une composante ont la **même cible**, la composante part
   en bloc ;
3. sinon, **toute la composante est refusée**, avec la liste des cibles
   divergentes. Pas de découpe, pas de choix majoritaire.

**Cas mesuré sur A_049** : les 43 éléments de réseau du niveau de travail à
supprimer sont **à cheval sur deux zones**. Le contrôle de zone les sortira donc en
`ARBITRAGE`, et la règle ci-dessus les refusera tant que la cible n'est pas unique.
**C'est le comportement voulu** : ce réseau demande une décision humaine — soit on
le scinde volontairement, soit on l'affecte en entier à une zone.

Rappel R15 fait 5 : une règle MEP se lit sur le **type** de système
(`RBS_PIPING_SYSTEM_TYPE_PARAM`, `RBS_DUCT_SYSTEM_TYPE_PARAM`), jamais sur le nom
d'instance.

## 6. Le cas « fusion de niveaux »

- Le décalage compensé **peut être positif** : le niveau d'accueil peut être sous
  l'élément. Aucune hypothèse de signe.
- **Déplacer un niveau déplace tout ce qu'il héberge** (candidat règle, à vérifier
  au protocole R16). Donc dans une fusion on conserve l'altitude du niveau **le
  plus peuplé** — le peuplement passe avant la fenêtre de coupe — quitte à poser
  une région de plan pour la partie décalée. Le bouton d'audit fournit le
  peuplement.
- **Fenêtre de fusion admissible, asymétrique : −800 / +300 mm.** Pas une valeur
  ronde : elle vient du plan de coupe de la vue en plan (1 200 mm au-dessus du
  niveau), lisible entre ~900 mm (allèges) et ~2 000 mm (linteaux) au-dessus du
  plancher réel. Au-delà, ce n'est plus un niveau, c'est une région de plan.
  **Candidat règle, à éprouver.**
- **Une fusion se fait à l'intérieur d'un bâtiment, jamais entre deux.**

## 7. Séquence de suppression d'un niveau — problème (b)

Un niveau ne se supprime que **vide au sens large**. Vide de géométrie ne suffit
pas : supprimer un niveau supprime aussi les vues en plan qu'il génère.

```
1. auditer TOUTES les references            (bouton "Audit niveaux", niveau en NIVEAUX_CONDAMNES)
2. repeter l'operation sur copie detachee   (jamais le premier essai sur la maquette vivante)
3. redistribuer les elements                (boucle semi-automatique du §3)
4. recreer ou reassocier les vues           (l'audit les a nommees)
5. verifier que l'audit renvoie zero        (meme bouton, meme parametrage)
6. supprimer le niveau
7. prouver par comparaison d'identifiants   (B15 : deux inventaires, comparaison ensembliste)
```

L'étape 7 n'est pas du confort : **un écart entre deux comptages ne prouve rien**
(R15 fait 3). Seule la comparaison par identifiant fait preuve.

## 8. Ergonomie et sécurités — communes à tout outil qui écrit

`SIMULATION = True` en tête de fichier, mode réel demandé explicitement ·
**confirmation nommant la maquette** · icône **orange** (un bundle sans `icon.png`
sort du code couleur) · **transaction unique**, annulation complète si le contrôle
arithmétique échoue · journal horodaté par `forms.save_file`, **jamais un chemin
Bureau/Desktop construit depuis le profil utilisateur** (OneDrive Known Folder
Move, nom localisé) · `ElementId.Value`, et jamais de résolution de propriété
pendant qu'un collecteur itère (R15 faits 7 et 8).

## 9. Ce qui reste ouvert, et qu'il faut mesurer avant d'écrire une ligne

| # | Question | Comment on tranche |
|---|---|---|
| 1 | ~~`Level.Elevation` et la boîte englobante sont-ils dans le même repère ?~~ | **RÉGLÉ le 2026-09-12** — non : c'est `ProjectElevation`. Voir partie 1, §1.1. Contrôle intégré au bouton d'audit |
| 2 | Que conserve Revit, catégorie par catégorie ? | protocole de la fiche **R16** |
| 3 | Comment détecter attachements et contraintes avant l'écriture ? | à chercher : `WallUtils.IsWallJoinAllowed`, catégorie « Contraintes », `Dimension.IsLocked` — **rien de vérifié** |
| 4 | La fenêtre −800 / +300 mm tient-elle en usage réel ? | à éprouver une fois les niveaux fusionnés |
| 5 | Un ancrage à deux niveaux se transforme-t-il en une transaction ? | protocole R16 |
| 6 | Une contrainte « jusqu'au niveau » se comporte-t-elle comme un décalage ? | protocole R16, à ajouter au geste |

**Cinq de ces six points ne sont pas tranchés.** Le point 1 l'est depuis que le
repère est mesuré et non supposé.
