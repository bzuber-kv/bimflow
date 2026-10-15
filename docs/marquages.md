# marquages — reporter un marquage plan photographié

> Outil CPython hors Revit, dans `tools\marquages\`. Il est issu du pilote du
> 2026-10-09 sur les pavés gravés de l'esplanade de The Study. Source de la
> connaissance : bordereau `WORK\dev\bimflow\actions\2026-10-09_CLOTURE_marquages_plans_pilote.md`
> (faits F1 à F11, règles candidates C-MP1 à C-MP6) et son addendum
> `2026-10-09b_ADDENDUM_cloture_marquages_zones_analyse.md`. Ce document
> n'en reprend que ce dont l'outil a besoin.
>
> **Portée : générique, à recadrer.** Le cas d'origine est un dallage de
> modules 300 × 600 mm. Le pas du module et les seuils sont lus dans un
> fichier de paramètres. Une autre surface demande un autre fichier, pas une
> modification du code.

## Ce que fait l'outil

Il part de photos d'un marquage plan posé sur une surface à repère
géométrique connu (pour un dallage, la grille des joints). Il produit :
- une **vue redressée** par marquage, à l'échelle (px/mm) ;
- le **statut de contrôle** de chaque vue ;
- le **regroupement des photos d'un même module** ;
- deux **tables** : une ligne par photo, une ligne par marquage.

Les tables font foi (C-MP4). Revit et Ivion seront alimentés depuis elles,
mais ces deux étapes ne sont pas encore outillées.

| Étape | Commande | Entrée | Sortie |
|---|---|---|---|
| 1. Redresser | `redresser` | photos | `vues\<photo>_pave.jpg`, `redressement.json` |
| 2. Contrôler le cadrage | `controler` | vues redressées | `controle.json` |
| 3. Empreintes | `empreintes` | vues acceptées | `empreintes.json` (toutes les paires) |
| 4. Tables | `tables` | les trois JSON | `photos.csv`, `marquages.csv` |

`chaine` enchaîne les quatre étapes. Chaque étape lit le résultat de la
précédente dans le dossier de travail. Si ce résultat manque, l'étape
s'arrête et nomme l'étape à lancer.

Le classement des supports (pavé, bordure, banc, pilier, muret, vue large),
la lecture des inscriptions et le positionnement ne sont **pas** outillés :
ce sont les étapes 1, 4 et 6 de la chaîne cible du bordereau.

## Installation et usage

```powershell
cd D:\Dropbox\Dev\bimflow\tools\marquages
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe marquages.py chaine -p parametres_dallage_300x600.json -t D:\travail\esplanade D:\photos\esplanade
```

- `-t` : dossier de travail. Il reçoit des **données d'affaire** (photos,
  noms gravés) : on ne le place **jamais** dans le dépôt.
- `--vues` : autre dossier de vues redressées (par défaut `<travail>\vues`).
  C'est lui qui remplace le `rect/` codé en dur du pilote.
- `--debug` (étapes `redresser` et `chaine`) : écrit en plus la vue de
  dessus annotée de chaque photo (rangées en rouge, module retenu en vert).
- Formats lus : JPEG, PNG, TIFF. **Le HEIC n'est pas lu** (Pillow ne le
  décode pas sans greffon) : exporter les photos en JPEG.

`.venv\` et `travail\` sont ignorés par git dans ce dossier.

## Méthode

1. **Redressement** (F1, F2). Les segments de joints (LSD) donnent deux
   points de fuite par RANSAC. Avec la focale, ils donnent l'orientation du
   sol. Une première vue de dessus en est tirée. Le profil des pixels
   sombres y fait apparaître les joints continus, dont l'écart donne le pas
   des rangées. On retient la rangée, puis la case, qui portent le plus de
   petits motifs sombres, au plus près du centre de la photo. Le module est
   ensuite découpé dans la photo **pleine résolution**, sur l'axe des joints,
   à `vue.px_par_mm`.
   - Le rapport longueur / largeur du module sert de contrôle (mode
     « 4 joints », ratio mesuré).
   - Quand il manque un joint de bout, ce rapport sert de repli (mode
     « 1 joint + rapport », ou « centré sur texte »). La vue est alors
     construite et non mesurée : le mode est écrit dans la table.
2. **Échelle** (F3). Une photo seule donne la forme, pas la taille. L'échelle
   vient du pas **relevé sur site**, porté par le fichier de paramètres.
   `px_par_mm_source` donne la résolution de la photo d'origine sur le module
   (F10 : 4,5 à 6 px/mm sur les gros plans du pilote).
3. **Contrôle du cadrage** (F5, C-MP2). Il vérifie trois choses :
   - un joint visible sur au moins `joints_min` côtés ;
   - pas plus de `lettres_coupees_max` traits gravés touchant le bord ;
   - au moins une ligne de texte horizontale lisible, et aucune aux
     capitales plus hautes que `capitale_max_mm`.

   Une vue refusée n'est pas déclarée fausse : elle passe
   **« à valider à la main »**, avec un repli par saisie des 4 coins (non
   outillé).
4. **Empreinte** (F6, F7, C-MP1). Un même texte n'identifie pas un module :
   au pilote, six inscriptions figurent sur 2 à 4 pavés distincts. Deux vues
   montrent le même module si leur **grain** s'apparie. La méthode est
   SIFT, gravure masquée, marge des joints masquée, filtre RANSAC. Toutes les
   paires de vues acceptées sont calculées et rendues, y compris à 0, pour
   qu'on puisse vérifier le trou entre « même » et « différent ».
5. **Tables** (C-MP4). Une ligne par photo : statut `ACCEPTE`,
   `A_VALIDER_A_LA_MAIN`, `ECHEC_REDRESSEMENT` ou `NON_CONTROLE`, avec sa
   raison. Une ligne par marquage : union des paires au-dessus du seuil. Le
   texte et le format ne sont pas lus par l'outil : ils sont écrits `NON_LU`,
   jamais laissés vides.

## Seuils mesurés (pilote, 2026-10-09)

| Paramètre | Valeur | Mesure qui le fonde |
|---|---|---|
| `camera.focale_sur_diagonale` | 0,552661 | F1 : f = 3946 px sur 7140 px de diagonale (iPhone 15 Pro Max, objectif principal), calibrée par les points de fuite ; valeur théorique ~3960 px, 0,4 % d'écart |
| `module.largeur_mm` × `longueur_mm` | 300 × 600 | relevé de Bruno, joints inclus. Rapport mesuré sur 111 pavés : 2,004 ± 0,018 (F2) |
| `vue.px_par_mm` | 2,0 | F10 : largement couvert par la résolution source |
| `controle.contraste_joint_min` | 18 niveaux | F5 |
| `controle.joints_min` | 3 | F5 |
| `controle.lettres_coupees_max` | 1 | F5 |
| `controle.capitale_max_mm` | 42 mm | F5, F8 : capitales des gabarits de 37 / 20 / 13 mm ; au-delà, c'est un zoom |
| `controle.lignes_lisibles` | ≥ 12 mm et 6 lettres, ou ≥ 30 mm et 4 lettres | F5 |
| `empreinte.seuil_meme_pave` | 25 points | F6 : 150 à 440 points pour un même pavé, 10 au plus pour deux pavés différents, sur 5 886 paires, sans cas ambigu |

Bilan du contrôle au pilote (F5) : **16 cadrages faux refusés sur 16**,
aucun faux accepté, et **2 cadrages corrects refusés** (une tache, un pied
de banc).

Les tailles de fenêtres en pixels du contrôle et de l'empreinte (bandes de
bord, flous, dilatation) ont été calées à 2 px/mm. Elles sont mises à
l'échelle si `vue.px_par_mm` change. Ce cas n'a **pas** été éprouvé.

## Limites

**Le redressement automatique réussit dans 85 % des cas** au pilote
(109 / 128, F4). Bruno a relevé trois causes d'erreur :
1. **zoom** : sur un gros plan, l'interligne du texte est pris pour le pas
   des pavés ;
2. **pavé mal orienté** : pavé tourné, ou zone dont l'appareillage change ;
3. **autre support** : bordure, banc, pilier, muret. Le classement des
   supports doit précéder le redressement (C-MP3) ; il n'est pas outillé.

S'y ajoutent les occultations et le choix d'une mauvaise case. Le contrôle
du cadrage est là pour rattraper ces erreurs. Les consignes de prise de vue
(C-MP5) en réduisent le nombre en amont : viser presque à la verticale,
montrer le pavé entier avec ses 4 joints, un seul pavé gravé centré par
photo.

Autres limites connues :
- **La focale est celle d'un appareil.** Une autre caméra, ou un autre
  objectif, demande de recalibrer `focale_sur_diagonale` (F1 : par les deux
  familles de joints d'une photo).
- **Le GPS du téléphone ne place rien** (F9 : 4 à 27 m d'erreur). Il ne sert
  qu'à regrouper.
- **La position n'est pas outillée.** Elle viendra de l'orthophoto (étape 6,
  addendum §1).
- **Noms de personnes** (C-MP6) : ils n'entrent dans aucun document du
  standard. La recherche par nom dans Ivion suppose l'accord du client
  (Loi 25).

## Tests

`tests\test_marquages.py` (sautés si OpenCV est absent). Les jeux d'essai de
`tests\fixtures\marquages\` sont **synthétiques** : grain aléatoire à graine
fixe, texte « KEOVIA TEST », aucune photo ni aucun nom d'affaire.
`synthese.py` les régénère.

| Vue témoin | Attendu |
|---|---|
| `vue_valide_pave.jpg` | contrôle accepté : 4 joints, une ligne de 20 mm |
| `vue_zoom_pave.jpg` | contrôle refusé, raison « zoom » (capitales de 50 mm) |
| `vue_doublon_pave.jpg` | même module que la vue valide, repris sous un autre angle : ≥ 150 points, et ≤ 10 contre la vue zoom |

S'y ajoutent deux tests sur une **photo synthétique en perspective** d'un
dallage à appareil décalé. Le redressement y retrouve le rapport 2:1 à 3 %
près. La chaîne complète, sur deux prises du même module sous deux angles,
en fait un seul marquage.

Ces tests vérifient le code, **pas la méthode** : une image synthétique est
plus propre qu'une photo de granit. Les chiffres qui valent sont ceux du
pilote, sur photos réelles.

## Correspondance avec le code du pilote

| Pilote (`WORK\dev\bimflow\output\marquages_plans_pilote_code\`) | Dépôt |
|---|---|
| `rectify.py` | `redressement.py` |
| `gate.py` | `controle.py` |
| `caps.py` | `capitales.py` |
| `same2.py`, `allpairs.py` | `empreintes.py` |
| *(scripts de tables, non déposés : données d'affaire)* | `tables.py` (refait, sans donnée d'affaire) |
| — | `parametres.py`, `marquages.py` |

Les algorithmes sont repris sans changement de logique. Les écarts au
pilote sont les suivants :
- chemins et constantes de surface lus dans les arguments et le fichier de
  paramètres ;
- les bornes du rapport de module (1,6 à 2,4) sont dérivées du rapport du
  module, soit 0,8 à 1,2 fois ce rapport ;
- une photo à une seule famille de joints est rendue en échec au lieu de
  lever une exception ;
- les sorties sont en français.
