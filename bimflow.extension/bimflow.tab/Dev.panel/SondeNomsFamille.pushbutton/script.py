# -*- coding: utf-8 -*-
"""sonde_noms_famille - Ou vit le nom qu'un volume in situ affiche ?

LECTURE SEULE - aucune transaction, rien n'est ecrit nulle part. Pas meme un
CSV : tout s'affiche a l'ecran.

POURQUOI. Le 2026-09-24, le bouton Renommer volumes a renomme 202 familles,
l'a verifie par relecture immediate (202/202), et l'arborescence du projet a
bien montre les nouveaux noms. Puis :
  - l'infobulle d'un volume, au survol, montrait l'ANCIEN nom ;
  - l'audit lance juste apres, sans rien toucher, lisait l'ANCIEN nom ;
  - un renommage A LA MAIN d'une seule famille rafraichissait l'arborescence,
    qui repassait alors a l'ANCIEN nom pour toutes les autres.
L'arborescence affichait donc un etat perime. L'ecriture n'a jamais ete
inscrite la ou les instances lisent leur nom. Et comme le renommage manuel,
lui, tient, ce n'est pas Revit qui refuse : c'est le script qui ecrit au
mauvais endroit.

CE QUE CETTE SONDE ETABLIT. Le nom d'une famille peut vivre a plusieurs
endroits, qui peuvent se desynchroniser :
    1. l'element Family                  Symbol.Family.Name
    2. le TYPE, propriete                Symbol.FamilyName
    3. le TYPE, parametre                SYMBOL_FAMILY_NAME_PARAM
    4. l'INSTANCE, parametre             ELEM_FAMILY_PARAM
                                         ELEM_FAMILY_AND_TYPE_PARAM
La sonde les imprime cote a cote. Celui qui garde l'ancien nom est celui que
Revit considere comme vrai - et donc celui qu'il faudra ecrire.

COMMENT S'EN SERVIR. La lancer DEUX fois : une fois maintenant, une fois
juste apres un mode 2 de Renommer volumes. C'est la comparaison des deux
sorties qui repond, pas une seule.

bimflow - volumes de zone, diagnostic - Keovia Solutions inc.
2026-09-24
"""

__title__ = "Sonde noms\nfamille"
__author__ = "Keovia Solutions inc."

# --------------------------------------------------------------------------
# PARAMETRES
# --------------------------------------------------------------------------

# Combien de volumes detailler. Le reste n'est que compte et doublons.
NB_DETAILLES = 3

# --------------------------------------------------------------------------

from pyrevit import revit, script, forms

from Autodesk.Revit.DB import (
    FilteredElementCollector,
    BuiltInCategory,
    BuiltInParameter,
    Family,
    FamilyInstance,
    FamilySymbol,
)

doc = revit.doc
out = script.get_output()


def id_de(eid):
    """R15 fait 7 : ElementId.Value en Revit 2024+, .IntegerValue avant."""
    if eid is None:
        return -1
    try:
        return int(eid.Value)
    except AttributeError:
        return int(eid.IntegerValue)


def texte(valeur):
    return u"" if valeur is None else u"{0}".format(valeur)


def sans_erreur(fonction):
    """Rend la valeur, ou le texte de l'erreur. Une sonde ne doit jamais
    s'arreter sur un acces qui echoue : c'est justement ce qu'on mesure."""
    try:
        return texte(fonction())
    except Exception as err:
        return u"(illisible : {0})".format(err)


def valeur_bip(element, nom_bip):
    """Valeur d'un BuiltInParameter, ou pourquoi elle manque."""
    bip = getattr(BuiltInParameter, nom_bip, None)
    if bip is None:
        return u"(BuiltInParameter {0} inconnu de cette version)".format(nom_bip)
    try:
        p = element.get_Parameter(bip)
    except Exception as err:
        return u"(illisible : {0})".format(err)
    if p is None:
        return u"(absent)"
    for lecture in ("AsString", "AsValueString"):
        try:
            v = getattr(p, lecture)()
            if v:
                return texte(v)
        except Exception:
            continue
    return u"(vide)"


# --------------------------------------------------------------------------
# 0. Le document
# --------------------------------------------------------------------------

if doc.IsFamilyDocument:
    forms.alert(u"Document famille : rien a sonder.", exitscript=True)

detache = None
try:
    detache = bool(doc.IsDetached)
except Exception:
    detache = None

out.print_md(u"# Sonde des noms de famille")
out.print_md(
    u"Maquette : **{0}** &nbsp;|&nbsp; {1} &nbsp;|&nbsp; **lecture seule, "
    u"aucune transaction**".format(
        doc.Title,
        u"copie detachee" if detache else
        (u"collaborative NON detachee" if doc.IsWorkshared else
         u"non collaborative"))
)
out.print_md(u"Fichier : `{0}`".format(doc.PathName or u"(jamais enregistree)"))

# --------------------------------------------------------------------------
# 1. Les cinq porteurs du nom, volume par volume
# --------------------------------------------------------------------------

ids = list(
    FilteredElementCollector(doc)
    .OfCategory(BuiltInCategory.OST_Mass)
    .WhereElementIsNotElementType()
    .ToElementIds()
)
# R15 fait 8 : le collecteur est consomme AVANT toute resolution de propriete.

out.print_md(u"## Ou vit le nom - les {0} premiers volumes".format(NB_DETAILLES))
out.print_md(
    u"Si ces cinq lignes ne disent pas toutes la meme chose, celle qui garde "
    u"l'ancien nom est celle que Revit tient pour vraie.")

detailles = 0
for eid in ids:
    if detailles >= NB_DETAILLES:
        break
    el = doc.GetElement(eid)
    if el is None or not isinstance(el, FamilyInstance):
        continue
    detailles += 1

    try:
        symbole = el.Symbol
    except Exception as err:
        out.print_md(u"### Volume `{0}` - type illisible : {1}".format(
            id_de(eid), err))
        continue
    try:
        famille = symbole.Family
    except Exception:
        famille = None

    out.print_md(u"### Volume `{0}`".format(id_de(eid)))
    lignes = [u"| Porteur | Identifiant | Valeur |", u"|---|---|---|"]
    lignes.append(u"| 1. element `Family`, `.Name` | `{0}` | `{1}` |".format(
        id_de(famille.Id) if famille is not None else u"-",
        sans_erreur(lambda: famille.Name) if famille is not None
        else u"(pas de famille)"))
    lignes.append(u"| 1 bis. `Family.IsInPlace` | | `{0}` |".format(
        sans_erreur(lambda: famille.IsInPlace) if famille is not None
        else u"-"))
    lignes.append(u"| 2. TYPE, propriete `.FamilyName` | `{0}` | `{1}` |".format(
        id_de(symbole.Id), sans_erreur(lambda: symbole.FamilyName)))
    lignes.append(u"| 3. TYPE, propriete `.Name` | | `{0}` |".format(
        sans_erreur(lambda: symbole.Name)))
    lignes.append(u"| 4. TYPE, param `SYMBOL_FAMILY_NAME_PARAM` | | `{0}` |".format(
        valeur_bip(symbole, "SYMBOL_FAMILY_NAME_PARAM")))
    lignes.append(u"| 5. TYPE, param `ALL_MODEL_FAMILY_NAME` | | `{0}` |".format(
        valeur_bip(symbole, "ALL_MODEL_FAMILY_NAME")))
    lignes.append(u"| 6. INSTANCE, param `ELEM_FAMILY_PARAM` | `{0}` | `{1}` |".format(
        id_de(eid), valeur_bip(el, "ELEM_FAMILY_PARAM")))
    lignes.append(u"| 7. INSTANCE, param `ELEM_FAMILY_AND_TYPE_PARAM` | | `{0}` |".format(
        valeur_bip(el, "ELEM_FAMILY_AND_TYPE_PARAM")))
    lignes.append(u"| 8. INSTANCE, param `ELEM_TYPE_PARAM` | | `{0}` |".format(
        valeur_bip(el, "ELEM_TYPE_PARAM")))
    out.print_md(u"\n".join(lignes))

# --------------------------------------------------------------------------
# 2. TOUTES les familles de categorie Volumes
# --------------------------------------------------------------------------

out.print_md(u"## Toutes les familles de categorie Volumes")
out.print_md(
    u"Si un renommage avait atterri sur d'autres elements que ceux portes par "
    u"les instances, on verrait ici des familles au nouveau nom a cote des "
    u"anciennes.")

ids_familles = list(FilteredElementCollector(doc).OfClass(Family).ToElementIds())
familles = []
for fid in ids_familles:
    f = doc.GetElement(fid)
    if f is None:
        continue
    categorie = u""
    try:
        if f.FamilyCategory is not None:
            categorie = f.FamilyCategory.Name
    except Exception:
        categorie = u"(categorie illisible)"
    nom = sans_erreur(lambda: f.Name)
    in_situ = sans_erreur(lambda: f.IsInPlace)
    familles.append((id_de(fid), nom, categorie, in_situ))

volumes_familles = [x for x in familles
                    if u"olume" in x[2] or u"ass" in x[2]]

out.print_md(
    u"- **{0}** famille(s) dans le document, dont **{1}** de categorie "
    u"Volumes".format(len(familles), len(volumes_familles)))

par_nom = {}
for fid, nom, categorie, in_situ in volumes_familles:
    par_nom.setdefault(nom, []).append(fid)
doublons = dict([(n, l) for n, l in par_nom.items() if len(l) > 1])

prefixes = {}
for fid, nom, categorie, in_situ in volumes_familles:
    tete = nom.split(u"__")[0] if nom else u"(vide)"
    prefixes[tete] = prefixes.get(tete, 0) + 1

out.print_md(u"### Repartition par premier segment du nom")
lignes = [u"| Premier segment | Familles |", u"|---|---:|"]
for tete in sorted(prefixes.keys()):
    lignes.append(u"| `{0}` | {1} |".format(tete, prefixes[tete]))
out.print_md(u"\n".join(lignes))

if doublons:
    out.print_md(u"### Noms de famille en DOUBLE")
    for nom, liste in sorted(doublons.items()):
        out.print_md(u"- `{0}` : {1}".format(nom, liste))
else:
    out.print_md(u"*Aucun nom de famille en double.*")

out.print_md(u"### Les 10 premieres, telles quelles")
lignes = [u"| Id | Nom | Categorie | In situ |", u"|---|---|---|---|"]
for fid, nom, categorie, in_situ in sorted(volumes_familles)[:10]:
    lignes.append(u"| `{0}` | `{1}` | {2} | {3} |".format(
        fid, nom, categorie, in_situ))
out.print_md(u"\n".join(lignes))

# --------------------------------------------------------------------------
# 3. Les types
# --------------------------------------------------------------------------

ids_types = list(
    FilteredElementCollector(doc)
    .OfCategory(BuiltInCategory.OST_Mass)
    .WhereElementIsElementType()
    .ToElementIds()
)
types = []
for tid in ids_types:
    t = doc.GetElement(tid)
    if t is None or not isinstance(t, FamilySymbol):
        continue
    types.append((id_de(tid),
                  sans_erreur(lambda: t.Name),
                  sans_erreur(lambda: t.FamilyName)))

out.print_md(u"## Les types de categorie Volumes")
noms_types = {}
for tid, nom, nom_famille in types:
    noms_types[nom] = noms_types.get(nom, 0) + 1
lignes = [u"| Nom de type | Occurrences |", u"|---|---:|"]
for nom in sorted(noms_types.keys()):
    lignes.append(u"| `{0}` | {1} |".format(nom, noms_types[nom]))
out.print_md(u"\n".join(lignes))
out.print_md(
    u"**{0}** type(s) en tout. Un meme nom porte plusieurs fois signifie que "
    u"Revit accepte des types homonymes dans des familles distinctes - "
    u"mesure du 2026-09-24.".format(len(types)))

out.print_md(
    u"---\n> **Rien n'a ete ecrit.** Relancer cette sonde juste apres un "
    u"mode 2 de `Renommer volumes` : c'est la comparaison des deux sorties "
    u"qui dira quel porteur a bouge, lequel est reste, et donc lequel il faut "
    u"ecrire."
)
