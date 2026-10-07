# -*- coding: utf-8 -*-
"""BLEU - lecture seule : rien n'est ecrit dans la maquette.

Photographie les systemes MEP de la maquette ouverte et de ses liens de
premier niveau choisis : types de systeme et systemes (noms, abreviations,
classifications, couleurs, materiaux), elements sans systeme, types de
canalisation et de gaine, electricite (distribution, tableaux, circuits),
filtres de vue et leurs regles, familles d'equipement et leurs parametres,
parametres de projet et partages, champs des nomenclatures.

Sortie : un dossier inventaire_<titre>_<AAAAMMJJ_HHMM> avec inventaire.json
et 18 CSV (UTF-8 avec BOM, separateur ;, virgule decimale).

Il mesure, il ne conclut pas. Toute valeur illisible vaut NON_LU et
figure dans 90_anomalies.csv. Detail : docs\\inventaire_systemes.md
"""

__title__ = "Inventaire\nsystèmes"
__author__ = "Keovia Solutions inc."

VERSION = u"2026-10-07c"

# pyRevit v6.5.5 / IronPython 3.4.2 (IPY342) - pas de f-string, pas de
# shebang, syntaxe 3.4. Toute la logique qui suit la lecture vit dans
# lib\bimflow_inventaire.py, testee hors Revit.
#
# Regles tenues ici :
# - aucune ouverture de modification du document, aucun emprunt, aucune
#   synchronisation : uniquement des lectures ;
# - ElementId.Value, jamais l'ancien entier ;
# - les collecteurs sont MATERIALISES (ToElementIds) avant toute
#   resolution de propriete : resoudre pendant l'iteration a deja tue Revit
#   (AccessViolationException, non rattrapable) ;
# - toute propriete lue passe par inv.lire (ou inv.compter_echec dans les
#   boucles par element) : une erreur devient NON_LU + anomalie, jamais une
#   cellule vide silencieuse.

import datetime
import os
import time
from collections import OrderedDict

import System

from pyrevit import revit, forms, script

import Autodesk.Revit.DB as DB
from Autodesk.Revit.DB import (
    BuiltInCategory, BuiltInParameter, Category, ElementId, Family,
    FamilyInstance, FilterElement, FilteredElementCollector,
    FilteredWorksetCollector, LabelUtils, ParameterElement,
    ParameterFilterElement, RevitLinkInstance, SelectionFilterElement,
    SharedParameterElement, StorageType, UnitTypeId, UnitUtils, View,
    ViewSchedule, WorksetKind,
)
from Autodesk.Revit.DB.Electrical import (
    DistributionSysType, ElectricalEquipment, ElectricalSystem,
)
from Autodesk.Revit.DB.Mechanical import (
    Duct, DuctType, FlexDuct, FlexDuctType, MechanicalSystem,
    MechanicalSystemType,
)
from Autodesk.Revit.DB.Plumbing import (
    FlexPipe, FlexPipeType, Pipe, PipeType, PipingSystem, PipingSystemType,
)

import bimflow_inventaire as L


debut = time.time()
doc = revit.doc
out = script.get_output()
inv = L.Inventaire()

INVALIDE = ElementId.InvalidElementId
# StorageType.None : "None" est un mot reserve de Python 3.
STOCKAGE_AUCUN = getattr(StorageType, "None")
PAS_UI = 200          # rafraichir la barre et tester l'annulation tous les N


class Annulation(Exception):
    pass


# ---------------------------------------------------------------------------
# 0. Petits lecteurs
# ---------------------------------------------------------------------------

def idv(eid):
    return int(eid.Value)


def non_lu(valeur):
    """Vrai si la lecture a echoue. Teste le type d'abord : un objet .NET
    n'est jamais compare a une chaine."""
    return isinstance(valeur, str) and valeur == L.NON_LU


def est_id(valeur):
    return isinstance(valeur, ElementId)


def valide(eid):
    return est_id(eid) and eid != INVALIDE


def nom_element(e):
    """Nom d'un element ; certains types masquent Name sous IronPython."""
    try:
        return e.Name
    except AttributeError:
        return DB.Element.Name.__get__(e)


def nom_par_id(d, eid):
    """Nom de l'element designe ; vide si l'identifiant est invalide."""
    if not valide(eid):
        return u""
    e = d.GetElement(eid)
    if e is None:
        raise LookupError(u"element {0} introuvable".format(idv(eid)))
    return nom_element(e)


def param_natif(e, nom_bip):
    bip = getattr(BuiltInParameter, nom_bip)
    p = e.get_Parameter(bip)
    if p is None:
        raise LookupError(u"parametre {0} absent".format(nom_bip))
    return p


def texte_natif(e, nom_bip):
    return param_natif(e, nom_bip).AsString() or u""


def id_natif(e, nom_bip):
    return param_natif(e, nom_bip).AsElementId()


def en_mm(v):
    return round(UnitUtils.ConvertFromInternalUnits(
        v, UnitTypeId.Millimeters), 1)


def en_celsius(v):
    return round(UnitUtils.ConvertFromInternalUnits(
        v, UnitTypeId.Celsius), 2)


def couleur_de(c):
    if not c.IsValid:
        return L.couleur(0, 0, 0, False)
    return L.couleur(c.Red, c.Green, c.Blue, True)


def ids_classe(d, classe):
    return list(FilteredElementCollector(d).OfClass(classe).ToElementIds())


def ids_categorie(d, bic):
    return list(FilteredElementCollector(d).OfCategory(bic)
                .WhereElementIsNotElementType().ToElementIds())


def categorie_native(nom_bic):
    """BuiltInCategory par son nom, ou None si la version ne la connait pas."""
    return getattr(BuiltInCategory, nom_bic, None)


def famille_et_type(d, el):
    t = d.GetElement(el.GetTypeId())
    if t is None:
        return u"", u""
    return t.FamilyName, nom_element(t)


def nom_categorie(d, cid):
    """Nom d'une categorie par son id. Les ids negatifs sont ceux de
    BuiltInCategory, qui ne sont PAS des elements : doc.GetElement ne les
    trouve pas (48 anomalies a la recette du 2026-10-07)."""
    if not valide(cid):
        return u""
    cat = Category.GetCategory(d, cid)
    if cat is None:
        raise LookupError(u"categorie {0} introuvable".format(idv(cid)))
    return cat.Name


def decrire_equipement(d, eq):
    """Equipement de base d'un systeme. MEPSystem.BaseEquipment rend null
    quand le systeme n'en a pas : la cellule le dit (AUCUN), elle ne reste
    pas vide."""
    if eq is None:
        return L.AUCUN
    famille, typ = famille_et_type(d, eq)
    return u"{0} : {1} [{2}]".format(famille, typ, idv(eq.Id))


class Contexte(object):
    """Une maquette lue : document, etiquette de source, lecteurs."""

    def __init__(self, d, source):
        self.d = d
        self.src = source
        self.statut = L.LU
        self.comptes = {}
        self.table_ss = d.GetWorksetTable() if d.IsWorkshared else None
        self.noms_lies = set()       # noms des parametres lies au projet

    def lire(self, table, ident, propriete, fonction,
             nature=L.NATURE_ERREUR):
        return inv.lire(self.src, table, ident, propriete, fonction, nature)

    def sous_projet(self, el):
        if self.table_ss is None:
            return u""
        return self.table_ss.GetWorkset(el.WorksetId).Name

    def niveau(self, el):
        if valide(el.LevelId):
            return nom_par_id(self.d, el.LevelId)
        reference = getattr(el, "ReferenceLevel", None)   # canalisations
        if reference is not None:
            return reference.Name
        return u""


class Avancement(object):
    def __init__(self, pb, total):
        self.pb = pb
        self.total = total
        self.fait = 0
        self.compteur = 0

    def verifier(self):
        if self.pb.cancelled:
            raise Annulation()

    def etape(self):
        self.fait += 1
        self.pb.update_progress(min(self.fait, self.total), self.total)
        self.verifier()

    def tic(self):
        self.compteur += 1
        if self.compteur % PAS_UI == 0:
            self.pb.update_progress(min(self.fait, self.total), self.total)
            self.verifier()


avancement = None


def tic():
    if avancement is not None:
        avancement.tic()


# ---------------------------------------------------------------------------
# 1. Systemes de tuyauterie et de gaine (tables 10 a 13)
# ---------------------------------------------------------------------------

DOMAINES = (
    (u"TUYAUTERIE", PipingSystemType, PipingSystem),
    (u"GAINE", MechanicalSystemType, MechanicalSystem),
)

PARAMS_TYPE_SYSTEME = ("RBS_PIPING_SYSTEM_TYPE_PARAM",
                       "RBS_DUCT_SYSTEM_TYPE_PARAM")


def taille_reseau(s, domaine):
    """PipingSystem.PipingNetwork : "Pipes and fittings which are contained
    in this system" ; MechanicalSystem.DuctNetwork : "The ducts and fittings
    contained within the system" (API 2026)."""
    if domaine == u"TUYAUTERIE":
        return s.PipingNetwork.Size
    return s.DuctNetwork.Size


def type_systeme_de(el):
    """Type de systeme porte par l'element (parametre natif), ou None."""
    for nom_bip in PARAMS_TYPE_SYSTEME:
        p = el.get_Parameter(getattr(BuiltInParameter, nom_bip))
        if p is not None:
            v = p.AsElementId()
            if valide(v):
                return idv(v)
    return None


def lire_systemes(ctx):
    d = ctx.d

    # Systemes (11), lus cote systeme.
    systemes = []
    for domaine, _cls_type, cls_sys in DOMAINES:
        for eid in ids_classe(d, cls_sys):
            systemes.append((domaine, eid))

    T = u"systemes"
    nb_sys_par_type = {}
    types_par_nom = {}
    lignes_sys = []
    for domaine, eid in systemes:
        tic()
        s = d.GetElement(eid)
        i = idv(eid)
        nom = ctx.lire(T, i, u"Nom", lambda: nom_element(s))
        tid = ctx.lire(T, i, u"Type_systeme", lambda: s.GetTypeId())
        t = d.GetElement(tid) if valide(tid) else None
        if t is not None:
            nb_sys_par_type[idv(tid)] = nb_sys_par_type.get(idv(tid), 0) + 1
            nom_type = ctx.lire(T, i, u"Type_systeme", lambda: nom_element(t))
            abrev = ctx.lire(T, i, u"Abreviation_type",
                             lambda: t.Abbreviation or u"")
        else:
            nom_type = abrev = L.NON_LU
            if est_id(tid):
                inv.anomalie(ctx.src, T, i, u"Type_systeme",
                             u"type de systeme introuvable")
        if not non_lu(nom):
            types_par_nom.setdefault(nom, []).append(nom_type)
        prefixe = L.code_nom(nom)
        lignes_sys.append({
            u"Domaine": domaine, u"Id": i, u"Nom": nom,
            u"Prefixe_nom": prefixe, u"Type_systeme": nom_type,
            u"Abreviation_type": abrev,
            u"Classification": ctx.lire(
                T, i, u"Classification",
                lambda: u"{0}".format(s.SystemType)),
            u"Prefixe_coherent": L.code_coherent(prefixe, abrev),
            u"Equipement_base": ctx.lire(
                T, i, u"Equipement_base",
                lambda: decrire_equipement(d, s.BaseEquipment)),
            u"Nb_elements_parametre": None,
            # Elements : terminaux et equipements seulement (doc API :
            # "Terminal elements in the system"). Le reseau - canalisations
            # ou gaines, et raccords - est lu a part.
            u"Nb_terminaux_api": ctx.lire(
                T, i, u"Nb_terminaux_api", lambda: s.Elements.Size),
            u"Nb_elements_reseau": ctx.lire(
                T, i, u"Nb_elements_reseau", lambda: taille_reseau(s, domaine)),
        })

    for nom, types in types_par_nom.items():
        if len(types) > 1:
            inv.anomalie(ctx.src, T, nom, u"Nom",
                         u"nom porte par {0} systemes : le compte cote "
                         u"element leur est attribue a chacun".format(
                             len(types)))

    # Elements MEP, lus cote element (parametres natifs).
    ids_mep = []
    for nom_bic in L.CATEGORIES_SYSTEME:
        bic = categorie_native(nom_bic)
        if bic is None:
            inv.non_applicable(ctx.src, u"elements_sans_systeme", nom_bic,
                         u"Categorie",
                         u"categorie inconnue de cette version de Revit")
            continue
        ids_mep.extend(ids_categorie(d, bic))

    T = u"elements_sans_systeme"
    elements = []
    for eid in ids_mep:
        tic()
        el = d.GetElement(eid)
        i = idv(eid)
        e = {u"id": i,
             u"categorie": ctx.lire(T, i, u"Categorie",
                                    lambda: el.Category.Name),
             u"noms_systeme": ctx.lire(
                 T, i, u"Nom_systeme",
                 lambda: texte_natif(el, "RBS_SYSTEM_NAME_PARAM")),
             u"type_systeme_id": ctx.lire(T, i, u"Type_systeme",
                                          lambda: type_systeme_de(el))}
        if not non_lu(e[u"noms_systeme"]) and \
                not L.noms_systemes(e[u"noms_systeme"]):
            fam_typ = ctx.lire(T, i, u"Famille_Type",
                               lambda: famille_et_type(d, el))
            if non_lu(fam_typ):
                fam_typ = (L.NON_LU, L.NON_LU)
            e[u"famille"], e[u"type"] = fam_typ
            e[u"niveau"] = ctx.lire(T, i, u"Niveau", lambda: ctx.niveau(el))
            e[u"sous_projet"] = ctx.lire(T, i, u"Sous_projet",
                                         lambda: ctx.sous_projet(el))
        elements.append(e)

    rep = L.repartir_elements(elements, types_par_nom)

    for ligne in lignes_sys:
        nom = ligne[u"Nom"]
        ligne[u"Nb_elements_parametre"] = (
            L.NON_LU if non_lu(nom) else rep[u"par_systeme"].get(nom, 0))
        inv.ajouter(u"systemes", ctx.src, ligne)

    for (systeme, type_txt, categorie), nb in sorted(
            rep[u"par_categorie"].items()):
        inv.ajouter(u"systemes_categories", ctx.src, {
            u"Systeme": systeme, u"Type_systeme": type_txt,
            u"Categorie": categorie, u"Nb": nb})
    for nom, nb in sorted(rep[u"inconnus"].items()):
        inv.anomalie(ctx.src, u"systemes_categories", nom, u"Systeme",
                     u"nom de systeme lu sur {0} element(s), aucun systeme "
                     u"de ce nom dans le document".format(nb))

    for e in rep[u"sans_systeme"]:
        inv.ajouter(u"elements_sans_systeme", ctx.src, {
            u"Id": e[u"id"], u"Categorie": e[u"categorie"],
            u"Famille": e[u"famille"], u"Type": e[u"type"],
            u"Niveau": e[u"niveau"], u"Sous_projet": e[u"sous_projet"]})

    ctx.comptes.update({
        u"elements_mep_lus": rep[u"total"],
        u"elements_multi_systemes": rep[u"multi"],
        u"affectations_sup": rep[u"affectations_sup"],
        u"elements_systeme_non_lu": rep[u"non_lus"],
        u"affectations_systeme_inconnu": sum(rep[u"inconnus"].values()),
    })

    # Types de systeme (10).
    T = u"types_systeme"
    for domaine, cls_type, _cls_sys in DOMAINES:
        for eid in ids_classe(d, cls_type):
            tic()
            t = d.GetElement(eid)
            i = idv(eid)
            nom = ctx.lire(T, i, u"Nom", lambda: nom_element(t))
            abrev = ctx.lire(T, i, u"Abreviation",
                             lambda: t.Abbreviation or u"")
            code = L.code_nom(nom)
            if domaine == u"TUYAUTERIE":
                fluide = ctx.lire(T, i, u"Fluide",
                                  lambda: nom_par_id(d, t.FluidType))
                temp = ctx.lire(T, i, u"Temperature_fluide_C",
                                lambda: en_celsius(t.FluidTemperature))
            else:
                fluide = temp = u""          # sans objet pour une gaine
            coul = ctx.lire(T, i, u"Couleur_ligne",
                            lambda: couleur_de(t.LineColor))
            if non_lu(coul):
                coul = {u"rvb": L.NON_LU, u"hex": L.NON_LU,
                        u"remplace": L.NON_LU}
            inv.ajouter(T, ctx.src, {
                u"Domaine": domaine, u"Id": i, u"Nom": nom,
                u"Abreviation": abrev,
                u"Classification_api": ctx.lire(
                    T, i, u"Classification_api",
                    lambda: u"{0}".format(t.SystemClassification)),
                u"Classification_libelle": ctx.lire(
                    T, i, u"Classification_libelle",
                    lambda: texte_natif(t, "RBS_SYSTEM_CLASSIFICATION_PARAM")),
                u"Code_nom": code,
                u"Code_coherent": L.code_coherent(code, abrev),
                u"Fluide": fluide, u"Temperature_fluide_C": temp,
                u"Materiau": ctx.lire(T, i, u"Materiau",
                                      lambda: nom_par_id(d, t.MaterialId)),
                u"Couleur_ligne_RVB": coul[u"rvb"],
                u"Couleur_ligne_hex": coul[u"hex"],
                u"Remplace": coul[u"remplace"],
                u"Motif_ligne": ctx.lire(T, i, u"Motif_ligne",
                                         lambda: motif_ligne(d, t)),
                u"Epaisseur_ligne": ctx.lire(T, i, u"Epaisseur_ligne",
                                             lambda: t.LineWeight),
                u"Nb_systemes": nb_sys_par_type.get(i, 0),
                u"Nb_elements": rep[u"par_type_id"].get(i, 0),
            })


def motif_ligne(d, t):
    pid = t.LinePatternId
    if not valide(pid):
        return u""
    if pid == DB.LinePatternElement.GetSolidPatternId():
        return u"Plein"
    return nom_par_id(d, pid)


# ---------------------------------------------------------------------------
# 2. Types de canalisation et de gaine (table 14)
# ---------------------------------------------------------------------------

def segments_de(d, t):
    groupe = DB.RoutingPreferenceRuleGroupType.Segments
    rpm = t.RoutingPreferenceManager
    noms = []
    for k in range(rpm.GetNumberOfRules(groupe)):
        regle = rpm.GetRule(groupe, k)
        seg = d.GetElement(regle.MEPPartId)
        noms.append(nom_element(seg) if seg is not None
                    else u"(id {0})".format(idv(regle.MEPPartId)))
    return noms


def lire_types_canalisation(ctx):
    d = ctx.d
    T = u"types_canalisation_gaine"
    occurrences = {}
    for classe in (Pipe, FlexPipe, Duct, FlexDuct):
        for eid in ids_classe(d, classe):
            tic()
            el = d.GetElement(eid)
            tid = ctx.lire(T, idv(eid), u"Type de l'occurrence",
                           lambda: el.GetTypeId())
            if valide(tid):
                occurrences[idv(tid)] = occurrences.get(idv(tid), 0) + 1

    familles = (
        (u"TUYAUTERIE", PipeType, True, False),
        (u"TUYAUTERIE", FlexPipeType, False, False),
        (u"GAINE", DuctType, False, True),
        (u"GAINE", FlexDuctType, False, True),
    )
    for domaine, classe, avec_segments, avec_forme in familles:
        for eid in ids_classe(d, classe):
            tic()
            t = d.GetElement(eid)
            i = idv(eid)
            inv.ajouter(T, ctx.src, {
                u"Domaine": domaine, u"Id": i,
                u"Famille_systeme": ctx.lire(T, i, u"Famille_systeme",
                                             lambda: t.FamilyName),
                u"Nom_type": ctx.lire(T, i, u"Nom_type",
                                      lambda: nom_element(t)),
                u"Forme": ctx.lire(T, i, u"Forme",
                                   lambda: u"{0}".format(t.Shape))
                if avec_forme else u"",
                u"Segments": ctx.lire(T, i, u"Segments",
                                      lambda: segments_de(d, t))
                if avec_segments else u"",
                u"Nb_occurrences": occurrences.get(i, 0),
            })


# ---------------------------------------------------------------------------
# 3. Electricite (tables 20 a 22)
# ---------------------------------------------------------------------------

def lire_electricite(ctx):
    d = ctx.d

    # Circuits (22), d'abord : ils donnent le nombre de circuits par tableau.
    T = u"elec_circuits"
    circuits_par_tableau = {}
    for eid in ids_classe(d, ElectricalSystem):
        tic()
        c = d.GetElement(eid)
        i = idv(eid)
        type_circuit = ctx.lire(T, i, u"Type_circuit",
                                lambda: u"{0}".format(c.CircuitType))
        type_systeme = ctx.lire(T, i, u"Type_systeme_elec",
                                lambda: u"{0}".format(c.SystemType))

        # Circuit de reserve ou d'espace, tension d'un circuit qui n'est pas
        # de puissance : l'echec est une limite prevue, pas une erreur.
        def lire_c(propriete, fonction):
            return ctx.lire(T, i, propriete, fonction,
                            L.nature_propriete_circuit(
                                propriete, type_circuit, type_systeme))

        base = lire_c(u"Tableau_id", lambda: c.BaseEquipment)
        if base is not None and not non_lu(base):
            cle = idv(base.Id)
            circuits_par_tableau[cle] = circuits_par_tableau.get(cle, 0) + 1
        inv.ajouter(T, ctx.src, {
            u"Id": i,
            u"Tableau": lire_c(u"Tableau", lambda: c.PanelName),
            u"Numero": lire_c(u"Numero", lambda: c.CircuitNumber),
            u"Type_systeme_elec": type_systeme,
            u"Type_circuit": type_circuit,
            u"Nom_charge": lire_c(u"Nom_charge", lambda: c.LoadName),
            # Unite non documentee : supposee interne (hypothese).
            u"Tension_V": lire_c(u"Tension_V",
                                 lambda: L.volts(c.Voltage, True)),
            u"Nb_poles": lire_c(u"Nb_poles", lambda: c.PolesNumber),
            u"Nb_elements": lire_c(u"Nb_elements", lambda: c.Elements.Size),
        })

    # Tableaux (21) : les FamilyInstance dont le MEPModel est un
    # ElectricalEquipment ET qui portent un nom de tableau. Les autres
    # equipements electriques (sans parametre de tableau) ne sont pas des
    # tableaux : comptes, et dits en une anomalie NON_APPLICABLE.
    T = u"elec_tableaux"
    tableaux_par_distribution = {}
    hors_tableaux = 0
    bic = categorie_native(u"OST_ElectricalEquipment")
    for eid in ids_categorie(d, bic):
        tic()
        el = d.GetElement(eid)
        i = idv(eid)
        equipement = ctx.lire(T, i, u"MEPModel", lambda: equipement_de(el))
        if non_lu(equipement):
            continue
        nom = ctx.lire(T, i, u"Nom_tableau", lambda: texte_si_present(
            el, "RBS_ELEC_PANEL_NAME"))
        if non_lu(nom):
            continue
        if not L.est_tableau(equipement is not None, nom):
            hors_tableaux += 1
            continue
        dist = ctx.lire(T, i, u"Systeme_distribution",
                        lambda: equipement.DistributionSystem)
        if dist is not None and not non_lu(dist):
            cle = idv(dist.Id)
            tableaux_par_distribution[cle] = \
                tableaux_par_distribution.get(cle, 0) + 1
        fam_typ = ctx.lire(T, i, u"Famille_Type",
                           lambda: famille_et_type(d, el))
        if non_lu(fam_typ):
            fam_typ = (L.NON_LU, L.NON_LU)
        inv.ajouter(T, ctx.src, {
            u"Id": i,
            u"Nom_tableau": nom,
            u"Famille": fam_typ[0], u"Type": fam_typ[1],
            # Pas de systeme de distribution : champ vide, declare (spec §7).
            u"Systeme_distribution": L.NON_LU if non_lu(dist) else (
                u"" if dist is None else ctx.lire(
                    T, i, u"Systeme_distribution",
                    lambda: nom_element(dist))),
            u"Alimente_par": ctx.lire(
                T, i, u"Alimente_par",
                lambda: texte_natif(el, "RBS_ELEC_PANEL_SUPPLY_FROM_PARAM"),
                L.NATURE_NON_APPLICABLE),
            u"Nb_circuits": circuits_par_tableau.get(i, 0),
            u"Niveau": ctx.lire(T, i, u"Niveau", lambda: ctx.niveau(el)),
            u"Sous_projet": ctx.lire(T, i, u"Sous_projet",
                                     lambda: ctx.sous_projet(el)),
        })
    if hors_tableaux:
        inv.non_applicable(
            ctx.src, T, u"", u"Tableau",
            u"{0} equipement(s) electrique(s) sans nom de tableau ou sans "
            u"ElectricalEquipment : hors table 21".format(hors_tableaux))
    ctx.comptes[u"equipements_electriques_hors_tableaux"] = hors_tableaux

    # Systemes de distribution (20).
    T = u"elec_distribution"
    for eid in ids_classe(d, DistributionSysType):
        tic()
        t = d.GetElement(eid)
        i = idv(eid)
        inv.ajouter(T, ctx.src, {
            u"Id": i,
            u"Nom": ctx.lire(T, i, u"Nom", lambda: nom_element(t)),
            u"Phase": ctx.lire(T, i, u"Phase",
                               lambda: u"{0}".format(t.ElectricalPhase)),
            u"Configuration": ctx.lire(
                T, i, u"Configuration",
                lambda: u"{0}".format(t.ElectricalPhaseConfiguration)),
            u"Nb_conducteurs": ctx.lire(T, i, u"Nb_conducteurs",
                                        lambda: t.NumWires),
            u"Tension_LL_V": ctx.lire(T, i, u"Tension_LL_V",
                                      lambda: tension(t.VoltageLineToLine)),
            u"Tension_LN_V": ctx.lire(T, i, u"Tension_LN_V",
                                      lambda: tension(t.VoltageLineToGround)),
            u"Nb_tableaux": tableaux_par_distribution.get(i, 0),
        })


def equipement_de(el):
    """ElectricalEquipment de l'occurrence, ou None."""
    if not isinstance(el, FamilyInstance):
        return None
    modele = el.MEPModel
    return modele if isinstance(modele, ElectricalEquipment) else None


def texte_si_present(el, nom_bip):
    """Texte du parametre natif, ou None s'il est absent de l'element."""
    p = el.get_Parameter(getattr(BuiltInParameter, nom_bip))
    if p is None:
        return None
    return p.AsString() or u""


def tension(type_tension):
    """VoltageType.ActualValue est DEJA en volts (doc API 2026)."""
    if type_tension is None:
        return u""
    return L.volts(type_tension.ActualValue, False)


# ---------------------------------------------------------------------------
# 4. Filtres de vue (tables 30 a 32)
# ---------------------------------------------------------------------------
# ParameterFilterElement.GetRules() est retire en 2024+ : on descend l'arbre
# de GetElementFilter() et on le convertit en dictionnaires pour la lib.

def nom_parametre(d, pid):
    v = idv(pid)
    if v < 0:
        bip = System.Enum.ToObject(BuiltInParameter, v)
        return LabelUtils.GetLabelFor(bip)
    e = d.GetElement(pid)
    if e is None:
        raise LookupError(u"parametre {0} introuvable".format(v))
    if isinstance(e, ParameterElement):
        return e.GetDefinition().Name
    return nom_element(e)


def guid_parametre(d, pid):
    if idv(pid) < 0:
        return u""
    e = d.GetElement(pid)
    if isinstance(e, SharedParameterElement):
        return u"{0}".format(e.GuidValue)
    return u""


REGLES_DE_VALEUR = (DB.FilterStringRule, DB.FilterDoubleRule,
                    DB.FilterIntegerRule, DB.FilterElementIdRule)


def convertir_regle(ctx, regle, fid):
    T = u"filtres_regles"
    r = {u"inverse": False, u"valeur": u"", u"valeur_unites_internes": False,
         u"parametre": u"", u"parametre_id": u"", u"parametre_guid": u""}
    if isinstance(regle, DB.FilterInverseRule):
        r[u"inverse"] = True
        regle = regle.GetInnerRule()
    classe = type(regle).__name__

    if classe == u"SharedParameterApplicableRule":
        r[u"operateur"] = classe
        r[u"parametre"] = ctx.lire(T, fid, u"Parametre",
                                   lambda: regle.ParameterName)
        return r
    if classe == u"FilterCategoryRule":
        r[u"operateur"] = classe
        r[u"valeur"] = ctx.lire(T, fid, u"Valeur", lambda: [
            nom_categorie(ctx.d, c) for c in regle.GetCategories()])
        return r

    pid = ctx.lire(T, fid, u"Parametre_id", lambda: regle.GetRuleParameter())
    if est_id(pid):
        r[u"parametre_id"] = idv(pid)
        r[u"parametre"] = ctx.lire(T, fid, u"Parametre",
                                   lambda: nom_parametre(ctx.d, pid))
        r[u"parametre_guid"] = ctx.lire(T, fid, u"Parametre_GUID",
                                        lambda: guid_parametre(ctx.d, pid))
    else:
        r[u"parametre_id"] = r[u"parametre"] = L.NON_LU

    if isinstance(regle, REGLES_DE_VALEUR):
        r[u"operateur"] = ctx.lire(
            T, fid, u"Operateur",
            lambda: type(regle.GetEvaluator()).__name__)
        if isinstance(regle, DB.FilterStringRule):
            r[u"valeur"] = ctx.lire(T, fid, u"Valeur",
                                    lambda: regle.RuleString)
        elif isinstance(regle, DB.FilterDoubleRule):
            r[u"valeur"] = ctx.lire(T, fid, u"Valeur",
                                    lambda: float(regle.RuleValue))
            r[u"valeur_unites_internes"] = True
        elif isinstance(regle, DB.FilterIntegerRule):
            r[u"valeur"] = ctx.lire(T, fid, u"Valeur",
                                    lambda: int(regle.RuleValue))
        elif isinstance(regle, DB.FilterElementIdRule):
            r[u"valeur"] = ctx.lire(
                T, fid, u"Valeur",
                lambda: u"{0} [{1}]".format(nom_par_id(ctx.d, regle.RuleValue),
                                            idv(regle.RuleValue)))
        else:
            r[u"valeur"] = L.NON_LU
            inv.anomalie(ctx.src, T, fid, u"Valeur",
                         u"regle de valeur {0} non decodee".format(classe))
    else:
        r[u"operateur"] = classe        # a une valeur / n'a pas de valeur...
    return r


def convertir_filtre(ctx, ef, fid):
    if ef is None:
        return None
    inverse = bool(ef.Inverted)
    if isinstance(ef, DB.LogicalAndFilter) or isinstance(ef, DB.LogicalOrFilter):
        return {u"type": u"ET" if isinstance(ef, DB.LogicalAndFilter) else u"OU",
                u"inverse": inverse,
                u"enfants": [convertir_filtre(ctx, e, fid)
                             for e in list(ef.GetFilters())]}
    if isinstance(ef, DB.ElementParameterFilter):
        return {u"type": u"PARAMETRES", u"inverse": inverse,
                u"regles": [convertir_regle(ctx, r, fid)
                            for r in list(ef.GetRules())]}
    classe = type(ef).__name__
    inv.anomalie(ctx.src, u"filtres_regles", fid, u"Arbre",
                 u"filtre de classe {0} non decode".format(classe))
    return {u"type": u"AUTRE", u"inverse": inverse, u"classe": classe}


def rvb(c):
    return couleur_de(c)[u"rvb"]


def lire_filtres(ctx):
    d = ctx.d

    # Application (32) : gabarits, et vues SANS gabarit (une vue pilotee par
    # un gabarit en recoit les filtres : ils ne sont pas dupliques).
    T = u"filtres_application"
    applications = []
    for vid in ids_classe(d, View):
        tic()
        v = d.GetElement(vid)
        i = idv(vid)
        est_gabarit = ctx.lire(T, i, u"Est_gabarit", lambda: v.IsTemplate)
        if non_lu(est_gabarit):
            continue
        if not est_gabarit:
            gabarit = ctx.lire(T, i, u"Gabarit", lambda: v.ViewTemplateId)
            if non_lu(gabarit) or valide(gabarit):
                continue
        permis = ctx.lire(T, i, u"Remplacements_permis",
                          lambda: v.AreGraphicsOverridesAllowed())
        if permis is not True:
            continue
        fids = ctx.lire(T, i, u"Filtres", lambda: list(v.GetFilters()))
        if non_lu(fids):
            continue
        nom_vue = ctx.lire(T, i, u"Vue", lambda: nom_element(v))
        for fid in fids:
            f = d.GetElement(fid)
            applications.append((idv(fid), est_gabarit))
            ogs = ctx.lire(T, i, u"Remplacements",
                           lambda: v.GetFilterOverrides(fid))
            ligne = {
                u"Vue_id": i, u"Vue": nom_vue, u"Est_gabarit": est_gabarit,
                u"Filtre": ctx.lire(T, i, u"Filtre",
                                    lambda: nom_element(f)),
                u"Active": ctx.lire(T, i, u"Active",
                                    lambda: v.GetIsFilterEnabled(fid)),
                u"Visible": ctx.lire(T, i, u"Visible",
                                     lambda: v.GetFilterVisibility(fid)),
            }
            if non_lu(ogs):
                for c in (u"Proj_ligne_RVB", u"Proj_motif_RVB",
                          u"Coupe_ligne_RVB", u"Coupe_motif_RVB",
                          u"Transparence", u"Demi_teinte"):
                    ligne[c] = L.NON_LU
            else:
                ligne.update({
                    u"Proj_ligne_RVB": ctx.lire(
                        T, i, u"Proj_ligne_RVB",
                        lambda: rvb(ogs.ProjectionLineColor)),
                    u"Proj_motif_RVB": ctx.lire(
                        T, i, u"Proj_motif_RVB",
                        lambda: rvb(ogs.SurfaceForegroundPatternColor)),
                    u"Coupe_ligne_RVB": ctx.lire(
                        T, i, u"Coupe_ligne_RVB",
                        lambda: rvb(ogs.CutLineColor)),
                    u"Coupe_motif_RVB": ctx.lire(
                        T, i, u"Coupe_motif_RVB",
                        lambda: rvb(ogs.CutForegroundPatternColor)),
                    u"Transparence": ctx.lire(T, i, u"Transparence",
                                              lambda: ogs.Transparency),
                    u"Demi_teinte": ctx.lire(T, i, u"Demi_teinte",
                                             lambda: ogs.Halftone),
                })
            inv.ajouter(T, ctx.src, ligne)

    comptes = L.compter_applications(applications)

    # Filtres (30) et leurs regles (31).
    T = u"filtres"
    for fid in ids_classe(d, FilterElement):
        tic()
        f = d.GetElement(fid)
        i = idv(fid)
        nom = ctx.lire(T, i, u"Nom", lambda: nom_element(f))
        categories = u""
        if isinstance(f, ParameterFilterElement):
            classe = u"REGLES"
            categories = ctx.lire(T, i, u"Categories", lambda: sorted(
                [nom_categorie(d, c) for c in f.GetCategories()]))
            arbre = ctx.lire(T, i, u"Regles",
                             lambda: convertir_filtre(ctx, f.GetElementFilter(),
                                                      i))
        elif isinstance(f, SelectionFilterElement):
            classe = u"SELECTION"
            arbre = None
        else:
            classe = type(f).__name__
            arbre = None
        if non_lu(arbre):
            regles, texte, nb = [], L.NON_LU, L.NON_LU
        else:
            regles, texte, nb = L.aplatir_filtre(arbre)
        for regle in regles:
            valeurs = {u"Filtre_id": i, u"Filtre": nom}
            valeurs.update(regle)
            inv.ajouter(u"filtres_regles", ctx.src, valeurs)
        nb_vues, nb_gabarits = comptes.get(i, (0, 0))
        inv.ajouter(T, ctx.src, {
            u"Id": i, u"Nom": nom, u"Classe": classe,
            u"Categories": categories, u"Regles_texte": texte,
            u"Nb_regles": nb, u"Nb_vues": nb_vues,
            u"Nb_gabarits": nb_gabarits})


# ---------------------------------------------------------------------------
# 5. Parametres de projet et partages (tables 50 et 51)
# ---------------------------------------------------------------------------

def type_donnees(definition):
    return L.identifiant_court(definition.GetDataType().TypeId)


def groupe(definition):
    gid = definition.GetGroupTypeId()
    if gid is None or not gid.TypeId:
        return u""
    return LabelUtils.GetLabelForGroup(gid)


def lire_parametres(ctx):
    d = ctx.d

    # Les GUID se lisent sur les SharedParameterElement, apparies par nom :
    # la table des liaisons expose une InternalDefinition sans GUID.
    T = u"parametres_partages"
    partages = []
    guids_par_nom = {}
    for eid in ids_classe(d, SharedParameterElement):
        tic()
        spe = d.GetElement(eid)
        i = idv(eid)
        nom = ctx.lire(T, i, u"Nom", lambda: spe.GetDefinition().Name)
        guid = ctx.lire(T, i, u"GUID", lambda: u"{0}".format(spe.GuidValue))
        if not non_lu(nom) and not non_lu(guid):
            guids_par_nom.setdefault(nom, []).append(guid)
        partages.append((i, spe, nom, guid))

    T = u"parametres_projet"
    liaisons = []
    it = d.ParameterBindings.ForwardIterator()
    it.Reset()
    while it.MoveNext():
        liaisons.append((it.Key, it.Current))

    guids_lies = set()
    for definition, liaison in liaisons:
        tic()
        nom = ctx.lire(T, u"", u"Nom", lambda: definition.Name)
        ident = nom
        if not non_lu(nom):
            ctx.noms_lies.add(nom)
        element = ctx.lire(T, ident, u"Id_definition",
                           lambda: d.GetElement(definition.Id))
        if isinstance(element, SharedParameterElement):
            partage, guid = True, u"{0}".format(element.GuidValue)
        elif isinstance(element, ParameterElement):
            partage, guid = False, u""
        else:
            candidats = guids_par_nom.get(nom, [])
            if len(candidats) == 1:
                partage, guid = True, candidats[0]
            elif not candidats:
                partage, guid = False, u""
            else:
                partage, guid = L.NON_LU, L.NON_LU
                inv.anomalie(ctx.src, T, ident, u"GUID",
                             u"{0} parametres partages portent ce nom, "
                             u"identifiant de definition illisible".format(
                                 len(candidats)))
        if partage is True:
            guids_lies.add(guid)
        inv.ajouter(T, ctx.src, {
            u"Nom": nom, u"Partage": partage, u"GUID": guid,
            u"Type_donnees": ctx.lire(T, ident, u"Type_donnees",
                                      lambda: type_donnees(definition)),
            u"Groupe": ctx.lire(T, ident, u"Groupe",
                                lambda: groupe(definition)),
            u"Liaison": u"OCCURRENCE"
            if isinstance(liaison, DB.InstanceBinding) else u"TYPE",
            u"Categories": ctx.lire(T, ident, u"Categories", lambda: sorted(
                [c.Name for c in liaison.Categories])),
        })

    T = u"parametres_partages"
    for i, spe, nom, guid in partages:
        inv.ajouter(T, ctx.src, {
            u"Nom": nom, u"GUID": guid,
            u"Type_donnees": ctx.lire(
                T, i, u"Type_donnees",
                lambda: type_donnees(spe.GetDefinition())),
            u"Lie_au_projet": L.NON_LU if non_lu(guid)
            else guid in guids_lies,
            u"Note": L.note_parametre_partage(nom),
        })


# ---------------------------------------------------------------------------
# 6. Familles des categories cibles et leurs parametres (tables 40 et 41)
# ---------------------------------------------------------------------------

class ParametreFamille(object):
    def __init__(self):
        self.meta = None
        self.remplissage = L.Remplissage()


def meta_parametre(ctx, p, portee):
    """Colonnes descriptives d'un parametre, lues une fois par famille."""
    d = ctx.d
    definition = p.Definition
    integre = idv(p.Id) < 0
    partage = bool(p.IsShared)
    guid = u"{0}".format(p.GUID) if partage else u""
    element_projet = None
    if not integre and not partage:
        element_projet = isinstance(d.GetElement(p.Id), ParameterElement)
    return {
        u"Parametre": definition.Name, u"Portee": portee,
        u"Origine": L.origine_parametre(integre, partage,
                                        definition.Name in ctx.noms_lies,
                                        element_projet),
        u"GUID": guid, u"Type_donnees": type_donnees(definition),
        u"Groupe": groupe(definition), u"Lecture_seule": bool(p.IsReadOnly),
    }


def accumuler(ctx, el, portee, cle_famille, accumulateurs):
    """Ajoute les valeurs des parametres de el aux accumulateurs."""
    T = u"familles_parametres"
    for p in list(el.Parameters):
        try:
            nom = p.Definition.Name
            cle = (portee, nom, idv(p.Id))
            stockage = p.StorageType
        except Exception as err:
            inv.compter_echec(ctx.src, T, cle_famille, u"Parametre", err)
            continue
        if stockage == STOCKAGE_AUCUN:
            continue
        acc = accumulateurs.get(cle)
        if acc is None:
            acc = accumulateurs[cle] = ParametreFamille()
            try:
                acc.meta = meta_parametre(ctx, p, portee)
            except Exception as err:
                inv.anomalie(ctx.src, T, cle_famille, nom,
                             u"description illisible : " + L.texte_erreur(err))
                acc.meta = {u"Parametre": nom, u"Portee": portee,
                            u"Origine": L.NON_LU, u"GUID": L.NON_LU,
                            u"Type_donnees": L.NON_LU, u"Groupe": L.NON_LU,
                            u"Lecture_seule": L.NON_LU}
        try:
            if stockage == StorageType.String:
                acc.remplissage.ajouter_texte(p.AsString())
            else:
                a_valeur = p.HasValue
                acc.remplissage.ajouter_valeur(
                    a_valeur, p.AsValueString() if a_valeur else None)
        except Exception as err:
            acc.remplissage.ajouter_illisible(L.texte_erreur(err))
            inv.compter_echec(ctx.src, T, cle_famille, nom, err)


def lire_familles(ctx):
    d = ctx.d
    T = u"familles"

    cibles = {}                       # id de categorie -> libelle
    bics = []
    for nom_bic, libelle in L.CATEGORIES_CIBLES:
        bic = categorie_native(nom_bic)
        if bic is None:
            inv.non_applicable(ctx.src, T, nom_bic, u"Categorie",
                         u"categorie '{0}' inconnue de cette version de "
                         u"Revit".format(libelle))
            continue
        cat = Category.GetCategory(d, bic)
        if cat is None:
            inv.non_applicable(ctx.src, T, nom_bic, u"Categorie",
                         u"categorie '{0}' absente du document".format(
                             libelle))
            continue
        cibles[idv(cat.Id)] = cat.Name
        bics.append(bic)

    # Occurrences des categories cibles, rattachees a leur famille.
    total_occurrences = 0
    instances = {}
    for bic in bics:
        ids = ids_categorie(d, bic)
        total_occurrences += len(ids)
        for eid in ids:
            tic()
            el = d.GetElement(eid)
            if not isinstance(el, FamilyInstance):
                continue
            fam_id = ctx.lire(T, idv(eid), u"Famille de l'occurrence",
                              lambda: idv(el.Symbol.Family.Id))
            if not non_lu(fam_id):
                instances.setdefault(fam_id, []).append(el)
    ctx.comptes[u"occurrences_categories_cibles"] = total_occurrences

    for fid in ids_classe(d, Family):
        f = d.GetElement(fid)
        i = idv(fid)
        cat_id = ctx.lire(T, i, u"Categorie", lambda: idv(f.FamilyCategory.Id))
        if cat_id not in cibles:
            continue
        categorie = cibles[cat_id]
        nom = ctx.lire(T, i, u"Famille", lambda: f.Name)
        cle_famille = u"{0} [{1}]".format(nom, i)
        types = ctx.lire(T, i, u"Nb_types", lambda: [
            d.GetElement(s) for s in f.GetFamilySymbolIds()])
        occurrences = instances.get(i, [])

        accumulateurs = OrderedDict()
        if not non_lu(types):
            for t in types:
                tic()
                accumuler(ctx, t, u"TYPE", cle_famille, accumulateurs)
        for el in occurrences:
            tic()
            accumuler(ctx, el, u"OCCURRENCE", cle_famille, accumulateurs)
        if not occurrences:
            inv.non_applicable(ctx.src, u"familles_parametres", cle_famille,
                         u"Parametres d'occurrence",
                         u"0 occurrence : parametres d'occurrence non lus "
                         u"(la famille n'est pas ouverte)")

        nb_type = nb_occ = 0
        guids = set()
        for cle, acc in accumulateurs.items():
            valeurs = {u"Categorie": categorie, u"Famille": nom}
            valeurs.update(acc.meta)
            valeurs.update(acc.remplissage.colonnes())
            inv.ajouter(u"familles_parametres", ctx.src, valeurs)
            if acc.meta[u"Portee"] == u"TYPE":
                nb_type += 1
            else:
                nb_occ += 1
            if acc.meta[u"Origine"] == L.PARTAGE:
                guids.add(acc.meta[u"GUID"])

        inv.ajouter(T, ctx.src, {
            u"Categorie": categorie, u"Famille": nom, u"Id_famille": i,
            u"In_situ": ctx.lire(T, i, u"In_situ", lambda: f.IsInPlace),
            u"Nb_types": L.NON_LU if non_lu(types) else len(types),
            u"Nb_occurrences": len(occurrences),
            u"Nb_param_type": nb_type, u"Nb_param_occurrence": nb_occ,
            u"Nb_param_partages": len(guids)})
    inv.publier_echecs()


# ---------------------------------------------------------------------------
# 7. Champs des nomenclatures (table 60)
# ---------------------------------------------------------------------------

def lire_nomenclatures(ctx):
    d = ctx.d
    T = u"nomenclatures_champs"
    for vid in ids_classe(d, ViewSchedule):
        tic()
        vs = d.GetElement(vid)
        i = idv(vid)
        ignoree = ctx.lire(T, i, u"Nature", lambda: bool(
            vs.IsTemplate or vs.IsTitleblockRevisionSchedule))
        if ignoree is not False:
            continue
        nom = ctx.lire(T, i, u"Nomenclature", lambda: nom_element(vs))
        definition = ctx.lire(T, i, u"Definition", lambda: vs.Definition)
        if non_lu(definition):
            continue
        categorie = ctx.lire(T, i, u"Categorie",
                             lambda: nom_categorie(d, definition.CategoryId))
        nb = ctx.lire(T, i, u"Champs", lambda: definition.GetFieldCount())
        if non_lu(nb):
            continue
        for k in range(nb):
            champ = ctx.lire(T, i, u"Champ {0}".format(k),
                             lambda: definition.GetField(k))
            if non_lu(champ):
                continue
            ligne = {u"Nomenclature": nom, u"Categorie": categorie,
                     u"Champ": ctx.lire(T, i, u"Champ {0}".format(k),
                                        lambda: champ.GetName())}
            pid = ctx.lire(T, i, u"Parametre_id {0}".format(k),
                           lambda: champ.ParameterId)
            if non_lu(pid):
                ligne.update({u"Parametre_id": L.NON_LU,
                              u"Parametre_GUID": L.NON_LU,
                              u"Origine": L.NON_LU})
            elif not valide(pid):
                ligne.update({u"Parametre_id": u"", u"Parametre_GUID": u"",
                              u"Origine": L.CALCULE})
            else:
                v = idv(pid)
                e = None if v < 0 else d.GetElement(pid)
                partage = isinstance(e, SharedParameterElement)
                ligne.update({
                    u"Parametre_id": v,
                    u"Parametre_GUID": u"{0}".format(e.GuidValue)
                    if partage else u"",
                    u"Origine": L.origine_parametre(
                        v < 0, partage, ligne[u"Champ"] in ctx.noms_lies,
                        None if v < 0 else isinstance(e, ParameterElement)),
                })
            inv.ajouter(T, ctx.src, ligne)


# ---------------------------------------------------------------------------
# 8. Maquettes a lire : hote et liens de premier niveau
# ---------------------------------------------------------------------------

def chemin_visible(d):
    if d.IsModelInCloud:
        return DB.ModelPathUtils.ConvertModelPathToUserVisiblePath(
            d.GetCloudModelPath())
    return d.PathName or u""


def sous_projets_fermes(d):
    if not d.IsWorkshared:
        return []
    return sorted([w.Name for w in FilteredWorksetCollector(d)
                   .OfKind(WorksetKind.UserWorkset).ToWorksets()
                   if not w.IsOpen])


if doc is None or doc.IsFamilyDocument:
    forms.alert(u"Ouvrir une maquette de projet (pas une famille).",
                exitscript=True)

titre_hote = doc.Title
SRC_HOTE = titre_hote

# Liens : un par type de lien (une maquette liee plusieurs fois est lue une
# fois). Les ids sont materialises avant toute resolution.
liens = []
types_vus = set()
for lid in list(FilteredElementCollector(doc).OfClass(RevitLinkInstance)
                .ToElementIds()):
    instance = doc.GetElement(lid)
    tid = inv.lire(SRC_HOTE, u"modeles", idv(lid), u"Type de lien",
                   lambda: instance.GetTypeId())
    if not valide(tid) or idv(tid) in types_vus:
        continue
    types_vus.add(idv(tid))
    type_lien = doc.GetElement(tid)
    nom_lien = inv.lire(SRC_HOTE, u"modeles", idv(tid), u"Nom du lien",
                        lambda: nom_element(type_lien))
    imbrique = inv.lire(SRC_HOTE, u"modeles", idv(tid), u"Lien imbrique",
                        lambda: bool(type_lien.IsNestedLink))
    ldoc = None
    if imbrique is False:
        ldoc = inv.lire(SRC_HOTE, u"modeles", idv(tid), u"Document du lien",
                        lambda: instance.GetLinkDocument())
    liens.append({u"type_id": idv(tid), u"nom": nom_lien,
                  u"imbrique": imbrique,
                  u"doc": ldoc if not non_lu(ldoc) else None,
                  u"titre": ldoc.Title if ldoc is not None and not non_lu(ldoc)
                  else nom_lien})

# Une meme maquette atteinte par deux types de lien n'est lue qu'une fois.
docs_vus = set()
for lien in liens:
    if lien[u"doc"] is None:
        continue
    cle = (lien[u"doc"].Title, lien[u"doc"].PathName)
    if cle in docs_vus:
        lien[u"doc"] = None
        lien[u"doublon"] = True
    docs_vus.add(cle)

etiquettes = L.identifiants_sources(
    [titre_hote] + [l[u"titre"] for l in liens])
for lien, etiquette in zip(liens, etiquettes[1:]):
    lien[u"source"] = etiquette

charges = [l for l in liens if l[u"doc"] is not None]
choisis = []
if charges:
    libelles = [l[u"source"] for l in charges]
    selection = forms.SelectFromList.show(
        libelles, multiselect=True,
        title=u"Liens a inventorier - l'hote est toujours lu",
        button_name=u"Lire l'hote + les liens coches")
    if selection:
        choisis = [l for l in charges if l[u"source"] in selection]

# Sous-projets fermes : listes et annonces AVANT tout chiffre.
a_lire = [(doc, SRC_HOTE, L.ROLE_HOTE)] + \
    [(l[u"doc"], l[u"source"], L.ROLE_LIEN) for l in choisis]
fermes = {}
for d, src, _role in a_lire:
    fermes[src] = inv.lire(src, u"modeles", u"", u"Sous-projets fermes",
                           lambda: sous_projets_fermes(d))
avec_fermes = [(src, f) for src, f in fermes.items()
               if f and not non_lu(f)]
if avec_fermes:
    texte = u"\n".join([u"- {0} : {1}".format(src, u", ".join(f))
                        for src, f in avec_fermes])
    reponse = forms.alert(
        u"Sous-projets FERMES : leurs elements ne sont pas charges et "
        u"compteraient zero sans le dire.\n\n" + texte +
        u"\n\nLes ouvrir avant de lancer l'inventaire, ou continuer en "
        u"sachant que les chiffres les excluent.",
        options=[u"Continuer quand meme", u"Annuler"])
    if reponse != u"Continuer quand meme":
        forms.alert(u"Inventaire annule. Rien n'a ete lu ni ecrit.",
                    exitscript=True)

base = forms.pick_folder(title=u"Dossier ou deposer l'inventaire")
if not base:
    forms.alert(u"Aucun dossier choisi. Rien n'a ete lu ni ecrit.",
                exitscript=True)

maintenant = datetime.datetime.now()
dossier = os.path.join(base, L.nom_dossier_sortie(titre_hote, maintenant))
suffixe = 2
racine_dossier = dossier
while os.path.exists(dossier):
    dossier = u"{0}_{1}".format(racine_dossier, suffixe)
    suffixe += 1


# ---------------------------------------------------------------------------
# 9. En-tete a l'ecran, avant tout chiffre
# ---------------------------------------------------------------------------

out.print_md(u"# Inventaire systemes")
out.print_md(u"**Version de l'outil** : `{0}` · **Maquette** : `{1}`".format(
    VERSION, titre_hote))
out.print_md(u"> Lecture seule : rien n'est ecrit dans la maquette.")
for src, f in avec_fermes:
    out.print_md(u"> **Sous-projets fermes dans `{0}`** : {1} - leurs "
                 u"elements ne sont PAS comptes.".format(src, u", ".join(f)))
if doc.IsWorkshared:
    detachee = inv.lire(SRC_HOTE, u"modeles", u"", u"Copie detachee",
                        lambda: bool(doc.IsDetached))
    if detachee is not True:
        out.print_md(u"> Maquette collaborative non detachee : l'inventaire "
                     u"decrit l'etat synchronise a l'instant de la lecture.")
non_lus = [l for l in liens
           if l[u"doc"] is None and not l.get(u"doublon")]
if non_lus:
    out.print_md(u"> Liens non lus : " + u", ".join(
        [u"`{0}`".format(l[u"source"]) for l in non_lus]))
non_choisis = [l for l in charges if l not in choisis]
if non_choisis:
    out.print_md(u"> Liens charges non coches (hors inventaire) : " +
                 u", ".join([u"`{0}`".format(l[u"source"])
                             for l in non_choisis]))


# ---------------------------------------------------------------------------
# 10. Lecture
# ---------------------------------------------------------------------------

PHASES = (
    (u"parametres", lire_parametres),
    (u"systemes", lire_systemes),
    (u"types_canalisation_gaine", lire_types_canalisation),
    (u"electricite", lire_electricite),
    (u"filtres", lire_filtres),
    (u"familles", lire_familles),
    (u"nomenclatures", lire_nomenclatures),
)


def meta_modele(d, src, role):
    lire = lambda prop, f: inv.lire(src, u"modeles", u"", prop, f)
    return inv.ajouter_modele(
        src, role, lire(u"titre", lambda: d.Title),
        lire(u"chemin_visible", lambda: chemin_visible(d)),
        lire(u"cloud", lambda: bool(d.IsModelInCloud)),
        lire(u"workshared", lambda: bool(d.IsWorkshared)),
        L.LU, liste_fermes(fermes.get(src)))


def liste_fermes(valeur):
    if non_lu(valeur):
        return [L.NON_LU]
    return valeur or []


# Liens non lus : une ligne de modele et une anomalie chacun. Un doublon
# (meme maquette qu'un autre type de lien) est lu sous l'autre etiquette.
for lien in liens:
    if lien[u"doc"] is not None or lien.get(u"doublon"):
        continue
    # Lien imbrique : limite prevue de la v0. Lien decharge : la maquette
    # n'a pas pu etre lue, c'est une erreur de lecture.
    nature = L.NATURE_ERREUR
    if lien[u"imbrique"] is True:
        statut = L.IMBRIQUE_NON_LU
        raison = u"lien imbrique : non lu (v0)"
        nature = L.NATURE_NON_APPLICABLE
    elif non_lu(lien[u"imbrique"]):
        statut = L.ERREUR
        raison = u"nature du lien illisible : non lu"
    else:
        statut = L.NON_CHARGE
        raison = u"lien decharge, introuvable ou sans document : non lu"
    inv.anomalie(SRC_HOTE, u"modeles", lien[u"type_id"], u"statut_lecture",
                 raison, nature)
    inv.ajouter_modele(lien[u"source"], L.ROLE_LIEN, lien[u"nom"], u"",
                       L.NON_LU, L.NON_LU, statut, [])

annule = False
contextes = []
with forms.ProgressBar(title=u"Inventaire systemes - {value}/{max_value}",
                       cancellable=True) as pb:
    avancement = Avancement(pb, len(a_lire) * len(PHASES))
    try:
        for d, src, role in a_lire:
            modele = meta_modele(d, src, role)
            ctx = Contexte(d, src)
            contextes.append((ctx, modele))
            for nom_phase, phase in PHASES:
                try:
                    phase(ctx)
                except Annulation:
                    raise
                except Exception as err:
                    inv.publier_echecs()
                    inv.anomalie(src, nom_phase, u"", u"phase entiere",
                                 L.texte_erreur(err))
                    ctx.statut = L.ERREUR
                avancement.etape()
    except Annulation:
        annule = True

if annule:
    forms.alert(u"Inventaire annule. Aucun fichier n'a ete ecrit.",
                exitscript=True)

for ctx, modele in contextes:
    modele[u"statut_lecture"] = ctx.statut
    comptes = inv.comptes_par_table(ctx.src)
    comptes.update(ctx.comptes)
    modele[u"comptes"] = comptes

L.calculer_controles(inv)

app = doc.Application
# OrderedDict : sous Python 3.4, un dict ne garde pas l'ordre d'insertion.
outil = OrderedDict([
    (u"nom", u"bimflow - Inventaire systemes"),
    (u"version", VERSION),
    (u"date_iso", maintenant.strftime("%Y-%m-%dT%H:%M:%S")),
    (u"utilisateur", app.Username),
    (u"revit_version", app.VersionNumber),
    (u"revit_build", app.VersionBuild),
    (u"revit_langue", u"{0}".format(app.Language)),
    (u"duree_s", round(time.time() - debut, 1)),
])

os.makedirs(dossier)
chemins = L.ecrire_sorties(dossier, inv, outil)


# ---------------------------------------------------------------------------
# 11. Bilan a l'ecran
# ---------------------------------------------------------------------------

out.print_md(u"## Maquettes")
out.print_table(
    table_data=[[m[u"source_modele"], m[u"role"], m[u"statut_lecture"],
                 u"{0}".format(m[u"comptes"].get(u"systemes", u"")),
                 u"{0}".format(m[u"comptes"].get(u"filtres", u"")),
                 u"{0}".format(m[u"comptes"].get(u"familles", u""))]
                for m in inv.modeles],
    columns=[u"Source", u"Role", u"Lecture", u"Systemes", u"Filtres",
             u"Familles"])

out.print_md(u"## Controles (99_controles.csv)")
out.print_table(
    table_data=[[c[u"Source_modele"], c[u"Controle"], c[u"Attendu"],
                 c[u"Mesure"], c[u"Statut"]]
                for c in inv.tables[u"controles"]],
    columns=[u"Source", u"Controle", u"Attendu", u"Mesure", u"Statut"])

out.print_md(u"**Anomalies : {0} ERREUR**, et {1} NON_APPLICABLE (limites de "
             u"lecture prevues) - detail dans `90_anomalies.csv`.".format(
                 inv.nombre_anomalies(nature=L.NATURE_ERREUR),
                 inv.nombre_anomalies(nature=L.NATURE_NON_APPLICABLE)))

sans_vue = [f for f in inv.tables[u"filtres"]
            if f[u"Nb_vues"] == 0 and f[u"Nb_gabarits"] == 0]
if sans_vue:
    out.print_md(u"{0} filtre(s) ne sont appliques a aucune vue ni a aucun "
                 u"gabarit (mesure, sans conclusion).".format(len(sans_vue)))

out.print_md(u"## Fichiers")
out.print_md(u"Dossier : `{0}`".format(dossier))
out.print_md(u"{0} fichiers : {1}".format(
    len(chemins), u", ".join([os.path.basename(c) for c in chemins])))
out.print_md(u"Duree : {0} s.".format(outil[u"duree_s"]))
