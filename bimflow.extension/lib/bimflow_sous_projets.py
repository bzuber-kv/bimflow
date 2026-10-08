# -*- coding: utf-8 -*-
"""bimflow_sous_projets - logique pure du bouton Table sous-projets.

Le bouton exporte la table des sous-projets utilisateur d'une maquette, puis
applique une table editee : GARDER, RENOMMER, CREER. Aucune action ne
deplace d'element - renommer ne touche aucun element (R14 fait 5), et il n'y
a ni vidage ni suppression.

Tout ce qui ne demande pas l'API vit ici : format du CSV (ecriture et
lecture), validation complete de la table contre l'etat du modele, plan, et
controle apres ecriture. Le bouton n'ecrit RIEN si une seule erreur
bloquante est trouvee.

PYTHON PUR, stdlib seulement, syntaxe 3.4 : tourne sous IronPython 3.4 dans
Revit (pyRevit ajoute ce dossier lib\\ au chemin) ET sous CPython 3 pour les
tests (tests\\test_bimflow_sous_projets.py). Ni Autodesk, ni clr, ni pyrevit.

bimflow - Keovia Solutions inc. - 2026-10-07
"""

import io
import re
from collections import OrderedDict


GARDER = u"GARDER"
RENOMMER = u"RENOMMER"
CREER = u"CREER"
ACTIONS = (GARDER, RENOMMER, CREER)

COLONNES = (u"Action", u"Nom_actuel", u"Nouveau_nom", u"Nb_elements",
            u"Proprietaire")

SEPARATEUR = u";"
FIN_DE_LIGNE = u"\r\n"
BOM = u"﻿"

ERREUR = u"ERREUR"
AVERTISSEMENT = u"AVERTISSEMENT"

# Caracteres refuses dans un nom de sous-projet : liste de l'exception
# ArgumentException de WorksetTable.RenameWorkset et Workset.Create
# (documentation de l'API Revit 2026).
CARACTERES_INTERDITS = u"{}[]|;<>?`~"

# Sous-projets crees par Revit a l'activation du travail partage, en
# francais et en anglais. Sous-projet 1 ne peut pas etre supprime ; les
# toucher merite un avertissement (R14).
SOUS_PROJETS_IMPOSES = (
    u"Sous-projet 1", u"Workset1",
    u"Vues, niveaux et grilles partagés", u"Shared Levels and Grids",
)

_ASCII_SANS_ESPACE = re.compile(u"^[\\x21-\\x7e]+$")


# ---------------------------------------------------------------------------
# 1. CSV
# ---------------------------------------------------------------------------

def _echapper(texte):
    if (SEPARATEUR in texte or u'"' in texte or u"\r" in texte
            or u"\n" in texte):
        return u'"' + texte.replace(u'"', u'""') + u'"'
    return texte


def texte_export(sous_projets):
    """Texte du CSV d'export, SANS BOM. sous_projets : dicts {"nom",
    "nb_elements", "proprietaire"}. Une ligne par sous-projet, triee par
    nom, Action pre-remplie GARDER."""
    lignes = [SEPARATEUR.join(COLONNES)]
    for sp in sorted(sous_projets, key=lambda s: s[u"nom"].lower()):
        valeurs = [GARDER, sp[u"nom"], u"",
                   u"{0}".format(sp.get(u"nb_elements", u"")),
                   sp.get(u"proprietaire") or u""]
        lignes.append(SEPARATEUR.join([_echapper(v) for v in valeurs]))
    return FIN_DE_LIGNE.join(lignes) + FIN_DE_LIGNE


def ecrire_texte(chemin, texte):
    """UNE seule ecriture, UTF-8 avec BOM. Pas de codec utf-8-sig : sous
    IronPython 3, il reecrit le BOM a chaque write()."""
    while texte.startswith(BOM):
        texte = texte[len(BOM):]
    with io.open(chemin, "w", encoding="utf-8", newline="") as f:
        f.write(BOM + texte)


def decoder(octets):
    """(texte, encodage). UTF-8 (avec ou sans BOM) d'abord ; a defaut
    cp1252, ce qu'ecrit Excel FR en « CSV (separateur : point-virgule) »."""
    try:
        texte = octets.decode("utf-8")
        encodage = u"utf-8"
    except UnicodeDecodeError:
        texte = octets.decode("cp1252")
        encodage = u"cp1252"
    while texte.startswith(BOM):
        texte = texte[len(BOM):]
    return texte, encodage


def lire_csv(texte):
    """Lignes d'un CSV RFC 4180 a separateur ';' -> liste de listes.
    Guillemets doubles, separateur et sauts de ligne entre guillemets
    acceptes ; fins de ligne CRLF ou LF. Les lignes vides sont ignorees."""
    lignes = []
    ligne = []
    champ = []
    entre_guillemets = False
    i = 0
    n = len(texte)
    while i < n:
        c = texte[i]
        if entre_guillemets:
            if c == u'"':
                if i + 1 < n and texte[i + 1] == u'"':
                    champ.append(u'"')
                    i += 1
                else:
                    entre_guillemets = False
            else:
                champ.append(c)
        elif c == u'"':
            entre_guillemets = True
        elif c == SEPARATEUR:
            ligne.append(u"".join(champ))
            champ = []
        elif c in (u"\r", u"\n"):
            if c == u"\r" and i + 1 < n and texte[i + 1] == u"\n":
                i += 1
            ligne.append(u"".join(champ))
            champ = []
            lignes.append(ligne)
            ligne = []
        else:
            champ.append(c)
        i += 1
    if champ or ligne:
        ligne.append(u"".join(champ))
        lignes.append(ligne)
    return [l for l in lignes if any(v.strip() for v in l)]


# ---------------------------------------------------------------------------
# 2. Lecture de la table
# ---------------------------------------------------------------------------

class Constat(object):
    def __init__(self, niveau, ligne, message):
        self.niveau = niveau
        self.ligne = ligne          # numero de ligne du fichier, en-tete = 1
        self.message = message

    def colonnes(self):
        return [self.niveau,
                u"" if self.ligne is None else u"{0}".format(self.ligne),
                self.message]


def lire_table(texte):
    """(lignes, constats). lignes : dicts {"numero", "action", "nom_actuel",
    "nouveau_nom"} des seules lignes bien formees. Les cellules sont lues
    sans les espaces de bord ; un nom qui en portait est signale."""
    constats = []
    brutes = lire_csv(texte)
    if not brutes:
        return [], [Constat(ERREUR, None, u"fichier vide")]
    entete = [c.strip() for c in brutes[0]]
    if tuple(entete) != COLONNES:
        return [], [Constat(
            ERREUR, 1, u"en-tete inattendu : {0} - attendu : {1}".format(
                u";".join(entete), u";".join(COLONNES)))]

    lignes = []
    for rang, brute in enumerate(brutes[1:], 2):
        if len(brute) != len(COLONNES):
            constats.append(Constat(
                ERREUR, rang, u"{0} colonne(s) au lieu de {1}".format(
                    len(brute), len(COLONNES))))
            continue
        action = brute[0].strip().upper()
        noms = []
        for rang_col in (1, 2):
            valeur = brute[rang_col]
            if valeur != valeur.strip():
                constats.append(Constat(
                    AVERTISSEMENT, rang,
                    u"espaces en bord de {0} \"{1}\" : retires a la "
                    u"lecture".format(COLONNES[rang_col], valeur)))
            noms.append(valeur.strip())
        if action not in ACTIONS:
            constats.append(Constat(
                ERREUR, rang, u"action \"{0}\" inconnue - admises : {1}"
                .format(brute[0], u", ".join(ACTIONS))))
            continue
        lignes.append({u"numero": rang, u"action": action,
                       u"nom_actuel": noms[0], u"nouveau_nom": noms[1]})
    return lignes, constats


# ---------------------------------------------------------------------------
# 3. Validation contre le modele
# ---------------------------------------------------------------------------

def caracteres_interdits(nom):
    return [c for c in nom if c in CARACTERES_INTERDITS]


def est_ascii_sans_espace(nom):
    return bool(_ASCII_SANS_ESPACE.match(nom))


def _emprunteur(existant, utilisateur):
    """Nom de l'utilisateur qui detient le sous-projet, s'il n'est pas
    l'utilisateur courant ; None sinon."""
    proprietaire = (existant.get(u"proprietaire") or u"").strip()
    if proprietaire and proprietaire.lower() != (utilisateur or u"").lower():
        return proprietaire
    return None


def valider(lignes, existants, utilisateur):
    """Constats de validation de la table contre le modele.

    existants : {nom: {"proprietaire": nom ou "", "nb_elements": n}} - les
      sous-projets UTILISATEUR du modele.
    utilisateur : nom de l'utilisateur Revit courant.

    Une ERREUR bloque toute ecriture. Un AVERTISSEMENT s'affiche et laisse
    passer."""
    constats = []
    noms_min = {}
    for nom in existants:
        noms_min.setdefault(nom.lower(), []).append(nom)

    sources_vues = {}
    cibles_vues = {}

    def nom_valide(rang, colonne, nom):
        if not nom:
            constats.append(Constat(ERREUR, rang, u"{0} vide".format(colonne)))
            return False
        interdits = caracteres_interdits(nom)
        if interdits:
            constats.append(Constat(
                ERREUR, rang, u"{0} \"{1}\" : caractere(s) refuse(s) par "
                u"Revit : {2}".format(colonne, nom, u" ".join(interdits))))
            return False
        return True

    for l in lignes:
        rang = l[u"numero"]
        action = l[u"action"]
        source = l[u"nom_actuel"]
        cible = l[u"nouveau_nom"]

        # Forme de la ligne.
        if action == GARDER:
            if not source:
                constats.append(Constat(ERREUR, rang,
                                        u"GARDER sans Nom_actuel"))
                continue
            if cible and cible != source:
                constats.append(Constat(
                    ERREUR, rang, u"GARDER \"{0}\" avec Nouveau_nom \"{1}\" : "
                    u"ecrire RENOMMER pour renommer, ou vider "
                    u"Nouveau_nom".format(source, cible)))
                continue
        elif action == RENOMMER:
            if not source or not cible:
                constats.append(Constat(
                    ERREUR, rang, u"RENOMMER exige Nom_actuel ET "
                    u"Nouveau_nom"))
                continue
        elif action == CREER:
            if source:
                constats.append(Constat(
                    ERREUR, rang, u"CREER \"{0}\" avec un Nom_actuel \"{1}\" : "
                    u"CREER ne prend que Nouveau_nom".format(cible, source)))
                continue
            if not cible:
                constats.append(Constat(ERREUR, rang,
                                        u"CREER sans Nouveau_nom"))
                continue

        # Source : doit exister, une seule fois dans la table.
        if source:
            if source not in existants:
                proches = noms_min.get(source.lower(), [])
                suite = (u" (casse differente : {0})".format(
                    u", ".join(proches)) if proches else u"")
                constats.append(Constat(
                    ERREUR, rang, u"source \"{0}\" absente du modele{1}"
                    .format(source, suite)))
            elif action == RENOMMER:
                autre = _emprunteur(existants[source], utilisateur)
                if autre:
                    constats.append(Constat(
                        ERREUR, rang, u"\"{0}\" est emprunte par {1} : lui "
                        u"demander de synchroniser en le liberant".format(
                            source, autre)))
                elif existants[source].get(u"editable") is False:
                    # La documentation de RenameWorkset ne pose aucune
                    # condition d'emprunt : on attend un emprunt implicite,
                    # comme pour un nom de famille (mesure du 2026-09-24),
                    # sans l'avoir mesure pour un sous-projet.
                    constats.append(Constat(
                        AVERTISSEMENT, rang, u"\"{0}\" n'est pas emprunte par "
                        u"vous : emprunt implicite attendu, non verifie"
                        .format(source)))
            if source in sources_vues:
                constats.append(Constat(
                    ERREUR, rang, u"source \"{0}\" deja traitee ligne {1}"
                    .format(source, sources_vues[source])))
            else:
                sources_vues[source] = rang

        # Cible : nom ecrit par la table.
        if action in (RENOMMER, CREER):
            if not nom_valide(rang, u"Nouveau_nom", cible):
                continue
            if action == RENOMMER and cible == source:
                constats.append(Constat(
                    AVERTISSEMENT, rang, u"RENOMMER \"{0}\" vers le meme nom : "
                    u"sans effet".format(source)))
                continue
            if cible in existants:
                constats.append(Constat(
                    ERREUR, rang, u"cible \"{0}\" deja existante dans le "
                    u"modele".format(cible)))
            else:
                proches = [n for n in noms_min.get(cible.lower(), [])
                           if n != source]
                if proches:
                    constats.append(Constat(
                        AVERTISSEMENT, rang, u"cible \"{0}\" ne differe que "
                        u"par la casse de {1}".format(
                            cible, u", ".join(proches))))
            if cible in cibles_vues:
                constats.append(Constat(
                    ERREUR, rang, u"cible \"{0}\" presente deux fois dans la "
                    u"table (ligne {1})".format(cible, cibles_vues[cible])))
            else:
                cibles_vues[cible] = rang
            if not est_ascii_sans_espace(cible):
                constats.append(Constat(
                    AVERTISSEMENT, rang, u"\"{0}\" n'est pas en ASCII sans "
                    u"espace".format(cible)))

        # Sous-projets imposes par Revit.
        if action in (RENOMMER, CREER):
            touches = [n for n in (source, cible) if n in SOUS_PROJETS_IMPOSES]
            for nom in touches:
                constats.append(Constat(
                    AVERTISSEMENT, rang, u"la table touche \"{0}\", cree par "
                    u"Revit a l'activation du travail partage (R14)".format(
                        nom)))

    absents = sorted([n for n in existants if n not in sources_vues],
                     key=lambda n: n.lower())
    if absents:
        constats.append(Constat(
            AVERTISSEMENT, None, u"{0} sous-projet(s) du modele absent(s) de la "
            u"table, laisses tels quels : {1}".format(
                len(absents), u", ".join(absents))))
    return constats


def bloquant(constats):
    return any(c.niveau == ERREUR for c in constats)


# ---------------------------------------------------------------------------
# 4. Plan et controle apres ecriture
# ---------------------------------------------------------------------------

def plan(lignes):
    """Operations a executer, dans l'ordre : creations puis renommages.
    GARDER et les renommages sans effet n'y figurent pas."""
    creations = [OrderedDict([(u"action", CREER), (u"nom_actuel", u""),
                              (u"nouveau_nom", l[u"nouveau_nom"]),
                              (u"ligne", l[u"numero"])])
                 for l in lignes if l[u"action"] == CREER]
    renommages = [OrderedDict([(u"action", RENOMMER),
                               (u"nom_actuel", l[u"nom_actuel"]),
                               (u"nouveau_nom", l[u"nouveau_nom"]),
                               (u"ligne", l[u"numero"])])
                  for l in lignes if l[u"action"] == RENOMMER
                  and l[u"nom_actuel"] != l[u"nouveau_nom"]]
    return creations + renommages


def ecarts_apres(operations, noms_lus):
    """Ecarts entre le plan et les noms relus apres ecriture. noms_lus :
    noms des sous-projets utilisateur relus dans le modele."""
    lus = set(noms_lus)
    ecarts = []
    for op in operations:
        cible = op[u"nouveau_nom"]
        if cible not in lus:
            ecarts.append(u"ligne {0} : \"{1}\" absent apres ecriture".format(
                op[u"ligne"], cible))
        if op[u"action"] == RENOMMER and op[u"nom_actuel"] in lus:
            ecarts.append(u"ligne {0} : \"{1}\" encore present apres "
                          u"renommage".format(op[u"ligne"], op[u"nom_actuel"]))
    return ecarts
