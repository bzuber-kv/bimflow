# Recalage global — mode d'emploi et protocole de test

> Version : 2026-08-27 · Statut : **écrit, non exécuté sur Revit**
> Bouton : `bimflow` ▸ Géoréférencement ▸ Recalage global
> Source : `bimflow.extension/bimflow.tab/Georeferencement.panel/RecalageGlobal.pushbutton/script.py`

---

## 1. Ce que fait l'outil, et ce qu'il ne fait pas

**Il fait** : déplacer la géométrie du modèle d'un vecteur `(dX, dY, dZ)` exprimé
en mm dans les axes du projet — donc relativement à l'origine interne, qui reste
fixe.

**Il ne fait pas** : redéfinir le système de coordonnées partagées. Les trois
repères (origine interne, point de base, point topographique) sont explicitement
exclus du déplacement. Le recalage décale la géométrie **sous** les repères.

Pour redéfinir le système partagé — c'est-à-dire déclarer que tel point du
modèle porte telles coordonnées réelles — utiliser « Spécifier les coordonnées
en un point » (R09 §2 et §3, étape 2). Les deux opérations sont distinctes et
ne se substituent pas l'une à l'autre.

| Besoin | Outil |
|---|---|
| La géométrie est au mauvais endroit dans le fichier | **Recalage global** (cet outil) |
| La géométrie est bien placée mais mal géoréférencée | « Spécifier les coordonnées en un point » |
| Le zéro de travail doit changer sans que rien ne bouge | Déverrouiller et déplacer le point de base |

---

## 2. Le principe de sécurité central

Le risque de cette opération est le **double déplacement des éléments hébergés** :
si l'on déplace le mur puis, séparément, la fenêtre qu'il porte, la fenêtre part
de deux fois le vecteur. Le même piège existe entre un niveau et les éléments qui
lui sont associés en altitude, et entre un groupe et ses membres.

La parade est structurelle, pas défensive :

- **Une seule transaction**, et **un seul appel `ElementTransformUtils.MoveElements`**
  par groupe d'option de conception — un appel unique dans le cas courant, sans
  options. Jamais d'itération élément par élément.
- Revit traite l'appel en bloc comme **une transformation rigide unique** : il
  calcule les positions finales à partir des positions initiales, puis régénère
  une seule fois. Les relations hôte/hébergé et niveau/altitude sont recalculées
  après coup, pas appliquées en cascade.
- Les **membres de groupe et d'assemblage sont exclus** du lot : c'est le groupe
  (ou l'assemblage) qui est déplacé, une fois. Sur groupes imbriqués, seul le
  groupe le plus extérieur a un `GroupId` invalide et entre donc dans le lot.

Corollaire : **ne jamais modifier le script pour boucler sur les éléments**, même
pour « mieux gérer les erreurs ». Si `MoveElements` refuse le lot, la transaction
est annulée et un diagnostic par bisection nomme les fautifs (§6).

### Pourquoi le périmètre n'est pas la sélection

Le lot est constitué par `FilteredElementCollector` sur tout le document, jamais
par `revit.get_selection()`. **La sélection Revit dépend de la vue active** :
« tout sélectionner » ne prend que ce qui y est visible. Ce qui est masqué,
filtré, hors zone de rognage, dans une option de conception non affichée, ou
simplement dans une vue non ouverte, n'entre pas dans la sélection — et rien ne
le signale.

Le mode de défaillance est le pire possible ici : un modèle recalé à 97 % passe
le contrôle sur trois points connus, puisque les trois points, eux, ont bougé.

Règle générale pour ce repo : tout script dont l'énoncé porte sur « tout le
modèle » collecte par `FilteredElementCollector`. `get_selection()` est réservé
aux outils où la portée est un choix délibéré de l'utilisateur.

---

## 3. Règles d'exclusion

Appliquées dans cet ordre, premier motif rencontré retenu :

| Code | Exclusion | Raison |
|---|---|---|
| `REPERE` | `DB.BasePoint`, `DB.InternalOrigin` | Le recalage décale la géométrie sous les repères |
| `VUE` | `DB.View` (couvre `ViewSheet`) | Une vue n'a pas de position dans le modèle |
| `VIEWPORT` | `DB.Viewport` | Position sur la feuille, pas dans le modèle |
| `ANNOTATION_DE_VUE` | `element.ViewSpecific` | Voir la réserve ci-dessous |
| `MEMBRE_DE_GROUPE` | `GroupId` valide | Le groupe est déplacé une fois |
| `MEMBRE_D_ASSEMBLAGE` | `AssemblyInstanceId` valide | Idem |
| `SANS_CATEGORIE` | `Category is None` | Objets internes au fichier |
| `CATEGORIE_EXCLUE` | Liste `CATEGORIES_EXCLUES` | Doublon de sécurité sur les repères, lignes d'esquisse, caméras |
| `CLASSE_EXCLUE` | Liste `CLASSES_EXCLUES_SUPPLEMENTAIRES` | Échappatoire alimentée par le diagnostic (§6) |

**Réserve sur `ANNOTATION_DE_VUE`.** Les éléments propres à une vue — cotes,
étiquettes, textes, lignes de détail — sont exclus, pour deux raisons : un appel
`MoveElements` ne peut pas mélanger éléments de modèle et éléments de vue, et les
étiquettes suivent leur hôte sans intervention.

**Le critère qui décide n'est pas le type d'annotation, mais l'attache**
(observation Bruno, 2026-08-27). Une annotation suit si et seulement si ses
références bougent :

| Cas | Comportement attendu | Statut |
|---|---|---|
| Cote dont les lignes d'attache pointent des objets déplacés | suit, **valeur inchangée** | hypothèse |
| Cote entre un objet déplacé et un repère (point de base, origine) | suit, **valeur modifiée du vecteur** | hypothèse — c'est le comportement *correct* : la géométrie a réellement bougé par rapport au repère |
| Cote attachée à un gabarit écarté du lot | s'étire, valeur faussée | hypothèse — à surveiller |
| Annotation « posée », texte libre, ligne de détail non attachée | **ne suit pas**, reste en arrière | hypothèse |

Deux conséquences pratiques.

**L'exclusion des cotes attachées n'est pas un pis-aller, c'est le comportement
juste.** Les inclure dans le lot serait l'erreur.

**Le troisième cas fournit un contrôle gratuit.** Une cote de coordonnées entre
la géométrie et le point de base doit varier **exactement du vecteur demandé** —
c'est un témoin indépendant, lisible dans le modèle lui-même, qui n'exige aucun
relevé préalable. À l'inverse, une cote linéaire entre deux objets tous deux
déplacés ne bougera pas d'un pouce : elle ne prouve rien. **Choisir le type de
cote en connaissance de cause** au moment des contrôles 7 et 15.

Restent les annotations posées, qui ne suivront pas. Le journal les compte par
catégorie. **À vérifier au test 5** : si le volume est significatif, prévoir une
passe manuelle ou une évolution de l'outil.

**Éléments inclus qui méritent l'œil** :

- **Instances de liens Revit** (`RevitLinkInstance`) — déplacées avec le modèle,
  ce qui préserve la position relative. Correct pour un lien inséré origine à
  origine ; **à revoir si le lien est inséré par emplacement partagé**, cas où le
  déplacer le désaligne du système partagé.
- **Instances d'import CAO** (`ImportInstance`) — mêmes réserves.
- ~~**Nuages de points**~~ — **retirés du lot le 2026-08-27**, voir §5. Le lien
  est à recréer après le recalage.
- **Pièces et surfaces** — leur point de localisation est déplacé ; les limites se
  recalculent depuis les murs.

---

## 4. Dépinglage et repinglage

Les éléments épinglés du lot sont dépinglés, déplacés, puis repinglés — **dans la
même transaction**. Si la transaction échoue, l'annulation restaure aussi l'état
d'épinglage. Le journal donne le compte.

Les épinglages ne survivent pas si un élément échoue au repinglage (élément
supprimé entre-temps, droits d'accès en modèle collaboratif) ; le compte de
repinglés dans le journal se compare alors au compte de dépinglés.

---

## 5. Protocole de test — à exécuter avant tout usage en production

> ## ⚠ Lire d'abord le §5 ter — conclusion opérationnelle
>
> **Ne jamais appliquer sans avoir passé le mode « Essai de stratégies ».**
> Sur un modèle contenant des objets à géométrie redéfinie, le recalage détruit
> des éléments. L'essai les **nomme à l'avance**, sans rien modifier : c'est lui
> qui rend la décision possible.

> **Statut au 2026-08-27, 14h55 : trois simulations passées, aucune application.**
> Le bouton se charge et s'exécute sous IPY342 sur `test_bz_Keovia.rvt`
> (20 966 éléments). Les passes A, B et C donnent des comptes **identiques** —
> 8 922 déplacés, 12 044 exclus, un seul groupe d'options — ce qui est le
> résultat attendu, le tri ne dépendant pas du vecteur. Les trois repères sont
> exclus nominativement.
>
> **Tout ce qui touche au déplacement lui-même reste non mesuré :** rien n'a
> encore été appliqué.

### Ce que la première simulation a révélé — et pourquoi ne pas appliquer en l'état

La table des exclusions s'est révélée saine ; c'est la table des **déplacés** qui
posait problème. Le lot de 8 922 embarquait de l'ordre de **1 600 éléments sans
géométrie** — Matériaux (387), Composants de légende (498), Systèmes de
canalisation (154), paramètres et nomenclatures — soit près de **20 %**.

`MoveElements` les aurait très probablement refusés, et comme l'appel est unique,
tout échouait. Pire, le diagnostic par bisection était hors d'échelle : il coûte
environ `k × log₂(n/k)` sondes, soit ~4 000 pour 1 600 fautifs parmi 8 922, contre
un plafond de 250. Il aurait rendu ~6 % des coupables après une longue attente.

**Le défaut était de conception.** Le tri procédait par liste **noire** — on
écarte ce qu'on a pensé à écarter — et chaque catégorie oubliée est un trou.
D'où le **filtre d'emprise** (`FILTRE_EMPRISE_ACTIF`), qui inverse en liste
**blanche** : n'est déplacé qu'un élément ayant une étendue réelle dans le modèle
(`get_BoundingBox(None)`).

Deux précautions dans son écriture :

- **Le test porte sur l'emprise, pas sur `Location`.** Les sols, toits et
  plafonds n'ont souvent pas de `Location` mais ont bien une emprise : un filtre
  sur la localisation les aurait écartés à tort.
- **Les gabarits en sont exemptés** (`CLASSES_DATUMS`). Un niveau est infini en
  plan, un quadrillage en élévation ; rien ne garantit qu'ils aient une emprise,
  et les perdre rendrait tout recalage en Z faux. Le journal **mesure** si cette
  exemption a servi, en comptant les gabarits dépourvus d'emprise.

### Résultat du filtre — **mesuré**, simulation du 2026-08-27 16:05

| Indicateur | Avant | Après |
|---|---|---|
| Éléments déplacés | 8 922 | **6 345** |
| Éléments exclus | 12 044 | 14 621 |
| Écartés en `SANS_EMPRISE` | — | **2 577** (29 % du lot d'origine) |

**Les gabarits n'ont pas d'emprise : 180 sauvés par l'exemption.** Sur les 186
niveaux, quadrillages et plans de référence du modèle, **180 ne possèdent aucune
emprise au sens de l'API**. Sans `CLASSES_DATUMS`, le filtre les aurait tous
écartés en silence et **toute la passe B aurait été fausse** — un recalage
altimétrique laissant les niveaux en arrière. La précaution passe du statut
« hypothèse » à « nécessité mesurée ».

**Les fuites de `ViewSpecific` sont colmatées.** Les 343 « Cotes automatiques de
l'esquisse » sont rattrapées, ainsi que les trois anomalies signalées : les 64
« Vues » qui n'étaient pas des `DB.View`, les 3 « Cotes » et les 3 « Élévations ».

### Deux réserves ouvertes avant toute application

**1. ~~Treize nuages de points écartés sur trente-neuf.~~ Tranché — les nuages
sont désormais TOUS exclus.** La simulation avait révélé un partage arbitraire :
26 nuages dans le lot, 13 écartés faute d'emprise. Décision Bruno du
2026-08-27 : les exclure entièrement.

*Motif métier* — un recalage global invalide de toute façon les liens de nuages.
La pratique est de les recréer après coup, et un nuage recalé en amont n'est
généralement plus valide. Les déplacer serait du travail perdu.

*Exigence attachée à la décision* — **le dire clairement**. Un nuage laissé en
arrière sans avertissement serait un piège : l'opérateur croirait son modèle
complet. Le message remonte donc à quatre endroits, du plus tardif au plus
précoce :

| Où | Quand l'opérateur le voit |
|---|---|
| Infobulle du bouton | avant même de cliquer |
| Rapport de simulation | avant de décider d'appliquer |
| **Boîte de confirmation** | juste avant le point de non-retour |
| Rapport final + journal | avec la mention « Action requise après ce recalage » |

Le motif d'exclusion est `NUAGE_DE_POINTS`, distinct de `SANS_EMPRISE`, et placé
tôt dans l'ordre des tests : un nuage déchargé doit être journalisé sous le motif
**métier** qui appelle une action, pas sous le motif technique qui l'expliquerait.

**2. « Ligne d'axe » : 2 540 éléments, soit 40 % du lot, non identifiés.** Si ce
sont les axes des canalisations et gaines, ce sont des **sous-éléments**, et les
déplacer avec leur hôte reproduirait le double déplacement que l'outil évite
pour les groupes. La colonne « Classes .NET », ajoutée au rapport, tranchera à
la prochaine simulation.

Restent au lot des familles parent/enfant du même genre, à surveiller :
escaliers (4) avec volées (5), paliers (1) et esquisses (68) ; garde-corps (6)
avec barreaux (31) et traverses (6) ; canalisations avec leurs isolations (5).

### Préparation

1. Ouvrir un modèle représentatif — de préférence **The Study**, qui porte
   des liens, un nuage, des groupes et des annotations.
2. **Enregistrer sous, en copie détachée** (`Détacher du central` si collaboratif).
   Le script refuse de continuer sur un modèle collaboratif non détaché sans
   confirmation explicite.
3. Repérer **trois points connus** bien répartis en plan et en altitude — angles
   de bâtiment, tête de poteau, arase de dalle. Y poser une **cote de coordonnées**
   (onglet Annoter, pas une cote d'élévation) et **relever les trois triplets**.
   C'est le contrôle qui fait foi (R09 §3, étape 3).
4. Relever la position et l'angle de l'origine interne (R09 §8) — ils ne doivent
   pas bouger.

### Exécution

> **Ordre des vecteurs d'essai — ne pas mélanger deux inconnues.** Le
> comportement des niveaux en `dZ` est un **point ouvert** (n° 1 ci-dessous) :
> on ignore si un élément hébergé suit son niveau *en plus* d'être déplacé.
> Lancer d'emblée un vecteur à `dZ ≠ 0` mêle deux questions — « l'outil
> fonctionne-t-il ? » et « le Z double-t-il ? » — et un écart constaté ne
> permettrait de trancher ni l'une ni l'autre. D'où la séquence :
>
> | Passe | Vecteur | Ce qu'elle isole |
> |---|---|---|
> | **A** | `1000 ; -2500 ; 0` | le fonctionnement en plan, sans les niveaux |
> | **B** | `0 ; 0 ; 150` | le seul comportement altimétrique, niveaux compris |
> | **C** | `1000 ; -2500 ; 150` | la combinaison, une fois A et B compris |
>
> **Le sondage (§5 bis) se relance à chaque passe.** Son résultat ne vaut que
> pour le vecteur sondé : une passe A verte ne dit rien de la passe B.
>
> Passer les contrôles 7 à 16 après **chaque** passe. La passe B est celle qui
> répond au point ouvert n° 1 ; c'est elle qu'il faut documenter le plus
> soigneusement.

5. Lancer le bouton en **Simulation seule** avec le vecteur de la passe en cours
   (commencer par la passe A ci-dessus). Lire le rapport :
   - le total d'éléments déplacés est-il plausible ?
   - **les comptes d'exclusion `ANNOTATION_DE_VUE`** — combien de textes et de
     lignes de détail vont rester en arrière ?
   - y a-t-il des exclusions `SANS_CATEGORIE` en volume anormal ?
   - le nombre de groupes d'options de conception est-il celui attendu ?
6. Relancer en **Simuler puis appliquer**, même vecteur.

### Contrôles

7. **Cote de coordonnées sur les trois points connus.** Chaque triplet doit avoir
   varié exactement du vecteur demandé. Un écart non nul invalide tout le reste.
8. **Contrôle automatique** intégré : le script échantillonne **un témoin par
   catégorie**, jusqu'à huit catégories distinctes, et compare leur déplacement
   au vecteur à 0,01 mm près.

   Deux choix de conception, tous deux dictés par le risque de double
   déplacement (renforcés le 2026-08-27, avant la première application) :

   - **La diversité prime sur le nombre.** Prendre les huit premiers venus les
     concentrerait sur « Ligne d'axe », 40 % du lot, et le contrôle passerait à
     côté d'un défaut ne frappant qu'une autre famille.
   - **`LocationCurve` autant que `LocationPoint`.** Sans cela le contrôle serait
     aveugle aux **murs** — précisément les éléments hébergés par un niveau,
     donc les premiers concernés par un double déplacement en Z. Le point de
     référence est l'origine de la courbe.

   Reste complémentaire, pas substitutif : il compare des points de localisation,
   pas la géométrie construite. Il ne voit ni les niveaux ni les gabarits, qui
   n'ont pas de `Location`.
9. **Origine interne** : position et angle inchangés (R09 §8).
10. **Repères** : point de base et point topographique n'ont pas bougé — donc les
    coordonnées partagées de la géométrie ont changé du vecteur. C'est le
    comportement voulu.
11. **Hébergés** : ouvrir une élévation, vérifier qu'aucune fenêtre ni porte n'a
    quitté son mur. C'est le test du double déplacement.
11 bis. **Les quatre suspects nommés par le sondage du 2026-08-27.** L'API accepte
    le lot, donc rien ne signalera une erreur : ces contrôles sont le seul filet.
    Le décalage recherché vaut **exactement le vecteur demandé** — donc très
    visible en vue en plan.
    - **« Ligne d'axe » (2 540)** — les axes coïncident-ils toujours avec leurs
      canalisations ? C'est le contrôle prioritaire : 40 % du lot, nature encore
      non identifiée.
    - **Escaliers** — volées et paliers toujours solidaires de l'escalier ?
    - **Garde-corps** — barreaux et lisses toujours alignés ?
    - **Isolations** — toujours sur leur canalisation ou leur gaine ?
11 ter. **Épinglage** : les 89 éléments épinglés avant l'opération le sont-ils
    toujours après ? Le script les dépingle puis les repingle dans la même
    transaction ; le rapport annonce le nombre repinglé.
12. **Niveaux** : les altitudes de niveau ont-elles bougé de `dZ` ? Les éléments
    associés sont-ils restés à leur offset ? Deux réponses possibles, toutes deux
    à documenter — voir le point ouvert n° 1 ci-dessous.
13. **Groupes** : les membres ont-ils bougé du vecteur, et non du double ?
14. **Liens et nuages** : position relative préservée ?
15. **Annotations** : les étiquettes ont-elles suivi ? Les textes libres sont-ils
    restés en arrière, comme annoncé ?
16. Relire le **journal Markdown** écrit à côté du modèle.

---

## 5 bis. Le sondage — savoir avant d'appliquer

Troisième mode au menu : **« Simulation + sondage »**. Il prédit le comportement
de `MoveElements` **sans rien appliquer** — chaque sonde annulée en
sous-transaction, transaction englobante annulée aussi.

### La règle qui gouverne sa conception : ne jamais rompre le contexte

> **Une fenêtre déplacée sans son mur quitte son hôte : Revit la refuse.** Or
> dans le lot complet, le mur bouge aussi et l'ensemble passe sans difficulté.
> Sonder une catégorie **isolée** fabrique donc des faux refus et désigne des
> coupables innocents. Vaut pour tout élément hébergé ou attaché : fenêtres,
> portes, ouvertures, isolations, garde-corps.
>
> *Réserve soulevée par Bruno, 2026-08-27 — elle a fait réécrire le sondage
> avant sa première exécution.*

### La seconde règle : un prédicteur doit reproduire l'opération qu'il prédit

> **Premier sondage, 2026-08-27 16:27 — échec instructif.** Le lot complet est
> refusé : `Unable to move element(s) due to at least one of them being pinned`.
> Or l'opération réelle **dépingle** avant de déplacer ; le sondage, lui, ne le
> faisait pas. Il testait donc une opération qui n'existe pas, et rapportait un
> obstacle que l'application n'aurait jamais rencontré.
>
> Corrigé : le sondage dépingle d'abord, exactement comme l'opération réelle, et
> le retour arrière repingle tout. Le nombre d'éléments dépinglés est rapporté —
> c'est en soi une mesure utile sur le modèle.

Effet de bord notable : comme les éléments épinglés se répartissent sur
plusieurs catégories, aucun retrait unique ne les enlevait tous. Le sondage a
donc rapporté « plusieurs causes indépendantes » — ce qui était **exact** et
préférable à la désignation d'un innocent, mais dont la cause réelle était en
amont, dans la fidélité du test.

D'où une méthode en deux temps :

1. **Le lot complet**, groupe par groupe. C'est la seule question qui compte :
   s'il passe, il n'y a rien à diagnostiquer.
2. **Seulement s'il échoue** : retrait d'**une** catégorie à la fois, le reste du
   lot intact (*leave-one-out*). Si le lot passe une fois la catégorie C retirée,
   C est **impliquée**.

Le mot « impliquée » est choisi : le test dit que retirer cette catégorie
débloque le lot, pas qu'elle est seule en cause.

**Limite assumée.** Si plusieurs causes indépendantes coexistent, aucun retrait
unique ne suffit et l'étape 2 ne désigne rien. Le cas est **détecté et rapporté
comme tel**, plutôt que passé sous silence — il appellera une reconstitution du
lot par ajouts successifs.

### Conséquence sur la bisection du §6

La même réserve la frappe : ses sous-lots séparent tout autant les hôtes de leurs
hébergés. Ce qu'elle nomme, ce sont les éléments qui ne bougent pas **seuls**, ce
qui n'est pas la même chose que ceux qui **bloquent le lot**. Son rapport porte
désormais cet avertissement. Elle ne garde d'utilité qu'en dernier recours, à
l'intérieur d'une catégorie déjà identifiée comme impliquée.

Le rapport propose enfin des **échantillons cliquables** pour chaque catégorie
impliquée : cliquer l'identifiant sélectionne l'élément dans Revit. C'est le
moyen le plus court d'identifier une catégorie dont la classe .NET ne dit rien —
« `Element` » nu, comme les 2 540 « Ligne d'axe ».

### Résultat — **mesuré**, sondage du 2026-08-27 16:30

> **Portée : passe A uniquement — `1000 ; -2500 ; 0`.**
> Un résultat de sondage ne vaut **que pour le vecteur sondé**. Le cas `dZ = 0`
> est le plus trompeur : un niveau étant infini en plan, un déplacement
> horizontal ne lui demande rien, et le lot passe **sans que le comportement
> altimétrique ait été éprouvé** — or c'est le seul qui pose question pour les
> gabarits. Le point ouvert n° 1 reste donc entier.
>
> *Réserve soulevée par Bruno, 2026-08-27. Le rapport et le journal portent
> désormais cette mention automatiquement, pour qu'aucun résultat ne puisse être
> relu détaché de son vecteur.*

**Pour ce vecteur, le lot complet est accepté.** Après dépinglage de
**89 éléments**, `MoveElements` accepte les 6 319 éléments en un seul appel.
Aucune catégorie refusée.

**Matrice complète — les trois formes de vecteur passent l'API** :

| Passe | Vecteur sondé | Résultat | Réserve de portée |
|---|---|---|---|
| A | `1000 ; -2500 ; 0` | accepté | affichée (Z non éprouvé) |
| B | `0 ; 0 ; 1500` | accepté | affichée (plan non éprouvé) |
| C | `10000 ; 25000 ; -10000` | accepté | **aucune** — les deux composantes sollicitées |

La passe C éprouve en prime un `dZ` **négatif** et des amplitudes d'un autre
ordre de grandeur. **La question de l'acceptation par l'API est close** : plus
aucun sondage n'apportera d'information. Tout ce qui reste relève de la justesse
géométrique, et seule l'application permet de la mesurer.

> ### Repartir d'un état propre entre chaque passe
>
> Les déplacements se **cumulent**. Appliquer A puis B sur le même fichier
> mesure `A + B`, pas `B`, et rend tous les contrôles ininterprétables. Entre
> deux passes : **Ctrl+Z**, ou rechargement du fichier. Vérifier le retour à
> l'état initial sur un point connu avant de relancer.

Deux enseignements :

- Les éléments **dépendants** — `StairsRun`, `StairsLanding`, `TopRail`,
  `PipeInsulation`, `DuctInsulation`, `Opening` — passent sans difficulté dans le
  lot complet. Ils n'auraient échoué qu'isolés. **La réserve sur le sondage par
  catégorie isolée est donc confirmée par la mesure** : elle aurait fabriqué une
  demi-douzaine de faux coupables.
- Le seul obstacle réel était l'épinglage, que l'outil traitait déjà.

> ### ⚠️ Ce que cette acceptation ne dit PAS
>
> `MoveElements` accepte le lot : cela établit que l'opération **ne plantera
> pas**. Cela n'établit **en rien** que le résultat sera *juste*.
>
> Le risque a changé de nature, et il a empiré. On ne redoute plus un échec
> propre avec transaction annulée et modèle intact ; on redoute désormais une
> **corruption silencieuse** qu'aucun message d'erreur ne signalera :
>
> | Risque non levé | Ce qu'on verrait |
> |---|---|
> | Double déplacement des 2 540 « Ligne d'axe » | axes décalés du vecteur par rapport à leurs canalisations |
> | Double déplacement des sous-éléments d'escalier | volées ou paliers désolidarisés |
> | Idem garde-corps | barreaux décalés de la lisse |
> | Idem hébergés | fenêtre sortie de son mur |
>
> **Les contrôles géométriques du protocole ne sont donc plus une formalité :
> ils sont devenus le seul filet.**

Face à une catégorie impliquée, deux issues :

- **l'exclure** via `CATEGORIES_EXCLUES`, si elle n'a rien à faire dans un
  recalage ;
- **lui réserver un appel dédié**, si le refus ne porte que sur une composante du
  vecteur. C'est le cas attendu pour les gabarits : un niveau n'a pas de sens en
  déplacement horizontal, mais doit suivre en Z.

---

## 5 ter. CONCLUSION OPÉRATIONNELLE — 2026-08-27

> ### Sur un modèle contenant des objets à géométrie redéfinie, le recalage détruit.
>
> Un recalage de `test_bz_Keovia.rvt` détruit le sol `4188355` — ou n'a pas lieu,
> la transaction étant annulée par sécurité. Aucune des sept stratégies
> éprouvées n'y change quoi que ce soit.
>
> **Ce n'est pas « l'outil ne marche pas ».** C'est : *il détruit des objets
> identifiables, et l'essai de stratégies les nomme AVANT qu'on décide.* La
> nuance est opérationnelle — voir « Deux usages qui restent légitimes ».

### Deux usages qui restent légitimes

**1. Sur un modèle propre, sans objet à géométrie redéfinie.** Le blocage tient
entièrement aux dalles à forme modifiée et aux 456 avertissements préexistants.
Un modèle sain n'a peut-être aucun de ces obstacles. **Non testé** — c'est la
première expérience à mener si le sujet revient. Voie plausible pour une **mise
au propre en début de projet**, quand l'origine n'est pas encore figée par des
mois de travail.

**2. Sur un modèle sale, quand le recalage est critique pour la livraison.**
Là, il n'y a pas le choix : il faut recaler et reconstruire ce qui est détruit.
Et c'est faisable, parce que **l'essai de stratégies fournit la liste nominative
des dégâts avant l'opération**. On ne subit pas la destruction, on la budgète :

> Quatre éléments perdus, dont un sol à forme modifiée à redessiner, plus des
> cotes et des contraintes — contre 437 avertissements sur 456 qui traversent
> intacts.

Décider en connaissance de cause n'est pas la même chose que renoncer. Le mode
**Essai de stratégies** existe précisément pour rendre ce choix possible.

### Les sept stratégies et leurs résultats

Toutes mesurées le 2026-08-27 sur `test_bz_Keovia.rvt`, vecteur
`10000 ; 10000 ; 10000`, 6 756 éléments.

| # | Stratégie | Supprimés | Santé (apparus / disparus / conservés) |
|---|---|---|---|
| 1 | Tel quel | **4** | 11 / 8 / 437 |
| 2 | Après désolidarisation des joints (975) | 6 | 43 / 82 / 363 |
| 3 | Après remise à plat des formes (78 dalles) | 6 | 14 / 10 / 435 |
| 4 | Deux passes, une transaction | **4** | 11 / 8 / 437 |
| 5 | Deux transactions, fragiles en dernier | **4** | 11 / 8 / 437 |
| 6 | Deux transactions, fragiles en premier | **4** | 11 / 8 / 437 |
| 7 | `CopyElements` au lieu de `MoveElements` | — | **refusé par l'API** |

Quatre stratégies laissent le modèle dans un état **rigoureusement identique**.
Les deux qui s'en écartent l'aggravent.

### Ce que chaque piste a appris, et pourquoi elle est close

**La désolidarisation aggrave.** Retirer les jonctions supprime les
avertissements « joints mais ne se croisent pas » et fait apparaître 46
chevauchements de sols et 42 de murs — plus rien ne se découpe. Les erreurs de
géométrie ne baissent que marginalement (7→6, 8→7, 6→5).

**La remise à plat des formes prouve une cause sans fournir un remède.**
Supprimer la donnée de forme fait bien disparaître « Échec de la modification de
la forme de dalle », mais casse ce qui s'y accrochait : cotes 20→32, contraintes
10→22. C'est un instrument de diagnostic, pas une solution.

**Le fractionnement ne change rien, quel que soit l'ordre.** Et la stratégie 5 a
livré le mécanisme : elle lève *« The referenced object is not valid »* en
tentant de déplacer la dalle **en seconde transaction**, parce qu'elle est déjà
détruite. Or elle n'était pas dans le lot de la première.

> **Le sol meurt du mouvement de ses VOISINS, pas du sien.**
> C'est ce qui condamne toute la famille « le traiter à part » : il est détruit
> avant son tour. Et c'est ce qui explique la réussite manuelle — avec la
> commande Déplacer, les voisins ne bougeaient pas.

**La copie n'est pas réfutée, elle n'a pas pu s'exécuter.** `CopyElements`
refuse catégoriquement un lot mêlant membres d'esquisse et autres éléments — ce
que `MoveElements` accepte en silence. Écarter les 1 151 `OST_SketchLines` puis
les 87 courbes d'escalier et de garde-corps n'a pas suffi : il en reste,
probablement parmi les 2 540 « Ligne d'axe » de classe `Element` nue, jamais
identifiées. Reprendre par une copie catégorie par catégorie, pour que Revit
désigne lui-même les fautives.

### Le constat général

**Une fois le projet démarré, déplacer le modèle par rapport à l'origine interne
est quasi impossible.** Ce n'est pas un défaut de cet outil : c'est une limite
de Revit, et elle est documentée par Autodesk.

- *« Revit currently does not support moving or redefining the position of the
  internal origin related to the model elements. »*
- La méthode recommandée est le **lien-puis-liaison** — nouveau fichier, lier
  origine à origine, déplacer le lien, lier. Elle contourne le problème mais
  **ne ramène que la géométrie** : vues, feuilles, nomenclatures et gabarits ne
  suivent pas. Rédhibitoire sur un projet en production.
- Déplacer toute la géométrie est explicitement qualifié de *« risky for large,
  complex projects »*.

Les forums Dynamo rapportent les mêmes messages sur les déplacements massifs.
**Le sujet n'a pas de bonne réponse connue à ce jour.**

### Trois conséquences, actées le 2026-08-27

**1. Le choix à l'ouverture du modèle est déterminant.** C'est le seul moment où
la position de l'origine interne se décide réellement. Après, elle est acquise.
Cette règle doit remonter au plan qualité BIM, pas rester dans la doc d'un outil.

**2. Il faut savoir récupérer les coordonnées relatives des repères.**
L'information existe — l'export **IFC 4** la restitue. Piste à instruire :
identifier où et comment, pour disposer d'un moyen de documenter la position des
repères indépendamment de Revit. *Statut : hypothèse à vérifier.*

**3. Court terme, sur The Study.** Enregistrer soigneusement toutes les données
de repérage au cas où, et **vivre avec une origine interne alignée sur rien** —
ni physique, ni modélisé, simplement laissée où elle est.

### Ce qui reste acquis

L'outil ne fonctionne pas ; le **banc d'essai**, si. Il reproduit fidèlement une
opération destructrice **sans rien détruire**, mesure la santé du modèle avant
et après, et nomme les éléments perdus. Il vaut pour tout script modifiant un
modèle, bien au-delà du recalage — voir §5 bis.

Et le tri fonctionne : sur 456 avertissements, **437 traversent le déplacement
intacts**. Le reste du modèle se déplace correctement. Le blocage est localisé.

---

## 6. Que faire si `MoveElements` refuse le lot

La transaction est annulée : **le modèle est intact**. Le script enchaîne alors
sur une recherche par bisection, en sous-transactions systématiquement annulées,
qui nomme les éléments fautifs (id, catégorie, classe .NET), plafonnée à 250
sondes.

Marche à suivre : ajouter les **noms de classes** rapportés à la constante
`CLASSES_EXCLUES_SUPPLEMENTAIRES`, en tête de `script.py`, puis relancer. Reporter
la trouvaille dans ce document et dans une fiche Rnn.

Suspects connus, non confirmés : `Level` et `Grid`. Ce sont des gabarits
(*datums*) ; un niveau est infini en plan, un quadrillage l'est en élévation, et
`MoveElements` pourrait refuser la composante de vecteur qui n'a pas de sens pour
eux. Ils sont volontairement **laissés dans le lot** : un recalage en Z sans les
niveaux serait faux. Si le refus se confirme, la correction n'est pas de les
exclure mais de leur réserver un appel `MoveElements` dédié, avec la seule
composante utile.

---

## 7. Points ouverts

1. **Niveaux et double déplacement en Z.** Le raisonnement du §2 dit que l'appel
   en bloc traite niveaux et éléments hébergés comme une transformation unique,
   sans cumul. Ce raisonnement est une **hypothèse**, pas une mesure. Le test 12
   la tranche. Si le cumul se produit, la correction est de retirer les niveaux du
   lot et de leur appliquer `dZ` séparément — mais alors les éléments associés
   verraient leur offset changer, ce qui est un autre problème. Ne pas improviser :
   documenter d'abord.

2. **Options de conception.** Un appel `MoveElements` ne peut pas mélanger des
   éléments appartenant à des options différentes ; le script les regroupe donc et
   émet un appel par option, dans la transaction unique. **Non vérifié.** Reste
   ouvert : Revit exige-t-il en plus que l'option soit *active* pour autoriser la
   modification de ses éléments ? Si oui, il faudra activer chaque option à tour de
   rôle, ce qui sort du modèle « une transaction ». Le script avertit l'utilisateur
   et lui demande confirmation dès qu'une option est détectée. **Tester sur un
   modèle porteur d'un jeu d'options avant tout usage.**

3. **Liens et nuages insérés par emplacement partagé.** Les déplacer avec le
   modèle est correct pour une insertion origine à origine, discutable pour une
   insertion par emplacement partagé — qui est la convention Keovia (R09 §4).
   À trancher après le test 14 ; si le comportement est faux, ajouter
   `RevitLinkInstance` et `PointCloudInstance` à une exclusion optionnelle.

4. **Textes et lignes de détail non attachés** — voir la réserve du §3.

5. **Modèle collaboratif.** Le script avertit mais n'empêche pas. Sur un central
   non détaché, les éléments appartenant à d'autres utilisateurs feront échouer
   l'appel. La règle reste : copie détachée.

---

## 8. Journal

Un fichier `recalage_global_<modele>_<AAAAMMJJ_HHMMSS>.md` est écrit à côté du
modèle — ou dans `%TEMP%` si le modèle n'est pas enregistré. Il contient l'entête
d'exécution, les groupes d'options, les comptes par catégorie, le journal des
exclusions par motif et catégorie, le résultat du contrôle automatique et le
résultat final. Il est produit aussi bien en simulation qu'en application et
qu'en échec.

---

## 9. Dérogations aux règles de développement

| Règle | Raison | Date |
|---|---|---|
| §1 shebang `#!/usr/bin/python3` | pyRevit lit la première ligne comme **directive de moteur** : « python3 » y forcerait CPython — or **aucun moteur CPython n'est déployé en netcore**, donc sous Revit 2026 (voir mesure ci-dessous). Le bouton ne se chargerait pas | 2026-08-27 |
| §1 `from __future__ import annotations` | Python 3.7+, hors de portée du niveau de langage 3.4 d'IPY342 | 2026-08-27 |
| §2 annotations de type PEP 604 | Syntaxe Python 3.10+ | 2026-08-27 |
| §2 `pathlib` obligatoire | **À réexaminer** — `pathlib` entre dans la stdlib en Python 3.4, donc vraisemblablement disponible. Motif d'origine caduc ; `os.path` conservé jusqu'à vérification dans Revit | 2026-08-27 |

Le code vise **IronPython 3.4.2**, moteur mesuré (voir ci-dessous) : pas de
f-strings, `io.open` en mode texte unicode, `ElementId.Value` avec repli sur
`IntegerValue` — ce dernier dépendant de la version de Revit, pas du moteur.

### Environnement mesuré — 2026-08-27 (KS101)

Le moteur actif est **IronPython 3.4.2** (`IPY342`), niveau de langage
**Python 3.4**. Preuve la plus directe, le manifeste que Revit lit au
démarrage — `%APPDATA%\Autodesk\Revit\Addins\2026\pyRevit.addin` :

```
...\pyRevit-Master\bin\netcore\engines\IPY342\pyRevitLoader.dll
```

Le moteur est nommé dans le chemin même du DLL. `pyrevit attached` le confirme.

> **Piège de méthode, à ne pas répéter.** `pyrevit clones engines` liste les
> déploiements *disponibles*, et l'un d'eux s'appelle littéralement `DEFAULT`
> (noyau IronPython 2.7.12). Lire ce nom comme « le moteur actif » est une
> erreur : le clone contient `IPY2712PR` **et** `IPY342`, et c'est
> l'**attachement** qui choisit. Seuls `pyrevit attached` et le manifeste
> `.addin` font foi.

Conséquences pour le code :

1. **Interop .NET — la contrainte structurante.** Sous IronPython 3, toute
   méthode de l'API attendant `ICollection` / `IList` / `ISet` refuse une liste
   Python (`TypeError`). IronPython 2 tolérait la coercion implicite ; ce n'est
   plus le cas. D'où `liste_dotnet()`, passage obligatoire de tout appel de ce
   type. Concerne aussi `CopyElements`, `RotateElements`, `doc.Delete`,
   `Selection.SetElementIds`, `NewGroup`.
2. **Aucun moteur CPython sous Revit 2026** : `CPY3123` n'est déployé qu'en
   netfx. Un `#! python3` empêcherait le bouton de se charger.
3. **Les f-strings restent proscrites** — Python 3.6+, hors de portée du niveau
   3.4. Les annotations PEP 604 et `from __future__ import annotations` aussi.
4. **`pathlib` est à réexaminer** : introduite en Python 3.4, elle est
   vraisemblablement disponible. La dérogation §2 qui l'écarte reposait sur
   « absente d'IronPython 2.7 », motif désormais caduc. `os.path` est conservé
   tant que la disponibilité réelle n'est pas vérifiée dans Revit.

Clone : unique, **v6.5.5** en `%APPDATA%\pyRevit-Master`. Le doublon
`C:\Program Files\pyRevit-Master`, qui servait Revit 2024 et 2025 (désinstallés),
a été supprimé le 2026-08-27.
