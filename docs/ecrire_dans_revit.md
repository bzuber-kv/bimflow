# Écrire dans Revit depuis pyRevit — faits mesurés

> Repo `bimflow` · extension pyRevit · créé le 2026-09-24
> Portée : **générique** — tout script pyRevit qui modifie une maquette.
> Environnement : Revit 2026, pyRevit 6.5.5, moteur **IPY342** — pas de shebang
> python3, niveau de langage Python 3.4 maximum (pas de f-strings).

Cette fiche ne porte que des faits **observés sur Revit**, avec la date et le
nombre d'éléments sur lesquels ils l'ont été. Tout ce qui n'est pas mesuré est
étiqueté comme tel. Les fiches R\* de l'affaire (OneDrive) restent la référence
métier ; celle-ci est la référence *outil*.

---

## 1. Aucun `script.exit()` après une écriture

**C'est la règle la plus chère de la journée du 2026-09-24.**

```python
script.exit()          # appelle sys.exit(), donc lève SystemExit
```

Une commande externe Revit qui se termine en levant `SystemExit` **rend
`Result.Cancelled`**. Et Revit, sur une commande qui rend `Cancelled`,
**annule tout ce qu'elle a modifié** — *transactions déjà committées
comprises*. Sans exception. Sans message. Sans trace au journal.

**Ce qui a été mesuré** *(The Study, copie détachée, 202 volumes in situ)* :
le bouton `Renommer volumes` committait 202 renommages, les relisait dans la
foulée — **202 sur 202 au nom voulu** — affichait son rapport, et tout était
revenu à l'ancien nom au clic suivant. La corrélation était parfaite sur six
exécutions : les modes qui sortaient par `script.exit()` voyaient leur
travail défait, ceux qui tombaient en fin de fichier persistaient.

**Ce qui a coûté cher.** Six hypothèses sont mortes avant celle-là — le
document actif (deux maquettes ouvertes), l'élément `Family` remplacé par
l'API, un porteur de nom désynchronisé parmi les huit, le `TransactionGroup`,
la passe de noms temporaires, le travail partagé. Une sonde de diagnostic a
été écrite pour la troisième. Et j'étais à une réponse d'écrire en fiche que
*renommer une famille in situ par l'API ne persiste pas* — ce qui est faux, et
aurait fait renoncer à un outil qui marche.

**La forme correcte.** Après la première écriture, le script laisse la
commande se terminer normalement : il n'y a plus de sortie anticipée, on
descend par des `if`. Les sorties **légitimes** sont celles qui suivent un
`RollBack`, un refus, une annulation par l'utilisateur, un lot vide — là,
rien n'a été écrit, et une annulation par Revit n'enlève rien.

**Contrôle automatique** : `tools\volumes\verifier_sorties_apres_ecriture.py`
signale tout `script.exit()` situé après le premier `Commit()`. C'est une
heuristique de **position**, pas une analyse de flot : elle désigne les
fichiers à relire, le jugement reste humain.

---

## 2. Caractères interdits dans un nom Revit

*[documenté, confirmé par l'échec du 2026-09-24]*

```
\   :   {   }   [   ]   |   ;   <   >   ?   `   ~
```

Le **tilde** est dans la liste, et c'est celui qui a mordu : le nom
temporaire de la passe 1 valait `~TMP_<id>`, et le lot entier a échoué sur
`Name cannot include prohibited characters`. Corrigé en `TMP_<id>`.

Bénéfice collatéral : l'échec a éprouvé le `TransactionGroup` pour de vrai —
la maquette n'est pas restée avec 202 familles à moitié renommées.

**Conséquence de forme.** Un nom construit par le script (nom temporaire,
suffixe, marqueur) ne doit utiliser que des lettres, des chiffres et
l'underscore. Et la collision avec un nom existant se vérifie **avant** la
transaction, pas en la subissant.

---

## 3. `forms.alert` plafonne à quatre options

*[mesuré le 2026-09-24, puis vérifié dans le code installé de pyRevit]*

`forms.alert(..., options=[...])` mappe les options sur les
`TaskDialogCommandLinkId` de Revit, et il n'y en a que **quatre**. Une
cinquième option est **silencieusement ignorée** : pas d'erreur, pas
d'avertissement, le bouton n'existe simplement pas dans la fenêtre.

Au-delà de quatre choix, utiliser `forms.CommandSwitchWindow.show(...)`, qui
n'a pas cette limite. Ou, mieux, réduire le nombre de modes : trois modes
lisibles valent mieux que cinq qui tiennent à une fenêtre.

---

## 4. Familles in situ : les types homonymes sont acceptés

*[mesuré le 2026-09-24 sur 202 volumes]*

Chaque volume in situ est **sa propre famille**. Deux types portant le même
nom vivent donc dans deux familles distinctes, et **Revit les accepte** : les
202 volumes de The Study portent tous un type nommé `Volume Ivion`.

Ce n'était pas acquis — Revit aurait pu imposer une unicité plus large sur
les familles in situ. Un essai sur trois volumes protégeait cette inconnue ;
elle est levée, l'essai a été retiré.

**Le nom d'une famille in situ s'affiche à huit endroits.** Le renommage
passe par `Family.Name` ; `SYMBOL_FAMILY_NAME_PARAM` est en lecture seule et
reflète `Family.Name` en direct. La sonde `Sonde noms famille` les imprime
côte à côte quand un doute revient.

---

## 5. Renommer en lot : deux passes, obligatoirement

Quand une règle de nommage **redistribue** les noms — une renumérotation, un
tri qui change — un nom final peut être déjà porté par une *autre* famille au
moment où on veut le poser. Revit refuse le doublon, et le lot casse au
milieu.

- **Passe 1** : chaque famille prend un nom temporaire unique, `TMP_<id>`.
- **Passe 2** : chacune prend son nom final.
- Les deux transactions sont enfermées dans un **`TransactionGroup`** : si la
  passe 2 échoue, la passe 1 est annulée avec elle, et la maquette ne reste
  pas avec des familles nommées `TMP_...`.

---

## 6. Vérifier par un audit relancé, jamais par le rapport du script

Un rapport de script dit ce que le script **croit** avoir fait. C'est
exactement ce qui a masqué le défaut n° 1 pendant six exécutions : le script
relisait les noms *dans la même session*, voyait 202/202, et avait raison —
jusqu'à ce que Revit annule tout après coup.

La vérification se fait donc **depuis l'extérieur** : un audit en lecture
seule relancé après le bouton d'écriture, ou une nomenclature. Sur les
volumes, c'est le rôle explicite du bouton `Audit volumes`, et c'est ainsi
qu'ont été validés le renommage (202/202 au motif, numéros 001→202 sans trou)
et l'écriture des paramètres (1010 valeurs, concordance nom ↔ paramètres sur
202/202).

**Corollaire, appris le même jour** : ne jamais rendre deux sorties
indiscernables. Un CSV de simulation et un CSV d'après-exécution qui portent
le même nom ne permettent plus de dire lequel on lit — et on finit par
déduire une écriture qui n'a pas eu lieu.

---

## 7. Écrire sur la maquette centrale

*[règle, 2026-09-24 — le comportement du code, pas un fait Revit]*

Jusqu'au 2026-09-24, les trois boutons volumes **refusaient** de tourner sur
une maquette collaborative non détachée. Le garde-fou a fait son travail
pendant la mise au point, mais il interdisait le seul usage qui compte à la
fin : écrire sur la maquette de production.

La règle vit maintenant dans **`bimflow.extension\lib\bimflow_maquette.py`**,
écrite une seule fois pour les trois boutons :

- sur **copie détachée** — rien ne change, aucune boîte de plus ;
- sur **maquette centrale** — plus de refus, mais une confirmation qui
  **nomme le fichier**, **annonce le nombre d'éléments concernés**, et fait
  **cocher** que l'on est seul dessus (ACT-052 (2)). La case n'est pas un
  ornement : non cochée, l'opération ne part pas.

Le drapeau `AUTORISER_NON_DETACHE` a disparu des trois scripts. Une constante
en tête de fichier que l'on met à `True` « juste pour cette fois » n'est pas
un garde-fou : personne ne pense à la remettre à `False`.

Corollaire pour l'audit, qui n'écrit rien : ce qu'il faut signaler n'est pas
un risque d'écriture, c'est un **risque de vérité**. Un audit de la centrale
décrit l'état *synchronisé* à l'instant de la lecture — le travail non
synchronisé des autres n'y est pas, et le JSON portera pourtant une date qui
fera autorité. Le constat part aussi dans le JSON.

### L'emprunt d'un standard de projet — mesuré, et il passe

L'hypothèse était celle-ci : un nom de famille relève des **standards de
projet**, pas des éléments ; en travail partagé, modifier un standard demande
un **emprunt exclusif** que Revit peut refuser. **La simulation ne peut pas y
répondre** — elle ne teste que la lecture. D'où le **mode 2 de `Renommer
volumes`, l'essai sur un seul volume**, qui écrit pour de vrai et rapporte ce
que Revit rend, sans repli inventé. Même raisonnement que l'essai sur trois
types (§4).

**Mesure du 2026-09-24, maquette centrale `thestudy_A_VOL`** :

| Étape | Résultat |
|---|---|
| essai sur 1 famille, réservation lue `NotOwned` | Revit **accepte** ; l'emprunt se fait implicitement |
| synchronisation, puis audit relancé | le nom **tient** côté central |
| lot complet : 202 familles, puis 202 types, puis les paramètres | **tout passe**, avec synchronisation et audit à chaque palier |

**Il n'y a donc pas de contrainte structurante** pour un outil Keovia qui
renomme des familles in situ sur une maquette ACC : l'API emprunte le
standard toute seule et Revit ne demande rien de plus.

⚠️ **Ce que cela ne dit pas.** L'opérateur était **seul** sur la maquette, et
aucune famille n'était détenue par quelqu'un d'autre (`NotOwned` avant
l'essai). Ce qui se passe quand un autre utilisateur détient le standard
reste **non mesuré** — et c'est précisément pourquoi la confirmation fait
cocher « je suis seul sur cette maquette » plutôt que de faire confiance à la
chance. Le mode 2 reste le bon premier geste sur toute nouvelle maquette
centrale : il coûte un clic et répond à la seule question qui compte.

---

## 8. Discipline générale, inchangée

- Tout script qui écrit est précédé d'un script d'**audit en lecture seule**
  sur le même périmètre.
- La **copie détachée** (R17) reste la voie sûre pour une maquette
  collaborative ; depuis le 2026-09-24 elle n'est plus la seule (§7).
  `IsWorkshared` reste vrai après un détachement conservant les sous-projets ;
  c'est **`IsDetached`** qui décide, et sur une version de Revit où la
  propriété serait illisible, le doute va du côté prudent : centrale.
- Un script d'écriture affiche une **simulation** d'abord, puis une
  confirmation qui **nomme la maquette**, et fait **un seul commit** pour tout
  le lot.
- L'identité d'un paramètre partagé est son **GUID**, jamais son nom (R08).
- `ElementId.Value` sur Revit 2024+ ; `.IntegerValue` est déprécié.
