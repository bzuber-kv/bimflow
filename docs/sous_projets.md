# Sous-projets — audit (B13) et migration (B14)

> Repo `bimflow` · extension pyRevit · créé le 2026-09-10
> Portée : **générique** — toute maquette Revit en travail partagé.
> Cas d'origine : affaire **A_049_TheStudy** (étape 0 bis du plan de mise en place
> des maquettes, 50 sous-projets → 35).
> Environnement : Revit 2026, pyRevit 6.5.5, moteur **IPY342** — pas de shebang
> python3, niveau de langage Python 3.4 maximum (pas de f-strings).

---

## Pourquoi ces deux boutons

L'opération « ranger les sous-projets » paraît anodine et ne l'est pas. Le
2026-09-10, sur The Study, une réassignation manuelle de `ZW_Défaut` vers
`Sous-projet 1` a fait passer un comptage de **3593 à 2590 objets** sans qu'aucune
erreur ne soit levée. L'écart n'a été vu que parce qu'un comptage avait été fait
avant. **Rien dans l'interface de Revit ne le signale.**

Ces deux outils existent pour rendre cet écart impossible à manquer.

## B13 — Audit des sous-projets (lecture seule)

Conforme à la discipline du backlog : *tout script qui écrit est précédé d'un
script d'audit en lecture seule sur le même périmètre.*

**Ce qu'il mesure.** Le nombre d'éléments par sous-projet **au niveau du
document**. C'est le point central : une sélection filtrée dans une vue 3D est un
comptage *de vue*, dépendant de la visibilité, des remplacements V/G, de la boîte
de coupe et des sous-projets ouverts. Deux comptages de vue ne sont pas
comparables ; deux comptages de document le sont.

**Ce qu'il rapporte, par sous-projet.**

| Colonne | Ce qu'elle sert |
|---|---|
| Total / Modèle / Spéc. vue | volume réel, et part d'éléments propres à une vue |
| Ouvert | un sous-projet **fermé n'est pas chargé** : il compterait zéro. Le script l'annonce en tête |
| Visible par défaut | explique une sélection vide alors que le sous-projet est plein |
| Supprimable | `Sous-projet 1` et `Vues, niveaux et grilles partagés` répondent NON |
| Autre proprio / Qui | **le test décisif** d'un échec de réassignation en modèle Forma |

Il écrit un **CSV horodaté** sur le Bureau et imprime le **squelette de la table
de correspondance** avec les noms exacts du modèle, à coller dans B14.

**Mode d'emploi.** Ouvrir tous les sous-projets, passer le script sur la
sauvegarde datée, puis sur le modèle courant, comparer la ligne
*TOTAL instances du document*.

## B14 — Migration des sous-projets (table de correspondance)

`SIMULATION = True` par défaut : le script imprime le plan d'exécution et ne
modifie rien.

| Action | Effet | Éléments écrits |
|---|---|---|
| `CREER` | crée un sous-projet absent | 0 |
| `RENOMMER` | renomme sur place | **0** |
| `VIDER` | déplace le contenu de source vers cible | tous |
| `GARDER` | ne fait rien, la ligne sert de trace | 0 |

**Renommer ne touche aucun élément.** C'est la règle de conception de l'outil :
toute correspondance 1 pour 1 passe en `RENOMMER`, donc à coût nul et sans risque
d'échec d'appropriation. Seul `VIDER` écrit sur les éléments — et c'est la seule
action qui peut buter sur un élément possédé par un autre utilisateur. Le script
les compte **avant** d'agir et refuse de le faire silencieusement.

**Optimisation à faire dans chaque affaire** : dans un groupe de fusion, basculer
le **plus gros membre** en `RENOMMER` vers le nom cible et ne `VIDER` que les
autres. Les comptes de B13 donnent le plus gros membre.

### Ce que le script ne fait pas, volontairement

Il **ne supprime aucun sous-projet**. L'API le permet
(`WorksetTable.DeleteWorkset`, transaction ouverte et sous-projet emprunté), mais
on s'en prive : quand un sous-projet est réellement vide, Revit le supprime *sans
poser de question*. S'il propose encore « supprimer les éléments / les
réassigner », c'est qu'il reste quelque chose dedans. **Le dialogue de Revit
devient le contrôle de fin de course** — exactement celui qui manquait le
2026-09-10.

### Sécurités

- arrêt si un sous-projet est fermé ;
- arrêt si un nom de la table n'existe pas dans le modèle (renvoi vers B13) ;
- avertissement pour tout sous-projet du modèle absent de la table ;
- transaction unique, annulation complète en cas d'échec ;
- confirmation explicite avant l'exécution réelle ;
- contrôle final : liste des sous-projets **qui ne sont pas** à zéro.

## Deux sous-projets ne se suppriment jamais

`Sous-projet 1` (Workset1) et `Vues, niveaux et grilles partagés` sont créés par
Revit à l'activation du travail partagé. Autodesk documente que **Workset1 ne peut
pas être supprimé** — seulement renommé. Une recommandation communautaire ancienne
déconseille aussi de le renommer (erreurs *« deletion of non-editable workset »*) ;
statut : **documenté, non mesuré, et contesté** — Autodesk autorise le renommage.

**Position Keovia retenue le 2026-09-10 (option A)** : on ne les supprime pas et
on ne les renomme pas. Ils sont déclarés au BEP comme conteneurs imposés, laissés
vides et jamais actifs. Une liste cible de N sous-projets devient donc, dans les
faits, **N + 1 conteneur imposé**.

*Candidat règle — cas d'origine A_049 : « toute maquette en travail partagé porte
deux sous-projets indestructibles ; le standard doit leur assigner un statut, pas
tenter de les supprimer ».*

## Références

- `bimflow_BACKLOG.md` — B13, B14
- `bimflow_REVIT_FICHES.md` — fiche R13 (à créer)
- `A_049_TheStudy\context\TheStudy_PEP.md` §4.4 — liste cible des 35
- `A_049_TheStudy\actions\2026-09-01_PLAN_mise_en_place_maquettes.md` §3.2, §3.3,
  étape 0 bis — la table de correspondance livrée avec B14 est celle de cette affaire
