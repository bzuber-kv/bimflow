# -*- coding: utf-8 -*-
# path : bimflow.extension/bimflow.tab/Georeferencement.panel/RecalageGlobal.pushbutton/script.py
"""Recalage global du modele : deplace tous les elements d'un vecteur donne en mm.

Le vecteur est exprime dans le repere du modele (axes projet), donc relatif a
l'origine interne, qui ne bouge pas. Les trois reperes (origine interne, point de
base, point topographique) sont exclus du deplacement : le recalage decale la
geometrie SOUS les reperes, il ne redefinit pas le systeme de coordonnees.
Pour redefinir le systeme partage, utiliser « Specifier les coordonnees en un
point » (R09 §2), pas cet outil.

Principe de securite central
----------------------------
UNE transaction, et UN appel `MoveElements` par groupe d'option de conception
(un seul appel dans le cas courant, sans options). Jamais element par element :
un deplacement individuel du mur puis de sa fenetre deplacerait la fenetre deux
fois. La forme en bloc laisse Revit recalculer les relations hote/heberge et
niveau/altitude une seule fois, apres la transformation.

MOTEUR
------
Mesure sur KS101 (2026-08-27), manifeste `pyRevit.addin` de Revit 2026 :
`...\\pyRevit-Master\\bin\\netcore\\engines\\IPY342\\pyRevitLoader.dll`.
Le moteur est donc **IronPython 3.4.2**, soit un niveau de langage Python 3.4.

Consequence d'interop, mesuree : sous IronPython 3, les methodes de l'API qui
attendent `ICollection` / `IList` / `ISet` **refusent une liste Python**
(`TypeError: expected ICollection[ElementId], got list`). La conversion est
obligatoire. Elle passe ici par `liste_dotnet()`, qui construit un
`List[DB.ElementId]`. **Tout nouvel appel de ce genre doit l'emprunter.**

DEROGATIONS a `_CONTEXT\\03_REGLES_DEV.md`
------------------------------------------
| Regle violee | Raison | Date |
|---|---|---|
| §1 shebang `#!/usr/bin/python3` | pyRevit lit la premiere ligne comme directive de moteur : « python3 » forcerait CPython. Or aucun moteur CPython n'est deploye en netcore, donc sous Revit 2026 — le bouton ne se chargerait pas du tout | 2026-08-27 |
| §1 `from __future__ import annotations` | Python 3.7+, hors de portee du niveau de langage 3.4 | 2026-08-27 |
| §2 annotations de type PEP 604 | Python 3.10+, idem | 2026-08-27 |
| §2 `pathlib` obligatoire | **A reexaminer** : `pathlib` entre dans la stdlib en Python 3.4, elle est donc vraisemblablement disponible sous IPY342. Le motif d'origine (« absente d'IronPython 2.7 ») est caduc. `os.path` conserve tant que la disponibilite reelle n'est pas verifiee dans Revit | 2026-08-27 |

Ces derogations sont inherentes a l'environnement pyRevit et couvertes par la
derogation « Type methode » deja actee au projet. Les f-strings restent
proscrites (Python 3.6+), et `ElementId.Value` garde son repli sur
`IntegerValue`, qui ne depend pas du moteur mais de la version de Revit.
"""

from __future__ import unicode_literals

import io
import os
import datetime

from System.Collections.Generic import List

from Autodesk.Revit import DB
from Autodesk.Revit.DB import IFailuresPreprocessor

from pyrevit import revit
from pyrevit import forms
from pyrevit import script


# --------------------------------------------------------------------------
# Reglages
# --------------------------------------------------------------------------

PIEDS_PAR_MM = 1.0 / 304.8

#: Tolerance du controle automatique post-deplacement, en mm.
TOLERANCE_CONTROLE_MM = 0.01

#: Nombre de CATEGORIES distinctes echantillonnees pour le controle automatique.
#: Un temoin par categorie : c'est la diversite, pas le nombre, qui donne au
#: controle une chance de voir un double deplacement qui ne frapperait qu'une
#: famille d'elements.
NB_POINTS_TEMOINS = 8

#: Nombre maximum de sondes de la bisection de diagnostic (garde-fou).
MAX_SONDES_DIAGNOSTIC = 250

#: Categories jamais deplacees. Doublon volontaire du test `isinstance` sur
#: `DB.BasePoint` : les noms d'enum varient selon les versions, l'un rattrape
#: ce que l'autre laisse passer.
CATEGORIES_EXCLUES = (
    "OST_ProjectBasePoint",
    "OST_SharedBasePoint",
    "OST_InternalOrigin",
    "OST_InternalPointOfOrigin",
    "OST_IOS_GeoSite",
    "OST_IOSSketchGrid",
    "OST_Cameras",
    # Lignes d'esquisse. Une esquisse est deja deplacee AVEC l'element qu'elle
    # definit ; la deplacer en plus est le double deplacement que l'outil
    # s'interdit pour les groupes. Reintegrees puis re-ecartees le 2026-08-27 :
    # la premiere comparaison ne portait que sur des comptes de messages,
    # l'inventaire des SUPPRESSIONS n'existait pas encore. C'est cet inventaire
    # qui doit trancher. Retirer cette ligne pour mesurer l'autre configuration.
    "OST_SketchLines",
    # Quadrillage de guidage : aide au calage des vues SUR LES FEUILLES, pas de
    # la geometrie de modele. Ajoute le 2026-08-27 apres qu'il soit ressorti
    # « non conforme » au controle — a juste titre, il n'avait pas a etre la.
    "OST_GuideGrid",
)

#: RETIRE de la liste ci-dessus le 2026-08-27 : `OST_SketchLines`.
#:
#: Il ecartait 1 151 esquisses — celles qui definissent sols, toits et
#: plafonds — pendant que les elements correspondants, eux, se deplacaient.
#: L'application du 2026-08-27 16:51 a produit trois messages qui designent
#: exactement ce decalage : « L'esquisse du sol est incorrecte » (14 elements),
#: « Impossible de creer l'extrusion » (8), « Echec de la modification de la
#: forme de dalle » (6).
#:
#: Principe general degage a cette occasion (remarque Bruno) : **toute
#: exclusion est un deplacement partiel**. Elle reproduit, a la frontiere entre
#: ce qui bouge et ce qui reste, l'effet du deplacement « un par un » que
#: l'outil s'interdit par ailleurs. Chaque ligne de cette liste doit donc etre
#: justifiee par autre chose qu'une intuition.

#: Echappatoire documentee. Si un appel `MoveElements` echoue, le diagnostic
#: nomme les classes fautives : les ajouter ici (noms de classes `DB.*`) et
#: relancer. Suspects connus non confirmes : "Level", "Grid".
CLASSES_EXCLUES_SUPPLEMENTAIRES = ()

#: Annuler toute la transaction des qu'une erreur Revit de gravite `Error`
#: survient, au lieu de laisser l'operateur arbitrer dans les dialogues.
#:
#: Motif, constate le 2026-08-27. Ces dialogues s'intitulent « Erreur —
#: impossible d'ignorer » et n'offrent que des issues DESTRUCTRICES :
#: « Supprimer les elements », « Detache les elements », « Supprimer les
#: contraintes », « Supprimer les references ». Les valider autorise Revit a
#: detruire pour faire passer l'operation — une dalle a forme modifiee a ainsi
#: disparu du modele. Trente-sept dialogues d'affilee ne sont pas un cadre ou
#: l'on decide bien.
#:
#: Avec ce reglage, le modele ressort INTACT et le rapport liste ce qui aurait
#: du etre detruit. Passer a False pour retrouver l'arbitrage manuel.
ANNULER_SUR_ERREUR = True

#: Filtre d'emprise : n'accepter que les elements ayant une etendue reelle dans
#: l'espace du modele. Passer a False pour reproduire le comportement anterieur
#: (utile pour comparer deux simulations sur un meme modele).
#:
#: Motif. Le tri procedait par liste NOIRE — on ecarte ce qu'on a pense a
#: ecarter — et la simulation du 2026-08-27 sur test_bz_Keovia a montre la
#: limite : de l'ordre de 1600 elements sans geometrie (materiaux, systemes,
#: nomenclatures, reglages, composants de legende) restaient dans le lot, soit
#: pres de 20 %. Ce filtre inverse la logique en liste BLANCHE.
FILTRE_EMPRISE_ACTIF = True

#: Nuages de points : ECARTES du deplacement (decision Bruno, 2026-08-27).
#:
#: Motif metier. Un recalage global invalide de toute facon les liens de nuages ;
#: la pratique est de les recreer apres coup, et les anciens nuages ne sont
#: generalement plus valides. Les deplacer serait donc du travail perdu.
#:
#: Exigence attachee a cette decision : le rapport, le journal ET la boite de
#: confirmation doivent le DIRE. Un nuage laisse en arriere sans avertissement
#: serait un piege — l'operateur croirait son modele complet.
EXCLURE_NUAGES_DE_POINTS = True

#: Categories reconnues comme nuages de points. Double detection avec le test
#: `isinstance` sur `DB.PointCloudInstance`, meme logique que pour les reperes.
CATEGORIES_NUAGES = ("OST_PointClouds",)

#: Categories exemptees du filtre d'emprise, au meme titre que les gabarits.
#:
#: `OST_Constraints` y entre le 2026-08-27 : le filtre ecartait 438 contraintes
#: faute d'emprise, et l'application a rapporte « Les contraintes ne sont pas
#: satisfaites » sur 10 elements. Une contrainte n'a pas d'etendue mais lie des
#: elements qui, eux, se deplacent — la laisser en arriere rompt le lien.
CATEGORIES_EXEMPTES_EMPRISE = ("OST_Constraints",)

#: Gabarits (*datums*) exemptes du filtre d'emprise. Un niveau est infini en
#: plan, un quadrillage en elevation : rien ne garantit que l'API leur donne
#: une emprise, et les perdre rendrait tout recalage en Z faux. Ils gardent
#: donc leur traitement anterieur, quoi que reponde `get_BoundingBox`.
CLASSES_DATUMS = ("Level", "Grid", "ReferencePlane")


LIBELLES_EXCLUSION = {
    "REPERE": "Repere de projet (origine interne, point de base, point topographique)",
    "VUE": "Vue ou feuille",
    "VIEWPORT": "Fenetre de vue sur feuille",
    "ANNOTATION_DE_VUE": "Element propre a une vue (annotation, cote, ligne de detail)",
    "MEMBRE_DE_GROUPE": "Membre de groupe — le groupe lui-meme est deplace",
    "MEMBRE_D_ASSEMBLAGE": "Membre d'assemblage — l'assemblage lui-meme est deplace",
    "SANS_CATEGORIE": "Element sans categorie (objet interne au fichier)",
    "CATEGORIE_EXCLUE": "Categorie exclue par reglage",
    "CLASSE_EXCLUE": "Classe exclue par reglage",
    "SANS_EMPRISE": "Sans emprise dans le modele (materiau, systeme, reglage, nomenclature)",
    "NUAGE_DE_POINTS": "Nuage de points — NON deplace, lien a recreer apres le recalage",
}


# --------------------------------------------------------------------------
# Utilitaires bas niveau
# --------------------------------------------------------------------------

def valeur_id(element_id):
    """Valeur entiere d'un ElementId, compatible Revit 2024+ et anterieur.

    Parameters
    ----------
    element_id : DB.ElementId

    Returns
    -------
    int
    """
    try:
        return element_id.Value
    except AttributeError:
        return element_id.IntegerValue


def mm_vers_pieds(valeur_mm):
    """Convertit des millimetres en pieds decimaux (unites internes Revit).

    Parameters
    ----------
    valeur_mm : float

    Returns
    -------
    float
    """
    try:
        return DB.UnitUtils.ConvertToInternalUnits(valeur_mm, DB.UnitTypeId.Millimeters)
    except Exception:
        return valeur_mm * PIEDS_PAR_MM


def pieds_vers_mm(valeur_pieds):
    """Convertit des pieds decimaux en millimetres.

    Parameters
    ----------
    valeur_pieds : float

    Returns
    -------
    float
    """
    try:
        return DB.UnitUtils.ConvertFromInternalUnits(valeur_pieds, DB.UnitTypeId.Millimeters)
    except Exception:
        return valeur_pieds * 304.8


def liste_dotnet(elements):
    """Construit une `List[ElementId]` .NET a partir d'elements Revit.

    Passage OBLIGATOIRE, pas une commodite : sous IronPython 3 (moteur mesure,
    voir l'en-tete du module), une methode de l'API attendant `ICollection`
    refuse une liste Python par `TypeError`. IronPython 2 tolerait la coercion
    implicite ; ce n'est plus le cas.

    Parameters
    ----------
    elements : list of DB.Element

    Returns
    -------
    System.Collections.Generic.List[DB.ElementId]
    """
    ids = List[DB.ElementId]()
    for element in elements:
        ids.Add(element.Id)
    return ids


def ids_de_categories(noms):
    """Valeurs entieres des ElementId de categorie, pour une liste de noms.

    Les noms d'enum `BuiltInCategory` varient selon les versions de Revit :
    ceux qui n'existent pas sont ignores en silence.

    Parameters
    ----------
    noms : iterable of str

    Returns
    -------
    set of int
    """
    valeurs = set()
    for nom in noms:
        bic = getattr(DB.BuiltInCategory, nom, None)
        if bic is None:
            continue
        valeurs.add(valeur_id(DB.ElementId(bic)))
    return valeurs


def classes_exclues():
    """Types .NET a exclure, resolus depuis leurs noms.

    Returns
    -------
    tuple of type
    """
    resolues = []
    for nom in CLASSES_EXCLUES_SUPPLEMENTAIRES:
        classe = getattr(DB, nom, None)
        if classe is not None:
            resolues.append(classe)
    return tuple(resolues)


def classes_datums():
    """Types .NET des gabarits, exemptes du filtre d'emprise.

    Returns
    -------
    tuple of type
    """
    resolues = []
    for nom in CLASSES_DATUMS:
        classe = getattr(DB, nom, None)
        if classe is not None:
            resolues.append(classe)
    return tuple(resolues)


def a_une_emprise(element):
    """Dit si l'element possede une etendue dans l'espace du modele.

    `get_BoundingBox(None)` demande l'emprise en coordonnees modele. Un element
    non geometrique — materiau, systeme de canalisation, nomenclature, reglage —
    renvoie None. Les elements d'esquisse (sols, toits, plafonds) en ont bien
    une, alors qu'ils n'ont souvent PAS de `Location` : c'est pourquoi le test
    porte sur l'emprise et non sur la localisation, qui les ecarterait a tort.

    En cas d'erreur, l'element est CONSERVE. Ce filtre ne doit jamais faire
    perdre de geometrie sur une exception ; si l'element est reellement
    indeplacable, le diagnostic par bisection le nommera.

    Parameters
    ----------
    element : DB.Element

    Returns
    -------
    bool
    """
    try:
        return element.get_BoundingBox(None) is not None
    except Exception:
        return True


def est_nuage_de_points(element, ids_nuages):
    """Dit si l'element est un nuage de points.

    Double detection, comme pour les reperes : la classe .NET rattrape ce que
    la categorie laisse passer, et reciproquement. Un nuage decharge peut ne
    plus exposer grand-chose.

    Parameters
    ----------
    element : DB.Element
    ids_nuages : set of int

    Returns
    -------
    bool
    """
    classe = getattr(DB, "PointCloudInstance", None)
    if classe is not None:
        try:
            if isinstance(element, classe):
                return True
        except Exception:
            pass
    try:
        if element.Category is not None and valeur_id(element.Category.Id) in ids_nuages:
            return True
    except Exception:
        pass
    return False


def nom_categorie(element):
    """Nom de categorie d'un element, ou un libelle de repli.

    Parameters
    ----------
    element : DB.Element

    Returns
    -------
    str
    """
    try:
        if element.Category is not None:
            return element.Category.Name
    except Exception:
        pass
    return "(sans categorie)"


# --------------------------------------------------------------------------
# Tri des elements
# --------------------------------------------------------------------------

def classer_element(element, ids_cat_exclues, classes_hors_jeu,
                    classe_origine_interne, datums, ids_nuages,
                    ids_exemptes_emprise):
    """Decide si un element doit etre deplace, et sinon pourquoi.

    L'ordre des tests est significatif : le premier motif rencontre est celui
    qui est journalise, et les motifs les plus specifiques passent en premier.
    Le filtre d'emprise vient en DERNIER, pour qu'un element ecarte par un
    motif precis garde ce motif au journal plutot que le motif generique.

    Parameters
    ----------
    element : DB.Element
    ids_cat_exclues : set of int
    classes_hors_jeu : tuple of type
    classe_origine_interne : type or None
        `DB.InternalOrigin` si la version de Revit l'expose, sinon None.
    datums : tuple of type
        Classes exemptees du filtre d'emprise.
    ids_nuages : set of int
        ElementId de categorie des nuages de points.

    Returns
    -------
    tuple of (bool, str or None)
        `(True, None)` si l'element doit etre deplace, sinon
        `(False, code_motif)`.
    """
    if isinstance(element, DB.BasePoint):
        return False, "REPERE"

    if classe_origine_interne is not None and isinstance(element, classe_origine_interne):
        return False, "REPERE"

    # ViewSheet derive de View : le test unique couvre vues et feuilles.
    if isinstance(element, DB.View):
        return False, "VUE"

    if isinstance(element, DB.Viewport):
        return False, "VIEWPORT"

    # Tot dans l'ordre : le motif « nuage » doit primer sur « sans emprise »,
    # sans quoi les nuages decharges seraient journalises sous un motif
    # technique au lieu du motif metier qui appelle une action.
    if EXCLURE_NUAGES_DE_POINTS and est_nuage_de_points(element, ids_nuages):
        return False, "NUAGE_DE_POINTS"

    if classes_hors_jeu and isinstance(element, classes_hors_jeu):
        return False, "CLASSE_EXCLUE"

    try:
        if element.ViewSpecific:
            return False, "ANNOTATION_DE_VUE"
    except Exception:
        pass

    # Un membre de groupe ne se deplace pas seul : le groupe est dans le lot,
    # et le deplacer deux fois decalerait le membre du double du vecteur. Sur
    # groupes imbriques, seul le groupe le plus exterieur a un GroupId invalide.
    try:
        if element.GroupId != DB.ElementId.InvalidElementId:
            return False, "MEMBRE_DE_GROUPE"
    except Exception:
        pass

    try:
        if element.AssemblyInstanceId != DB.ElementId.InvalidElementId:
            return False, "MEMBRE_D_ASSEMBLAGE"
    except Exception:
        pass

    if element.Category is None:
        return False, "SANS_CATEGORIE"

    if valeur_id(element.Category.Id) in ids_cat_exclues:
        return False, "CATEGORIE_EXCLUE"

    # Filtre d'emprise, en dernier. Les gabarits y echappent : les perdre
    # rendrait tout recalage en Z faux.
    if FILTRE_EMPRISE_ACTIF:
        exempte = (datums and isinstance(element, datums)) or \
                  (valeur_id(element.Category.Id) in ids_exemptes_emprise)
        if not exempte and not a_une_emprise(element):
            return False, "SANS_EMPRISE"

    return True, None


def trier_modele(document):
    """Parcourt le modele et repartit les elements entre deplaces et exclus.

    Parameters
    ----------
    document : DB.Document

    Returns
    -------
    tuple of (list, list, int)
        `(a_deplacer, exclusions, datums_sans_emprise)`. `exclusions` est une
        liste de tuples `(element, code_motif)`. Le troisieme terme compte les
        gabarits qui SERAIENT tombes sans l'exemption `CLASSES_DATUMS` : il
        mesure si cette exemption a reellement servi.
    """
    ids_cat_exclues = ids_de_categories(CATEGORIES_EXCLUES)
    ids_nuages = ids_de_categories(CATEGORIES_NUAGES)
    ids_exemptes_emprise = ids_de_categories(CATEGORIES_EXEMPTES_EMPRISE)
    classes_hors_jeu = classes_exclues()
    classe_origine_interne = getattr(DB, "InternalOrigin", None)
    datums = classes_datums()

    a_deplacer = []
    exclusions = []

    collecteur = DB.FilteredElementCollector(document).WhereElementIsNotElementType()
    for element in collecteur:
        garder, motif = classer_element(
            element, ids_cat_exclues, classes_hors_jeu, classe_origine_interne,
            datums, ids_nuages, ids_exemptes_emprise
        )
        if garder:
            a_deplacer.append(element)
        else:
            exclusions.append((element, motif))

    # Mesure de securite. Un compte non nul prouve que l'exemption des gabarits
    # a evite de les perdre — donc que niveaux et quadrillages n'ont pas
    # d'emprise au sens de l'API, et qu'un filtre sans exemption aurait fausse
    # tout recalage en Z.
    datums_sans_emprise = 0
    if FILTRE_EMPRISE_ACTIF and datums:
        for element in a_deplacer:
            if isinstance(element, datums) and not a_une_emprise(element):
                datums_sans_emprise += 1

    return a_deplacer, exclusions, datums_sans_emprise


def grouper_par_option(elements):
    """Regroupe les elements par option de conception.

    Un appel `MoveElements` ne peut pas melanger des elements appartenant a des
    options de conception differentes. Le modele principal forme un groupe, et
    chaque option de conception le sien.

    Parameters
    ----------
    elements : list of DB.Element

    Returns
    -------
    list of tuple
        Liste de `(libelle, elements)`, modele principal en tete.
    """
    principal = []
    par_option = {}
    libelles = {}

    for element in elements:
        try:
            option = element.DesignOption
        except Exception:
            option = None

        if option is None:
            principal.append(element)
            continue

        cle = valeur_id(option.Id)
        if cle not in par_option:
            par_option[cle] = []
            try:
                libelles[cle] = option.Name
            except Exception:
                libelles[cle] = "Option {0}".format(cle)
        par_option[cle].append(element)

    groupes = []
    if principal:
        groupes.append(("Modele principal", principal))
    for cle in sorted(par_option.keys()):
        groupes.append(("Option de conception : {0}".format(libelles[cle]), par_option[cle]))
    return groupes


def comptes_par_categorie(elements):
    """Compte les elements par categorie, avec les classes .NET rencontrees.

    La classe est ce qui permet d'identifier ce qu'un element EST, quand le nom
    de categorie reste ambigu. « Ligne d'axe » ne dit pas s'il s'agit d'un axe
    autonome ou du sous-element d'une canalisation — et la reponse decide s'il y
    a risque de double deplacement. La colonne de classes existe pour trancher
    ce genre de question sans quitter le rapport.

    Parameters
    ----------
    elements : list of DB.Element

    Returns
    -------
    list of tuple
        `(nom_categorie, compte, classes)` trie par compte decroissant, ou
        `classes` nomme les deux classes .NET les plus frequentes.
    """
    comptes = {}
    classes = {}
    for element in elements:
        nom = nom_categorie(element)
        comptes[nom] = comptes.get(nom, 0) + 1
        par_classe = classes.setdefault(nom, {})
        nom_classe = type(element).__name__
        par_classe[nom_classe] = par_classe.get(nom_classe, 0) + 1

    lignes = []
    for nom, compte in comptes.items():
        tri = sorted(classes[nom].items(), key=lambda paire: (-paire[1], paire[0]))
        resume = ", ".join("{0} ({1})".format(classe, n) for classe, n in tri[:2])
        if len(tri) > 2:
            resume += ", +{0} autre(s)".format(len(tri) - 2)
        lignes.append((nom, compte, resume))
    return sorted(lignes, key=lambda ligne: (-ligne[1], ligne[0]))


def comptes_exclusions(exclusions):
    """Compte les exclusions par motif puis par categorie.

    Parameters
    ----------
    exclusions : list of tuple

    Returns
    -------
    list of tuple
        `(libelle_motif, nom_categorie, compte)` trie par compte decroissant.
    """
    comptes = {}
    for element, motif in exclusions:
        cle = (motif, nom_categorie(element))
        comptes[cle] = comptes.get(cle, 0) + 1

    lignes = []
    for (motif, categorie), compte in comptes.items():
        lignes.append((LIBELLES_EXCLUSION.get(motif, motif), categorie, compte))
    return sorted(lignes, key=lambda ligne: (-ligne[2], ligne[0], ligne[1]))


# --------------------------------------------------------------------------
# Deplacement
# --------------------------------------------------------------------------

def deplacer_lot(document, elements, vecteur):
    """Depingle PUIS deplace. Unique point de passage du deplacement.

    POURQUOI CE POINT DE PASSAGE EXISTE
    -----------------------------------
    Revit refuse tout lot contenant un element epingle. Le depinglage n'est donc
    pas une precaution mais une etape inseparable du deplacement.

    L'oubli de cette etape a fausse DEUX instruments de mesure successifs le
    2026-08-27 : le sondage d'abord, l'essai de strategies ensuite — chacun
    rapportant « element epingle », un obstacle que l'operation reelle ne
    rencontre jamais puisqu'elle depingle. Corriger le premier n'a pas empeche
    d'ecrire le second avec le meme trou.

    D'ou cette fonction : **on ne peut plus deplacer sans depingler**, la regle
    est portee par le code et non par la memoire de qui l'ecrit.

    Parameters
    ----------
    document : DB.Document
    elements : list of DB.Element
    vecteur : DB.XYZ

    Returns
    -------
    list of DB.Element
        Les elements depingles, a repingler par l'appelant si la transaction
        doit etre validee. Inutile si elle est annulee : le retour arriere
        retablit l'epinglage.
    """
    depingles = depingler(elements)
    DB.ElementTransformUtils.MoveElements(document, liste_dotnet(elements), vecteur)
    return depingles


def copier_lot(document, elements, vecteur):
    """Copie le lot avec translation, sans toucher aux originaux.

    Autre chemin d'API que `MoveElements`, et celui qu'un utilisateur emprunte
    en copiant-collant a la main. Teste ici SANS supprimer les originaux : la
    question est seulement de savoir si tout se copie, la suppression n'y
    ajouterait qu'un risque.

    Le critere est le comptage : si `CopyElements` rend moins d'elements qu'on
    ne lui en a donne, la difference est ce qu'il n'a pas su reproduire.

    Returns
    -------
    tuple of (int, int, int)
        `(nombre soumis, nombre obtenu, nombre ecarte comme courbe)`.
    """
    # `CopyElements` REFUSE un lot melant des membres d'esquisse a d'autres
    # elements : « The input set of elements contains Sketch members along with
    # other elements » (mesure du 2026-08-27). Ecarter `OST_SketchLines` ne
    # suffit pas — il reste les esquisses d'escalier et de garde-corps, qui
    # portent d'autres categories mais sont des membres d'esquisse aussi.
    #
    # Le critere retenu est la CLASSE et non la categorie : tout ce qui derive
    # de `CurveElement` est une courbe d'esquisse ou de modele, et suit son
    # parent sans avoir besoin d'etre copie separement. C'est independant de la
    # langue de l'interface, la ou une liste de categories ne le serait pas.
    ids = List[DB.ElementId]()
    ecartes = 0
    for element in elements:
        if isinstance(element, DB.CurveElement):
            ecartes += 1
            continue
        ids.Add(element.Id)

    nouveaux = DB.ElementTransformUtils.CopyElements(document, ids, vecteur)
    try:
        obtenus = nouveaux.Count
    except AttributeError:
        obtenus = len(list(nouveaux))

    # Le total demande est celui reellement SOUMIS : on ne pretend pas avoir
    # copie ce qu'on a ecarte. `ecartes` est rapporte a part.
    return ids.Count, obtenus, ecartes


def deplacer_en_bloc(document, groupes, vecteur):
    """Deplace chaque groupe d'un seul appel `MoveElements`.

    A appeler a l'interieur d'une transaction ouverte.

    Parameters
    ----------
    document : DB.Document
    groupes : list of tuple
        Sortie de `grouper_par_option`.
    vecteur : DB.XYZ
        Vecteur en unites internes (pieds).

    Returns
    -------
    tuple of (list, list)
        `(appels, depingles)` ou `appels` liste `(libelle, nombre)` et
        `depingles` les elements a repingler apres validation.
    """
    appels = []
    depingles = []
    for libelle, elements in groupes:
        depingles.extend(deplacer_lot(document, elements, vecteur))
        appels.append((libelle, len(elements)))
    return appels, depingles


def depingler(elements):
    """Depingle les elements epingles et retourne ceux qui l'etaient.

    A appeler a l'interieur d'une transaction ouverte.

    Parameters
    ----------
    elements : list of DB.Element

    Returns
    -------
    list of DB.Element
        Les elements a repingler apres deplacement.
    """
    depingles = []
    for element in elements:
        try:
            if element.Pinned:
                element.Pinned = False
                depingles.append(element)
        except Exception:
            continue
    return depingles


def repingler(elements):
    """Repingle les elements passes en argument.

    A appeler a l'interieur de la meme transaction que `depingler`.

    Parameters
    ----------
    elements : list of DB.Element

    Returns
    -------
    int
        Nombre d'elements effectivement repingles.
    """
    compte = 0
    for element in elements:
        try:
            element.Pinned = True
            compte += 1
        except Exception:
            continue
    return compte


# --------------------------------------------------------------------------
# Controle automatique
# --------------------------------------------------------------------------

def relever_avertissements_document(document):
    """Releve les avertissements PERSISTANTS du document.

    `Document.GetWarnings()` retourne ce que montre « Verifier les
    avertissements » : l'etat de sante du modele, independamment de toute
    transaction. A distinguer des messages captures pendant une transaction,
    qui sont l'evenement et non l'etat.

    Parameters
    ----------
    document : DB.Document

    Returns
    -------
    dict
        `{(texte, tuple d'ids) : compte}`.
    """
    releve = {}
    try:
        messages = document.GetWarnings()
    except Exception:
        return releve

    for message in messages:
        try:
            texte = message.GetDescriptionText()
        except Exception:
            texte = "(indisponible)"
        try:
            ids = tuple(sorted(valeur_id(i) for i in message.GetFailingElements()))
        except Exception:
            ids = ()
        cle = (texte, ids)
        releve[cle] = releve.get(cle, 0) + 1
    return releve


def comparer_avertissements(avant, apres):
    """Compare deux releves de sante du modele.

    CRITERE DE RECETTE (formulation Bruno, 2026-08-27)
    -------------------------------------------------
    Une translation rigide ne doit RIEN changer a la sante du modele. Un
    avertissement present avant doit l'etre apres, sur les memes elements.

    - Un avertissement **apparu** signale une geometrie abimee par l'operation.
    - Un avertissement **disparu** est tout aussi suspect : il signale le plus
      souvent que l'element porteur a ete SUPPRIME pour faire passer
      l'operation. Ne jamais le lire comme une amelioration.

    L'operation est conforme si les deux listes sont vides.

    Parameters
    ----------
    avant, apres : dict
        Sorties de `relever_avertissements_document`.

    Returns
    -------
    tuple of (list, list, int)
        `(apparus, disparus, nb_conserves)`, chaque entree etant
        `(texte, ids, compte)`.
    """
    apparus = []
    disparus = []
    conserves = 0

    for cle, compte in apres.items():
        precedent = avant.get(cle, 0)
        if compte > precedent:
            apparus.append((cle[0], cle[1], compte - precedent))
        conserves += min(compte, precedent)

    for cle, compte in avant.items():
        restant = apres.get(cle, 0)
        if compte > restant:
            disparus.append((cle[0], cle[1], compte - restant))

    apparus.sort(key=lambda ligne: (-ligne[2], ligne[0]))
    disparus.sort(key=lambda ligne: (-ligne[2], ligne[0]))
    return apparus, disparus, conserves


def relever_niveaux(document):
    """Releve l'altitude de chaque niveau, en mm.

    Les niveaux n'ont pas de `Location` : le controle par points temoins ne les
    voit pas. C'etait l'angle mort du dispositif, alors meme que le sort des
    niveaux est LA question ouverte d'un recalage altimetrique. Leur propriete
    `Elevation` se lit directement — ce releve comble le trou.

    Parameters
    ----------
    document : DB.Document

    Returns
    -------
    dict
        `{valeur_id: (nom, altitude_mm)}`.
    """
    releve = {}
    for niveau in DB.FilteredElementCollector(document).OfClass(DB.Level):
        try:
            releve[valeur_id(niveau.Id)] = (niveau.Name,
                                            pieds_vers_mm(niveau.Elevation))
        except Exception:
            continue
    return releve


def comparer_niveaux(avant, apres, dz_mm):
    """Compare deux releves d'altitude de niveaux au deplacement attendu.

    Parameters
    ----------
    avant, apres : dict
        Sorties de `relever_niveaux`.
    dz_mm : float
        Deplacement vertical demande.

    Returns
    -------
    list of tuple
        `(nom, altitude_avant, altitude_apres, ecart_au_vecteur, conforme)`
        trie par altitude initiale.
    """
    lignes = []
    for cle, (nom, altitude_avant) in avant.items():
        if cle not in apres:
            lignes.append((nom, altitude_avant, None, None, False))
            continue
        altitude_apres = apres[cle][1]
        ecart = (altitude_apres - altitude_avant) - dz_mm
        lignes.append((nom, altitude_avant, altitude_apres, ecart,
                       abs(ecart) <= TOLERANCE_CONTROLE_MM))
    return sorted(lignes, key=lambda ligne: ligne[1])


def point_de_reference(element):
    """Un point de l'element en coordonnees MODELE, ou None.

    Le coin minimal de l'emprise (`get_BoundingBox(None)`) est exprime en
    coordonnees modele quel que soit le mode d'hebergement de l'element. C'est
    ce qui en fait un temoin fiable.

    POURQUOI PAS `LocationPoint`
    ----------------------------
    Abandonne le 2026-08-27, apres un faux positif. Pour un poteau porteur
    contraint entre deux niveaux, `LocationPoint.Z` semble exprime par rapport
    a son niveau de base : il ne bouge pas quand le modele se deplace. Le
    controle a rapporte un ecart de -10 000 mm sur un poteau **visuellement a
    sa place**. Un faux positif dans le seul filet de securite est pire qu'une
    absence de controle : il fait douter des vrais signalements.

    Reserve : l'emprise d'un element peut varier legerement si ses jonctions
    changent. Un ecart de l'ordre du millimetre sur un mur joint n'est donc pas
    forcement un deplacement fautif — c'est l'ordre de grandeur du vecteur qui
    signe un vrai defaut.

    Parameters
    ----------
    element : DB.Element

    Returns
    -------
    DB.XYZ or None
    """
    try:
        emprise = element.get_BoundingBox(None)
        if emprise is not None:
            return emprise.Min
    except Exception:
        pass

    # Repli pour les rares elements sans emprise restes dans le lot.
    try:
        localisation = element.Location
    except Exception:
        return None
    if isinstance(localisation, DB.LocationPoint):
        try:
            return localisation.Point
        except Exception:
            return None
    if isinstance(localisation, DB.LocationCurve):
        try:
            return localisation.Curve.GetEndPoint(0)
        except Exception:
            return None
    return None


def choisir_points_temoins(elements, nombre):
    """Selectionne des temoins repartis sur des categories DIFFERENTES.

    Prendre les N premiers venus les concentrerait sur la categorie la plus
    nombreuse — ici « Ligne d'axe », 40 % du lot — et le controle passerait a
    cote d'un double deplacement qui ne frapperait que, disons, les elements
    hebergés par un niveau. **La diversite de categories est ce qui donne au
    controle une chance de voir le defaut**, pas le nombre de points.

    Parameters
    ----------
    elements : list of DB.Element
    nombre : int
        Nombre de categories distinctes visees.

    Returns
    -------
    list of tuple
        `(element_id, XYZ_avant)`, une entree par categorie.
    """
    par_categorie = {}
    for element in elements:
        if len(par_categorie) >= nombre:
            break
        nom = nom_categorie(element)
        if nom in par_categorie:
            continue
        point = point_de_reference(element)
        if point is None:
            continue
        par_categorie[nom] = (element.Id, point)
    return [par_categorie[nom] for nom in sorted(par_categorie.keys())]


def verifier_points_temoins(document, temoins, vecteur):
    """Compare le deplacement observe au vecteur demande, en mm.

    Parameters
    ----------
    document : DB.Document
    temoins : list of tuple
        Sortie de `choisir_points_temoins`, relevee avant deplacement.
    vecteur : DB.XYZ
        Vecteur demande, en unites internes.

    Returns
    -------
    list of tuple
        `(element_id, categorie, ecart_dx_mm, ecart_dy_mm, ecart_dz_mm, conforme)`.
    """
    resultats = []
    for element_id, point_avant in temoins:
        element = document.GetElement(element_id)
        if element is None:
            continue
        # Meme extracteur qu'avant deplacement : comparer deux points obtenus
        # differemment n'aurait aucun sens.
        point_apres = point_de_reference(element)
        if point_apres is None:
            continue

        ecarts = (
            pieds_vers_mm((point_apres.X - point_avant.X) - vecteur.X),
            pieds_vers_mm((point_apres.Y - point_avant.Y) - vecteur.Y),
            pieds_vers_mm((point_apres.Z - point_avant.Z) - vecteur.Z),
        )
        conforme = all(abs(ecart) <= TOLERANCE_CONTROLE_MM for ecart in ecarts)
        resultats.append(
            (element_id, nom_categorie(element), ecarts[0], ecarts[1], ecarts[2], conforme)
        )
    return resultats


# --------------------------------------------------------------------------
# Diagnostic — isolement des elements refuses
# --------------------------------------------------------------------------

class CollecteurDAvertissements(IFailuresPreprocessor):
    """Enregistre les avertissements Revit d'une transaction, sans les etouffer.

    Les messages « objets detaches », « formes redefinies » et consorts sont la
    trace des relations rompues par un deplacement. Ils defilent a l'ecran puis
    disparaissent : sans capture, impossible de savoir CE qui a casse ni OU.

    Ce collecteur les note et rend la main a Revit (`Continue`), qui garde son
    comportement normal — l'utilisateur voit toujours ses boites de dialogue.
    On observe, on ne modifie rien.
    """

    def __init__(self, annuler_sur_erreur=True):
        self.messages = []
        self.erreurs_bloquantes = False
        # Reglable par instance, et non lu dans la constante globale : un ESSAI
        # doit aller au bout pour reveler tous les messages, la ou une
        # APPLICATION doit proteger le modele. Confondre les deux ferait
        # rapporter « echoue » a une strategie dont les seules victimes sont
        # des cotes — perte acceptee (constat Bruno, 2026-08-27).
        self.annuler_sur_erreur = annuler_sur_erreur

    def PreprocessFailures(self, accessor):
        try:
            for echec in accessor.GetFailureMessages():
                try:
                    severite = echec.GetSeverity()
                    gravite = str(severite)
                    if severite == DB.FailureSeverity.Error:
                        self.erreurs_bloquantes = True
                except Exception:
                    gravite = "?"
                try:
                    texte = echec.GetDescriptionText()
                except Exception:
                    texte = "(description indisponible)"
                try:
                    ids = [valeur_id(i) for i in echec.GetFailingElementIds()]
                except Exception:
                    ids = []
                self.messages.append((gravite, texte, ids))
        except Exception:
            pass

        # Annuler plutot que de laisser Revit appliquer ses resolutions
        # destructrices. Le modele ressort intact ; le rapport dira quoi.
        if self.annuler_sur_erreur and self.erreurs_bloquantes:
            return DB.FailureProcessingResult.ProceedWithRollBack

        return DB.FailureProcessingResult.Continue


def resumer_avertissements(messages):
    """Regroupe les avertissements par texte, avec comptes et echantillons d'ids.

    Parameters
    ----------
    messages : list of tuple
        `(gravite, texte, ids)`.

    Returns
    -------
    list of tuple
        `(gravite, texte, nb_occurrences, nb_elements, ids_echantillon)` trie
        par nombre d'elements decroissant.
    """
    groupes = {}
    for gravite, texte, ids in messages:
        cle = (gravite, texte)
        if cle not in groupes:
            groupes[cle] = {"occurrences": 0, "ids": []}
        groupes[cle]["occurrences"] += 1
        groupes[cle]["ids"].extend(ids)

    lignes = []
    for (gravite, texte), donnees in groupes.items():
        ids = donnees["ids"]
        lignes.append((gravite, texte, donnees["occurrences"], len(ids), ids[:6]))
    return sorted(lignes, key=lambda ligne: (-ligne[3], -ligne[2], ligne[1]))


def desolidariser(document, elements):
    """Defait les joints entre les elements du lot et leurs voisins.

    Les messages du 2026-08-27 implicaient massivement les joints : « joints
    mais ne se croisent pas » (48 elements), « impossible de conserver le joint
    entre le mur et cible », « impossible de couper l'element joint ». Un joint
    force Revit a recalculer une decoupe mutuelle apres le deplacement ; sur une
    geometrie fragile — dalle a forme modifiee — ce recalcul echoue.

    Returns
    -------
    int
        Nombre de joints defaits.
    """
    defaits = 0
    for element in elements:
        try:
            voisins = DB.JoinGeometryUtils.GetJoinedElements(document, element)
        except Exception:
            continue
        for id_voisin in voisins:
            voisin = document.GetElement(id_voisin)
            if voisin is None:
                continue
            try:
                if DB.JoinGeometryUtils.AreElementsJoined(document, element, voisin):
                    DB.JoinGeometryUtils.UnjoinGeometry(document, element, voisin)
                    defaits += 1
            except Exception:
                continue
    return defaits


def remettre_formes_a_plat(document, elements):
    """Remet a plat les dalles a forme modifiee (points et lignes de pente).

    Destructif en soi — a n'employer qu'en ESSAI annule, ou accompagne d'une
    restauration. Sert ici a repondre a une seule question : est-ce la donnee
    de forme qui bloque le deplacement, ou autre chose ?

    Returns
    -------
    int
        Nombre de formes remises a plat.
    """
    remises = 0
    for element in elements:
        # L'editeur s'obtient par propriete OU par methode selon la version, et
        # le nom differe entre Floor et Toposolid. Le filtre `IsEnabled` a ete
        # retire : il ecartait tout le monde et rendait cette strategie muette
        # — zero preparation, resultat identique a « tel quel » (2026-08-27).
        editeur = None
        for acces in ("SlabShapeEditor", "GetSlabShapeEditor"):
            try:
                valeur = getattr(element, acces, None)
            except Exception:
                continue
            if valeur is None:
                continue
            try:
                editeur = valeur() if callable(valeur) else valeur
            except Exception:
                editeur = None
            if editeur is not None:
                break
        if editeur is None:
            continue
        try:
            editeur.ResetSlabShape()
            remises += 1
        except Exception:
            continue
    return remises


def essayer_strategie(document, groupes_ids, vecteur, preparation, libelle,
                      fragiles=None, separer_transactions=False,
                      fragiles_dabord=False, methode="deplacer"):
    """Tente le deplacement complet sous une strategie, puis annule TOUT.

    Le commit interne fait **traiter** les erreurs par Revit — un simple
    `SubTransaction` annule ne les declenche jamais, ce qui rendait le sondage
    aveugle aux degats. Le `TransactionGroup` annule ensuite defait le commit
    ET la preparation : le modele ressort intact.

    Les dialogues sont neutralises pendant l'essai (`SetForcedModalHandling`) :
    il s'agit de mesurer, pas de faire arbitrer trente-sept fois.

    ON PASSE DES IDENTIFIANTS, PAS DES ELEMENTS
    -------------------------------------------
    L'annulation d'un `TransactionGroup` **invalide les objets `Element`**
    detenus en memoire : les strategies suivantes travaillaient sur des
    references mortes et levaient « The referenced object is not valid »
    (constate le 2026-08-27). Seuls les identifiants survivent au retour
    arriere ; les elements sont donc re-resolus au debut de chaque strategie.

    Parameters
    ----------
    document : DB.Document
    groupes_ids : list of tuple
        `(libelle_groupe, [valeurs entieres d'ElementId])`.
    vecteur : DB.XYZ
    preparation : callable or None
        Recoit `(document, elements)` avant le deplacement.
    libelle : str
    fragiles : set of int or None
        Si fourni, le deplacement se fait en DEUX appels `MoveElements` : le
        gros du lot d'abord, ces elements-la ensuite. Reproduit les conditions
        de la manipulation manuelle qui, seule, a sauve la dalle 4188355 :
        deplacer l'objet fragile a part, et non noye dans 7 900 voisins dont
        Revit tente de maintenir toutes les jonctions simultanement.

    Returns
    -------
    tuple
        `(libelle, reussi, nb_preparation, avertissements)`.
    """
    # Un essai va jusqu'au bout : on veut voir TOUS les messages, y compris
    # ceux dont les degats sont acceptables. Le groupe annule tout ensuite.
    collecteur = CollecteurDAvertissements(annuler_sur_erreur=False)
    incidents = []
    # Etat de sante AVANT, releve hors du groupe : c'est la reference contre
    # laquelle se juge la strategie.
    sante_avant = relever_avertissements_document(document)
    bilan_sante = None
    supprimes = []

    etat = {"preparations": 0, "reussi": True, "demandes": 0, "obtenus": 0,
            "ecartes": 0}

    def executer_sous_lot(sous_lot, avec_preparation):
        """Une transaction : preparation optionnelle, puis deplacement."""
        transaction = DB.Transaction(document, "bimflow - essai")
        transaction.Start()
        # Chaque reglage optionnel est garde separement : si l'un d'eux echoue,
        # le PREPROCESSEUR doit survivre. Groupes dans un seul try, une
        # exception sur SetForcedModalHandling faisait sauter le
        # SetFailureHandlingOptions final — donc plus aucune capture, et un
        # essai muet. C'est ce qui s'est produit le 2026-08-27.
        try:
            options = transaction.GetFailureHandlingOptions()
            options.SetFailuresPreprocessor(collecteur)
            for reglage in (lambda: options.SetForcedModalHandling(False),
                            lambda: options.SetClearAfterRollback(True)):
                try:
                    reglage()
                except Exception:
                    pass
            transaction.SetFailureHandlingOptions(options)
        except Exception:
            pass

        try:
            if avec_preparation and preparation is not None:
                etat["preparations"] += preparation(document, sous_lot)

            if methode == "copier":
                # Compter AVANT l'appel : si `CopyElements` leve, un comptage
                # place apres ne s'executerait jamais et le rapport afficherait
                # « 0 soumis, 0 obtenus » — indiscernable d'un lot vide. Defaut
                # constate le 2026-08-27, corrige ici.
                etat["demandes"] += len(sous_lot)
                demandes, obtenus, ecartes = copier_lot(
                    document, sous_lot, vecteur)
                etat["obtenus"] += obtenus
                etat["ecartes"] += ecartes
                if transaction.Commit() != DB.TransactionStatus.Committed:
                    etat["reussi"] = False
                return

            # Strategie 4 : deux appels dans UNE transaction. Distincte de la
            # strategie 5, qui scinde les transactions elles-memes.
            if fragiles and not separer_transactions:
                ordinaires = [e for e in sous_lot
                              if valeur_id(e.Id) not in fragiles]
                a_part = [e for e in sous_lot if valeur_id(e.Id) in fragiles]
                if ordinaires:
                    deplacer_lot(document, ordinaires, vecteur)
                if a_part:
                    deplacer_lot(document, a_part, vecteur)
            else:
                deplacer_lot(document, sous_lot, vecteur)

            if transaction.Commit() != DB.TransactionStatus.Committed:
                etat["reussi"] = False
                if not incidents:
                    incidents.append("Transaction annulee par Revit "
                                     "(aucun message capture).")
        except Exception as erreur:
            # NE JAMAIS avaler : sans ce texte, l'essai rapporte « echoue »
            # sans dire pourquoi, et n'apprend rien. Defaut constate le
            # 2026-08-27 — trois strategies « echouees », zero message.
            etat["reussi"] = False
            incidents.append("{0} : {1}".format(
                type(erreur).__name__,
                str(erreur).replace("\n", " ")[:300]))
            try:
                if transaction.HasStarted() and not transaction.HasEnded():
                    transaction.RollBack()
            except Exception:
                pass

    groupe = DB.TransactionGroup(document, "bimflow - essai " + libelle)
    groupe.Start()
    try:
        for _, ids in groupes_ids:
            # Re-resolution : voir la note sur l'invalidation des references.
            elements = []
            for valeur in ids:
                try:
                    element = document.GetElement(DB.ElementId(valeur))
                except Exception:
                    continue
                if element is not None:
                    elements.append(element)
            if not elements:
                continue

            # Deux TRANSACTIONS distinctes, et non deux appels dans une seule.
            # Revit ne regenere qu'au commit : dans une transaction unique il
            # voit l'etat final ou tout a bouge, donc toutes les jonctions a
            # maintenir. En deux transactions, la premiere laisse les jonctions
            # se rompre — un simple avertissement — et la seconde deplace
            # l'objet fragile alors qu'il n'y a plus rien a maintenir. C'est la
            # transposition de la sequence manuelle qui, seule, a preserve la
            # dalle 4188355.
            if separer_transactions and fragiles:
                lot_fragile = [e for e in elements
                               if valeur_id(e.Id) in fragiles]
                lot_reste = [e for e in elements
                             if valeur_id(e.Id) not in fragiles]
                # L'ORDRE est le tout. La dalle 4188355 meurt du mouvement de
                # ses VOISINS, pas du sien : la deplacer en second, c'est la
                # deplacer deja detruite. La deplacer en PREMIER reproduit la
                # seule condition ou elle a survecu — celle de la manipulation
                # manuelle, ou les voisins n'avaient pas encore bouge.
                sous_lots = ([lot_fragile, lot_reste] if fragiles_dabord
                             else [lot_reste, lot_fragile])
            else:
                sous_lots = [elements]

            for rang_lot, sous_lot in enumerate(sous_lots):
                if not sous_lot:
                    continue
                executer_sous_lot(sous_lot, rang_lot == 0)

        # Sante APRES, releve pendant que le groupe est encore actif : apres le
        # RollBack le modele est revenu a son etat initial et la comparaison
        # n'aurait plus aucun sens.
        bilan_sante = comparer_avertissements(
            sante_avant, relever_avertissements_document(document))

        # Inventaire des DISPARITIONS. Un avertissement qui s'efface est
        # ambigu : l'element a-t-il ete supprime, ou seulement modifie ? Seule
        # cette verification tranche, et la reponse change la correction a
        # apporter — empecher une destruction n'est pas restaurer une donnee.
        for _, ids in groupes_ids:
            for valeur in ids:
                try:
                    if document.GetElement(DB.ElementId(valeur)) is None:
                        supprimes.append(valeur)
                except Exception:
                    supprimes.append(valeur)
    finally:
        groupe.RollBack()

    if methode == "copier":
        # Les instruments habituels sont muets ici : tous les identifiants
        # changent, donc tout parait « supprime » et tout avertissement parait
        # deplace. Seul le comptage a un sens.
        supprimes = []
        bilan_sante = None
        incidents.append(
            "Copie : {0} elements soumis, {1} obtenus{2} "
            "({3} courbes d'esquisse ecartees, refusees par CopyElements "
            "en melange)".format(
                etat["demandes"], etat["obtenus"],
                "" if etat["demandes"] == etat["obtenus"]
                else " — {0} NON reproduits".format(
                    etat["demandes"] - etat["obtenus"]),
                etat["ecartes"]))

    return (libelle, etat["reussi"], etat["preparations"],
            resumer_avertissements(collecteur.messages), incidents, bilan_sante,
            supprimes)


def _sonde(document, elements, vecteur):
    """Tente un `MoveElements` annule aussitot. Retourne (accepte, detail).

    A appeler a l'interieur d'une transaction ouverte.
    """
    sous_transaction = DB.SubTransaction(document)
    sous_transaction.Start()
    try:
        deplacer_lot(document, elements, vecteur)
        return True, ""
    except Exception as erreur:
        return False, str(erreur).replace("\n", " ")[:160]
    finally:
        sous_transaction.RollBack()


def sonder_deplacement(document, groupes, vecteur):
    """Predit le comportement de `MoveElements` sans rien appliquer.

    NE JAMAIS SONDER UNE CATEGORIE ISOLEE
    -------------------------------------
    Une fenetre deplacee sans son mur quitte son hote : Revit la refuse. De
    meme pour tout element attache separe de son support. Or dans le lot
    complet, le mur bouge aussi et l'ensemble passe sans difficulte. Sonder une
    categorie seule **fabrique donc des faux refus** et designe des coupables
    innocents. (Remarque Bruno, 2026-08-27 — elle vaut aussi pour la bisection
    de `isoler_elements_refuses`, dont les sous-lots separent tout autant les
    hotes de leurs heberges.)

    D'ou la methode en deux temps, qui ne rompt jamais le contexte :

    1. **Le lot complet**, groupe par groupe. C'est la seule question qui
       compte : s'il passe, il n'y a rien a diagnostiquer.
    2. **Seulement s'il echoue** : retrait d'UNE categorie a la fois, le reste
       du lot intact (*leave-one-out*). Si le lot passe une fois la categorie C
       retiree, C est **impliquee** — le mot est choisi, elle n'est pas
       forcement seule en cause.

    Limite assumee : si plusieurs causes independantes coexistent, aucun
    retrait unique ne suffira et l'etape 2 ne designera rien. Le cas est
    detecte et rapporte comme tel plutot que passe sous silence.

    Tout est annule : le modele ressort intact.

    Parameters
    ----------
    document : DB.Document
    groupes : list of tuple
        Sortie de `grouper_par_option`.
    vecteur : DB.XYZ

    Returns
    -------
    tuple of (bool, list, list, int)
        `(lot_complet_accepte, echecs_de_groupe, impliquees, nb_depingles)` ou
        `echecs_de_groupe` liste `(libelle_groupe, detail)` et `impliquees`
        liste `(libelle_groupe, nom_categorie, nombre, detail_du_lot_complet)`.
    """
    echecs_de_groupe = []
    impliquees = []
    nb_depingles = 0

    transaction = DB.Transaction(document, "bimflow - sondage")
    transaction.Start()
    try:
        # Le sondage doit reproduire FIDELEMENT l'operation reelle, qui depingle
        # avant de deplacer. Sans cette etape, il testerait une operation qui
        # n'existe pas et rapporterait « element epingle » — un refus sans aucun
        # rapport avec ce qui se passerait a l'application. Le RollBack final
        # repingle tout. (Defaut constate au sondage du 2026-08-27 16:27.)
        tous = [element for _, elements in groupes for element in elements]
        nb_depingles = len(depingler(tous))

        for libelle_groupe, elements in groupes:
            accepte, detail = _sonde(document, elements, vecteur)
            if accepte:
                continue
            echecs_de_groupe.append((libelle_groupe, detail))

            par_categorie = {}
            for element in elements:
                par_categorie.setdefault(nom_categorie(element), []).append(element)

            for nom in sorted(par_categorie.keys()):
                ecartes = set(valeur_id(e.Id) for e in par_categorie[nom])
                reste = [e for e in elements if valeur_id(e.Id) not in ecartes]
                if not reste:
                    continue
                passe, _ = _sonde(document, reste, vecteur)
                if passe:
                    impliquees.append(
                        (libelle_groupe, nom, len(par_categorie[nom]), detail))
    finally:
        transaction.RollBack()

    return (not echecs_de_groupe), echecs_de_groupe, impliquees, nb_depingles


def isoler_elements_refuses(document, elements, vecteur):
    """Nomme par bisection les elements que `MoveElements` refuse SEULS.

    RESERVE IMPORTANTE — lire avant d'exploiter le resultat
    -------------------------------------------------------
    La bisection coupe le lot en deux et **separe les hotes de leurs heberges** :
    une fenetre sondee sans son mur est refusee alors qu'elle passerait dans le
    lot complet. Ce que cette fonction nomme, ce sont donc les elements qui ne
    peuvent pas bouger SEULS — ce qui n'est pas la meme chose que les elements
    qui bloquent le lot. Attendre des faux positifs sur tout ce qui est heberge
    ou attache. (Reserve soulevee par Bruno, 2026-08-27.)

    Preferer `sonder_deplacement`, qui ne rompt jamais le contexte. Cette
    fonction ne garde d'utilite qu'en dernier recours, a l'interieur d'une
    categorie deja identifiee comme impliquee.

    Toutes les sondes sont annulees : le modele ressort intact. Le cout est en
    O(k log n) sondes pour k fautifs, borne par `MAX_SONDES_DIAGNOSTIC` — borne
    largement insuffisante des que k depasse la trentaine.

    Parameters
    ----------
    document : DB.Document
    elements : list of DB.Element
    vecteur : DB.XYZ

    Returns
    -------
    tuple of (list, bool)
        `(elements_refuses, diagnostic_complet)`. Le drapeau est False si le
        plafond de sondes a ete atteint avant la fin de la recherche.
    """
    compteur = {"sondes": 0}

    def sonder(lot):
        """Retourne True si Revit accepte de deplacer ce lot."""
        compteur["sondes"] += 1
        sous_transaction = DB.SubTransaction(document)
        sous_transaction.Start()
        try:
            deplacer_lot(document, lot, vecteur)
            return True
        except Exception:
            return False
        finally:
            sous_transaction.RollBack()

    def chercher(lot):
        if not lot or compteur["sondes"] >= MAX_SONDES_DIAGNOSTIC:
            return []
        if sonder(lot):
            return []
        if len(lot) == 1:
            return list(lot)
        milieu = len(lot) // 2
        return chercher(lot[:milieu]) + chercher(lot[milieu:])

    transaction = DB.Transaction(document, "bimflow - diagnostic recalage")
    transaction.Start()
    try:
        refuses = chercher(list(elements))
    finally:
        transaction.RollBack()

    return refuses, compteur["sondes"] < MAX_SONDES_DIAGNOSTIC


# --------------------------------------------------------------------------
# Journal
# --------------------------------------------------------------------------

def dossier_journal(document):
    """Determine ou ecrire le journal : a cote du modele, sinon dans TEMP.

    Parameters
    ----------
    document : DB.Document

    Returns
    -------
    str
    """
    chemin = document.PathName
    if chemin and os.path.isdir(os.path.dirname(chemin)):
        return os.path.dirname(chemin)
    return os.environ.get("TEMP", os.path.expanduser("~"))


def ecrire_journal(document, horodatage, vecteur_mm, mode, a_deplacer,
                   exclusions, groupes, appels, nb_depingles, controles,
                   message_final, note_filtre="", sondages=None,
                   avertissements=None, niveaux=None):
    """Ecrit le journal d'execution au format Markdown.

    Parameters
    ----------
    document : DB.Document
    horodatage : datetime.datetime
    vecteur_mm : tuple of float
    mode : str
        "SIMULATION" ou "APPLIQUE".
    a_deplacer : list of DB.Element
    exclusions : list of tuple
    groupes : list of tuple
    appels : list of tuple or None
    nb_depingles : int or None
    controles : list of tuple or None
    message_final : str

    Returns
    -------
    str
        Chemin du fichier ecrit.
    """
    nom_modele = os.path.splitext(os.path.basename(document.PathName or "modele_non_enregistre"))[0]
    nom_fichier = "recalage_global_{0}_{1}.md".format(
        nom_modele, horodatage.strftime("%Y%m%d_%H%M%S")
    )
    chemin = os.path.join(dossier_journal(document), nom_fichier)

    lignes = []
    lignes.append("# Recalage global — journal d'execution")
    lignes.append("")
    lignes.append("| Champ | Valeur |")
    lignes.append("|---|---|")
    lignes.append("| Date | {0} |".format(horodatage.strftime("%Y-%m-%d %H:%M:%S")))
    lignes.append("| Modele | {0} |".format(document.PathName or "(non enregistre)"))
    lignes.append("| Mode | {0} |".format(mode))
    lignes.append("| Vecteur demande (mm) | dX = {0:.3f} · dY = {1:.3f} · dZ = {2:.3f} |".format(*vecteur_mm))
    lignes.append("| Elements deplaces | {0} |".format(len(a_deplacer)))
    lignes.append("| Elements exclus | {0} |".format(len(exclusions)))
    lignes.append("| Appels MoveElements | {0} |".format(len(appels) if appels is not None else "—"))
    lignes.append("| Elements depingles puis repingles | {0} |".format(
        nb_depingles if nb_depingles is not None else "—"))
    lignes.append("")
    if note_filtre:
        lignes.append(note_filtre)
        lignes.append("")

    lignes.append("## Groupes d'options de conception")
    lignes.append("")
    lignes.append("| Groupe | Elements |")
    lignes.append("|---|---|")
    for libelle, elements in groupes:
        lignes.append("| {0} | {1} |".format(libelle, len(elements)))
    lignes.append("")

    lignes.append("## Elements deplaces, par categorie")
    lignes.append("")
    lignes.append("| Categorie | Nombre | Classes .NET |")
    lignes.append("|---|---|---|")
    for nom, compte, classes in comptes_par_categorie(a_deplacer):
        lignes.append("| {0} | {1} | {2} |".format(nom, compte, classes))
    lignes.append("")

    lignes.append("## Exclusions")
    lignes.append("")
    lignes.append("| Motif | Categorie | Nombre |")
    lignes.append("|---|---|---|")
    for motif, categorie, compte in comptes_exclusions(exclusions):
        lignes.append("| {0} | {1} | {2} |".format(motif, categorie, compte))
    lignes.append("")

    if sondages is not None:
        lot_passe, echecs_de_groupe, impliquees, nb_depingles = sondages
        lignes.append("## Sondage — aucune modification appliquee")
        lignes.append("")
        lignes.append("{0} element(s) depingle(s) avant sondage, comme le ferait "
                      "l'operation reelle.".format(nb_depingles))
        lignes.append("")
        if lot_passe:
            lignes.append("**Le lot complet est accepte par `MoveElements`** "
                          "pour le vecteur dX = {0:.3f} · dY = {1:.3f} · "
                          "dZ = {2:.3f} mm, groupe par groupe.".format(*vecteur_mm))
            lignes.append("")
            reserve = avertissement_composantes(vecteur_mm)
            if reserve:
                lignes.append("> " + reserve.replace("\n", " "))
                lignes.append("")
        else:
            lignes.append("| Groupe refuse en lot complet | Erreur |")
            lignes.append("|---|---|")
            for groupe, detail in echecs_de_groupe:
                lignes.append("| {0} | {1} |".format(groupe, detail or "—"))
            lignes.append("")
            if impliquees:
                lignes.append("Categories dont le retrait suffit a debloquer le "
                              "lot — « impliquees », pas necessairement seules "
                              "en cause :")
                lignes.append("")
                lignes.append("| Categorie | Elements | Groupe |")
                lignes.append("|---|---|---|")
                for groupe, nom, nombre, _ in impliquees:
                    lignes.append("| {0} | {1} | {2} |".format(nom, nombre, groupe))
            else:
                lignes.append("**Aucun retrait unique ne debloque le lot** : "
                              "plusieurs causes independantes coexistent.")
            lignes.append("")

    if niveaux:
        lignes.append("## Altitude des niveaux (mm) — ecart au dZ demande")
        lignes.append("")
        lignes.append("| Niveau | Avant | Apres | Ecart | Conforme |")
        lignes.append("|---|---|---|---|---|")
        for nom, avant, apres, ecart, conforme in niveaux:
            lignes.append("| {0} | {1:.1f} | {2} | {3} | {4} |".format(
                nom, avant,
                "—" if apres is None else "{0:.1f}".format(apres),
                "—" if ecart is None else "{0:.4f}".format(ecart),
                "oui" if conforme else "NON"))
        lignes.append("")

    if avertissements:
        total = sum(ligne[3] for ligne in avertissements)
        lignes.append("## ⚠ Avertissements Revit — relations rompues")
        lignes.append("")
        lignes.append("{0} avertissement(s) distinct(s), {1} element(s) "
                      "concerne(s). L'API a accepte le deplacement, ce qui ne "
                      "veut pas dire que le resultat est juste.".format(
                          len(avertissements), total))
        lignes.append("")
        lignes.append("| Gravite | Message | Occurrences | Elements | Echantillon d'ids |")
        lignes.append("|---|---|---|---|---|")
        for gravite, texte, occurrences, nb, ids in avertissements:
            lignes.append("| {0} | {1} | {2} | {3} | {4} |".format(
                gravite, texte, occurrences, nb,
                ", ".join(str(i) for i in ids) or "—"))
        lignes.append("")

    if controles:
        lignes.append("## Controle automatique sur points temoins")
        lignes.append("")
        lignes.append("| Element | Categorie | Ecart dX (mm) | Ecart dY (mm) | Ecart dZ (mm) | Conforme |")
        lignes.append("|---|---|---|---|---|---|")
        for element_id, categorie, ex, ey, ez, conforme in controles:
            lignes.append("| {0} | {1} | {2:.4f} | {3:.4f} | {4:.4f} | {5} |".format(
                valeur_id(element_id), categorie, ex, ey, ez, "oui" if conforme else "NON"))
        lignes.append("")
        lignes.append("Tolerance : {0} mm. Ce controle ne remplace pas le releve manuel ".format(
            TOLERANCE_CONTROLE_MM))
        lignes.append("par cotes de coordonnees sur trois points connus (R09 §3, etape 3).")
        lignes.append("")

    lignes.append("## Resultat")
    lignes.append("")
    lignes.append(message_final)
    lignes.append("")

    # io.open en mode texte unicode, les noms de categorie Revit etant
    # accentues. Sous IronPython 3 c'est l'`open` standard ; la forme explicite
    # est conservee pour que l'encodage reste lisible au point d'appel.
    fichier = io.open(chemin, "w", encoding="utf-8")
    try:
        fichier.write("\n".join(lignes))
    finally:
        fichier.close()

    return chemin


# --------------------------------------------------------------------------
# Interface
# --------------------------------------------------------------------------

def demander_vecteur():
    """Demande le vecteur de recalage a l'utilisateur.

    Returns
    -------
    tuple of float or None
        `(dx_mm, dy_mm, dz_mm)`, ou None si l'utilisateur annule.
    """
    while True:
        saisie = forms.ask_for_string(
            default="0 ; 0 ; 0",
            prompt="Vecteur de recalage en mm, dans les axes du projet.\n"
                   "Format : dX ; dY ; dZ",
            title="Recalage global — vecteur",
        )
        if not saisie:
            return None

        morceaux = saisie.replace(",", ".").replace(";", " ").split()
        if len(morceaux) != 3:
            forms.alert("Trois valeurs attendues, separees par « ; ».", title="Saisie invalide")
            continue
        try:
            valeurs = tuple(float(morceau) for morceau in morceaux)
        except ValueError:
            forms.alert("Valeurs numeriques attendues.", title="Saisie invalide")
            continue

        if all(abs(valeur) < 1e-9 for valeur in valeurs):
            forms.alert("Le vecteur est nul — rien a faire.", title="Vecteur nul")
            continue

        return valeurs


def verifier_contexte(document):
    """Verifie que le document se prete a l'operation.

    Parameters
    ----------
    document : DB.Document

    Returns
    -------
    bool
        True si l'operation peut se poursuivre.
    """
    if document.IsFamilyDocument:
        forms.alert("Cet outil s'applique a un modele de projet, pas a une famille.",
                    title="Recalage global")
        return False

    if getattr(document, "IsWorkshared", False) and not getattr(document, "IsDetached", False):
        reponse = forms.alert(
            "Ce modele est collaboratif et n'est pas detache.\n\n"
            "Le recalage doit se faire sur une COPIE DETACHEE. Sur un modele\n"
            "collaboratif, les elements appartenant a d'autres utilisateurs ne\n"
            "peuvent pas etre modifies et l'operation echouera partiellement.",
            title="Modele collaboratif",
            options=["Arreter", "Poursuivre quand meme"],
        )
        if reponse != "Poursuivre quand meme":
            return False

    return True


def publier_rapport(sortie, document, vecteur_mm, a_deplacer, exclusions, groupes,
                    note_filtre=""):
    """Affiche le rapport de simulation dans la fenetre pyRevit.

    Parameters
    ----------
    sortie : pyrevit.output.PyRevitOutputWindow
    document : DB.Document
    vecteur_mm : tuple of float
    a_deplacer : list of DB.Element
    exclusions : list of tuple
    groupes : list of tuple
    """
    sortie.print_md("# Recalage global — simulation")
    sortie.print_md(
        "**Modele** : {0}".format(document.PathName or "(non enregistre)")
    )
    sortie.print_md(
        "**Vecteur demande** : dX = {0:.3f} mm · dY = {1:.3f} mm · dZ = {2:.3f} mm".format(*vecteur_mm)
    )
    sortie.print_md(
        "**Bilan** : {0} elements a deplacer, {1} exclus, "
        "{2} appel(s) `MoveElements` dans une transaction unique.".format(
            len(a_deplacer), len(exclusions), len(groupes))
    )
    if note_filtre:
        sortie.print_md(note_filtre)

    sortie.print_table(
        table_data=[[libelle, len(elements)] for libelle, elements in groupes],
        title="Groupes d'options de conception",
        columns=["Groupe", "Elements"],
    )

    sortie.print_table(
        table_data=[list(ligne) for ligne in comptes_par_categorie(a_deplacer)],
        title="Elements deplaces, par categorie",
        columns=["Categorie", "Nombre", "Classes .NET"],
    )

    sortie.print_table(
        table_data=[list(ligne) for ligne in comptes_exclusions(exclusions)],
        title="Exclusions",
        columns=["Motif", "Categorie", "Nombre"],
    )


def avertissement_composantes(vecteur_mm):
    """Nomme les composantes du vecteur que le sondage n'a PAS eprouvees.

    Un resultat de sondage ne vaut QUE pour le vecteur sonde. Le cas le plus
    trompeur est `dZ = 0` : un niveau etant infini en plan, un deplacement
    horizontal ne lui demande rien, et le lot passe sans que le comportement
    altimetrique — le seul qui pose question pour les gabarits — ait ete
    eprouve. (Reserve soulevee par Bruno, 2026-08-27.)

    Parameters
    ----------
    vecteur_mm : tuple of float

    Returns
    -------
    str
        Chaine vide si le vecteur sollicite les deux comportements.
    """
    horizontal = abs(vecteur_mm[0]) > 1e-9 or abs(vecteur_mm[1]) > 1e-9
    vertical = abs(vecteur_mm[2]) > 1e-9

    if horizontal and vertical:
        return ""
    if horizontal:
        return ("**Ce sondage ne vaut que pour un deplacement horizontal.** "
                "`dZ = 0` : le comportement altimetrique n'a PAS ete eprouve. "
                "Un niveau etant infini en plan, il n'a rien eu a faire ici — "
                "c'est en Z qu'il bouge reellement. Sonder la passe B "
                "(`0 ; 0 ; dZ`) avant tout recalage altimetrique.")
    return ("**Ce sondage ne vaut que pour un deplacement altimetrique.** "
            "Le comportement en plan n'a PAS ete eprouve. Sonder la passe A "
            "avant tout recalage horizontal.")


def publier_sondages(sortie, sondages, a_deplacer, vecteur_mm):
    """Affiche le resultat du sondage.

    Parameters
    ----------
    sortie : pyrevit.output.PyRevitOutputWindow
    sondages : tuple
        Sortie de `sonder_deplacement`.
    a_deplacer : list of DB.Element
        Sert a proposer des echantillons cliquables.
    """
    lot_passe, echecs_de_groupe, impliquees, nb_depingles = sondages

    sortie.print_md("## Sondage — rien n'a ete applique")
    sortie.print_md(
        "{0} element(s) depingle(s) avant sondage, comme le ferait l'operation "
        "reelle. Le retour arriere les a repingles.".format(nb_depingles)
    )

    if lot_passe:
        sortie.print_md(
            "**Le lot complet passe pour le vecteur "
            "dX = {0:.3f} · dY = {1:.3f} · dZ = {2:.3f} mm.** `MoveElements` "
            "accepte l'integralite du lot, groupe par groupe. Rien ne s'oppose a "
            "l'application du point de vue de l'API — restent les controles "
            "geometriques du protocole, qui seuls diront si le resultat est "
            "*juste*.".format(*vecteur_mm)
        )
        reserve = avertissement_composantes(vecteur_mm)
        if reserve:
            sortie.print_md("### Portee de ce resultat\n\n" + reserve)
        return

    sortie.print_table(
        table_data=[[groupe, detail or "—"] for groupe, detail in echecs_de_groupe],
        title="Groupes refuses en lot complet",
        columns=["Groupe", "Erreur"],
    )

    if not impliquees:
        sortie.print_md(
            "**Aucun retrait de categorie unique ne debloque le lot.** C'est le "
            "signe de plusieurs causes independantes : retirer une categorie ne "
            "suffit pas, une autre bloque encore. Prochaine etape : reconstituer "
            "le lot par ajouts successifs pour nommer chaque cause."
        )
        return

    sortie.print_table(
        table_data=[
            [nom, str(nombre), groupe] for groupe, nom, nombre, _ in impliquees
        ],
        title="Categories impliquees — leur retrait suffit a debloquer le lot",
        columns=["Categorie", "Elements", "Groupe"],
    )
    sortie.print_md(
        "« Impliquee » et non « fautive » : le test dit que retirer cette "
        "categorie debloque le lot, pas qu'elle est seule en cause."
    )

    # Echantillons cliquables : cliquer l'identifiant selectionne l'element dans
    # Revit. Moyen le plus court d'identifier une categorie dont la classe .NET
    # ne dit rien — « Element » nu, typiquement.
    noms = set(ligne[1] for ligne in impliquees)
    echantillons = {}
    for element in a_deplacer:
        nom = nom_categorie(element)
        if nom in noms and len(echantillons.get(nom, [])) < 3:
            echantillons.setdefault(nom, []).append(element)

    if echantillons:
        sortie.print_table(
            table_data=[
                [nom] + [sortie.linkify(element.Id) for element in elements]
                + [""] * (3 - len(elements))
                for nom, elements in sorted(echantillons.items())
            ],
            title="Echantillons a inspecter — cliquer pour selectionner dans Revit",
            columns=["Categorie", "Exemple 1", "Exemple 2", "Exemple 3"],
        )

    sortie.print_md(
        "Marche a suivre : identifier ces elements dans Revit, puis decider "
        "categorie par categorie — exclusion via `CATEGORIES_EXCLUES`, ou appel "
        "`MoveElements` dedie si le refus ne porte que sur une composante du "
        "vecteur (cas attendu pour les gabarits)."
    )


def publier_controles(sortie, controles):
    """Affiche le resultat du controle automatique.

    Parameters
    ----------
    sortie : pyrevit.output.PyRevitOutputWindow
    controles : list of tuple
    """
    if not controles:
        sortie.print_md(
            "**Controle automatique** : aucun point temoin exploitable "
            "(aucun element a position ponctuelle dans le lot)."
        )
        return

    sortie.print_table(
        table_data=[
            [str(valeur_id(element_id)), categorie,
             "{0:.4f}".format(ex), "{0:.4f}".format(ey), "{0:.4f}".format(ez),
             "oui" if conforme else "NON"]
            for element_id, categorie, ex, ey, ez, conforme in controles
        ],
        title="Controle automatique sur points temoins (ecart au vecteur demande)",
        columns=["Element", "Categorie", "dX (mm)", "dY (mm)", "dZ (mm)", "Conforme"],
    )
    sortie.print_md(
        "Tolerance {0} mm. **Ce controle ne remplace pas** le releve manuel par "
        "cotes de coordonnees sur trois points connus.".format(TOLERANCE_CONTROLE_MM)
    )


# --------------------------------------------------------------------------
# Point d'entree
# --------------------------------------------------------------------------

def main():
    document = revit.doc
    sortie = script.get_output()

    if not verifier_contexte(document):
        return

    vecteur_mm = demander_vecteur()
    if vecteur_mm is None:
        return

    mode = forms.alert(
        "Vecteur : dX = {0:.3f} · dY = {1:.3f} · dZ = {2:.3f} mm\n\n"
        "La simulation ne modifie rien : elle liste les comptes par categorie\n"
        "et le journal des exclusions.".format(*vecteur_mm),
        title="Recalage global — mode",
        options=["Simulation seule",
                 "Simulation + sondage",
                 "Essai de strategies (rien applique)",
                 "Simuler puis appliquer"],
    )
    if not mode:
        return

    horodatage = datetime.datetime.now()
    vecteur = DB.XYZ(
        mm_vers_pieds(vecteur_mm[0]),
        mm_vers_pieds(vecteur_mm[1]),
        mm_vers_pieds(vecteur_mm[2]),
    )

    a_deplacer, exclusions, datums_sans_emprise = trier_modele(document)

    if not FILTRE_EMPRISE_ACTIF:
        note_filtre = "Filtre d'emprise **desactive** — comportement anterieur."
    else:
        note_filtre = "Filtre d'emprise **actif**."
        if datums_sans_emprise:
            note_filtre += (
                " {0} gabarit(s) (niveaux, quadrillages, plans de reference) n'ont "
                "PAS d'emprise et n'ont ete conserves que par l'exemption "
                "`CLASSES_DATUMS` — sans elle, tout recalage en Z serait faux."
            ).format(datums_sans_emprise)
        else:
            note_filtre += (
                " Les gabarits ont tous une emprise : l'exemption `CLASSES_DATUMS` "
                "n'a rien change sur ce modele."
            )

    # Nuages de points : ecartes volontairement, mais JAMAIS en silence.
    nb_nuages = sum(1 for _, motif in exclusions if motif == "NUAGE_DE_POINTS")
    if nb_nuages:
        texte_nuages = (
            "{0} nuage(s) de points ne sont PAS deplaces.\n"
            "Le lien devra etre recree apres le recalage : un nuage recale en\n"
            "amont n'est generalement plus valide."
        ).format(nb_nuages)
        note_filtre += "\n\n**{0} nuage(s) de points NON deplace(s).** Le lien " \
                       "devra etre recree apres le recalage — un nuage recale en " \
                       "amont n'est generalement plus valide.".format(nb_nuages)
    else:
        texte_nuages = ""

    if not a_deplacer:
        forms.alert("Aucun element eligible au deplacement.", title="Recalage global")
        return

    groupes = grouper_par_option(a_deplacer)
    publier_rapport(sortie, document, vecteur_mm, a_deplacer, exclusions, groupes,
                    note_filtre)

    if mode == "Essai de strategies (rien applique)":
        sortie.print_md(
            "## Essai de strategies — rien ne sera applique\n\n"
            "Chaque strategie deplace le lot complet, laisse Revit **traiter** "
            "ses erreurs, puis annule tout. Comptez plusieurs minutes."
        )
        # Identifiants et non elements : le retour arriere du groupe invalide
        # les objets `Element`, et chaque strategie doit repartir du frais.
        groupes_ids = [(libelle_groupe, [valeur_id(e.Id) for e in elements])
                       for libelle_groupe, elements in groupes]

        # La strategie 4 n'existe qu'apres la 1 : elle se calibre sur ce que
        # celle-ci detruit reellement, plutot que sur une definition devinee de
        # « fragile ». D'ou une liste qui s'allonge en cours de route.
        strategies = [
            (None, None, False, False, "deplacer", "1. Tel quel"),
            (desolidariser, None, False, False, "deplacer",
             "2. Apres desolidarisation des joints"),
            (remettre_formes_a_plat, None, False, False, "deplacer",
             "3. Apres remise a plat des formes de dalle"),
            (None, None, False, False, "copier",
             "7. COPIE au lieu de deplacement — autre chemin d'API"),
        ]
        rang = 0
        while rang < len(strategies):
            (preparation, fragiles, separer, dabord, methode,
             libelle) = strategies[rang]
            (libelle, reussi, nb_preparation, avertissements,
             incidents, bilan_sante, supprimes) = essayer_strategie(
                document, groupes_ids, vecteur, preparation, libelle,
                fragiles, separer, dabord, methode)

            if rang == 0 and supprimes:
                fragiles_mesures = set(supprimes)
                strategies.append((
                    None, fragiles_mesures, False, False, "deplacer",
                    "4. Deux passes, UNE transaction — les {0} elements "
                    "detruits par la 1 deplaces a part".format(len(supprimes))))
                strategies.append((
                    None, fragiles_mesures, True, False, "deplacer",
                    "5. Deux transactions — les fragiles en DERNIER"))
                strategies.append((
                    None, fragiles_mesures, True, True, "deplacer",
                    "6. Deux transactions — les fragiles en PREMIER, "
                    "seule sequence ou la dalle a survecu manuellement"))
            total = sum(ligne[3] for ligne in avertissements)

            # Le verdict porte sur la SANTE du modele, pas sur le nombre de
            # messages transitoires : une translation rigide doit laisser le
            # modele exactement aussi sain — ou aussi malade — qu'avant.
            if bilan_sante is None:
                verdict = "INDETERMINE"
            else:
                apparus, disparus, conserves = bilan_sante
                verdict = "CONFORME" if not apparus and not disparus else "NON CONFORME"

            sortie.print_md(
                "### {0}\n\n**{1}** — {2} message(s) transitoire(s) distinct(s), "
                "{3} element(s) concerne(s){4}.".format(
                    libelle, verdict, len(avertissements), total,
                    "" if nb_preparation == 0
                    else ", {0} operation(s) de preparation".format(nb_preparation))
            )
            for incident in incidents:
                sortie.print_md("**Incident** : `{0}`".format(incident))

            if supprimes:
                sortie.print_md(
                    "### ⚠ {0} element(s) SUPPRIME(s) par le deplacement\n\n"
                    "Ces elements du lot n'existaient plus apres l'operation. "
                    "C'est une destruction, pas une degradation.".format(
                        len(supprimes))
                )
                sortie.print_table(
                    table_data=[[str(v)] for v in supprimes[:40]],
                    title="Identifiants supprimes",
                    columns=["Element"],
                )
            else:
                sortie.print_md(
                    "**Aucun element supprime** — tous les elements du lot "
                    "existent encore apres l'operation."
                )

            if bilan_sante is not None:
                apparus, disparus, conserves = bilan_sante
                sortie.print_md(
                    "Sante du modele : **{0} avertissement(s) apparu(s)**, "
                    "**{1} disparu(s)**, {2} conserve(s) a l'identique. "
                    "Un disparu est aussi suspect qu'un apparu : il signale le "
                    "plus souvent que l'element porteur a ete supprime.".format(
                        sum(l[2] for l in apparus), sum(l[2] for l in disparus),
                        conserves)
                )
                for titre, lignes_sante in (("Avertissements APPARUS", apparus),
                                            ("Avertissements DISPARUS", disparus)):
                    if lignes_sante:
                        sortie.print_table(
                            table_data=[
                                [texte, str(compte),
                                 ", ".join(sortie.linkify(DB.ElementId(i))
                                           for i in ids[:4]) or "—"]
                                for texte, ids, compte in lignes_sante[:15]
                            ],
                            title=titre,
                            columns=["Message", "Nombre", "Elements"],
                        )

            if avertissements:
                sortie.print_table(
                    table_data=[[g, t, str(o), str(n)]
                                for g, t, o, n, _ in avertissements],
                    title="Messages restants",
                    columns=["Gravite", "Message", "Occurrences", "Elements"],
                )

            rang += 1

        sortie.print_md(
            "**Le modele est intact.** Lire d'abord le compte d'elements "
            "SUPPRIMES : c'est le seul degat irreversible. Le reste — "
            "avertissements apparus, messages transitoires — se rattrape."
        )
        return

    sondages = None
    if mode == "Simulation + sondage":
        sondages = sonder_deplacement(document, groupes, vecteur)
        publier_sondages(sortie, sondages, a_deplacer, vecteur_mm)

    if mode != "Simuler puis appliquer":
        resume = "Simulation seule — le modele n'a pas ete modifie."
        if sondages is not None:
            lot_passe, echecs_de_groupe, impliquees, nb_depingles = sondages
            if lot_passe:
                resume += ("\n\nSondage : le lot complet est ACCEPTE par "
                           "MoveElements pour CE vecteur "
                           "({0:.1f} ; {1:.1f} ; {2:.1f} mm), apres depinglage de "
                           "{3} element(s). Toutes les sondes ont ete annulees."
                           ).format(vecteur_mm[0], vecteur_mm[1], vecteur_mm[2],
                                    nb_depingles)
                reserve = avertissement_composantes(vecteur_mm)
                if reserve:
                    resume += "\n\n" + reserve.replace("**", "")
            else:
                resume += ("\n\nSondage : {0} groupe(s) refuse(s) en lot complet, "
                           "{1} categorie(s) impliquee(s). Sondes annulees.").format(
                               len(echecs_de_groupe), len(impliquees))
        chemin = ecrire_journal(
            document, horodatage, vecteur_mm,
            "SIMULATION" if sondages is None else "SIMULATION + SONDAGE",
            a_deplacer, exclusions, groupes, None, None, None,
            resume, note_filtre, sondages,
        )
        sortie.print_md("**Journal** : `{0}`".format(chemin))
        return

    nb_options = sum(1 for libelle, _ in groupes if libelle != "Modele principal")
    if nb_options:
        confirmation = forms.alert(
            "Le modele comporte {0} option(s) de conception.\n\n"
            "Chaque option est deplacee par un appel `MoveElements` distinct,\n"
            "dans la meme transaction. Ce comportement n'a pas encore ete\n"
            "verifie sur un modele reel — controler le resultat option par\n"
            "option avant d'exploiter le fichier.".format(nb_options),
            title="Options de conception",
            options=["Arreter", "Poursuivre"],
        )
        if confirmation != "Poursuivre":
            return

    message_confirmation = (
        "Appliquer le deplacement de {0} elements ?\n\n"
        "Operation annulable par Ctrl+Z, mais a mener sur une copie detachee."
    ).format(len(a_deplacer))
    if texte_nuages:
        message_confirmation += "\n\n" + texte_nuages

    confirmation = forms.alert(
        message_confirmation,
        title="Confirmation",
        options=["Appliquer", "Annuler"],
    )
    if confirmation != "Appliquer":
        return

    temoins = choisir_points_temoins(a_deplacer, NB_POINTS_TEMOINS)
    niveaux_avant = relever_niveaux(document)

    transaction = DB.Transaction(
        document,
        "bimflow - recalage global ({0:.1f} ; {1:.1f} ; {2:.1f} mm)".format(*vecteur_mm),
    )
    transaction.Start()

    # Capturer les avertissements Revit — « objets detaches », « formes
    # redefinies ». Ils defilent a l'ecran puis disparaissent ; sans cela le
    # journal ne garde aucune trace de CE qui a casse ni OU. Le collecteur
    # observe et rend la main : les dialogues habituels s'affichent toujours.
    collecteur = CollecteurDAvertissements(annuler_sur_erreur=ANNULER_SUR_ERREUR)
    try:
        options_echec = transaction.GetFailureHandlingOptions()
        options_echec.SetFailuresPreprocessor(collecteur)
        transaction.SetFailureHandlingOptions(options_echec)
    except Exception:
        pass

    try:
        appels, depingles = deplacer_en_bloc(document, groupes, vecteur)
        nb_repingles = repingler(depingles)
        # Commit() ne leve pas si le preprocesseur a demande l'annulation : il
        # retourne un statut. Sans ce controle, on annoncerait un succes alors
        # que le modele n'a pas bouge.
        statut = transaction.Commit()
    except Exception as erreur:
        # Le cas courant est un refus de `MoveElements` : la transaction est
        # encore ouverte, RollBack est la bonne reponse. Mais si c'est `Commit`
        # qui a echoue, Revit a deja clos la transaction et RollBack leverait a
        # son tour — masquant l'erreur d'origine derriere un « transaction not
        # started » sans rapport. D'ou le garde-fou.
        try:
            if transaction.HasStarted() and not transaction.HasEnded():
                transaction.RollBack()
        except Exception:
            pass
        sortie.print_md("## Echec — le modele est intact")
        sortie.print_md("`MoveElements` a rejete le lot : `{0}`".format(erreur))
        sortie.print_md("Recherche des elements fautifs par bisection...")

        refuses, complet = isoler_elements_refuses(document, a_deplacer, vecteur)
        if refuses:
            sortie.print_table(
                table_data=[
                    [sortie.linkify(element.Id), nom_categorie(element),
                     type(element).__name__]
                    for element in refuses[:100]
                ],
                title="Elements refuses par MoveElements SEULS",
                columns=["Element", "Categorie", "Classe"],
            )
            sortie.print_md(
                "**A lire avec reserve.** La bisection separe les hotes de leurs "
                "heberges : une fenetre sondee sans son mur est refusee alors "
                "qu'elle passerait dans le lot complet. Cette liste nomme ce qui "
                "ne bouge pas SEUL, pas ce qui bloque le lot. Relancer plutot en "
                "mode **Simulation + sondage**, qui ne rompt pas le contexte."
            )
        if not complet:
            sortie.print_md(
                "Plafond de {0} sondes atteint : la liste est partielle.".format(
                    MAX_SONDES_DIAGNOSTIC)
            )

        ecrire_journal(
            document, horodatage, vecteur_mm, "ECHEC", a_deplacer, exclusions,
            groupes, None, None, None,
            "Echec : {0}\n\nTransaction annulee, modele intact.".format(erreur),
            note_filtre,
        )
        return

    avertissements = resumer_avertissements(collecteur.messages)

    if statut != DB.TransactionStatus.Committed:
        sortie.print_md("## Annule par securite — le modele est INTACT")
        sortie.print_md(
            "Revit a signale des erreurs de gravite `Error`. Ses seules issues "
            "sont destructrices — supprimer des elements, detacher, supprimer "
            "des contraintes. Plutot que de vous les faire arbitrer une par "
            "une, la transaction a ete **annulee** : rien n'a ete modifie.\n\n"
            "Reglage : `ANNULER_SUR_ERREUR` en tete de `script.py`."
        )
        if avertissements:
            sortie.print_table(
                table_data=[
                    [gravite, texte, str(occurrences), str(nb),
                     ", ".join(sortie.linkify(DB.ElementId(i)) for i in ids) or "—"]
                    for gravite, texte, occurrences, nb, ids in avertissements
                ],
                title="Ce qui aurait du etre detruit pour que l'operation passe",
                columns=["Gravite", "Message", "Occurrences", "Elements", "Echantillon"],
            )
        chemin = ecrire_journal(
            document, horodatage, vecteur_mm, "ANNULE (erreurs Revit)", a_deplacer,
            exclusions, groupes, None, None, None,
            "Annule par securite : Revit signalait des erreurs dont les seules "
            "resolutions etaient destructrices. Modele intact.",
            note_filtre, None, avertissements, None,
        )
        sortie.print_md("**Journal** : `{0}`".format(chemin))
        return

    controles = verifier_points_temoins(document, temoins, vecteur)
    niveaux = comparer_niveaux(niveaux_avant, relever_niveaux(document),
                               vecteur_mm[2])

    sortie.print_md("## Deplacement applique")

    if avertissements:
        total = sum(ligne[3] for ligne in avertissements)
        sortie.print_md(
            "### ⚠ {0} avertissement(s) Revit, {1} element(s) concerne(s)\n\n"
            "Ces messages signalent des **relations rompues** — attaches "
            "perdues, esquisses redefinies. L'API a accepte le deplacement, "
            "mais le resultat n'est pas forcement juste. **Ne pas exploiter ce "
            "fichier avant d'avoir compris chaque ligne.**".format(
                len(avertissements), total)
        )
        sortie.print_table(
            table_data=[
                [gravite, texte, str(occurrences), str(nb),
                 ", ".join(sortie.linkify(DB.ElementId(i)) for i in ids) or "—"]
                for gravite, texte, occurrences, nb, ids in avertissements
            ],
            title="Avertissements Revit — cliquer un identifiant pour selectionner",
            columns=["Gravite", "Message", "Occurrences", "Elements", "Echantillon"],
        )
    sortie.print_md(
        "{0} elements deplaces en {1} appel(s) `MoveElements`, "
        "{2} elements depingles puis repingles.".format(
            len(a_deplacer), len(appels), nb_repingles)
    )
    if niveaux:
        non_conformes_niveaux = [ligne for ligne in niveaux if not ligne[4]]
        sortie.print_table(
            table_data=[
                [nom,
                 "{0:.1f}".format(avant),
                 "—" if apres is None else "{0:.1f}".format(apres),
                 "—" if ecart is None else "{0:.4f}".format(ecart),
                 "oui" if conforme else "NON"]
                for nom, avant, apres, ecart, conforme in niveaux
            ],
            title="Altitude des niveaux (mm) — ecart au dZ demande",
            columns=["Niveau", "Avant", "Apres", "Ecart", "Conforme"],
        )
        if non_conformes_niveaux:
            sortie.print_md(
                "**{0} niveau(x) sur {1} n'ont pas suivi le dZ demande.** "
                "Or les poteaux, murs et sols leur sont contraints : deplacer "
                "les elements SANS leurs niveaux — ou l'inverse — produit une "
                "geometrie ecartelee. C'est la cause a examiner en premier."
                .format(len(non_conformes_niveaux), len(niveaux))
            )

    publier_controles(sortie, controles)

    non_conformes = [ligne for ligne in controles if not ligne[5]]
    message = "Deplacement applique : {0} elements, {1} appel(s) MoveElements.".format(
        len(a_deplacer), len(appels))
    if non_conformes:
        message += "\n\n**{0} point(s) temoin(s) hors tolerance** — verifier avant " \
                   "d'exploiter le fichier.".format(len(non_conformes))
        sortie.print_md(
            "**{0} point(s) temoin(s) hors tolerance.** Annuler (Ctrl+Z) et "
            "investiguer avant d'exploiter le fichier.".format(len(non_conformes))
        )

    chemin = ecrire_journal(
        document, horodatage, vecteur_mm, "APPLIQUE", a_deplacer, exclusions,
        groupes, appels, nb_repingles, controles, message, note_filtre,
        None, avertissements, niveaux,
    )
    sortie.print_md("**Journal** : `{0}`".format(chemin))
    if texte_nuages:
        sortie.print_md(
            "## Action requise apres ce recalage\n\n"
            "**{0} nuage(s) de points n'ont PAS ete deplaces.** Recreer le lien "
            "de nuage : un nuage recale en amont n'est generalement plus "
            "valide.".format(nb_nuages)
        )
    sortie.print_md(
        "Controle qui fait foi : poser une **cote de coordonnees** sur trois "
        "points connus et verifier l'ecart attendu (R09 §3)."
    )


main()
