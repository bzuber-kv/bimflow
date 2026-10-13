# -*- coding: utf-8 -*-
"""Renommer selon table - applique une table de correspondance au modele actif.

#############################################################################
# STATUT : NON EPROUVE dans Revit au 2026-10-13. Logique testee sous        #
# CPython (tests\test_bimflow_correspondance.py) et pre-simulee hors Revit  #
# sur deux photos de maquette. Ce script ECRIT en mode reel : le resultat   #
# affiche ne prouve rien, la verification se fait par une photo maquette    #
# relancee apres coup (R19 fait 6).                                         #
#############################################################################

SIMULATION PAR DEFAUT. Le bouton lit la table, verifie chaque ligne contre le
modele, affiche le plan complet et ecrit un rapport JSON date a cote de la
table - sans ouvrir aucune transaction. Le mode reel est derriere une case a
cocher, proposee seulement quand aucune ligne n'est refusee ; sur maquette
centrale, la confirmation de lib\\bimflow_maquette s'y ajoute.

CE QUI EST ECRIT en mode reel, dans un TransactionGroup de deux passes
(passe 1 : noms temporaires TMP_<id>, sans tilde ; passe 2 : noms finaux,
changements de type, parametres) - tout ou rien :
    niveaux            nom ; REF_Batiment (ou REF_Etage) selon la table
    quadrillages       nom ; type renomme, ou change si le type cible est
                       porte par un autre type (lib\\bimflow_correspondance)
    volumes in situ    nom de famille ; REF_Zone, REF_Etage, REF_Batiment
                       recalcules du NOUVEAU nom (lib\\bimflow_noms) ;
                       REF_Id seulement sur demande de la ligne ET doublon
                       mesure dans le modele
    vues               nom, si et seulement s'il contient un ancien nom de
                       niveau renomme (gabarits signales, jamais renommes)

Relations Copier/Controler des niveaux et quadrillages renommes : signalees,
jamais modifiees.

Parametres lus et ecrits par GUID ; les GUID viennent du socle versionne
(shared_parameters\\keovia_socle_parametres.txt), cherches par NOM.

Doc : docs\\renommer_selon_table.md

bimflow - Keovia Solutions inc. - 2026-10-13
"""

__title__ = "Renommer\nselon table"
__author__ = "Keovia Solutions inc."

import datetime
import io
import os
from collections import OrderedDict

import System

from pyrevit import revit, forms, script

from Autodesk.Revit.DB import (
    BuiltInCategory, ElementId, Family, FamilyInstance,
    FilteredElementCollector, FilteredWorksetCollector, Grid, Level,
    StorageType, Transaction, TransactionGroup, TransactionStatus, View,
    WorksetKind,
)
from Autodesk.Revit.UI import (TaskDialog, TaskDialogCommonButtons,
                               TaskDialogResult)

import bimflow_correspondance as C
import bimflow_photo as photo
from bimflow_maquette import (etat as etat_maquette, mot_de_letat,
                              confirmer_centrale)

doc = revit.doc
out = script.get_output()
md = photo.echapper_md

OUTIL = u"bimflow - Renommer selon table"


# --------------------------------------------------------------------------
# Petits lecteurs
# --------------------------------------------------------------------------

def id_de(eid):
    try:
        return int(eid.Value)
    except Exception:
        return None


def element_id(i):
    return ElementId(System.Int64(i))


def nom_de(el):
    try:
        return el.Name
    except Exception:
        return None


GUIDS = {}


def guid(texte):
    g = GUIDS.get(texte)
    if g is None:
        g = System.Guid(texte)
        GUIDS[texte] = g
    return g


def parametre(el, guid_texte):
    try:
        return el.get_Parameter(guid(guid_texte))
    except Exception:
        return None


def lire_params(el, guids):
    """{nom: {"valeur", "ecrivable"}} des parametres PRESENTS sur l'instance.
    Absent : pas de cle. Illisible : valeur NON_LU, non ecrivable."""
    d = OrderedDict()
    for nom, g in guids.items():
        p = parametre(el, g)
        if p is None:
            continue
        try:
            texte = p.StorageType == StorageType.String
            d[nom] = {u"valeur": p.AsString() if texte else p.AsValueString(),
                      u"ecrivable": bool(texte and not p.IsReadOnly)}
        except Exception:
            d[nom] = {u"valeur": photo.NON_LU, u"ecrivable": False}
    return d


def surveillance(el):
    """Texte decrivant une relation Copier/Controler, ou None."""
    morceaux = []
    try:
        if el.IsMonitoringLinkElement():
            n = len(list(el.GetMonitoredLinkElementIds()))
            morceaux.append(u"surveille {0} element(s) d'un lien".format(n))
    except Exception:
        pass
    try:
        if el.IsMonitoringLocalElement():
            n = len(list(el.GetMonitoredLocalElementIds()))
            morceaux.append(u"surveille {0} element(s) du modele".format(n))
    except Exception:
        pass
    return u" ; ".join(morceaux) or None


def ids(collecteur):
    return list(collecteur.ToElementIds())


# --------------------------------------------------------------------------
# Corps - une fonction, des return : aucun script.exit() (R19 fait 1)
# --------------------------------------------------------------------------

def main():
    if doc.IsFamilyDocument:
        forms.alert(u"Document famille : rien a traiter.")
        return

    collaboratif, detache, centrale = etat_maquette(doc)
    out.print_md(u"# Renommer selon table - {0}".format(md(doc.Title)))
    out.print_md(u"**Maquette** : {0} - {1}".format(
        md(doc.Title), mot_de_letat(collaboratif, detache)))

    fermes = []
    if collaboratif:
        for ws in FilteredWorksetCollector(doc).OfKind(WorksetKind.UserWorkset):
            if not ws.IsOpen:
                fermes.append(ws.Name)
    if fermes:
        out.print_md(
            u"> **{0} sous-projet(s) FERME(S)** : {1}. Leurs elements ne sont "
            u"pas charges ; une ligne dont l'element y est range sort « sans "
            u"objet » a tort.".format(len(fermes),
                                      md(u", ".join(sorted(fermes)))))

    chemin_table = forms.pick_file(file_ext="csv",
                                   title=u"Table de correspondance")
    if not chemin_table:
        out.print_md(u"**Annule** : aucune table choisie. Rien n'a ete lu ni "
                     u"ecrit.")
        return
    with io.open(chemin_table, "rb") as f:
        octets = f.read()
    lignes, erreurs, encodage = C.lire_table(octets)
    out.print_md(u"**Table** : {0} ({1} octets, {2}, {3} ligne(s) de "
                 u"donnees)".format(md(chemin_table), len(octets), encodage,
                                    len(lignes)))
    if erreurs:
        out.print_md(u"## Table illisible - rien n'est analyse")
        for e in erreurs:
            out.print_md(u"- {0}".format(md(e)))
        return

    # --- socle -----------------------------------------------------------
    dossier_lib = os.path.dirname(os.path.abspath(C.__file__))
    socle = photo.lire_socle(photo.chemin_socle(dossier_lib))
    g_niv, manque_n = photo.guids_requis(socle, C.PARAMS_NIVEAU)
    g_vol, manque_v = photo.guids_requis(socle, C.PARAMS_VOLUME)
    for nom in manque_n + manque_v:
        out.print_md(u"> `{0}` absent du socle : jamais lu ni ecrit.".format(
            nom))
    guid_de = dict(list(g_niv.items()) + list(g_vol.items()))

    # --- modele ------------------------------------------------------------
    # Collecteurs MATERIALISES avant toute resolution (CLAUDE.md, API Revit).
    modele = {u"niveaux": {}, u"quadrillages": {}, u"types_quadrillage": {},
              u"volumes": {}, u"familles": {}, u"vues": {}, u"autres": {}}
    for eid in ids(FilteredElementCollector(doc).OfClass(Level)):
        el = doc.GetElement(eid)
        modele[u"niveaux"][id_de(eid)] = {
            u"nom": nom_de(el), u"params": lire_params(el, g_niv),
            u"surveillance": surveillance(el)}
    for eid in ids(FilteredElementCollector(doc).OfCategory(
            BuiltInCategory.OST_Grids).WhereElementIsElementType()):
        modele[u"types_quadrillage"][id_de(eid)] = nom_de(doc.GetElement(eid))
    for eid in ids(FilteredElementCollector(doc).OfClass(Grid)):
        el = doc.GetElement(eid)
        modele[u"quadrillages"][id_de(eid)] = {
            u"nom": nom_de(el), u"type_id": id_de(el.GetTypeId()),
            u"surveillance": surveillance(el)}
    for eid in ids(FilteredElementCollector(doc).OfClass(Family)):
        modele[u"familles"][id_de(eid)] = nom_de(doc.GetElement(eid))
    for eid in ids(FilteredElementCollector(doc).OfCategory(
            BuiltInCategory.OST_Mass).WhereElementIsNotElementType()):
        el = doc.GetElement(eid)
        famille, fid, in_situ = None, None, None
        if isinstance(el, FamilyInstance):
            try:
                fam = el.Symbol.Family
                famille, fid, in_situ = fam.Name, id_de(fam.Id), bool(
                    fam.IsInPlace)
            except Exception:
                famille = photo.NON_LU
        modele[u"volumes"][id_de(eid)] = {
            u"famille": famille, u"famille_id": fid, u"in_situ": in_situ,
            u"params": lire_params(el, g_vol)}
    for eid in ids(FilteredElementCollector(doc).OfClass(View)):
        v = doc.GetElement(eid)
        modele[u"vues"][id_de(eid)] = {u"nom": nom_de(v),
                                       u"gabarit": bool(v.IsTemplate)}
    connus = set()
    for rub in (u"niveaux", u"quadrillages", u"volumes"):
        connus.update(modele[rub].keys())
    for l in lignes:
        try:
            i = int(l[u"id_revit"])
        except ValueError:
            continue
        if i in connus:
            continue
        el = doc.GetElement(element_id(i))
        if el is not None:
            cat = el.Category.Name if el.Category is not None else u"?"
            modele[u"autres"][i] = u"{0} « {1} »".format(cat, nom_de(el))

    # --- analyse -----------------------------------------------------------
    a = C.analyser(lignes, modele)
    refus = a.refus()
    afficher(a, fermes)

    # --- choix du mode ------------------------------------------------------
    reel = False
    if refus:
        TaskDialog.Show(OUTIL, u"{0} ligne(s) refusee(s) : le mode reel n'est "
                        u"pas propose. Rapport de simulation ecrit a cote de "
                        u"la table.".format(len(refus)))
    elif a.nb_operations() == 0:
        TaskDialog.Show(OUTIL, u"Aucune operation : le modele porte deja ce "
                        u"que dit la table.")
    else:
        d = TaskDialog(OUTIL)
        d.MainInstruction = u"Simulation terminee : {0} operation(s), aucun " \
                            u"refus.".format(a.nb_operations())
        d.MainContent = (
            u"Maquette : {0}\n\nLe plan complet est affiche dans la fenetre "
            u"de sortie.\n\nPar defaut, rien n'est ecrit. Pour appliquer, "
            u"cocher la case PUIS Oui.".format(doc.Title))
        d.VerificationText = u"Mode REEL : ecrire dans « {0} »".format(
            doc.Title)
        d.CommonButtons = (TaskDialogCommonButtons.Yes |
                           TaskDialogCommonButtons.No)
        d.DefaultButton = TaskDialogResult.No
        reel = (d.Show() == TaskDialogResult.Yes and
                d.WasVerificationChecked())
        if reel and centrale:
            reel = confirmer_centrale(
                doc, u"Appliquer la table de correspondance",
                a.nb_operations(), u"operation(s)",
                u"Deux passes en un TransactionGroup : un echec annule tout.")

    ecriture = None
    if reel:
        ecriture = ecrire(a, guid_de)
        afficher_ecriture(ecriture)
    else:
        out.print_md(u"---\n**SIMULATION** : aucune transaction ouverte, rien "
                     u"n'a ete ecrit dans la maquette.")

    rapport_json(a, chemin_table, octets, collaboratif, detache, fermes,
                 ecriture)


# --------------------------------------------------------------------------
# Affichage
# --------------------------------------------------------------------------

def afficher(a, fermes):
    out.print_md(u"## Comptes par categorie")
    lignes = [u"| Categorie | Appliquees | Refusees | Sans objet |",
              u"|---|---:|---:|---:|"]
    for cat, c in a.comptes().items():
        lignes.append(u"| {0} | {1} | {2} | {3} |".format(
            md(cat), c[C.APPLIQUEE], c[C.REFUSEE], c[C.SANS_OBJET]))
    out.print_md(u"\n".join(lignes))
    out.print_md(
        u"Operations prevues : renommages {0} ; changements de type {1} ; "
        u"parametres {2}.".format(
            u", ".join(u"{0} {1}".format(md(k), len(v))
                       for k, v in a.renommages.items()),
            len(a.retypages), len(a.parametres)))

    out.print_md(u"## Lignes refusees")
    refus = a.refus()
    if not refus:
        out.print_md(u"*Aucune.*")
    for r in refus:
        out.print_md(u"- ligne {0} - {1} {2} « {3} » : {4}".format(
            r.numero if r.numero is not None else u"-", md(r.categorie),
            r.id_revit, md(r.ancien), md(u" ; ".join(r.motifs))))

    if a.avertissements:
        out.print_md(u"## Avertissements - signales, non bloquants")
        for w in a.avertissements:
            out.print_md(u"- {0}".format(md(w)))

    out.print_md(u"## Lignes appliquees (plan)")
    app = [r for r in a.tous() if r.verdict == C.APPLIQUEE]
    for r in app[:400]:
        out.print_md(u"- {0} {1} : {2}".format(
            md(r.categorie), r.id_revit, md(u" ; ".join(r.operations))))
    if len(app) > 400:
        out.print_md(u"*... et {0} autre(s), toutes au rapport JSON.*".format(
            len(app) - 400))

    out.print_md(u"## Ordre d'application conseille")
    for t in C.ORDRE_CONSEILLE:
        out.print_md(md(t))
    out.print_md(u"Cette maquette porte : {0} niveau(x), {1} quadrillage(s), "
                 u"{2} volume(s), {3} vue(s).".format(
                     *[sum(1 for r in a.tous() if r.categorie == c)
                       for c in (C.NIVEAU, C.QUADRILLAGE, C.VOLUME, C.VUE)]))


def afficher_ecriture(e):
    out.print_md(u"---\n# Ecriture")
    if e[u"echec"]:
        out.print_md(u"## ECHEC - tout a ete annule\n{0}\n\n**La maquette est "
                     u"dans l'etat ou elle etait avant le clic** (les deux "
                     u"passes annulees ensemble).".format(md(e[u"echec"])))
        return
    out.print_md(u"{0} operation(s) en deux passes, groupe assimile. "
                 u"Relecture dans la meme session : {1} ecart(s).".format(
                     e[u"operations"], len(e[u"ecarts_relecture"])))
    for x in e[u"ecarts_relecture"]:
        out.print_md(u"- {0}".format(md(x)))
    out.print_md(u"> **Ce resultat ne prouve rien** (R19 fait 6). Verifier par "
                 u"une **photo maquette** relancee dans une execution separee.")


# --------------------------------------------------------------------------
# Ecriture - deux passes, un TransactionGroup, tout ou rien
# --------------------------------------------------------------------------

def _renommer(espace, i, nom):
    el = doc.GetElement(element_id(i))
    if el is None:
        raise Exception(u"{0} {1} introuvable au moment d'ecrire".format(
            espace, i))
    el.Name = nom


def ecrire(a, guid_de):
    e = OrderedDict([(u"mode", u"reel"), (u"echec", None), (u"operations", 0),
                     (u"ref_id_generes", []), (u"ecarts_relecture", [])])
    groupe = TransactionGroup(doc, u"bimflow - renommer selon table")
    groupe.Start()
    faits = 0
    try:
        t1 = Transaction(doc, u"bimflow - noms temporaires")
        t1.Start()
        try:
            for espace, ren in a.renommages.items():
                for i in ren:
                    _renommer(espace, i, C.nom_temporaire(i))
        except Exception:
            t1.RollBack()
            raise
        if t1.Commit() != TransactionStatus.Committed:
            raise Exception(u"passe 1 : commit refuse par Revit")

        t2 = Transaction(doc, u"bimflow - noms definitifs et parametres")
        t2.Start()
        try:
            for espace, ren in a.renommages.items():
                for i, (avant, apres) in ren.items():
                    faits += 1
                    _renommer(espace, i, apres)
            for i, (avant, apres) in a.retypages.items():
                faits += 1
                doc.GetElement(element_id(i)).ChangeTypeId(element_id(apres))
            for i, nom, avant, apres in a.parametres:
                faits += 1
                el = doc.GetElement(element_id(i))
                p = parametre(el, guid_de[nom]) if el is not None else None
                if p is None:
                    raise Exception(u"{0} introuvable sur {1}".format(nom, i))
                if apres is None:          # REF_Id regenere
                    # Guid.NewGuid() est un UUID de version 4
                    apres = u"{0}".format(System.Guid.NewGuid())
                    e[u"ref_id_generes"].append(OrderedDict([
                        (u"id", i), (u"avant", avant), (u"apres", apres)]))
                if not p.Set(apres):
                    raise Exception(u"Set() a rendu False : {0} sur {1}".format(
                        nom, i))
        except Exception:
            t2.RollBack()
            raise
        if t2.Commit() != TransactionStatus.Committed:
            raise Exception(u"passe 2 : commit refuse par Revit")
    except Exception as err:
        e[u"echec"] = u"{0}".format(err)

    if e[u"echec"] is None:
        groupe.Assimilate()
        e[u"operations"] = faits
        for espace, ren in a.renommages.items():
            for i, (avant, apres) in ren.items():
                lu = nom_de(doc.GetElement(element_id(i)))
                if lu != apres:
                    e[u"ecarts_relecture"].append(
                        u"{0} {1} : lu « {2} », attendu « {3} »".format(
                            espace, i, lu, apres))
    else:
        groupe.RollBack()
        e[u"ref_id_generes"] = []
    return e


# --------------------------------------------------------------------------
# Rapport JSON, date, a cote de la table
# --------------------------------------------------------------------------

def rapport_json(a, chemin_table, octets, collaboratif, detache, fermes,
                 ecriture):
    local = datetime.datetime.now()
    utc = datetime.datetime.utcnow()
    mode = u"reel" if ecriture is not None else u"simulation"
    en_tete = OrderedDict([
        (u"outil", OUTIL), (u"version_outil", C.VERSION), (u"mode", mode),
        (u"date", photo.date_iso(local, photo.decalage_minutes(local, utc))),
        (u"modele", doc.Title), (u"chemin", doc.PathName or None),
        (u"collaboratif", collaboratif), (u"detache", detache),
        (u"sous_projets_fermes", sorted(fermes)),
        (u"table", OrderedDict([(u"chemin", chemin_table),
                                (u"octets", len(octets))])),
    ])
    donnees = C.rapport(a, en_tete, ecriture)
    dossier, nom_table = os.path.split(chemin_table)
    nom = C.nom_rapport(nom_table, doc.Title,
                        local.strftime(u"%Y-%m-%d_%H%M"), mode)
    chemin = photo.chemin_libre(dossier, nom)
    try:
        photo.ecrire_json(chemin, donnees)
        out.print_md(u"**Rapport** : {0}".format(md(chemin)))
    except Exception as err:
        out.print_md(u"**Rapport NON ecrit** ({0}) : {1}".format(
            md(chemin), md(u"{0}".format(err))))
    out.print_md(u"*{0} - version {1} - mode {2}*".format(
        OUTIL, C.VERSION, mode))


main()
