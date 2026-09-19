# -*- coding: utf-8 -*-
"""Mesure les parametres de projet d'une maquette : liaisons, remplissage, valeurs.

Outil BLEU : lecture seule, aucune transaction, rien n'est modifie.

Il repond a une seule question : QUE CONTIENT reellement chaque parametre de
projet ? Il ne conclut pas a la suppression (regle C7) : il ecrit ce qu'il
mesure, la decision reste humaine.

Limite a dire : ce bouton ne voit que les PARAMETRES DE PROJET. Un parametre
porte par une famille chargee ne s'y trouve pas et se retire dans l'editeur de
familles, pas ici.

pyRevit v6.5.5 / IronPython 3.4.2 (IPY342) - pas de f-string, pas de shebang.
"""

__title__ = "Audit\nparametres"
__author__ = "Keovia Solutions inc."

VERSION = u"2026-09-19n"

import codecs

from pyrevit import revit, forms, script

from Autodesk.Revit.DB import (
    FilteredElementCollector, InstanceBinding, StorageType,
)

doc = revit.doc
out = script.get_output()

# Au-dela de ce nombre de categories liees, la liaison est signalee comme large.
SEUIL_CATEGORIES_LARGE = 15
# Au-dela de ce taux de remplissage, on considere le parametre reellement utilise.
SEUIL_REMPLISSAGE = 0.05
# Nombre de valeurs distinctes affichees en exemple.
EXEMPLES_MAX = 6


def norm(txt):
    return txt if txt else u""


# ---------------------------------------------------------------------------
# 0. Les parametres PARTAGES presents dans le document
# ---------------------------------------------------------------------------
# La table des liaisons expose une InternalDefinition, qui ne porte PAS de GUID.
# Interroger definition.GUID renvoie donc toujours une erreur, et conclure de la
# que rien n'est partage serait faux. Les GUID se lisent sur les
# SharedParameterElement du document, appaires par nom.

partages = {}
try:
    from Autodesk.Revit.DB import SharedParameterElement
    elems = list(FilteredElementCollector(doc)
                 .OfClass(SharedParameterElement).ToElements())
    for spe in elems:
        try:
            partages[spe.GetDefinition().Name] = str(spe.GuidValue)
        except Exception:
            continue
except Exception:
    partages = {}


# ---------------------------------------------------------------------------
# 1. Lire les liaisons
# ---------------------------------------------------------------------------

params = []   # dict par parametre
it = doc.ParameterBindings.ForwardIterator()
it.Reset()
while it.MoveNext():
    definition = it.Key
    binding = it.Current

    cats = []
    try:
        for c in binding.Categories:
            cats.append(c.Name)
    except Exception:
        pass

    est_occurrence = isinstance(binding, InstanceBinding)

    guid = partages.get(definition.Name, u"(projet, non partage)")

    params.append({
        "nom": definition.Name,
        "guid": guid,
        "occurrence": est_occurrence,
        "categories": sorted(cats),
        "remplis": 0,
        "total": 0,
        "valeurs": set(),
    })

if not params:
    forms.alert(u"Cette maquette ne porte aucun parametre de projet.",
                exitscript=True)

# Index : nom de categorie -> parametres a chercher sur ses elements
par_categorie = {}
for p in params:
    for nom_cat in p["categories"]:
        par_categorie.setdefault(nom_cat, []).append(p)


# ---------------------------------------------------------------------------
# 2. Parcourir le modele
# ---------------------------------------------------------------------------
# R15 : on MATERIALISE le collecteur avant de resoudre la moindre propriete.
# Resoudre pendant l'iteration provoque une AccessViolationException qui tue le
# processus et ne se rattrape pas.

def valeur_lisible(p):
    """Retourne (rempli, texte). Rempli = le champ porte quelque chose."""
    try:
        st = p.StorageType
    except Exception:
        return False, u""

    if st == StorageType.String:
        v = p.AsString()
        if v is None or not v.strip():
            return False, u""
        return True, v.strip()

    if st == StorageType.ElementId:
        try:
            eid = p.AsElementId()
        except Exception:
            return False, u""
        if eid is None or eid.Value < 0:
            return False, u""
        return True, str(eid.Value)

    # Entier, reel : on s'appuie sur HasValue puis sur le rendu Revit.
    try:
        if not p.HasValue:
            return False, u""
        v = p.AsValueString()
    except Exception:
        return False, u""
    if v is None or not v.strip():
        return False, u""
    return True, v.strip()


def parcourir(collecteur, etiquette):
    elements = list(collecteur.ToElements())
    out.print_md(u"- " + etiquette + u" : " + str(len(elements)) + u" elements lus")
    for el in elements:
        try:
            cat = el.Category
        except Exception:
            continue
        if cat is None:
            continue
        cibles = par_categorie.get(cat.Name)
        if not cibles:
            continue
        for p in cibles:
            try:
                param = el.LookupParameter(p["nom"])
            except Exception:
                continue
            if param is None:
                continue
            p["total"] += 1
            rempli, texte = valeur_lisible(param)
            if rempli:
                p["remplis"] += 1
                if len(p["valeurs"]) < 2000:
                    p["valeurs"].add(texte)


out.print_md(u"# Audit des parametres de projet")
out.print_md(u"**Version de l'outil** : `" + VERSION + u"`")
out.print_md(u"**Maquette** : `" + doc.Title + u"`")
out.print_md(u"> Lecture seule. Rien n'a ete modifie.")
out.print_md(u"## Lecture")

parcourir(
    FilteredElementCollector(doc).WhereElementIsNotElementType(),
    u"occurrences",
)
parcourir(
    FilteredElementCollector(doc).WhereElementIsElementType(),
    u"types",
)


# ---------------------------------------------------------------------------
# 3. Bilan
# ---------------------------------------------------------------------------

def taux(p):
    if p["total"] == 0:
        return 0.0
    return float(p["remplis"]) / float(p["total"])


def diagnostic(p):
    """Ce que la MESURE dit. Jamais 'supprimable' (C7)."""
    n_cat = len(p["categories"])
    n_val = len(p["valeurs"])
    t = taux(p)

    if p["total"] == 0:
        return u"aucun element porteur dans cette maquette"
    if p["remplis"] == 0:
        if n_cat >= SEUIL_CATEGORIES_LARGE:
            return u"vide partout, liaison large"
        return u"vide partout"
    if n_val == 1:
        return u"une seule valeur distincte sur " + str(p["remplis"]) + u" objets"
    if t < SEUIL_REMPLISSAGE and n_cat >= SEUIL_CATEGORIES_LARGE:
        return u"rempli marginalement, liaison large"
    if t < SEUIL_REMPLISSAGE:
        return u"rempli marginalement"
    return u"utilise"


params.sort(key=lambda p: (taux(p), -len(p["categories"]), p["nom"]))

lignes = []
for p in params:
    t = taux(p)
    lignes.append([
        p["nom"],
        u"occ." if p["occurrence"] else u"type",
        str(len(p["categories"])),
        str(p["remplis"]) + u" / " + str(p["total"]),
        u"%.1f %%" % (t * 100.0),
        str(len(p["valeurs"])),
        diagnostic(p),
    ])

out.print_md(u"## Bilan — du moins rempli au plus rempli")
out.print_table(
    table_data=lignes,
    columns=[u"Parametre", u"Port.", u"Cat.", u"Rempli", u"Taux",
             u"Val. distinctes", u"Ce que la mesure dit"],
)

out.print_md(
    u"> **Ce tableau mesure, il ne conclut pas.** « vide partout » ne veut pas "
    u"dire supprimable : un parametre peut etre declare en avance d'une "
    u"campagne de saisie. La decision reste humaine."
)
out.print_md(
    u"> Ce bouton ne voit que les **parametres de projet**. Un parametre porte "
    u"par une famille chargee n'apparait pas ici et se retire dans l'editeur "
    u"de familles."
)
out.print_md(
    u"> **Limite du test de remplissage** : pour un parametre Oui/Non ou "
    u"numerique, un champ laisse a `Non` ou a zero se lit comme vide. "
    u"« 0 rempli » y signifie « aucune valeur non nulle », pas forcement "
    u"« jamais touche ». Pour un parametre texte, la lecture est exacte."
)

# Detail des valeurs, pour les parametres qui en ont peu
maigres = [p for p in params if 0 < len(p["valeurs"]) <= EXEMPLES_MAX]
if maigres:
    out.print_md(u"## Parametres a vocabulaire etroit")
    for p in maigres:
        vals = u" · ".join([u"`" + v + u"`" for v in sorted(p["valeurs"])])
        out.print_md(u"- **" + p["nom"] + u"** : " + vals)


# ---------------------------------------------------------------------------
# 4. CSV
# ---------------------------------------------------------------------------

chemin = forms.save_file(file_ext="csv", default_name="audit_parametres")
if chemin:
    f = codecs.open(chemin, "w", "utf-8")
    try:
        f.write(u"﻿")
        f.write(u";".join([
            u"Parametre", u"GUID", u"Portee", u"Nb_categories", u"Categories",
            u"Elements_porteurs", u"Elements_remplis", u"Taux_pct",
            u"Valeurs_distinctes", u"Exemples", u"Mesure",
        ]) + u"\n")
        for p in params:
            exemples = sorted(p["valeurs"])[:EXEMPLES_MAX]
            f.write(u";".join([
                p["nom"],
                p["guid"],
                u"occurrence" if p["occurrence"] else u"type",
                str(len(p["categories"])),
                u"|".join(p["categories"]),
                str(p["total"]),
                str(p["remplis"]),
                u"%.1f" % (taux(p) * 100.0),
                str(len(p["valeurs"])),
                u"|".join([e.replace(u";", u",") for e in exemples]),
                diagnostic(p),
            ]) + u"\n")
    finally:
        f.close()
    out.print_md(u"---")
    out.print_md(u"CSV ecrit : `" + chemin + u"`")
else:
    out.print_md(u"---")
    out.print_md(u"Pas de CSV — le tableau ci-dessus reste lisible.")

out.print_md(
    u"**Pour retirer un parametre** : `Gerer` → `Parametres du projet` → "
    u"le selectionner → `Supprimer`. Cela efface aussi ses valeurs dans cette "
    u"maquette, sans retour possible. Pour le garder sur les seules categories "
    u"qui le portent vraiment, ne pas supprimer : **decocher les categories** "
    u"en trop."
)
