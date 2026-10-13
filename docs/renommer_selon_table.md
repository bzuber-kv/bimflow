# Renommer selon table — appliquer une table de correspondance au modèle actif

> Repo `bimflow` · portée : **générique** (standard Keovia) · créé le 2026-10-13
> Bouton : `bimflow.tab\Dev.panel\RenommerSelonTable.pushbutton` — **orange, écrit en mode réel**
> Logique testable : `bimflow.extension\lib\bimflow_correspondance.py` · tests : `tests\test_bimflow_correspondance.py`
> Statut : version `2026-10-13b` **non éprouvée** dans Revit ; la `2026-10-13a` a tué Revit à la lecture (§8.2) ; logique testée sous CPython et pré-simulée hors Revit (§8.1).

## 1. Ce que fait le bouton

Il lit une table de correspondance (CSV), vérifie **chaque ligne contre le
modèle actif**, affiche le plan complet et écrit un **rapport JSON daté à côté
de la table**. Par défaut il s'arrête là : **simulation, aucune transaction**.

Le mode réel est derrière une **case à cocher**, proposée seulement quand
**aucune ligne n'est refusée** ; sur maquette centrale, la confirmation de
`lib\bimflow_maquette.py` (nom du fichier, nombre d'opérations, case « seul
sur la maquette ») s'y ajoute.

Une même table sert **toutes les maquettes d'un projet** : un élément absent
du modèle actif rend sa ligne *sans objet*, jamais refusée.

## 2. La table

UTF-8 (avec ou sans BOM) ou cp1252, séparateur `;`, en-tête exact :

```
categorie;id_revit;ancien_nom;nouveau_nom;parametre;ancienne_valeur;nouvelle_valeur;statut;remarque
```

Seules les lignes au statut **`validé`** s'appliquent ; les autres sont *sans
objet*.

| `categorie` | Élément | `parametre` admis | Effet |
|---|---|---|---|
| `niveau` | `Level` | vide, `REF_Batiment`, `REF_Etage` | nom ; paramètre à `nouvelle_valeur` |
| `quadrillage` | `Grid` | vide ou `type` | nom ; type du quadrillage porté à `nouvelle_valeur` (§4) |
| `volume` | famille in situ, catégorie Volumes | vide, ou `REF_Batiment / REF_Etage` (liste `/`) | nom de famille ; `REF_Zone`, `REF_Etage`, `REF_Batiment` **recalculés du nouveau nom** |
| `zone …` | aucun | — | table de référence : contrôle des volumes, toujours *sans objet* |

## 3. Contrôle d'entrée — rien n'est approché

Une ligne est **refusée** si :
- l'élément `id_revit` existe mais n'est pas de la catégorie annoncée ;
- il ne porte pas **exactement** `ancien_nom` (casse et blancs compris) ;
- le paramètre nommé ne vaut pas exactement `ancienne_valeur`, est absent ou
  en lecture seule ;
- `nouveau_nom` est vide ou contient un caractère refusé par Revit
  (`\ : { } [ ] | ; < > ? `` ` `` ~`) ;
- le même id apparaît deux fois ;
- volume : le nouveau nom est hors motif (`bimflow_noms.lire`), porte une clé de
  bâtiment (`JU`, `MI`, `SC`, `SE` — règle caduque depuis le 2026-10-13), ou ce
  que la table annonce (`nouvelle_valeur`) diffère de ce que le nouveau nom
  donne ; la zone diffère de celle de la table des zones ;
- un nom final heurte un nom existant non renommé, ou un nom temporaire
  `TMP_<id>` est déjà pris (vérifié avant toute transaction).

Une seule ligne refusée suffit à **retirer le mode réel** : l'écriture est
tout ou rien.

## 4. Règles d'écriture

- **`REF_Batiment` d'un volume** = préfixe de sa zone (secteur de la
  colonne). La clé de fin de nom ne garde que `sup` et `mez`.
- **`REF_Id`** n'est jamais écrit, **sauf** sur une ligne de volume dont la
  `remarque` le demande (« REF_Id à régénérer ») **et** dont la valeur
  actuelle est portée par au moins un autre volume du modèle — un doublon
  **mesuré**. Nouvel identifiant : `Guid.NewGuid()` (UUID v4).
- **Types de quadrillage.** Les cibles demandées par les quadrillages d'un
  type : une seule → le type est renommé ; plusieurs → les quadrillages dont
  la cible est le nom final d'un autre type **changent de type**, et le type
  est renommé vers la cible restante s'il n'en reste qu'une. Deux types vers
  le même nom, ou plusieurs cibles sans porteur : refus. Un type renommé qui
  porte des quadrillages hors table est signalé.
- **Vues** : renommées seulement si leur nom contient un ancien nom de niveau
  **renommé**, borné par un caractère non alphanumérique (`Plan SC_N00`,
  `SC_N01_Coupe` oui ; `XSC_N00` non). Deux occurrences qui se chevauchent :
  refus. **Gabarits** signalés, jamais renommés. Rien d'autre n'est déduit d'un
  nom de vue.
- **Copier/Contrôler** : toute relation sur un niveau ou un quadrillage de la
  table est **signalée**, jamais modifiée.
- **Deux passes dans un `TransactionGroup`** : passe 1, chaque élément renommé
  prend `TMP_<id>` (sans tilde, R19 fait 2) ; passe 2, noms finaux, changements
  de type et paramètres. Un échec annule les deux passes.
- Aucun `script.exit()` : le corps est une fonction, les sorties sont des
  `return` (R19 fait 1).

## 5. Rapport

Écran : comptes par catégorie (appliquées / refusées / sans objet), lignes
refusées avec motif, avertissements, plan, **ordre d'application conseillé**.

JSON : `<table>_rapport_<modèle>_<AAAA-MM-JJ_HHMM>_<simulation|reel>.json`,
dans le dossier de la table, jamais écrasé (`_2`…), écrit atomiquement. Une
simulation et une écriture ne portent jamais le même nom (R19 fait 6,
corollaire). Rubriques : `en_tete`, `ordre_conseille`, `comptes`,
`operations_prevues`, `ecriture` (`null` en simulation), `avertissements`,
`refusees`, `appliquees`, `sans_objet`.

## 6. Ordre d'application conseillé

1. la maquette qui porte les quadrillages : niveaux, quadrillages, types ;
2. la maquette qui porte les volumes : niveaux, volumes ;
3. les autres maquettes du projet : niveaux et vues seulement.

Entre deux maquettes : synchroniser, puis **photo maquette** relancée — c'est
elle qui vérifie, pas le rapport du bouton.

## 7. Limites connues

- **Sous-projets fermés** : annoncés en tête ; leurs éléments manquent et
  sortent *sans objet* à tort.
- **Unicité des noms de vue** comparée à toutes les vues : plus strict que
  Revit.
- **Emprunt** sur maquette centrale : non mesuré pour niveaux, quadrillages et
  vues (mesuré pour les familles in situ, R19 fait 5).
- **Copier/Contrôler depuis une autre maquette** : seul ce que le modèle actif
  surveille est vu ; qu'une autre maquette surveille ces niveaux ne se voit
  pas d'ici.

## 8. Recette

### 8.1 Pré-simulation hors Revit — 2026-10-13

Logique rejouée sous CPython sur deux photos maquette (`2026-10-13b`) ;
approximations : aucune vue, volumes supposés in situ, paramètres supposés
écrivables, aucune relation Copier/Contrôler. *Spécifique The Study* pour les
comptes (table de 369 lignes de données).

| Photo | Niveaux | Quadrillages | Types | Volumes | Zones | Refus |
|---|---|---|---|---|---|---|
| `thestudy_G_AN` 01:15 | 23 appliquées | 73 appliquées | 5 renommés, 1 changement de type | 217 sans objet | 56 sans objet | 0 |
| `thestudy_G_VL` 01:18 | 23 appliquées | 73 sans objet | — | 215 appliquées, 2 sans objet | 56 sans objet | 0 |

`REF_Id` : une seule régénération prévue, le volume en doublon (§4).

### 8.2 2026-10-13, 09:59–10:03 — version `2026-10-13a`, copies détachées `thestudy_G_AN` et `thestudy_G_VL`

Journal Revit et minidump du rapport d'erreur (CER) :
- deux lancements arrêtés à la boîte de choix du CSV (annulation de Bruno) :
  rien lu, rien écrit, aucun rapport — conforme ;
- troisième lancement, sur `thestudy_G_AN_détaché` : **Revit tué** environ 25 s
  après le clic, sans message. Aucune transaction n'était ouverte : la phase de
  lecture était en cours. Cause : 56 exceptions attrapées en série dans une
  même boucle (`docs\ecrire_dans_revit.md` §8). Motif de la version
  `2026-10-13b`.

### 8.3 Simulation de la version `2026-10-13b`

À faire.

## 9. Historique des versions

| Version | Date | Contenu |
|---|---|---|
| `2026-10-13a` | 2026-10-13 | Première version. Tue Revit à la lecture d'une table à lignes `zone` (§8.2). |
| `2026-10-13b` | 2026-10-13 | Plus aucune exception attrapée dans une boucle : ids lus par `id_entier()`, qui ne lève rien ; lectures de famille et de paramètre dans des fonctions à part ; test qui l'impose. |
