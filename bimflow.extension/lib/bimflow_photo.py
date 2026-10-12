# -*- coding: utf-8 -*-
"""bimflow_photo - logique pure du bouton « Photo maquette ».

Le bouton (Dev.panel\\PhotoMaquette.pushbutton) lit la maquette ; tout ce qui
ne demande pas Revit vit ici et se teste sous CPython (tests\\
test_bimflow_photo.py) : lecture du socle de parametres, configuration du
dossier de sortie, nom du fichier, orientation des quadrillages, choix du
sens de la transformation interne -> partage, et bilan par rubrique.

Ce module n'importe ni Autodesk, ni clr, ni pyrevit.

STANDARD, PAS INSTANCE. Aucune valeur d'affaire ici : le dossier de sortie
vient d'un fichier de configuration du poste, les GUID viennent du socle
versionne (shared_parameters\\keovia_socle_parametres.txt), lus par NOM. Le
bouton ne connait que des noms de parametres du socle.

Syntaxe IronPython 3.4 : pas de f-string, pas d'annotation, pas de pathlib,
OrderedDict des que l'ordre compte.

bimflow - Keovia Solutions inc. - 2026-10-12
"""

import io
import json
import math
import os
import re
from collections import OrderedDict

# --------------------------------------------------------------------------
# Ce que la photo releve - noms du socle, jamais de GUID en dur
# --------------------------------------------------------------------------

PARAMS_NIVEAU = (u"REF_Batiment", u"REF_Etage")
PARAMS_VOLUME = (u"REF_Zone", u"REF_Etage", u"REF_Batiment",
                 u"CLS_Nature_volume", u"REF_Id")

# Valeur d'une lecture qui a echoue (exception), par opposition a une valeur
# ABSENTE (le parametre n'existe pas sur l'element : null). Convention du
# depot : jamais d'indisponibilite silencieuse.
NON_LU = u"NON_LU"

# Statuts d'un parametre lu par GUID.
LU = u"lu"
VIDE = u"vide"          # le parametre existe, sans valeur -> null
ABSENT = u"absent"      # le parametre n'existe pas sur l'element -> null
ILLISIBLE = u"illisible"  # la lecture a leve une exception -> NON_LU

PIED_MM = 304.8

# --------------------------------------------------------------------------
# Socle de parametres partages
# --------------------------------------------------------------------------


def _decoder(octets):
    """Texte d'un fichier de parametres partages : Revit l'ecrit parfois en
    UTF-16 (avec BOM), le socle du depot est en ASCII."""
    if octets[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return octets.decode("utf-16")
    if octets[:3] == b"\xef\xbb\xbf":
        return octets[3:].decode("utf-8")
    try:
        return octets.decode("utf-8")
    except UnicodeDecodeError:
        return octets.decode("latin-1")


def lire_socle_texte(texte):
    """{nom: guid} des lignes PARAM, dans l'ordre du fichier.

    L'en-tete *PARAM donne la position des colonnes GUID et NAME : on ne la
    suppose pas."""
    guids = OrderedDict()
    i_guid = 1
    i_nom = 2
    for ligne in texte.splitlines():
        champs = ligne.rstrip(u"\r\n").split(u"\t")
        if not champs:
            continue
        if champs[0] == u"*PARAM":
            if u"GUID" in champs and u"NAME" in champs:
                i_guid = champs.index(u"GUID")
                i_nom = champs.index(u"NAME")
            continue
        if champs[0] != u"PARAM" or len(champs) <= max(i_guid, i_nom):
            continue
        guids[champs[i_nom].strip()] = champs[i_guid].strip().lower()
    return guids


def lire_socle(chemin):
    with io.open(chemin, "rb") as f:
        return lire_socle_texte(_decoder(f.read()))


def guids_requis(socle, noms):
    """(OrderedDict nom -> guid des noms trouves, liste des noms absents)."""
    trouves = OrderedDict()
    manquants = []
    for nom in noms:
        if nom in socle:
            trouves[nom] = socle[nom]
        else:
            manquants.append(nom)
    return trouves, manquants


def chemin_socle(dossier_lib):
    """Socle versionne du depot, vu depuis bimflow.extension\\lib."""
    return os.path.normpath(os.path.join(
        dossier_lib, os.pardir, os.pardir, u"shared_parameters",
        u"keovia_socle_parametres.txt"))


# --------------------------------------------------------------------------
# Configuration du dossier de sortie - un fichier par poste, hors depot
# --------------------------------------------------------------------------

CLE_DOSSIER = u"dossier_sortie"
NOM_CONFIG = u"photo_maquette.json"

_VAR = re.compile(r"%([^%]+)%")


def developper(chemin, environ=None):
    """Developpe %VAR% (forme Windows) et ~, sans dependre de l'OS courant.

    Une variable inconnue est laissee telle quelle : le chemin restera
    inutilisable et le rapport le dira, plutot que d'ecrire ailleurs."""
    if environ is None:
        environ = os.environ
    haut = dict((k.upper(), v) for k, v in environ.items())

    def remplacer(m):
        return haut.get(m.group(1).upper(), m.group(0))

    resultat = _VAR.sub(remplacer, chemin)
    if resultat.startswith(u"~"):
        resultat = os.path.expanduser(resultat)
    return resultat


def chemin_config(environ=None):
    """%APPDATA%\\bimflow\\photo_maquette.json (repli : ~\\bimflow)."""
    if environ is None:
        environ = os.environ
    base = environ.get("APPDATA") or os.path.join(
        os.path.expanduser(u"~"), u"AppData", u"Roaming")
    return os.path.join(base, u"bimflow", NOM_CONFIG)


def lire_config(chemin, environ=None):
    """(dossier developpe ou None, gabarit brut ou None, motif si None)."""
    if not os.path.isfile(chemin):
        return None, None, u"pas de configuration ({0})".format(chemin)
    try:
        with io.open(chemin, "r", encoding="utf-8-sig") as f:
            donnees = json.load(f)
    except Exception as err:
        return None, None, u"configuration illisible ({0}) : {1}".format(
            chemin, err)
    brut = donnees.get(CLE_DOSSIER) if isinstance(donnees, dict) else None
    if not brut:
        return None, None, u"cle {0} absente de {1}".format(CLE_DOSSIER,
                                                            chemin)
    return developper(brut, environ), brut, None


def ecrire_config(chemin, dossier):
    parent = os.path.dirname(chemin)
    if parent and not os.path.isdir(parent):
        os.makedirs(parent)
    contenu = json.dumps(OrderedDict([(CLE_DOSSIER, dossier)]),
                         ensure_ascii=False, indent=2)
    with io.open(chemin, "w", encoding="utf-8") as f:
        f.write(contenu + u"\n")


# --------------------------------------------------------------------------
# Nom du fichier de sortie
# --------------------------------------------------------------------------

_INTERDIT_FICHIER = re.compile(u'[\\\\/:*?"<>|\\s]+')


def nom_fichier(titre, instant):
    """<modele>_<AAAA-MM-JJ_HHMM>.json - titre lu a l'execution, jamais
    suppose. Les caracteres interdits d'un nom de fichier Windows et les
    blancs deviennent '_' ; l'extension .rvt eventuelle est retiree."""
    base = titre or u"sans_titre"
    if base.lower().endswith(u".rvt"):
        base = base[:-4]
    base = _INTERDIT_FICHIER.sub(u"_", base).strip(u"._") or u"sans_titre"
    return u"{0}_{1}.json".format(base, instant.strftime(u"%Y-%m-%d_%H%M"))


def chemin_libre(dossier, nom, existe=os.path.exists):
    """Chemin qui n'ecrase jamais une photo precedente : _2, _3... ajoutes
    avant l'extension si la minute est deja prise."""
    chemin = os.path.join(dossier, nom)
    if not existe(chemin):
        return chemin
    racine, ext = os.path.splitext(nom)
    n = 2
    while True:
        chemin = os.path.join(dossier, u"{0}_{1}{2}".format(racine, n, ext))
        if not existe(chemin):
            return chemin
        n += 1


# --------------------------------------------------------------------------
# Geometrie plane
# --------------------------------------------------------------------------


def azimut_deg(dx, dy):
    """Azimut du vecteur (dx, dy) : 0 = +Y (nord du repere), sens horaire,
    dans [0, 360). None pour un vecteur nul."""
    if abs(dx) < 1e-12 and abs(dy) < 1e-12:
        return None
    a = math.degrees(math.atan2(dx, dy)) % 360.0
    a = round(a, 4)
    return 0.0 if a >= 360.0 else a


def direction_deg(azimut):
    """Orientation d'une droite sans sens : azimut ramene dans [0, 180)."""
    if azimut is None:
        return None
    d = round(azimut % 180.0, 4)
    return 0.0 if d >= 180.0 else d


def distance(a, b):
    return math.sqrt(sum((a[i] - b[i]) ** 2 for i in range(3)))


def choisir_sens(candidats, tolerance_mm):
    """Choisit la transformation interne -> partage la mieux verifiee.

    candidats : liste de (nom, residu_mm ou None). Le residu est l'ecart,
    sur les points de controle (point topographique, point de base), entre
    la position partagee que Revit annonce et celle que la transformation
    calcule. Rend (nom, residu) ou (None, motif) si aucun candidat ne passe
    sous la tolerance - auquel cas les coordonnees partagees valent null.
    """
    valides = [(n, r) for n, r in candidats if r is not None]
    if not valides:
        return None, u"aucun point de controle lisible"
    valides.sort(key=lambda c: c[1])
    nom, residu = valides[0]
    if residu > tolerance_mm:
        return None, u"meilleur residu {0:.3f} mm ({1}) > tolerance {2} mm"\
            .format(residu, nom, tolerance_mm)
    return nom, residu


# --------------------------------------------------------------------------
# Bilan par rubrique
# --------------------------------------------------------------------------

def _champs_nuls(enregistrement, champs):
    """Champs null ou NON_LU ; un NON_LU est compte sous `<champ> (NON_LU)`
    pour ne pas se confondre avec une absence."""
    manques = []
    for c in champs:
        v = enregistrement.get(c)
        if v is None:
            manques.append(c)
        elif v == NON_LU:
            manques.append(u"{0} (NON_LU)".format(c))
    return manques


# Identifiants qui doivent etre UNIQUES dans une maquette, par rubrique.
# REF_Id : cle de jointure vers Ivion (socle). Un copier-coller dans Revit
# recopie la valeur : l'unicite se controle A POSTERIORI (decision Bruno du
# 2026-10-12), d'ou ce comptage a chaque photo. Le comptage ne corrige rien
# et ne designe pas l'original : il liste les elements qui partagent la cle.
IDENTIFIANTS_UNIQUES = OrderedDict([(u"volumes", (u"REF_Id",))])


def _porteur(el, champ):
    p = el.get(u"parametres", {}).get(champ)
    return p.get(u"porteur") if p else None


def controle_unicite(elements, champ):
    """Controle d'unicite d'un identifiant, et ce qu'il a pu controler.

    Rend {valeurs_controlees, portees_par_type, doublons}. Seules comptent
    les valeurs LUES et portees par l'INSTANCE : une valeur portee par le
    type est partagee par construction entre toutes ses instances, ce n'est
    pas un doublon de saisie, et elle est comptee a part. null et NON_LU ne
    sont pas des valeurs. La comparaison ignore casse et blancs de bord
    (detection seulement : la valeur publiee reste celle lue)."""
    groupes = OrderedDict()
    par_type = 0
    for el in elements:
        v = el.get(champ)
        if v is None or v == NON_LU or v == u"":
            continue
        if _porteur(el, champ) == u"type":
            par_type += 1
            continue
        groupes.setdefault(v.strip().lower(), []).append(el)
    resultat = []
    for cle, els in groupes.items():
        if len(els) < 2:
            continue
        resultat.append(OrderedDict([
            (u"valeur", els[0].get(champ)),
            (u"nombre", len(els)),
            (u"elements", [OrderedDict([(u"id", e.get(u"id")),
                                        (u"nom", e.get(u"nom")),
                                        (u"famille", e.get(u"famille"))])
                           for e in els]),
        ]))
    return OrderedDict([
        (u"valeurs_controlees", sum(len(e) for e in groupes.values())),
        (u"portees_par_type", par_type),
        (u"doublons", resultat),
    ])


def doublons(elements, champ):
    """Raccourci : la liste des doublons de controle_unicite."""
    return controle_unicite(elements, champ)[u"doublons"]


def bilan(photo):
    """Comptes par rubrique et liste des signalements.

    Chaque champ null est compte, par rubrique et par champ ; un parametre
    ABSENT, VIDE ou NON_LU l'est aussi, avec son statut. Rien n'est deduit,
    rien n'est corrige : on compte ce qui est dans la photo."""
    comptes = OrderedDict()
    signalements = []

    def compter(rubrique, elements, champs_suivis, avec_params):
        nuls = OrderedDict((c, 0) for c in champs_suivis)
        statuts = OrderedDict()
        for el in elements:
            for c in _champs_nuls(el, champs_suivis):
                nuls[c] = nuls.get(c, 0) + 1
            if avec_params:
                for nom, p in el.get(u"parametres", OrderedDict()).items():
                    s = statuts.setdefault(nom, OrderedDict(
                        [(LU, 0), (VIDE, 0), (ABSENT, 0), (ILLISIBLE, 0)]))
                    s[p.get(u"statut", ILLISIBLE)] += 1
        resume = OrderedDict([(u"nombre", len(elements))])
        resume[u"champs_nuls"] = OrderedDict(
            (c, n) for c, n in nuls.items() if n)
        if avec_params:
            resume[u"parametres"] = statuts
        comptes[rubrique] = resume
        for c, n in nuls.items():
            if n:
                signalements.append(u"{0} : {1} sur {2} sans `{3}`".format(
                    rubrique, n, len(elements), c))
        for nom, s in statuts.items():
            manque = s[VIDE] + s[ABSENT] + s[ILLISIBLE]
            if manque:
                signalements.append(
                    u"{0} : `{1}` non lu sur {2} / {3} (absent {4}, vide {5},"
                    u" NON_LU {6})".format(rubrique, nom, manque,
                                           len(elements), s[ABSENT],
                                           s[VIDE], s[ILLISIBLE]))

    compter(u"niveaux", photo.get(u"niveaux", []),
            (u"elevation_pbp_mm",), True)
    compter(u"quadrillages", photo.get(u"quadrillages", []),
            (u"debut_partage_m", u"fin_partage_m", u"orientation_deg",
             u"type"), False)
    compter(u"volumes", photo.get(u"volumes", []),
            (u"famille", u"boite_mm"), True)
    compter(u"pieces", photo.get(u"pieces", []),
            (u"numero", u"nom", u"niveau", u"surface_m2", u"point_mm"),
            False)
    compter(u"sous_projets", photo.get(u"sous_projets", []),
            (u"nombre_elements",), False)
    compter(u"liens", photo.get(u"liens", []),
            (u"type", u"epingle"), False)
    for rubrique, champs in IDENTIFIANTS_UNIQUES.items():
        elements = photo.get(rubrique, [])
        for champ in champs:
            ctrl = controle_unicite(elements, champ)
            comptes[rubrique][u"unicite_" + champ] = ctrl
            if elements and not ctrl[u"valeurs_controlees"]:
                signalements.append(
                    u"{0} : unicite de `{1}` NON CONTROLEE - aucune valeur "
                    u"lue sur l'instance ({2} elements)".format(
                        rubrique, champ, len(elements)))
            if ctrl[u"portees_par_type"]:
                signalements.append(
                    u"{0} : `{1}` porte par le TYPE sur {2} element(s) - "
                    u"unicite par element impossible".format(
                        rubrique, champ, ctrl[u"portees_par_type"]))
            for g in ctrl[u"doublons"]:
                quoi = u", ".join(
                    u"`{0}` (id {1})".format(e[u"famille"] or e[u"nom"],
                                              e[u"id"])
                    for e in g[u"elements"])
                signalements.append(
                    u"{0} : `{1}` EN DOUBLE - {2} sur {3} elements : {4}"
                    .format(rubrique, champ, g[u"valeur"], g[u"nombre"],
                            quoi))
    return comptes, signalements


def ecrire_json(chemin, donnees):
    """JSON UTF-8 sans BOM, ecrit en une fois."""
    texte = json.dumps(donnees, ensure_ascii=False, indent=2)
    with io.open(chemin, "w", encoding="utf-8") as f:
        f.write(texte)
        f.write(u"\n")
