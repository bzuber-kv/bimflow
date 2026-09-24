# -*- coding: utf-8 -*-
"""renommer_volumes - Renomme les familles des volumes de zone, dans l'ordre
de l'espace.

Reecrit le 2026-09-24 (il ne posait auparavant qu'une nature sur les volumes
"0" ; il refait desormais le nom entier).

OBJET. Donner a chaque volume in situ un nom au motif etendu :

    VOL_nnn__<REF_Zone>__<REF_Etage>__<CLS_Nature_volume>[__<cle>]

Le numero nnn suit l'espace, sur trois niveaux : par batiment (JU, MI, SC,
SE, puis EXT), puis par colonne triee d'ouest en est puis du sud au nord du
PROJET, puis du bas vers le haut dans la colonne. Lire une nomenclature
triee par nom, c'est alors descendre le batiment colonne par colonne.

#############################################################################
# STATUT : NON EPROUVE dans Revit au 2026-09-24. Le CLASSEMENT, lui, a ete  #
# rejoue hors Revit sur l'audit du 2026-09-24 (201 volumes) par             #
# tools/volumes/dry_run_depuis_audit.py, QUI APPELLE LE MEME CODE :         #
# 0 non resolu, 0 collision, x puis y croissants dans les 4 batiments,      #
# zmin croissant dans les 61 colonnes.                                      #
# Ce qui n'est PAS eprouve : l'ecriture elle-meme - le renommage des        #
# familles, et surtout celui des types (voir ESSAI ci-dessous).             #
#############################################################################

QUATRE MODES, choisis au lancement. La simulation est le defaut, et aucune
transaction n'existe avant un choix explicite.

  1. Simulation            lecture seule, CSV du avant/apres
  2. Renommer les familles ecriture, en DEUX PASSES
  3. Types : essai sur 3   ecriture, trois volumes seulement
  4. Types : tous          ecriture, apres l'essai et pas avant

POURQUOI DEUX PASSES AU RENOMMAGE. Les numeros redistribuent les noms : un
nom final peut etre deja porte par une AUTRE famille au moment ou on veut
le poser, et Revit refuse alors le doublon. Passe 1 : chaque famille prend
un nom temporaire "TMP_<id>". Passe 2 : chacune prend son nom final. Les
deux transactions sont enfermees dans un TransactionGroup : si la passe 2
echoue, la passe 1 est annulee avec elle, et la maquette ne reste pas avec
des familles nommees "TMP_...".

ATTENTION - le nom temporaire s'ecrivait "~TMP_<id>" jusqu'au 2026-09-24 :
le tilde fait partie des caracteres que Revit REFUSE dans un nom, et la
passe 1 echouait sur "Name cannot include prohibited characters" - mesure du
jour, sur les 202 volumes de The Study. Caracteres interdits [documente] :
antislash, deux-points, accolades, crochets, barre verticale, point-virgule,
chevrons, point d'interrogation, accent grave, tilde. Le lot entier a ete
annule proprement, ce qui a au moins eprouve le TransactionGroup pour de
vrai.

L'ESSAI DES NOMS DE TYPE [hypothese, a lever sur Revit]. Chaque volume in
situ est sa propre famille, donc deux types homonymes vivent dans DEUX
familles distinctes et devraient etre acceptes. Revit peut imposer une
unicite plus large sur les familles in situ : PERSONNE ICI NE LE SAIT. Le
mode 3 en renomme TROIS et rapporte ce qui s'est passe. Si Revit refuse,
le script s'arrete et le dit - il n'invente aucun repli.

bimflow - volumes de zone, mode ecriture - Keovia Solutions inc.
"""

__title__ = "Renommer\nvolumes"
__author__ = "Keovia Solutions inc."

# --------------------------------------------------------------------------
# PARAMETRES
# --------------------------------------------------------------------------

# Nom de type voulu pour tous les volumes.
NOM_TYPE_VOULU = "Volume Ivion"

# Combien de volumes l'essai de renommage de type traite.
TAILLE_ESSAI = 3

# Nord local par groupe de batiments, en degres. PREVU, NON ACTIF : {"SE": 6.6}
# ferait pivoter les centres des colonnes de SE avant le tri. Personne n'a
# mesure que cela ameliore l'ordre, et changer le tri change tous les numeros.
NORD_LOCAL = {}

# Une maquette collaborative doit etre traitee sur une COPIE DETACHEE (R17).
AUTORISER_NON_DETACHE = False

# Typos relevees a la main sur la maquette au 2026-09-24. Ces quatre noms ne
# se decoupent pas : la table les traduit, elle ne les devine pas. Elle
# devient inutile des que les noms sont refaits.
# Meme table que tools/volumes/dry_run_depuis_audit.py.
CORRECTIONS = {
    "Volume 019__SC_Bp_Cp_3p_3p__ROOF_TOITURE":
        ("SC_Bp_Cp_3p_3p", "ROOF", "TOITURE", None),
    "Volume 089__MI_Amg_Am_4mg_5m_ROOF__ENTRETOIT":
        ("MI_Amg_Am_4mg_5m", "ROOF", "ENTRETOIT", None),
    "Volume 100__MI_Dm_Emg_6m_7m__ROOF_ENTRETOIT":
        ("MI_Dm_Emg_6m_7m", "ROOF", "ENTRETOIT", None),
    # nature absente du nom ; ETAGE arbitre par Bruno le 2026-09-24
    "Volume 098__MI_Dm_Emg_6m_7m__FLOOR_1":
        ("MI_Dm_Emg_6m_7m", "FLOOR_1", "ETAGE", None),
}

# --------------------------------------------------------------------------

import io

from pyrevit import revit, script, forms

try:
    from bimflow_noms import (extraire, ref_batiment, nom_de_famille,
                              incoherence_etage_nature, ETAGES_CONNUS)
    from bimflow_volumes import classer
except ImportError:
    from pyrevit import forms as _formulaires
    _formulaires.alert(
        u"Modules partages bimflow_noms / bimflow_volumes introuvables.\n\n"
        u"Ils doivent se trouver dans bimflow.extension\\lib\\. Sans eux, ni "
        u"le decoupage des noms ni le classement spatial ne sont "
        u"disponibles, et ce script ne s'execute pas.",
        exitscript=True,
    )

from Autodesk.Revit.DB import (
    FilteredElementCollector,
    BuiltInCategory,
    Family,
    FamilyInstance,
    Transaction,
    TransactionGroup,
    TransactionStatus,
)
from Autodesk.Revit.UI import TaskDialog, TaskDialogCommonButtons, TaskDialogResult

doc = revit.doc
out = script.get_output()

MM_PAR_PIED = 304.8
try:
    from Autodesk.Revit.DB import UnitUtils, UnitTypeId
    _UNITE_MM = UnitTypeId.Millimeters
except Exception:
    UnitUtils = None
    _UNITE_MM = None


def mm(valeur):
    if valeur is None:
        return None
    if UnitUtils is not None and _UNITE_MM is not None:
        try:
            return UnitUtils.ConvertFromInternalUnits(valeur, _UNITE_MM)
        except Exception:
            pass
    return valeur * MM_PAR_PIED


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


def lien_de(eid):
    try:
        return out.linkify(eid)
    except Exception:
        return u"`{0}`".format(id_de(eid))


# --------------------------------------------------------------------------
# 0. Garde-fous
# --------------------------------------------------------------------------

if doc.IsFamilyDocument:
    forms.alert(u"Document famille : rien a renommer.", exitscript=True)

collaboratif = bool(doc.IsWorkshared)
detache = None
try:
    detache = bool(doc.IsDetached)
except Exception:
    detache = None

# Rappel : IsWorkshared reste True apres un detachement conservant les
# sous-projets. C'est IsDetached qui tranche, et lui seul.
NON_DETACHEE = collaboratif and detache is not True

MODES = [u"1 - Simuler (lecture seule, aucune ecriture)",
         u"2 - Renommer les familles (ECRIT dans la maquette)",
         u"3 - Noms de type : ESSAI sur {0} volumes (ECRIT)".format(TAILLE_ESSAI),
         u"4 - Noms de type : tous les volumes (ECRIT)",
         u"5 - DIAGNOSTIC : essai instrumente sur {0} familles (ECRIT)".format(
             TAILLE_ESSAI)]

# forms.alert n'affiche QUE QUATRE options : il s'appuie sur le TaskDialog de
# Revit, dont TaskDialogCommandLinkId s'arrete a CommandLink4, et pyRevit
# jette les suivantes SANS RIEN DIRE (pyrevit\forms\_ipy.py : "if idx <
# max_clinks"). Le mode 5 avait disparu du dialogue pour cette raison, et
# rien dans l'ecran ne le signalait. CommandSwitchWindow, elle, n'a pas
# cette limite.
mode = None
try:
    mode = forms.CommandSwitchWindow.show(
        MODES,
        message=u"Volumes de zone - que faire ?",
    )
except Exception:
    # repli : le dialogue Revit, tronque a quatre - on le dit.
    mode = forms.alert(
        u"Volumes de zone - que faire ?\n\n"
        u"ATTENTION : ce dialogue de repli n'affiche que les QUATRE premiers "
        u"modes.",
        title=u"bimflow - Renommer les volumes",
        options=MODES[:4],
    )
if not mode:
    script.exit()

ECRITURE = not mode.startswith(u"1")
MODE_TYPES = mode.startswith(u"3") or mode.startswith(u"4")
ESSAI = mode.startswith(u"3")
DIAGNOSTIC = mode.startswith(u"5")

if ECRITURE and NON_DETACHEE and not AUTORISER_NON_DETACHE:
    forms.alert(
        u"Maquette collaborative, et ce n'est pas une copie detachee.\n\n"
        u"Ce script ECRIT dans le modele : il ne tourne que sur une copie "
        u"detachee (R17). Rappel : IsWorkshared reste vrai apres un "
        u"detachement conservant les sous-projets - c'est IsDetached qui "
        u"tranche.\n\n"
        u"Rouvrir avec \"Detacher du fichier central\", puis relancer.",
        exitscript=True,
    )

# --------------------------------------------------------------------------
# 1. Lecture et classement - LECTURE SEULE, quel que soit le mode
# --------------------------------------------------------------------------

ids = list(
    FilteredElementCollector(doc)
    .OfCategory(BuiltInCategory.OST_Mass)
    .WhereElementIsNotElementType()
    .ToElementIds()
)
# R15 fait 8 : le collecteur est consomme AVANT toute resolution de propriete.

volumes = []
non_resolus = []        # (eid, nom, motif)
noms_familles = {}      # id famille -> nom actuel
element_famille = {}    # id famille -> ElementId
element_type = {}       # id volume -> ElementId du type

for eid in ids:
    el = doc.GetElement(eid)
    if el is None:
        continue
    if not isinstance(el, FamilyInstance):
        non_resolus.append((eid, None, u"volume qui n'est pas une instance de famille"))
        continue
    try:
        symbole = el.Symbol
        famille = symbole.Family
        nom = famille.Name
        in_situ = bool(famille.IsInPlace)
        fid = id_de(famille.Id)
    except Exception as err:
        non_resolus.append((eid, None, u"identite illisible : {0}".format(err)))
        continue

    if not in_situ:
        non_resolus.append((eid, nom, u"volume qui n'est pas in situ"))
        continue

    lu, motif = extraire(nom, CORRECTIONS)
    if lu is None:
        non_resolus.append((eid, nom, motif))
        continue
    zone, etage, nature, cle = lu

    try:
        bb = el.get_BoundingBox(None)
    except Exception as err:
        bb = None
    if bb is None:
        non_resolus.append((eid, nom, u"boite englobante absente"))
        continue

    try:
        nom_type = symbole.Name
    except Exception:
        nom_type = u""

    noms_familles[fid] = nom
    element_famille[fid] = famille.Id
    element_type[id_de(eid)] = symbole.Id

    volumes.append({
        "id": id_de(eid),
        "eid": eid,
        "fid": fid,
        "nom": nom,
        "type": nom_type,
        "zone": zone,
        "etage": etage,
        "nature": nature,
        "cle": cle,
        # le BAT de tri est deduit par classer(), du prefixe de la zone
        "xc": mm((bb.Min.X + bb.Max.X) / 2.0),
        "yc": mm((bb.Min.Y + bb.Max.Y) / 2.0),
        "zmin": mm(bb.Min.Z),
    })

ordonnes, colonnes = classer(volumes, NORD_LOCAL)

for v in ordonnes:
    v["nouveau"] = nom_de_famille(v["numero"], v["zone"], v["etage"],
                                  v["nature"], v["cle"])

# --- controles ------------------------------------------------------------

collisions = {}
for v in ordonnes:
    collisions.setdefault(v["nouveau"], []).append(v["id"])
collisions = dict([(k, ids_) for k, ids_ in collisions.items() if len(ids_) > 1])

# une meme famille peut porter plusieurs instances : elle n'a qu'UN nom
noms_par_famille = {}
for v in ordonnes:
    noms_par_famille.setdefault(v["fid"], set()).add(v["nouveau"])
familles_multiples = dict([(f, sorted(n)) for f, n in noms_par_famille.items()
                           if len(n) > 1])

incoherences = [(v["id"], v["nom"], incoherence_etage_nature(v["etage"], v["nature"]))
                for v in ordonnes
                if incoherence_etage_nature(v["etage"], v["nature"])]
etages_inconnus = sorted(set([v["etage"] for v in ordonnes
                              if v["etage"] not in ETAGES_CONNUS]))
dispersees = [c for c in colonnes if c["dispersion"] > 1.0]

BLOQUANT = bool(non_resolus) or bool(collisions) or bool(familles_multiples)

# --------------------------------------------------------------------------
# 2. Rapport de lecture
# --------------------------------------------------------------------------

out.print_md(u"# Renommage des volumes de zone")
out.print_md(
    u"Maquette : **{0}** &nbsp;|&nbsp; {1} &nbsp;|&nbsp; mode : **{2}**".format(
        doc.Title,
        u"copie detachee" if detache else
        (u"collaborative NON detachee" if collaboratif else u"non collaborative"),
        mode)
)
out.print_md(
    u"- **{0}** volume(s) classe(s), **{1}** colonne(s)\n"
    u"- **{2}** NON RESOLU(S)\n"
    u"- **{3}** collision(s) de nom final".format(
        len(ordonnes), len(colonnes), len(non_resolus), len(collisions))
)

out.print_md(u"## Decompte par BAT, dans l'ordre de parcours")
out.print_md(
    u"*BAT est le **prefixe de REF_Zone** : c'est lui qui trie. "
    u"`REF_Batiment`, que la cle peut surcharger, dit de quel batiment "
    u"releve un volume - il ne trie rien.*")
premier, dernier, nb_vol, nb_col = {}, {}, {}, {}
for v in ordonnes:
    premier.setdefault(v["bat"], v["numero"])
    dernier[v["bat"]] = v["numero"]
    nb_vol[v["bat"]] = nb_vol.get(v["bat"], 0) + 1
for c in colonnes:
    nb_col[c["batiment"]] = nb_col.get(c["batiment"], 0) + 1
tableau = [u"| BAT | Colonnes | Volumes | Plage |", u"|---|---:|---:|---|"]
for bat in sorted(nb_vol.keys(), key=lambda b: premier[b]):
    tableau.append(u"| **{0}** | {1} | {2} | `VOL_{3:03d}` -> `VOL_{4:03d}` |".format(
        bat, nb_col.get(bat, 0), nb_vol[bat], premier[bat], dernier[bat]))
out.print_md(u"\n".join(tableau))

if non_resolus:
    out.print_md(u"## NON RESOLUS - aucun ne sera renomme")
    for eid, nom, motif in non_resolus:
        out.print_md(u"- {0} `{1}` : {2}".format(lien_de(eid), texte(nom), motif))

if collisions:
    out.print_md(u"## COLLISIONS - deux volumes aboutiraient au meme nom")
    for nom, ids_ in sorted(collisions.items()):
        out.print_md(u"- `{0}` : {1}".format(nom, ids_))
    out.print_md(u"> Il manque une cle `sup` a l'un des deux.")

if familles_multiples:
    out.print_md(u"## UNE FAMILLE, DEUX NOMS VOULUS")
    for fid, noms in familles_multiples.items():
        out.print_md(u"- famille `{0}` (`{1}`) : {2}".format(
            fid, texte(noms_familles.get(fid)), u", ".join(noms)))
    out.print_md(
        u"> Cette famille porte plusieurs instances, qui ne tombent pas au "
        u"meme rang. Une famille n'a qu'un nom : a trancher dans Revit.")

if dispersees:
    out.print_md(u"## Colonnes dispersees - leurs volumes ne partagent pas un centre")
    for c in dispersees:
        out.print_md(u"- `{0}` : dispersion **{1:.0f} mm** sur {2} volume(s)".format(
            c["zone"], c["dispersion"], len(c["volumes"])))
    out.print_md(
        u"> Le classement reste valide - il trie sur le centre moyen - mais "
        u"une zone dont les tranches ne se superposent pas n'est pas une "
        u"colonne, et la chaine site_model le refusera (regle R1).")

if incoherences:
    out.print_md(u"## Etage et nature ne s'accordent pas - signale, PAS bloquant")
    for eid, nom, motif in incoherences:
        out.print_md(u"- {0} `{1}` : {2}".format(lien_de(eid), texte(nom), motif))

if etages_inconnus:
    out.print_md(u"## Etages hors de la liste connue *(liste ouverte)*")
    out.print_md(u", ".join([u"`{0}`".format(e) for e in etages_inconnus]))

# --------------------------------------------------------------------------
# 3. CSV
# --------------------------------------------------------------------------

ENTETE_CSV = u";".join([
    u"element_id", u"ancien_nom_famille", u"nouveau_nom_famille",
    u"ancien_nom_type", u"BAT", u"REF_Zone", u"REF_Etage",
    u"CLS_Nature_volume", u"cle", u"REF_Batiment", u"xc", u"yc", u"zmin",
])

FRAGMENTS_INTERDITS = ("onedrive", "\\work\\")


def champ(valeur):
    return texte(valeur).replace(u";", u",").replace(u"\n", u" ")


def ecrire_csv(resultats=None, suffixe=u""):
    """resultats : {id volume : nom reellement porte apres ecriture}."""
    lignes = [ENTETE_CSV]
    for v in ordonnes:
        nouveau = v["nouveau"]
        if resultats is not None:
            nouveau = resultats.get(v["id"], u"(NON RENOMME)")
        lignes.append(u";".join([
            champ(v["id"]), champ(v["nom"]), champ(nouveau), champ(v["type"]),
            champ(v["bat"]), champ(v["zone"]), champ(v["etage"]),
            champ(v["nature"]), champ(v["cle"] or u""),
            champ(ref_batiment(v["zone"], v["cle"])),
            champ(u"%.1f" % v["xc"]), champ(u"%.1f" % v["yc"]),
            champ(u"%.1f" % v["zmin"]),
        ]))
    defaut = u"renommage_volumes_{0}{1}".format(
        doc.Title.replace(u" ", u"_"), suffixe)
    for _ in range(3):
        chemin = forms.save_file(file_ext="csv", default_name=defaut)
        if not chemin:
            out.print_md(u"*CSV non ecrit (annule).*")
            return None
        if any(f in chemin.lower() for f in FRAGMENTS_INTERDITS):
            forms.alert(u"Ni OneDrive ni WORK : choisir un autre dossier.\n\n"
                        u"{0}".format(chemin))
            continue
        f = io.open(chemin, "w", encoding="utf-8-sig", newline="")
        try:
            f.write(u"\n".join(lignes))
        finally:
            f.close()
        out.print_md(u"**CSV** : `{0}` ({1} ligne(s))".format(
            chemin, len(lignes) - 1))
        return chemin
    return None


if not ECRITURE:
    # Le CSV n'est demande que la ou il sert : en simulation, et apres le
    # renommage des familles. Les modes de type n'en produisent pas.
    out.print_md(u"## Export du avant / apres")
    ecrire_csv()
    out.print_md(
        u"---\n**Simulation terminee.** Aucune transaction n'a ete ouverte, "
        u"rien n'a ete ecrit dans la maquette."
    )
    script.exit()

# --------------------------------------------------------------------------
# 4. Refus d'ecrire tant qu'un cas n'est pas tranche
# --------------------------------------------------------------------------

if BLOQUANT:
    out.print_md(
        u"---\n# ECRITURE REFUSEE\n"
        u"**{0} non resolu(s), {1} collision(s), {2} famille(s) a deux noms.** "
        u"Aucune transaction n'a ete ouverte.\n\n"
        u"Un renommage partiel laisserait la maquette a moitie dans chaque "
        u"motif, et le numero de chacun dependrait de qui a ete traite. Ces "
        u"cas se tranchent dans Revit, puis on relance.".format(
            len(non_resolus), len(collisions), len(familles_multiples))
    )
    script.exit()

# --------------------------------------------------------------------------
# 4 bis. DIAGNOSTIC - mode 5, trois familles, tout instrumente
#
# Mesure du 2026-09-24 : le mode 2 renomme 202 familles, la relecture
# immediate rend 202/202 au nom voulu, et pourtant l'audit suivant lit les
# ANCIENS noms sur les 202. Les cinq porteurs du nom sont d'accord entre eux
# (sonde du meme jour), donc ce n'est pas "j'ecris le mauvais champ".
#
# HYPOTHESE A TESTER ICI : renommer une famille in situ REMPLACE l'element
# Family. L'identifiant mis en cache designerait alors un element devenu
# orphelin - j'ecrirais dedans, je le relirais, j'y verrais mon nouveau nom,
# pendant que les instances continueraient de pointer ailleurs. Ce mode
# relit donc la famille DEUX fois apres chaque ecriture : par l'identifiant
# mis en cache, ET par l'instance. Si les deux divergent, la cause est la.
# --------------------------------------------------------------------------

if DIAGNOSTIC:

    from Autodesk.Revit.DB import BuiltInParameter

    cibles = ordonnes[:TAILLE_ESSAI]

    def etat(v, moment):
        """Une ligne de tableau : ce que chaque chemin de lecture rend."""
        el = doc.GetElement(v["eid"])
        par_instance_id = u"?"
        par_instance_nom = u"?"
        par_cache_nom = u"?"
        param_nom = u"?"
        try:
            famille_fraiche = el.Symbol.Family
            par_instance_id = u"{0}".format(id_de(famille_fraiche.Id))
            par_instance_nom = famille_fraiche.Name
        except Exception as err:
            par_instance_nom = u"(illisible : {0})".format(err)
        try:
            famille_cache = doc.GetElement(element_famille[v["fid"]])
            par_cache_nom = (famille_cache.Name if famille_cache is not None
                             else u"(element introuvable)")
        except Exception as err:
            par_cache_nom = u"(illisible : {0})".format(err)
        try:
            p = el.Symbol.get_Parameter(
                BuiltInParameter.SYMBOL_FAMILY_NAME_PARAM)
            param_nom = p.AsString() if p is not None else u"(absent)"
        except Exception as err:
            param_nom = u"(illisible : {0})".format(err)
        return (u"| {0} | `{1}` | `{2}` | `{3}` | `{4}` |".format(
            moment, par_instance_id, par_instance_nom, par_cache_nom,
            param_nom))

    out.print_md(u"---")
    out.print_md(u"# DIAGNOSTIC - essai instrumente sur {0} famille(s)".format(
        len(cibles)))
    out.print_md(
        u"Trois chemins de lecture, cote a cote, a chaque etape :\n\n"
        u"- **par l'instance** : `instance.Symbol.Family` - refait a chaque "
        u"lecture, c'est ce que voient l'audit et l'infobulle ;\n"
        u"- **par le cache** : `doc.GetElement(id releve AVANT)` - c'est ce "
        u"que le mode 2 ecrit, et ce que sa relecture lit ;\n"
        u"- **le parametre** `SYMBOL_FAMILY_NAME_PARAM` du type.\n\n"
        u"S'ils divergent, la cause est trouvee.")

    dialogue = TaskDialog(u"bimflow - Diagnostic de renommage")
    dialogue.MainInstruction = u"Renommer {0} famille(s), pas a pas ?".format(
        len(cibles))
    dialogue.MainContent = (
        u"Maquette : {0}\n\n"
        u"Une transaction PAR famille, et une relecture par trois chemins "
        u"apres chaque etape. Puis une regeneration, et une relecture de "
        u"plus.\n\n"
        u"Trois familles seulement : reversible a la main en une minute.".format(
            doc.Title)
    )
    dialogue.CommonButtons = (TaskDialogCommonButtons.Yes |
                              TaskDialogCommonButtons.No)
    dialogue.DefaultButton = TaskDialogResult.No
    if dialogue.Show() != TaskDialogResult.Yes:
        out.print_md(u"**Annule.** Rien n'a ete ecrit.")
        script.exit()

    ENTETE = (u"| Moment | Id famille vu par l'instance | Nom par l'instance "
              u"| Nom par le cache | SYMBOL_FAMILY_NAME_PARAM |\n"
              u"|---|---|---|---|---|")

    for v in cibles:
        out.print_md(u"## Volume `{0}` -> `{1}`".format(v["id"], v["nouveau"]))
        lignes = [ENTETE, etat(v, u"**avant**")]

        transaction = Transaction(doc, u"bimflow - diagnostic renommage")
        depart = transaction.Start()
        if depart != TransactionStatus.Started:
            out.print_md(u"**Transaction refusee** : `{0}`".format(depart))
            continue

        erreur = None
        try:
            famille = doc.GetElement(element_famille[v["fid"]])
            famille.Name = v["nouveau"]
        except Exception as err:
            erreur = err

        if erreur is None:
            lignes.append(etat(v, u"apres `Set`, AVANT commit"))
            etat_commit = transaction.Commit()
            lignes.append(etat(v, u"apres `Commit` ({0})".format(etat_commit)))
        else:
            transaction.RollBack()
            lignes.append(u"| **ECHEC du Set** | | `{0}` | | |".format(erreur))

        out.print_md(u"\n".join(lignes))

    # --- une regeneration, puis une derniere lecture ----------------------
    out.print_md(u"## Apres une regeneration du document")
    transaction = Transaction(doc, u"bimflow - diagnostic regeneration")
    etat_regen = u"(non ouverte)"
    if transaction.Start() == TransactionStatus.Started:
        try:
            doc.Regenerate()
            etat_regen = u"{0}".format(transaction.Commit())
        except Exception as err:
            transaction.RollBack()
            etat_regen = u"echec : {0}".format(err)
    lignes = [ENTETE]
    for v in cibles:
        lignes.append(etat(v, u"volume `{0}`".format(v["id"])))
    out.print_md(u"Regeneration : `{0}`".format(etat_regen))
    out.print_md(u"\n".join(lignes))

    # --- TEST B : le parametre du type est-il inscriptible ? --------------
    out.print_md(u"## Le parametre `SYMBOL_FAMILY_NAME_PARAM` est-il inscriptible ?")
    v = cibles[0]
    el = doc.GetElement(v["eid"])
    try:
        p = el.Symbol.get_Parameter(BuiltInParameter.SYMBOL_FAMILY_NAME_PARAM)
    except Exception as err:
        p = None
        out.print_md(u"Parametre illisible : `{0}`".format(err))
    if p is not None:
        out.print_md(u"- `IsReadOnly` : **{0}**".format(p.IsReadOnly))
        if not p.IsReadOnly:
            transaction = Transaction(doc, u"bimflow - diagnostic param famille")
            if transaction.Start() == TransactionStatus.Started:
                try:
                    rendu = p.Set(v["nouveau"])
                    etat_c = transaction.Commit()
                    out.print_md(u"- `Set()` a rendu **{0}**, commit `{1}`".format(
                        rendu, etat_c))
                except Exception as err:
                    transaction.RollBack()
                    out.print_md(u"- `Set()` a leve : `{0}` - tout annule".format(err))
            out.print_md(u"\n".join([ENTETE, etat(v, u"apres ecriture du parametre")]))
        else:
            out.print_md(
                u"- en lecture seule : ce n'est donc pas par la que "
                u"l'interface renomme.")

    out.print_md(
        u"---\n> **Comment lire ce tableau.** Si l'identifiant de famille vu "
        u"par l'instance CHANGE apres le renommage, l'element `Family` est "
        u"remplace : mon cache pointe alors sur un orphelin, et c'est la "
        u"cause. S'il ne change pas mais que les deux noms divergent, c'est "
        u"la lecture par le cache qui ment. S'ils restent d'accord et que le "
        u"nom retombe apres la regeneration, Revit restaure le nom depuis "
        u"ailleurs, et il faudra chercher ou."
    )
    script.exit()

# --------------------------------------------------------------------------
# 5. Renommage des FAMILLES - deux passes, un groupe de transactions
# --------------------------------------------------------------------------

if not MODE_TYPES:

    a_renommer = {}     # fid -> (avant, apres)
    for v in ordonnes:
        a_renommer[v["fid"]] = (v["nom"], v["nouveau"])
    inchanges = [f for f, (a, b) in a_renommer.items() if a == b]

    # Noms temporaires de la passe 1. Ni tilde ni aucun des caracteres que
    # Revit refuse : \ : { } [ ] | ; < > ? ` ~
    temporaires = dict([(fid, u"TMP_{0}".format(fid)) for fid in a_renommer])

    # GARDE, avant toute transaction : un nom temporaire ne doit heurter ni un
    # nom de famille existant, ni un nom final. Ici, aucune famille ne
    # s'appelle TMP_... et tous les noms finaux commencent par VOL_ - mais
    # cela ne doit pas etre vrai par chance sur la prochaine affaire.
    noms_existants = set()
    for _fid_ex in list(FilteredElementCollector(doc).OfClass(Family)
                        .ToElementIds()):
        _f_ex = doc.GetElement(_fid_ex)
        if _f_ex is None:
            continue
        try:
            noms_existants.add(_f_ex.Name)
        except Exception:
            continue
    noms_finaux = set([apres for avant, apres in a_renommer.values()])

    heurts = []
    for fid, provisoire in sorted(temporaires.items()):
        if provisoire in noms_existants:
            heurts.append((provisoire, u"une famille porte deja ce nom"))
        if provisoire in noms_finaux:
            heurts.append((provisoire, u"c'est aussi un nom final du lot"))
    if len(set(temporaires.values())) != len(temporaires):
        heurts.append((u"(plusieurs)", u"deux familles auraient le meme nom "
                                       u"temporaire"))

    if heurts:
        out.print_md(
            u"---\n# ECRITURE REFUSEE - noms temporaires en conflit\n"
            u"La passe 1 pose des noms `TMP_<id>` avant de poser les noms "
            u"finaux. Ceux-ci heurtent l'existant, et aucune transaction n'a "
            u"ete ouverte :")
        for nom, motif in heurts:
            out.print_md(u"- `{0}` : {1}".format(nom, motif))
        out.print_md(
            u"> Changer le prefixe temporaire en tete de script, ou renommer "
            u"a la main la famille qui gene. **Ne pas employer de tilde** : "
            u"Revit refuse l'antislash, les deux-points, les accolades, les "
            u"crochets, la barre verticale, le point-virgule, les chevrons, "
            u"le point d'interrogation, l'accent grave et le tilde.")
        script.exit()

    dialogue = TaskDialog(u"bimflow - Renommage des volumes de zone")
    dialogue.MainInstruction = u"Renommer {0} famille(s) ?".format(len(a_renommer))
    dialogue.MainContent = (
        u"Maquette : {0}\n"
        u"Fichier : {1}\n\n"
        u"{2} famille(s) portent deja leur nom final.\n\n"
        u"Deux passes : chaque famille prend d'abord un nom temporaire, puis "
        u"son nom final - sans quoi un nom deja porte par une autre famille "
        u"ferait echouer le lot. Les deux passes sont annulees ensemble si "
        u"l'une echoue.\n\n"
        u"Script NON EPROUVE. Verifier ensuite dans l'arborescence du projet "
        u"et avec le bouton Audit volumes.".format(
            doc.Title, doc.PathName or u"(jamais enregistree)", len(inchanges))
    )
    dialogue.CommonButtons = (TaskDialogCommonButtons.Yes |
                              TaskDialogCommonButtons.No)
    dialogue.DefaultButton = TaskDialogResult.No
    if dialogue.Show() != TaskDialogResult.Yes:
        out.print_md(u"---\n**Annule par l'utilisateur.** Rien n'a ete ecrit.")
        script.exit()

    groupe = TransactionGroup(doc, u"bimflow - renommage des volumes")
    groupe.Start()
    echec = None
    faits = 0

    try:
        t1 = Transaction(doc, u"bimflow - noms temporaires")
        t1.Start()
        try:
            for fid in sorted(a_renommer.keys()):
                famille = doc.GetElement(element_famille[fid])
                if famille is None:
                    raise Exception(u"famille {0} introuvable".format(fid))
                famille.Name = temporaires[fid]
        except Exception:
            t1.RollBack()
            raise
        if t1.Commit() != TransactionStatus.Committed:
            raise Exception(u"passe 1 : commit refuse par Revit")

        t2 = Transaction(doc, u"bimflow - noms definitifs")
        t2.Start()
        try:
            for fid in sorted(a_renommer.keys()):
                famille = doc.GetElement(element_famille[fid])
                if famille is None:
                    raise Exception(u"famille {0} introuvable".format(fid))
                # compteur AVANT l'appel qui peut lever
                faits += 1
                famille.Name = a_renommer[fid][1]
        except Exception:
            t2.RollBack()
            raise
        if t2.Commit() != TransactionStatus.Committed:
            raise Exception(u"passe 2 : commit refuse par Revit")
    except Exception as err:
        echec = err

    if echec is None:
        groupe.Assimilate()
    else:
        groupe.RollBack()
        faits = 0

    out.print_md(u"---")
    out.print_md(u"# Renommage des familles")
    if echec is not None:
        out.print_md(
            u"## ECHEC - tout a ete annule\n`{0}`\n\n"
            u"**La maquette est dans l'etat ou elle etait avant le clic.** Les "
            u"deux passes ont ete annulees ensemble : aucune famille ne reste "
            u"avec un nom temporaire.".format(echec)
        )
        script.exit()

    # relecture du resultat REEL, famille par famille
    reels = {}
    for v in ordonnes:
        famille = doc.GetElement(element_famille[v["fid"]])
        try:
            reels[v["id"]] = famille.Name if famille is not None else u"(introuvable)"
        except Exception as err:
            reels[v["id"]] = u"(illisible : {0})".format(err)
    conformes = len([v for v in ordonnes if reels.get(v["id"]) == v["nouveau"]])

    out.print_md(
        u"**{0} famille(s) renommee(s)** en deux passes, un seul groupe de "
        u"transactions.\n\n"
        u"**{1} volume(s) sur {2}** portent le nom voulu, verifie par "
        u"relecture apres ecriture.".format(len(a_renommer), conformes,
                                            len(ordonnes))
    )
    # Un seul CSV, ecrit APRES : il porte l'ancien nom, le nom voulu et le
    # nom reellement porte. Le demander aussi avant l'ecriture faisait deux
    # fichiers quasi identiques, et deux boites de dialogue.
    out.print_md(u"## Export du avant / apres, releve APRES ecriture")
    ecrire_csv(reels)
    out.print_md(
        u"> **Suite.** Passer **Audit volumes** pour verifier, puis **MAJ "
        u"params volumes**. Les noms de TYPE se traitent a part, par le mode "
        u"3 (essai sur {0}) avant le mode 4.".format(TAILLE_ESSAI)
    )
    script.exit()

# --------------------------------------------------------------------------
# 6. Noms de TYPE - l'essai d'abord, et il rapporte ce qu'il observe
# --------------------------------------------------------------------------

# L'ESSAI D'ABORD, ET LE SCRIPT LE VERIFIE. Le mode 4 ne part sur les 202
# que si au moins un volume porte deja le nom de type voulu - c'est-a-dire
# si le mode 3 est passe. Sans cette garde, un clic de trop sautait
# exactement l'etape qui protege des 202.
if not ESSAI:
    temoins = [v for v in ordonnes if v["type"] == NOM_TYPE_VOULU]
    if not temoins:
        out.print_md(u"---")
        out.print_md(
            u"# MODE 4 REFUSE - l'essai n'a pas eu lieu\n"
            u"Aucun volume ne porte encore le nom de type `{0}` : le mode 3 "
            u"n'est pas passe, ou il a echoue.\n\n"
            u"**Ce que l'essai protege.** Personne n'a mesure si Revit "
            u"accepte deux types homonymes dans deux familles in situ "
            u"distinctes. S'il refuse, mieux vaut l'apprendre sur {1} volumes "
            u"que sur {2}.\n\n"
            u"Relancer le bouton et choisir le **mode 3**.".format(
                NOM_TYPE_VOULU, TAILLE_ESSAI, len(ordonnes))
        )
        script.exit()

cibles = ordonnes[:TAILLE_ESSAI] if ESSAI else ordonnes
deja = [v for v in cibles if v["type"] == NOM_TYPE_VOULU]
a_faire = [v for v in cibles if v["type"] != NOM_TYPE_VOULU]

out.print_md(u"---")
out.print_md(u"# Noms de type -> `{0}`".format(NOM_TYPE_VOULU))
out.print_md(
    u"{0} volume(s) vise(s), dont **{1}** portent deja ce nom de type.\n\n"
    u"> **Ce qui est en jeu, et qui n'est PAS connu.** Chaque volume in situ "
    u"est sa propre famille : deux types homonymes vivraient donc dans deux "
    u"familles distinctes, ce que Revit devrait accepter. Mais il peut "
    u"imposer une unicite plus large sur les familles in situ. **Personne ne "
    u"l'a mesure.** C'est l'objet de cet essai.".format(
        len(cibles), len(deja))
)

if not a_faire:
    out.print_md(u"*Rien a faire : tous portent deja le nom voulu.*")
    script.exit()

dialogue = TaskDialog(u"bimflow - Noms de type")
dialogue.MainInstruction = u"Renommer le type de {0} volume(s) en \"{1}\" ?".format(
    len(a_faire), NOM_TYPE_VOULU)
dialogue.MainContent = (
    u"Maquette : {0}\n\n"
    u"{1}\n\n"
    u"Comportement de Revit INCONNU sur ce point : si le deuxieme type "
    u"homonyme est refuse, le script s'arrete, annule tout, et rapporte "
    u"l'erreur exacte. Il n'essaiera aucun repli.".format(
        doc.Title,
        u"ESSAI sur {0} volume(s) - a lire avant de traiter les {1}.".format(
            len(a_faire), len(ordonnes)) if ESSAI else
        u"TOUS les volumes. A ne lancer qu'APRES un essai concluant.")
)
dialogue.CommonButtons = (TaskDialogCommonButtons.Yes |
                          TaskDialogCommonButtons.No)
dialogue.DefaultButton = TaskDialogResult.No
if dialogue.Show() != TaskDialogResult.Yes:
    out.print_md(u"**Annule par l'utilisateur.** Rien n'a ete ecrit.")
    script.exit()

journal = []
echec = None
transaction = Transaction(doc, u"bimflow - noms de type des volumes")
if transaction.Start() != TransactionStatus.Started:
    forms.alert(u"Revit a refuse d'ouvrir la transaction.", exitscript=True)

try:
    for v in a_faire:
        symbole = doc.GetElement(element_type[v["id"]])
        if symbole is None:
            raise Exception(u"type du volume {0} introuvable".format(v["id"]))
        journal.append((v["id"], v["type"]))
        symbole.Name = NOM_TYPE_VOULU
except Exception as err:
    echec = err

if echec is None:
    etat = transaction.Commit()
    if etat != TransactionStatus.Committed:
        echec = u"Commit refuse par Revit (etat : {0})".format(etat)
else:
    transaction.RollBack()

out.print_md(u"## Resultat de l'{0}".format(u"essai" if ESSAI else u"execution"))

if echec is not None:
    out.print_md(
        u"### REVIT A REFUSE - tout a ete annule\n"
        u"Erreur exacte, telle que l'API l'a rendue :\n\n"
        u"```\n{0}\n```\n\n"
        u"**{1} type(s) avaient ete traites avant le refus.** L'hypothese "
        u"\"deux types homonymes dans deux familles in situ distinctes sont "
        u"acceptes\" est donc FAUSSE, au moins dans ce cas. C'est un fait "
        u"mesure, a porter en fiche.\n\n"
        u"Aucun repli n'est tente : le nom de type voulu se decidera en "
        u"connaissance de cause.".format(echec, len(journal))
    )
    script.exit()

# relecture : ce que les types portent VRAIMENT
reels = {}
for v in cibles:
    symbole = doc.GetElement(element_type[v["id"]])
    try:
        reels[v["id"]] = symbole.Name if symbole is not None else u"(introuvable)"
    except Exception as err:
        reels[v["id"]] = u"(illisible : {0})".format(err)
conformes = len([v for v in cibles if reels.get(v["id"]) == NOM_TYPE_VOULU])

out.print_md(
    u"**{0} type(s) renomme(s)**, et **{1} sur {2}** portent bien "
    u"`{3}` a la relecture.".format(
        len(a_faire), conformes, len(cibles), NOM_TYPE_VOULU)
)
lignes = [u"| Volume | Type avant | Type apres |", u"|---|---|---|"]
for v in cibles:
    lignes.append(u"| {0} | `{1}` | `{2}` |".format(
        lien_de(v["eid"]), texte(v["type"]), texte(reels.get(v["id"]))))
out.print_md(u"\n".join(lignes))

if ESSAI:
    out.print_md(
        u"> **Essai concluant sur {0} volume(s) : Revit a accepte des types "
        u"homonymes dans des familles in situ distinctes.** C'est un fait "
        u"mesure ce jour, sur cette maquette - pas une regle generale tant "
        u"qu'il n'est pas retrouve ailleurs.\n\n"
        u"> Le mode 4 traite les {1} volumes.".format(
            len(a_faire), len(ordonnes))
    )
else:
    out.print_md(
        u"> **Suite.** Passer **Audit volumes**, puis **MAJ params volumes**."
    )
