# -*- coding: utf-8 -*-
"""Liste les parametres que Revit cree lui-meme, et signale ceux qu'on double.

Outil BLEU : lecture seule, aucune transaction.

Il repond a une question qui se repose a chaque version de Revit :
QUELS PARAMETRES N'AI-JE PAS A CREER, parce que Revit les fournit deja ?

Il mesure au lieu de reciter : il ouvre les objets du modele et releve, pour
chaque categorie, les parametres dont la definition porte un BuiltInParameter.
Puis il confronte cette liste aux parametres de projet de la maquette.

pyRevit v6.5.5 / IronPython 3.4.2 (IPY342) - pas de f-string, pas de shebang.
"""

__title__ = "Parametres\nnatifs"
__author__ = "Keovia Solutions inc."

VERSION = u"2026-09-19n"

import codecs
import unicodedata

from pyrevit import revit, forms, script

from Autodesk.Revit.DB import BuiltInParameter, FilteredElementCollector

doc = revit.doc
out = script.get_output()

# Objets echantillonnes par categorie : au-dela, on n'apprend plus rien.
ECHANTILLON = 5


def cle(nom):
    """Nom normalise pour comparer : minuscules, sans accent, sans ponctuation."""
    if not nom:
        return u""
    n = unicodedata.normalize("NFD", nom)
    n = u"".join([c for c in n if unicodedata.category(c) != "Mn"])
    n = n.lower()
    return u"".join([c for c in n if c.isalnum()])


def natifs_de(el):
    """Noms des parametres de cet element dont la definition est un built-in."""
    noms = set()
    try:
        params = list(el.Parameters)
    except Exception:
        return noms
    for p in params:
        try:
            d = p.Definition
            bip = d.BuiltInParameter
        except Exception:
            continue          # definition externe : c'est un parametre a nous
        try:
            if bip == BuiltInParameter.INVALID:
                continue
        except Exception:
            continue
        noms.add(d.Name)
    return noms


# ---------------------------------------------------------------------------
# 1. Relever, categorie par categorie
# ---------------------------------------------------------------------------

out.print_md(u"# Parametres natifs de Revit — releve sur `" + doc.Title + u"`")
out.print_md(u"**Version de l'outil** : `" + VERSION + u"`")
out.print_md(u"> Lecture seule. Rien n'a ete modifie.")

vus = {}          # nom de categorie -> {"occ": set, "type": set, "n": int}
elements = list(FilteredElementCollector(doc)
                .WhereElementIsNotElementType().ToElements())

for el in elements:
    try:
        cat = el.Category
    except Exception:
        continue
    if cat is None:
        continue
    nom_cat = cat.Name
    fiche = vus.setdefault(nom_cat, {"occ": set(), "type": set(), "n": 0})
    if fiche["n"] >= ECHANTILLON:
        continue
    fiche["n"] += 1
    fiche["occ"] |= natifs_de(el)
    try:
        t = doc.GetElement(el.GetTypeId())
    except Exception:
        t = None
    if t is not None:
        fiche["type"] |= natifs_de(t)

if not vus:
    forms.alert(u"Aucun objet de modele dans cette maquette.", exitscript=True)

out.print_md(u"- " + str(len(elements)) + u" objets parcourus, " +
             str(len(vus)) + u" categories rencontrees")


# ---------------------------------------------------------------------------
# 2. Le socle natif : ce que TOUTE categorie porte
# ---------------------------------------------------------------------------

communs_occ = None
communs_type = None
for fiche in vus.values():
    communs_occ = set(fiche["occ"]) if communs_occ is None else (communs_occ & fiche["occ"])
    if fiche["type"]:
        communs_type = set(fiche["type"]) if communs_type is None else (communs_type & fiche["type"])

communs_occ = communs_occ or set()
communs_type = communs_type or set()

out.print_md(u"## Presents sur TOUTES les categories — a ne jamais recreer")
out.print_md(u"**En occurrence** : " +
             u" · ".join([u"`" + n + u"`" for n in sorted(communs_occ)]))
out.print_md(u"**Sur le type** : " +
             u" · ".join([u"`" + n + u"`" for n in sorted(communs_type)]))


# ---------------------------------------------------------------------------
# 3. Les doublons : mes parametres de projet qui portent un nom de natif
# ---------------------------------------------------------------------------

miens = {}
it = doc.ParameterBindings.ForwardIterator()
it.Reset()
while it.MoveNext():
    miens[it.Key.Name] = []

index = {}
for nom_cat, fiche in vus.items():
    for n in (fiche["occ"] | fiche["type"]):
        index.setdefault(cle(n), set()).add(n)

collisions = []
echos = []
for nom in sorted(miens.keys()):
    k = cle(nom)
    if k in index:
        collisions.append([nom, sorted(index[k])[0]])
        continue
    # Doublon prefixe : DB_Fabricant contre Fabricant. Le nom n'est pas
    # identique, mais la chose designee l'est souvent.
    for kn in index:
        if len(kn) >= 5 and k != kn and k.endswith(kn):
            echos.append([nom, sorted(index[kn])[0]])
            break

out.print_md(u"## Collisions de nom — le defaut le plus couteux")
if collisions:
    out.print_table(table_data=collisions,
                    columns=[u"Parametre de projet", u"Natif de meme nom"])
    out.print_md(
        u"> Les deux coexistent sur le meme objet, l'un se remplit, l'autre "
        u"pas, et personne ne sait plus lequel il lit."
    )
else:
    out.print_md(u"*Aucune.*")

out.print_md(u"## Doublons probables — votre nom contient celui d'un natif")
if echos:
    out.print_table(table_data=echos,
                    columns=[u"Parametre de projet", u"Natif correspondant"])
    out.print_md(
        u"> Signalement, **pas** verdict. Deux paramètres ne font doublon que "
        u"s'ils ont la meme **autorite** : un miroir d'une cle produite dans "
        u"une base externe n'est pas un doublon du champ natif que Revit "
        u"fournit, meme si le nom se ressemble."
    )
else:
    out.print_md(u"*Aucun.*")

out.print_md(
    u"> **Ce que ce releve ne dit pas** : qu'un natif de meme NOM porte la meme "
    u"CHOSE. Verifier le sens avant de conclure au doublon."
)


# ---------------------------------------------------------------------------
# 4. CSV — le detail par categorie
# ---------------------------------------------------------------------------

chemin = forms.save_file(file_ext="csv", default_name="parametres_natifs")
if chemin:
    f = codecs.open(chemin, "w", "utf-8")
    try:
        f.write(u"﻿")
        f.write(u"Categorie;Portee;Parametre_natif\n")
        for nom_cat in sorted(vus.keys()):
            for n in sorted(vus[nom_cat]["occ"]):
                f.write(u";".join([nom_cat, u"occurrence", n]) + u"\n")
            for n in sorted(vus[nom_cat]["type"]):
                f.write(u";".join([nom_cat, u"type", n]) + u"\n")
    finally:
        f.close()
    out.print_md(u"---")
    out.print_md(u"CSV ecrit : `" + chemin + u"`")
