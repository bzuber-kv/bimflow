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
# STATUT : EPROUVE le 2026-09-24 sur The Study - 202 familles renommees,    #
# 202 types renommes, verifies par un AUDIT LANCE SEPAREMENT : 202/202 au   #
# motif VOL_nnn, numeros 001 a 202 sans trou, 202/202 types "Volume Ivion". #
# Le classement avait ete rejoue hors Revit d'abord, par                    #
# tools/volumes/dry_run_depuis_audit.py, qui appelle LE MEME CODE - et les  #
# deux ont rendu le meme resultat, au volume pres.                          #
# Puis EPROUVE SUR MAQUETTE CENTRALE le meme jour (thestudy_A_VOL) : essai  #
# sur un volume, lot complet, synchronisation et audit a chaque palier.     #
#############################################################################

QUATRE MODES, choisis au lancement. La simulation est le defaut, et aucune
transaction n'existe avant un choix explicite.

  1. Simuler               lecture seule, CSV du avant/apres
  2. ESSAI sur UN volume   ecriture, une seule famille, puis arret
  3. Renommer les familles ecriture, en DEUX PASSES
  4. Noms de type          ecriture, en une passe

L'ESSAI SUR UN SEUL VOLUME existe pour une question que la simulation ne
peut pas poser : elle ne teste que la LECTURE. Un nom de famille releve des
standards de projet, pas des elements ; en travail partage, le modifier
demande un emprunt exclusif que Revit peut refuser [hypothese, non mesuree
au 2026-09-24]. L'essai ecrit pour de vrai, sur un volume choisi parmi ceux
dont le nom vise est libre, et rapporte ce que Revit rend - sans repli
invente. Un refus serait un fait mesure a porter en fiche : une contrainte
structurante pour tout outil Keovia qui renomme des familles sur ACC.

MAQUETTE CENTRALE. Ce script ne refuse plus d'ecrire sur une maquette
collaborative non detachee. Il demande une confirmation qui NOMME le
fichier, ANNONCE le nombre d'elements concernes et fait cocher que l'on est
seul dessus (ACT-052 (2)). Sur copie detachee, rien ne change. La regle vit
dans lib\\bimflow_maquette.py, une seule fois pour les trois boutons.

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

AUCUN script.exit() APRES UNE ECRITURE, et c'est la regle la plus chere de
la journee. script.exit() appelle sys.exit(), donc leve SystemExit : la
commande externe rend Cancelled, et Revit ANNULE tout ce qu'elle a modifie -
transactions commitees comprises, sans exception, sans message, sans trace.
Mesure du 2026-09-24 : les modes qui sortaient ainsi voyaient leurs 202
renommages defaits au run suivant ; ceux qui tombaient a la fin du fichier
persistaient. Six hypotheses sont mortes avant celle-la.
Controle : tools/volumes/verifier_sorties_apres_ecriture.py

LES TYPES HOMONYMES [mesure le 2026-09-24]. Chaque volume in situ est sa
propre famille, et Revit accepte 202 types nommes pareil dans 202 familles
distinctes. L'essai sur trois volumes qui protegeait cette inconnue a ete
supprime : l'inconnue est levee.

bimflow - volumes de zone, mode ecriture - Keovia Solutions inc.
"""

__title__ = "Renommer\nvolumes"
__author__ = "Keovia Solutions inc."

# --------------------------------------------------------------------------
# PARAMETRES
# --------------------------------------------------------------------------

# Nom de type voulu pour tous les volumes.
NOM_TYPE_VOULU = "Volume Ivion"

# Nord local par groupe de batiments, en degres. PREVU, NON ACTIF : {"SE": 6.6}
# ferait pivoter les centres des colonnes de SE avant le tri. Personne n'a
# mesure que cela ameliore l'ordre, et changer le tri change tous les numeros.
NORD_LOCAL = {}

# Le drapeau AUTORISER_NON_DETACHE a disparu le 2026-09-24 : il n'existait
# que pour contourner un refus qui n'existe plus. Une maquette centrale se
# traite desormais par une confirmation, pas par une constante en tete de
# fichier que personne ne pense a remettre a False.

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
    from bimflow_maquette import (etat as etat_maquette, mot_de_letat,
                                  proprietaire, confirmer_centrale)
except ImportError:
    from pyrevit import forms as _formulaires
    _formulaires.alert(
        u"Modules partages bimflow_noms / bimflow_volumes / bimflow_maquette "
        u"introuvables.\n\n"
        u"Ils doivent se trouver dans bimflow.extension\\lib\\. Sans eux, ni "
        u"le decoupage des noms, ni le classement spatial, ni la porte "
        u"d'entree des ecritures ne sont disponibles, et ce script ne "
        u"s'execute pas.",
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

# Rappel : IsWorkshared reste True apres un detachement conservant les
# sous-projets. C'est IsDetached qui tranche, et lui seul - bimflow_maquette
# est le seul endroit ou cette regle est ecrite.
collaboratif, detache, CENTRALE = etat_maquette(doc)

MODES = [u"1 - Simuler (lecture seule, aucune ecriture)",
         u"2 - ESSAI : renommer UN SEUL volume (ECRIT)",
         u"3 - Renommer les familles (ECRIT dans la maquette)",
         u"4 - Noms de type -> \"{0}\" (ECRIT)".format(NOM_TYPE_VOULU)]

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
MODE_ESSAI = mode.startswith(u"2")
MODE_TYPES = mode.startswith(u"4")

out.print_md(u"**Maquette** : `{0}` - {1}".format(
    doc.Title, mot_de_letat(collaboratif, detache)))

# La confirmation « maquette centrale » ne se pose PAS ici : elle annonce le
# nombre d'elements concernes, et ce nombre n'existe qu'apres la lecture.
# Elle est au bloc 3 bis, juste avant la premiere transaction.

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
# 3 bis. Maquette centrale : la porte, pas le mur
#
# Jusqu'au 2026-09-24, ce bloc etait un REFUS. Il laisse passer desormais,
# apres une confirmation qui nomme le fichier et annonce le nombre d'elements
# concernes - d'ou sa place ici, apres la lecture : avant, ce nombre n'existe
# pas. Sur copie detachee, rien de tout cela ne s'affiche : le comportement
# des trois boutons y est inchange.
# --------------------------------------------------------------------------

if CENTRALE:
    if MODE_ESSAI:
        _operation = u"ESSAI - renommer la famille d'UN SEUL volume"
        _nb, _quoi = 1, u"famille de volume"
        _consequence = (u"L'essai s'arrete apres ce volume, quoi qu'il arrive, "
                        u"et rapporte exactement ce que Revit rend.")
    elif MODE_TYPES:
        _operation = u"Renommer les NOMS DE TYPE en \"{0}\"".format(NOM_TYPE_VOULU)
        _nb, _quoi = len(ordonnes), u"volume(s) vises"
        _consequence = (u"Ceux qui portent deja ce nom de type seront ignores ; "
                        u"le compte exact est dans la boite suivante. Une seule "
                        u"transaction : un echec annule tout le lot.")
    else:
        _operation = u"Renommer les FAMILLES au motif VOL_nnn"
        _nb, _quoi = len(ordonnes), u"famille(s) de volume"
        _consequence = (u"Deux passes dans un meme groupe de transactions : "
                        u"un echec annule les deux.")

    if not confirmer_centrale(doc, _operation, _nb, _quoi, _consequence):
        out.print_md(
            u"---\n**Annule.** Rien n'a ete ecrit.\n\n"
            u"> La confirmation « maquette centrale » demande un Oui **et** la "
            u"case « je suis seul sur cette maquette ». Les deux, parce que "
            u"c'est le modele de production."
        )
        script.exit()

# --------------------------------------------------------------------------
# 4. Refus d'ecrire tant qu'un cas n'est pas tranche
#
# L'ESSAI N'EST PAS CONCERNE : il ne traite qu'un volume, choisi parmi ceux
# qui sont propres, et sa question n'est pas « le lot est-il pret ? » mais
# « Revit me laisse-t-il ecrire ici ? ». Repondre a la seconde n'exige pas
# d'avoir resolu la premiere.
# --------------------------------------------------------------------------

if BLOQUANT and not MODE_ESSAI:
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
# 4 bis. ESSAI SUR UN SEUL VOLUME
#
# A QUOI IL SERT. Un nom de famille releve des STANDARDS DE PROJET, pas des
# elements. En travail partage, modifier un standard demande un emprunt
# EXCLUSIF, que Revit peut refuser si un autre utilisateur le detient
# [hypothese, non mesuree au 2026-09-24]. La simulation ne le detectera
# jamais : elle ne teste que la lecture. Cet essai ecrit pour de vrai, sur UN
# volume, et rapporte ce que Revit rend - meme raisonnement que l'essai sur
# trois types, qui a servi.
#
# CE QU'IL NE FAIT PAS. Aucun repli invente. Si Revit refuse, l'erreur exacte
# est imprimee telle que l'API la rend, et c'est un FAIT MESURE a porter en
# fiche : ce serait une contrainte structurante pour tout outil Keovia qui
# renomme des familles sur une maquette ACC.
#
# LE CHOIX DU VOLUME. Le premier de l'ordre de classement dont le nom doit
# changer ET dont le nom vise n'est porte par aucune famille. Cette seconde
# condition evite d'echouer sur un doublon - ce serait un echec vrai, mais
# pas celui qu'on mesure ici. Le volume traite porte donc son nom DEFINITIF :
# rien a nettoyer, rien a defaire.
# --------------------------------------------------------------------------

if MODE_ESSAI:

    noms_de_familles = set()
    for _fid_ex in list(FilteredElementCollector(doc).OfClass(Family)
                        .ToElementIds()):
        _f_ex = doc.GetElement(_fid_ex)
        if _f_ex is None:
            continue
        try:
            noms_de_familles.add(_f_ex.Name)
        except Exception:
            continue

    candidat = None
    ecartes = []
    for v in ordonnes:
        if v["nom"] == v["nouveau"]:
            ecartes.append((v, u"porte deja son nom final"))
            continue
        if v["nouveau"] in noms_de_familles:
            ecartes.append((v, u"une famille porte deja `{0}`".format(v["nouveau"])))
            continue
        candidat = v
        break

    out.print_md(u"---")
    out.print_md(u"# ESSAI sur un seul volume")

    if BLOQUANT:
        out.print_md(
            u"> **Le lot complet serait refuse en l'etat** ({0} non resolu(s), "
            u"{1} collision(s), {2} famille(s) a deux noms). L'essai passe "
            u"quand meme : il ne demande pas si le lot est pret, il demande si "
            u"Revit laisse ecrire ici.".format(
                len(non_resolus), len(collisions), len(familles_multiples))
        )

    if candidat is None:
        out.print_md(
            u"## Aucun volume ne convient - rien n'a ete ecrit\n"
            u"Sur {0} volume(s) lus, aucun ne remplit les deux conditions : "
            u"son nom doit changer, et le nom vise doit etre libre.".format(
                len(ordonnes))
        )
        for v, motif in ecartes[:10]:
            out.print_md(u"- {0} `{1}` : {2}".format(
                lien_de(v["eid"]), texte(v["nom"]), motif))
        if len(ecartes) > 10:
            out.print_md(u"- *... et {0} autre(s).*".format(len(ecartes) - 10))
        out.print_md(
            u"> Si tous portent deja leur nom final, l'essai n'a plus d'objet : "
            u"passer au mode 3. Sinon, trancher les doublons dans Revit."
        )
        script.exit()   # rien n'a ete ecrit : cette sortie est legitime

    statut, qui = proprietaire(doc, element_famille[candidat["fid"]])
    out.print_md(
        u"**Volume choisi** : {0}\n\n"
        u"| | |\n|---|---|\n"
        u"| nom actuel | `{1}` |\n"
        u"| nom vise | `{2}` |\n"
        u"| zone | `{3}` |\n"
        u"| reservation | {4} |\n"
        u"| proprietaire | {5} |\n".format(
            lien_de(candidat["eid"]), texte(candidat["nom"]),
            texte(candidat["nouveau"]), texte(candidat["zone"]),
            texte(statut) or u"*illisible*",
            texte(qui) or u"*personne, ou illisible*")
    )
    out.print_md(
        u"> La reservation lue ci-dessus porte sur l'ELEMENT famille. Elle ne "
        u"dit pas ce que Revit fera d'un standard de projet : c'est justement "
        u"ce que l'ecriture va montrer."
    )

    dialogue = TaskDialog(u"bimflow - Essai sur un volume")
    dialogue.MainInstruction = u"Renommer UNE famille, pour voir ?"
    dialogue.MainContent = (
        u"Maquette : {0}\n\n"
        u"`{1}`\n   ->   `{2}`\n\n"
        u"Une seule famille, une seule transaction. Le script s'arrete "
        u"ensuite, quel que soit le resultat.\n\n"
        u"Si Revit refuse, tout est annule et l'erreur exacte est rapportee - "
        u"aucun repli n'est tente.".format(
            doc.Title, texte(candidat["nom"]), texte(candidat["nouveau"]))
    )
    dialogue.CommonButtons = (TaskDialogCommonButtons.Yes |
                              TaskDialogCommonButtons.No)
    dialogue.DefaultButton = TaskDialogResult.No
    if dialogue.Show() != TaskDialogResult.Yes:
        out.print_md(u"**Annule par l'utilisateur.** Rien n'a ete ecrit.")
        script.exit()   # rien n'a ete ecrit : cette sortie est legitime

    echec = None
    etat_commit = None
    transaction = Transaction(doc, u"bimflow - essai de renommage")
    if transaction.Start() != TransactionStatus.Started:
        # Revit refuse d'OUVRIR la transaction : c'est deja un resultat.
        out.print_md(
            u"## REVIT A REFUSE D'OUVRIR LA TRANSACTION\n"
            u"Rien n'a ete ecrit. Sur une maquette centrale, c'est le signe "
            u"que le document n'est pas modifiable depuis cette commande - "
            u"maquette ouverte en lecture seule, ou transaction deja ouverte "
            u"ailleurs.\n\n"
            u"**Fait mesure**, a porter en fiche avec la date et le nom de la "
            u"maquette."
        )
        script.exit()   # rien n'a ete ecrit : cette sortie est legitime

    try:
        famille = doc.GetElement(element_famille[candidat["fid"]])
        if famille is None:
            raise Exception(u"famille {0} introuvable".format(candidat["fid"]))
        famille.Name = candidat["nouveau"]
    except Exception as err:
        echec = err

    if echec is None:
        etat_commit = transaction.Commit()
        if etat_commit != TransactionStatus.Committed:
            echec = u"Commit refuse par Revit (etat : {0})".format(etat_commit)
    else:
        transaction.RollBack()

    out.print_md(u"## Resultat")

    if echec is not None:
        out.print_md(
            u"### REVIT A REFUSE - tout a ete annule\n"
            u"Erreur exacte, telle que l'API l'a rendue :\n\n"
            u"```\n{0}\n{1}\n```\n\n"
            u"**Ce qu'il faut en retenir, et le porter en fiche comme FAIT "
            u"MESURE** (avec la date, le nom de la maquette et l'etat de "
            u"reservation ci-dessus) : renommer une famille in situ sur une "
            u"maquette centrale echoue dans ces conditions. Ce serait une "
            u"contrainte structurante pour tout outil Keovia qui renomme des "
            u"familles sur une maquette ACC - et la reponse serait alors de "
            u"travailler sur copie detachee, ou d'obtenir l'emprunt exclusif "
            u"avant de lancer.\n\n"
            u"Aucun repli n'est tente. La maquette est dans l'etat ou elle "
            u"etait avant le clic.".format(
                type(echec).__name__ if isinstance(echec, Exception) else u"",
                echec)
        )
    else:
        relu = u"(illisible)"
        try:
            famille = doc.GetElement(element_famille[candidat["fid"]])
            relu = famille.Name if famille is not None else u"(introuvable)"
        except Exception as err:
            relu = u"(illisible : {0})".format(err)

        out.print_md(
            u"### Revit a accepte\n"
            u"La famille porte maintenant `{0}` a la relecture "
            u"{1}.\n\n"
            u"**Ce que cela prouve, et rien de plus** : l'API a pu ecrire un "
            u"nom de famille sur cette maquette, a cet instant, avec les "
            u"droits de cet utilisateur. Cela ne dit pas que le lot de {2} "
            u"passera - un autre utilisateur peut detenir un autre standard.\n\n"
            u"**Ce que cela ne prouve pas encore** : que l'ecriture TIENT. "
            u"Seule une execution SEPAREE d'**Audit volumes** le dira - c'est "
            u"la lecon du 2026-09-24, et elle a coute une journee.".format(
                texte(relu),
                u"(conforme)" if relu == candidat["nouveau"] else u"**(DIFFERENT du nom vise)**",
                len(ordonnes))
        )
        out.print_md(
            u"> **Suite.** Sauvegarder, synchroniser, relancer **Audit "
            u"volumes**. Si le nom a tenu, le mode 3 peut traiter le lot."
        )
    # PAS de script.exit() ici : une ecriture a eu lieu, et sortir ferait
    # rendre Cancelled a la commande - Revit annulerait ce qu'on vient de
    # commiter. C'est exactement le defaut du 2026-09-24.

# --------------------------------------------------------------------------
# --------------------------------------------------------------------------
# 5. Renommage des FAMILLES - deux passes, un groupe de transactions
#
# AUCUN script.exit() APRES UNE ECRITURE, dans ce bloc ni dans les suivants.
# Mesure du 2026-09-24 : script.exit() appelle sys.exit(), leve SystemExit,
# et la commande externe rend alors Cancelled - ce qui fait ANNULER PAR REVIT
# tout ce qu'elle a modifie. Les blocs qui sortaient ainsi voyaient leurs
# renommages defaits ; ceux qui tombaient a la fin du fichier ont persiste.
# Les sorties prematurees ne sont conservees que la ou RIEN n'a ete ecrit -
# refus, annulation, lot vide : la, une annulation par Revit n'enleve rien.
# --------------------------------------------------------------------------

if not MODE_TYPES and not MODE_ESSAI:

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
        u"Verifier ensuite avec le bouton Audit volumes, dans une execution "
        u"SEPAREE : c'est elle qui prouve que l'ecriture a tenu.".format(
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
        u"> **Suite.** Passer **Audit volumes** pour verifier - dans une "
        u"execution SEPAREE, c'est elle qui prouve que l'ecriture a tenu - "
        u"puis **MAJ params volumes**. Les noms de type se traitent a part, "
        u"par le mode 3."
    )
    # PAS de script.exit() ici : il ferait rendre Cancelled a la commande, et
    # Revit annulerait les 202 renommages qu'on vient de commiter.

# --------------------------------------------------------------------------
# 6. Noms de TYPE - l'essai d'abord, et il rapporte ce qu'il observe
# 6. Noms de TYPE - une seule etape depuis le 2026-09-24
# --------------------------------------------------------------------------
#
# L'essai sur trois volumes a ete supprime : il existait pour une inconnue
# qui est levee. MESURE du 2026-09-24 sur The Study : Revit accepte 202 types
# homonymes dans 202 familles in situ distinctes, et les noms tiennent a
# travers sauvegardes, changements de fenetre et executions successives.
#
# Les modes 1, 2 et 3 n'entrent pas ici. Avant le 2026-09-24, ils en
# sortaient par script.exit() - ce qui faisait rendre Cancelled a la commande
# et annulait leurs ecritures. La porte est donc fermee par un test, jamais
# par une sortie.
if MODE_TYPES:

    cibles = ordonnes
    deja = [v for v in cibles if v["type"] == NOM_TYPE_VOULU]
    a_faire = [v for v in cibles if v["type"] != NOM_TYPE_VOULU]

    out.print_md(u"---")
    out.print_md(u"# Noms de type -> `{0}`".format(NOM_TYPE_VOULU))
    out.print_md(
        u"{0} volume(s) vise(s), dont **{1}** portent deja ce nom de type.\n\n"
        u"> **Ce qui est acquis.** Chaque volume in situ est sa propre "
        u"famille, et Revit accepte des types homonymes dans des familles "
        u"distinctes : mesure du 2026-09-24 sur The Study, 202 types nommes "
        u"`{2}` dans 202 familles, noms tenus a travers sauvegardes et "
        u"executions successives.".format(
            len(cibles), len(deja), NOM_TYPE_VOULU)
    )

    if not a_faire:
        out.print_md(u"*Rien a faire : tous portent deja le nom voulu.*")
        script.exit()

    dialogue = TaskDialog(u"bimflow - Noms de type")
    dialogue.MainInstruction = u"Renommer le type de {0} volume(s) en \"{1}\" ?".format(
        len(a_faire), NOM_TYPE_VOULU)
    dialogue.MainContent = (
        u"Maquette : {0}\n\n"
        u"{1} volume(s) a traiter, sur {2}. Les autres portent deja ce nom.\n\n"
        u"Une seule transaction : si un renommage echoue, TOUT est annule et "
        u"l'erreur exacte est rapportee. Aucun repli n'est tente.".format(
            doc.Title, len(a_faire), len(ordonnes))
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

    out.print_md(u"## Resultat de l'execution")

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

    out.print_md(
        u"> **Suite.** Passer **Audit volumes** - dans une execution SEPAREE, "
        u"c'est elle qui prouve que l'ecriture a tenu - puis **MAJ params "
        u"volumes**."
    )
