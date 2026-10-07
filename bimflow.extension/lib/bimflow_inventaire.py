# -*- coding: utf-8 -*-
"""bimflow_inventaire - logique pure du bouton Inventaire systemes.

Le bouton (Conformite.panel\\InventaireSystemes.pushbutton) lit la maquette
par l'API Revit et convertit ce qu'il lit en dictionnaires simples. Tout ce
qui suit la lecture vit ici : schema des sorties, code d'un nom, coherences,
remplissage, parcours d'un arbre de filtre, repartition des elements par
systeme, controles arithmetiques, serialisation CSV et JSON.

L'outil MESURE, il ne conclut pas : aucune sortie ne qualifie un objet,
elle ecrit ce qui est compte ("0 occurrence", "n'est applique a aucune vue").

Aucune indisponibilite silencieuse : une propriete illisible donne la valeur
NON_LU dans sa cellule ET une ligne dans la table des anomalies. Le seul
endroit qui attrape une erreur de lecture est Inventaire.lire, qui la publie.

PYTHON PUR, stdlib seulement, syntaxe 3.4 : ce fichier tourne sous
IronPython 3.4 dans Revit (pyRevit ajoute ce dossier lib\\ au chemin) ET
sous CPython 3 pour les tests (tests\\test_bimflow_inventaire.py). Ni
Autodesk, ni clr, ni pyrevit : il recoit des dictionnaires.

bimflow - Keovia Solutions inc. - 2026-10-07
"""

import io
import json
import os
import re
from collections import OrderedDict

try:
    import unicodedata
except ImportError:            # disponibilite non verifiee sous IPY342
    unicodedata = None


SCHEMA = u"bimflow.inventaire/0.1"

NON_LU = u"NON_LU"
OUI = u"OUI"
NON = u"NON"
INDETERMINE = u"INDETERMINE"

BOM = u"﻿"
SEPARATEUR_CSV = u";"
FIN_DE_LIGNE_CSV = u"\r\n"
SEPARATEUR_LISTE = u" | "

LONGUEUR_EXEMPLE = 60

ROLE_HOTE = u"HOTE"
ROLE_LIEN = u"LIEN"

LU = u"LU"
NON_CHARGE = u"NON_CHARGE"
IMBRIQUE_NON_LU = u"IMBRIQUE_NON_LU"
ERREUR = u"ERREUR"

# Origine d'un parametre (tables 41 et 60).
INTEGRE = u"INTEGRE"
PARTAGE = u"PARTAGE"
PROJET = u"PROJET"
FAMILLE = u"FAMILLE"
CALCULE = u"CALCULE"

# Etat d'une valeur de parametre.
VIDE = u"VIDE"
TIRET = u"TIRET"
RENSEIGNE = u"RENSEIGNE"

# Type de systeme lu sur un element mais absent des systemes du document.
INTROUVABLE = u"INTROUVABLE"


# ---------------------------------------------------------------------------
# 1. Schema des sorties
# ---------------------------------------------------------------------------
# (cle JSON, fichier CSV, colonnes apres Source_modele). L'ordre est celui du
# JSON et des fichiers. Chaque tableau du JSON a exactement ces colonnes ; les
# CSV en sont des projections.

COLONNE_SOURCE = u"Source_modele"

TABLES = (
    (u"types_systeme", u"10_types_systeme.csv", (
        u"Domaine", u"Id", u"Nom", u"Abreviation", u"Classification_api",
        u"Classification_libelle", u"Code_nom", u"Code_coherent", u"Fluide",
        u"Temperature_fluide_C", u"Materiau", u"Couleur_ligne_RVB",
        u"Couleur_ligne_hex", u"Remplace", u"Motif_ligne", u"Epaisseur_ligne",
        u"Nb_systemes", u"Nb_elements")),
    (u"systemes", u"11_systemes.csv", (
        u"Domaine", u"Id", u"Nom", u"Prefixe_nom", u"Type_systeme",
        u"Abreviation_type", u"Classification", u"Prefixe_coherent",
        u"Equipement_base", u"Nb_elements_parametre", u"Nb_elements_api")),
    (u"systemes_categories", u"12_systemes_categories.csv", (
        u"Systeme", u"Type_systeme", u"Categorie", u"Nb")),
    (u"elements_sans_systeme", u"13_elements_sans_systeme.csv", (
        u"Id", u"Categorie", u"Famille", u"Type", u"Niveau", u"Sous_projet")),
    (u"types_canalisation_gaine", u"14_types_canalisation_gaine.csv", (
        u"Domaine", u"Id", u"Famille_systeme", u"Nom_type", u"Forme",
        u"Segments", u"Nb_occurrences")),
    (u"elec_distribution", u"20_elec_distribution.csv", (
        u"Id", u"Nom", u"Phase", u"Configuration", u"Nb_conducteurs",
        u"Tension_LL_V", u"Tension_LN_V", u"Nb_tableaux")),
    (u"elec_tableaux", u"21_elec_tableaux.csv", (
        u"Id", u"Nom_tableau", u"Famille", u"Type", u"Systeme_distribution",
        u"Alimente_par", u"Nb_circuits", u"Niveau", u"Sous_projet")),
    (u"elec_circuits", u"22_elec_circuits.csv", (
        u"Id", u"Tableau", u"Numero", u"Type_systeme_elec", u"Type_circuit",
        u"Nom_charge", u"Tension_V", u"Nb_poles", u"Nb_elements")),
    (u"filtres", u"30_filtres.csv", (
        u"Id", u"Nom", u"Classe", u"Categories", u"Regles_texte", u"Nb_regles",
        u"Nb_vues", u"Nb_gabarits")),
    (u"filtres_regles", u"31_filtres_regles.csv", (
        u"Filtre_id", u"Filtre", u"Chemin", u"Parametre", u"Parametre_id",
        u"Parametre_GUID", u"Operateur", u"Valeur", u"Valeur_unites_internes",
        u"Inverse")),
    (u"filtres_application", u"32_filtres_application.csv", (
        u"Vue_id", u"Vue", u"Est_gabarit", u"Filtre", u"Active", u"Visible",
        u"Proj_ligne_RVB", u"Proj_motif_RVB", u"Coupe_ligne_RVB",
        u"Coupe_motif_RVB", u"Transparence", u"Demi_teinte")),
    (u"familles", u"40_familles.csv", (
        u"Categorie", u"Famille", u"Id_famille", u"In_situ", u"Nb_types",
        u"Nb_occurrences", u"Nb_param_type", u"Nb_param_occurrence",
        u"Nb_param_partages")),
    (u"familles_parametres", u"41_familles_parametres.csv", (
        u"Categorie", u"Famille", u"Parametre", u"Portee", u"Origine", u"GUID",
        u"Type_donnees", u"Groupe", u"Lecture_seule", u"Nb_porteurs",
        u"Nb_renseignes", u"Nb_tiret", u"Taux_remplissage",
        u"Nb_valeurs_distinctes", u"Exemple_valeur")),
    (u"parametres_projet", u"50_parametres_projet.csv", (
        u"Nom", u"Partage", u"GUID", u"Type_donnees", u"Groupe", u"Liaison",
        u"Categories")),
    (u"parametres_partages", u"51_parametres_partages.csv", (
        u"Nom", u"GUID", u"Type_donnees", u"Lie_au_projet", u"Note")),
    (u"nomenclatures_champs", u"60_nomenclatures_champs.csv", (
        u"Nomenclature", u"Categorie", u"Champ", u"Parametre_id",
        u"Parametre_GUID", u"Origine")),
    (u"anomalies", u"90_anomalies.csv", (
        u"Table", u"Id", u"Propriete", u"Raison")),
    (u"controles", u"99_controles.csv", (
        u"Controle", u"Attendu", u"Mesure", u"Statut")),
)

FICHIER_JSON = u"inventaire.json"


def colonnes(table):
    """Colonnes completes d'une table, Source_modele en tete."""
    for cle, _fichier, cols in TABLES:
        if cle == table:
            return (COLONNE_SOURCE,) + cols
    raise KeyError(u"table inconnue : {0}".format(table))


def fichiers_attendus():
    """Les 19 fichiers produits : le JSON puis les 18 CSV."""
    return [FICHIER_JSON] + [fichier for _cle, fichier, _cols in TABLES]


# Categories cibles des tables 40 et 41 : (nom BuiltInCategory, libelle).
# Le nom est resolu a l'execution ; une categorie inconnue de la version de
# Revit donne une anomalie, pas un plantage. OST_PlumbingEquipment n'existe
# que dans les versions recentes.
CATEGORIES_CIBLES = (
    (u"OST_MechanicalEquipment", u"Equipements mecaniques"),
    (u"OST_PlumbingEquipment", u"Equipements de plomberie"),
    (u"OST_ElectricalEquipment", u"Equipements electriques"),
    (u"OST_PlumbingFixtures", u"Appareils sanitaires"),
    (u"OST_LightingFixtures", u"Luminaires"),
    (u"OST_ElectricalFixtures", u"Appareils electriques"),
    (u"OST_PipeAccessory", u"Accessoires de canalisation"),
    (u"OST_PipeFitting", u"Raccords de canalisation"),
    (u"OST_DuctAccessory", u"Accessoires de gaine"),
    (u"OST_DuctFitting", u"Raccords de gaine"),
    (u"OST_DuctTerminal", u"Bouches d'aeration"),
    (u"OST_Sprinklers", u"Gicleurs"),
    (u"OST_FireAlarmDevices", u"Dispositifs d'alarme incendie"),
    (u"OST_CommunicationDevices", u"Dispositifs de communication"),
    (u"OST_DataDevices", u"Dispositifs de donnees"),
    (u"OST_SecurityDevices", u"Dispositifs de securite"),
    (u"OST_NurseCallDevices", u"Dispositifs d'appel infirmier"),
    (u"OST_TelephoneDevices", u"Dispositifs telephoniques"),
)

# Categories dont les elements sont repartis par systeme (tables 11 a 13) :
# le domaine tuyauterie et gaine. L'electricite a ses propres tables (20-22).
CATEGORIES_SYSTEME = (
    u"OST_PipeCurves", u"OST_FlexPipeCurves", u"OST_PipeFitting",
    u"OST_PipeAccessory", u"OST_PlumbingFixtures", u"OST_PlumbingEquipment",
    u"OST_Sprinklers", u"OST_MechanicalEquipment",
    u"OST_DuctCurves", u"OST_FlexDuctCurves", u"OST_DuctFitting",
    u"OST_DuctAccessory", u"OST_DuctTerminal",
)


# ---------------------------------------------------------------------------
# 2. Textes : accents, normalisation, code d'un nom
# ---------------------------------------------------------------------------

_SPECIAUX = {
    u"œ": u"oe", u"Œ": u"OE", u"æ": u"ae", u"Æ": u"AE",
    u"ß": u"ss", u"’": u"'", u"‘": u"'", u" ": u" ",
}

# Repli si unicodedata manque : lettres accentuees courantes -> base.
_ACCENTUES = (u"àáâãäåçèéê"
              u"ëìíîïñòóôõ"
              u"öùúûüýÿ"
              u"ÀÁÂÃÄÅÇÈÉÊ"
              u"ËÌÍÎÏÑÒÓÔÕ"
              u"ÖÙÚÛÜÝ")
_BASES = (u"aaaaaaceeeeiiiinooooouuuuyy"
          u"AAAAAACEEEEIIIINOOOOOUUUUY")
_TABLE_REPLI = dict(zip(_ACCENTUES, _BASES))


def _sans_accents_repli(texte):
    return u"".join([_TABLE_REPLI.get(c, c) for c in texte])


def sans_accents(texte):
    """Texte sans diacritiques (e accent aigu -> e, oe lie -> oe)."""
    if not texte:
        return u""
    for special, rempl in _SPECIAUX.items():
        texte = texte.replace(special, rempl)
    if unicodedata is None:
        return _sans_accents_repli(texte)
    decompose = unicodedata.normalize("NFKD", texte)
    return u"".join([c for c in decompose if not unicodedata.combining(c)])


def normaliser(texte):
    """Cle de comparaison : sans accents, majuscules, espaces reduits."""
    if texte is None:
        return u""
    return u" ".join(sans_accents(texte).upper().split())


_SEPARATEURS_CODE = re.compile(u"[_ \\-]")


def code_nom(nom):
    """Segment du nom avant le premier '_', espace ou '-' ("" si absent)."""
    if not nom or nom == NON_LU:
        return u""
    return _SEPARATEURS_CODE.split(nom.strip(), 1)[0]


def code_coherent(code, abreviation):
    """OUI / NON / INDETERMINE : code egal a l'abreviation, sans tenir compte
    de la casse ni des accents. INDETERMINE si l'un des deux manque."""
    if code == NON_LU or abreviation == NON_LU:
        return INDETERMINE
    a = normaliser(code)
    b = normaliser(abreviation)
    if not a or not b:
        return INDETERMINE
    return OUI if a == b else NON


def tronquer(texte, longueur=LONGUEUR_EXEMPLE):
    if texte is None:
        return u""
    if len(texte) <= longueur:
        return texte
    return texte[:longueur - 3] + u"..."


_NOTES_IFC = None


def note_parametre_partage(nom):
    """EXPORTATEUR_IFC pour les parametres que l'exportateur IFC cree
    lui-meme (libelles FR et EN) ; vide sinon."""
    global _NOTES_IFC
    if _NOTES_IFC is None:
        _NOTES_IFC = set([normaliser(n) for n in (
            u"IfcGUID", u"Exporter au format IFC",
            u"Type prédéfini d'IFC", u"Type prédéfini IFC",
            u"Export to IFC", u"IFC Predefined Type")])
    return u"EXPORTATEUR_IFC" if normaliser(nom) in _NOTES_IFC else u""


def identifiant_court(type_id):
    """Forme courte d'un ForgeTypeId : 'autodesk.spec.aec:length-2.0.0' ->
    'length' ; 'autodesk.spec:spec.string-2.0.0' -> 'string'."""
    if not type_id or type_id == NON_LU:
        return type_id or u""
    court = type_id.split(u":")[-1]
    court = re.sub(u"-\\d+(\\.\\d+)*$", u"", court)
    if court.startswith(u"spec."):
        court = court[len(u"spec."):]
    return court


def origine_parametre(integre, partage, nom_lie_au_projet, element_projet=None):
    """INTEGRE / PARTAGE / PROJET / FAMILLE / INDETERMINE.

    integre, partage, nom_lie_au_projet : booleens, ou None si illisibles.
    element_projet : l'identifiant du parametre designe-t-il un parametre du
    document (ParameterElement) ? None si on ne sait pas.

    INTEGRE si natif ; PARTAGE si partage ; PROJET si non partage et nom lie
    au projet ; FAMILLE sinon. INDETERMINE quand une lecture manque, ou quand
    le nom et l'identifiant se contredisent (un parametre de famille qui
    porte le nom d'un parametre de projet)."""
    if integre is None:
        return INDETERMINE
    if integre:
        return INTEGRE
    if partage is None:
        return INDETERMINE
    if partage:
        return PARTAGE
    if nom_lie_au_projet is None:
        return INDETERMINE
    if element_projet is None:
        return PROJET if nom_lie_au_projet else FAMILLE
    if nom_lie_au_projet and element_projet:
        return PROJET
    if not nom_lie_au_projet and not element_projet:
        return FAMILLE
    return INDETERMINE


# ---------------------------------------------------------------------------
# 3. Couleurs, dossier de sortie, identifiants de source
# ---------------------------------------------------------------------------

def couleur(rouge, vert, bleu, valide):
    """{'rvb', 'hex', 'remplace'} ; couleur invalide -> vides et NON."""
    if not valide:
        return {u"rvb": u"", u"hex": u"", u"remplace": NON}
    return {
        u"rvb": u"{0} {1} {2}".format(int(rouge), int(vert), int(bleu)),
        u"hex": u"#{0:02X}{1:02X}{2:02X}".format(
            int(rouge), int(vert), int(bleu)),
        u"remplace": OUI,
    }


_INTERDITS_FICHIER = re.compile(u'[\\\\/:*?"<>|\\x00-\\x1f]')


def nom_dossier_sortie(titre, horodatage):
    """inventaire_<titre>_<AAAAMMJJ_HHMM>. horodatage : datetime."""
    propre = (titre or u"").strip()
    if propre.lower().endswith(u".rvt"):
        propre = propre[:-4]
    propre = _INTERDITS_FICHIER.sub(u"_", propre).strip().rstrip(u".")
    if not propre:
        propre = u"maquette"
    return u"inventaire_{0}_{1}".format(
        propre, horodatage.strftime("%Y%m%d_%H%M"))


def identifiants_sources(titres):
    """Une etiquette unique par maquette : le titre, suffixe #2, #3... en cas
    de doublon."""
    vus = {}
    resultat = []
    for titre in titres:
        base = titre or u"(sans titre)"
        vus[base] = vus.get(base, 0) + 1
        if vus[base] == 1:
            resultat.append(base)
        else:
            resultat.append(u"{0} #{1}".format(base, vus[base]))
    return resultat


# ---------------------------------------------------------------------------
# 4. Remplissage d'un parametre
# ---------------------------------------------------------------------------

def etat_texte(texte):
    """VIDE / TIRET / RENSEIGNE pour une valeur texte."""
    if texte is None:
        return VIDE
    propre = texte.strip()
    if not propre:
        return VIDE
    if propre == u"-":
        return TIRET
    return RENSEIGNE


class Remplissage(object):
    """Accumule les valeurs d'un parametre sur ses porteurs (types ou
    occurrences) et rend les colonnes de remplissage de la table 41."""

    def __init__(self):
        self.nb_porteurs = 0
        self.nb_renseignes = 0
        self.nb_tiret = 0
        self.valeurs = set()
        self.exemple = None
        self.nb_illisibles = 0
        self.raison_illisible = None

    def _renseigne(self, texte):
        self.nb_renseignes += 1
        if texte is not None:
            self.valeurs.add(texte)
            if self.exemple is None:
                self.exemple = texte

    def ajouter_texte(self, texte):
        """Parametre texte : renseigne si non vide apres strip et != '-'."""
        self.nb_porteurs += 1
        etat = etat_texte(texte)
        if etat == TIRET:
            self.nb_tiret += 1
        elif etat == RENSEIGNE:
            self._renseigne(texte.strip())
        return etat

    def ajouter_valeur(self, a_valeur, texte=None):
        """Parametre numerique, Oui/Non ou identifiant : renseigne si
        HasValue. texte (rendu Revit) sert aux valeurs distinctes."""
        self.nb_porteurs += 1
        if not a_valeur:
            return VIDE
        self._renseigne(texte.strip() if texte else None)
        return RENSEIGNE

    def ajouter_illisible(self, raison):
        """Porteur dont la valeur n'a pas pu etre lue : il compte comme
        porteur, et le nombre d'echecs est publie en anomalie."""
        self.nb_porteurs += 1
        self.nb_illisibles += 1
        if self.raison_illisible is None:
            self.raison_illisible = raison

    def taux(self):
        """Fraction 0..1, arrondie a 4 decimales ; None sans porteur."""
        if self.nb_porteurs == 0:
            return None
        return round(float(self.nb_renseignes) / float(self.nb_porteurs), 4)

    def colonnes(self):
        return OrderedDict([
            (u"Nb_porteurs", self.nb_porteurs),
            (u"Nb_renseignes", self.nb_renseignes),
            (u"Nb_tiret", self.nb_tiret),
            (u"Taux_remplissage", self.taux()),
            (u"Nb_valeurs_distinctes", len(self.valeurs)),
            (u"Exemple_valeur", tronquer(self.exemple)),
        ])


# ---------------------------------------------------------------------------
# 5. Filtres de vue : parcours de l'arbre
# ---------------------------------------------------------------------------
# L'adaptateur convertit GetElementFilter() en dictionnaires :
#   {"type": "ET" | "OU", "inverse": bool, "enfants": [noeuds]}
#   {"type": "PARAMETRES", "inverse": bool, "regles": [regles]}
#   {"type": "AUTRE", "inverse": bool, "classe": "NomDeClasse"}
# et chaque regle :
#   {"parametre", "parametre_id", "parametre_guid", "operateur" (nom de la
#    classe d'evaluateur ou de regle), "valeur", "valeur_unites_internes",
#    "inverse" (regle enveloppee dans FilterInverseRule)}

OPERATEURS = {
    u"FilterStringEquals": u"egal a",
    u"FilterStringBeginsWith": u"commence par",
    u"FilterStringEndsWith": u"finit par",
    u"FilterStringContains": u"contient",
    u"FilterStringGreater": u"superieur a",
    u"FilterStringGreaterOrEqual": u"superieur ou egal a",
    u"FilterStringLess": u"inferieur a",
    u"FilterStringLessOrEqual": u"inferieur ou egal a",
    u"FilterNumericEquals": u"egal a",
    u"FilterNumericGreater": u"superieur a",
    u"FilterNumericGreaterOrEqual": u"superieur ou egal a",
    u"FilterNumericLess": u"inferieur a",
    u"FilterNumericLessOrEqual": u"inferieur ou egal a",
    u"HasValueFilterRule": u"a une valeur",
    u"HasNoValueFilterRule": u"n'a pas de valeur",
    u"SharedParameterApplicableRule": u"parametre partage applicable",
    u"FilterCategoryRule": u"categorie parmi",
    u"FilterGlobalParameterAssociationRule": u"associe au parametre global",
}

LIBELLES_NOEUDS = {u"ET": u"ET", u"OU": u"OU", u"PARAMETRES": u"PARAM",
                   u"AUTRE": u"AUTRE"}


def libelle_operateur(operateur):
    return OPERATEURS.get(operateur, operateur or u"")


def _texte_regle(regle):
    op = libelle_operateur(regle.get(u"operateur"))
    valeur = regle.get(u"valeur")
    if valeur is None or valeur == u"":
        texte = u"{0} {1}".format(regle.get(u"parametre") or u"?", op)
    else:
        texte = u'{0} {1} "{2}"'.format(
            regle.get(u"parametre") or u"?", op, formater_texte(valeur))
    if regle.get(u"inverse"):
        texte = u"NON ({0})".format(texte)
    return texte


def _texte_noeud(noeud):
    genre = noeud.get(u"type")
    if genre in (u"ET", u"OU"):
        morceaux = [_texte_noeud(e) for e in noeud.get(u"enfants") or []]
        texte = (u" " + genre + u" ").join([u"(" + m + u")" for m in morceaux])
    elif genre == u"PARAMETRES":
        regles = [_texte_regle(r) for r in noeud.get(u"regles") or []]
        texte = u" ET ".join(regles) if len(regles) > 1 else (
            regles[0] if regles else u"")
        if len(regles) > 1:
            texte = u"(" + texte + u")"
    else:
        texte = u"[filtre {0}]".format(noeud.get(u"classe") or u"?")
    if noeud.get(u"inverse"):
        texte = u"NON (" + texte + u")"
    return texte


def _etiquette(noeud, rang):
    base = LIBELLES_NOEUDS.get(noeud.get(u"type"), u"AUTRE")
    if rang is not None:
        base = u"{0}[{1}]".format(base, rang)
    if noeud.get(u"inverse"):
        base = u"NON " + base
    return base


def aplatir_filtre(arbre):
    """(lignes de regles, texte lisible, nombre de regles).

    Chaque ligne porte le Chemin depuis la racine (ex. 'ET/OU[2]/PARAM[1]/R1')
    et les colonnes de la table 31 sans Filtre_id ni Filtre. Un noeud inverse
    est prefixe de NON dans le chemin ; la colonne Inverse dit si la REGLE
    elle-meme est inverse (FilterInverseRule)."""
    if not arbre:
        return [], u"", 0
    lignes = []

    def descendre(noeud, chemin):
        genre = noeud.get(u"type")
        if genre in (u"ET", u"OU"):
            for i, enfant in enumerate(noeud.get(u"enfants") or []):
                descendre(enfant, chemin + u"/" + _etiquette(enfant, i + 1))
        elif genre == u"PARAMETRES":
            for j, regle in enumerate(noeud.get(u"regles") or []):
                lignes.append(OrderedDict([
                    (u"Chemin", u"{0}/R{1}".format(chemin, j + 1)),
                    (u"Parametre", regle.get(u"parametre")),
                    (u"Parametre_id", regle.get(u"parametre_id")),
                    (u"Parametre_GUID", regle.get(u"parametre_guid") or u""),
                    (u"Operateur", libelle_operateur(regle.get(u"operateur"))),
                    (u"Valeur", regle.get(u"valeur")),
                    (u"Valeur_unites_internes",
                     bool(regle.get(u"valeur_unites_internes"))),
                    (u"Inverse", bool(regle.get(u"inverse"))),
                ]))

    descendre(arbre, _etiquette(arbre, None))
    return lignes, _texte_noeud(arbre), len(lignes)


def compter_applications(applications):
    """{filtre_id: (nb_vues, nb_gabarits)} depuis des (filtre_id, est_gabarit)."""
    comptes = {}
    for filtre_id, est_gabarit in applications:
        vues, gabarits = comptes.get(filtre_id, (0, 0))
        if est_gabarit:
            gabarits += 1
        else:
            vues += 1
        comptes[filtre_id] = (vues, gabarits)
    return comptes


# ---------------------------------------------------------------------------
# 6. Repartition des elements MEP par systeme (cote element)
# ---------------------------------------------------------------------------

def noms_systemes(texte):
    """Noms de systeme lus sur un element (parametre natif 'Nom du systeme') :
    plusieurs noms sont separes par des virgules."""
    if not texte or texte == NON_LU:
        return []
    return [n.strip() for n in texte.split(u",") if n.strip()]


def repartir_elements(elements, types_par_systeme):
    """Repartit les elements MEP par systeme, depuis l'element.

    elements : dicts {"id", "categorie", "famille", "type", "niveau",
      "sous_projet", "noms_systeme" (texte, None ou NON_LU),
      "type_systeme_id" (identifiant ou None)}.
    types_par_systeme : {nom de systeme: [noms de type de systeme]}.

    Rend un dict :
      par_systeme      {nom: nb elements}
      par_categorie    {(systeme, type, categorie): nb}
      par_type_id      {type_systeme_id: nb elements}
      sans_systeme     [elements]
      multi            nb d'elements dans plusieurs systemes
      affectations_sup nb d'affectations au-dela de la premiere
      non_lus          nb d'elements au nom de systeme illisible
      inconnus         {nom: nb} noms lus sans systeme de ce nom
      total            nb d'elements lus
    """
    r = {u"par_systeme": {}, u"par_categorie": {}, u"par_type_id": {},
         u"sans_systeme": [], u"multi": 0, u"affectations_sup": 0,
         u"non_lus": 0, u"inconnus": {}, u"total": 0}
    for el in elements:
        r[u"total"] += 1
        tid = el.get(u"type_systeme_id")
        if tid is not None and tid != NON_LU:
            r[u"par_type_id"][tid] = r[u"par_type_id"].get(tid, 0) + 1
        brut = el.get(u"noms_systeme")
        if brut == NON_LU:
            r[u"non_lus"] += 1
            continue
        noms = noms_systemes(brut)
        if not noms:
            r[u"sans_systeme"].append(el)
            continue
        if len(noms) > 1:
            r[u"multi"] += 1
            r[u"affectations_sup"] += len(noms) - 1
        for nom in noms:
            r[u"par_systeme"][nom] = r[u"par_systeme"].get(nom, 0) + 1
            types = types_par_systeme.get(nom)
            if types is None:
                r[u"inconnus"][nom] = r[u"inconnus"].get(nom, 0) + 1
                type_txt = INTROUVABLE
            else:
                type_txt = SEPARATEUR_LISTE.join(types)
            cle = (nom, type_txt, el.get(u"categorie") or u"")
            r[u"par_categorie"][cle] = r[u"par_categorie"].get(cle, 0) + 1
    return r


# ---------------------------------------------------------------------------
# 7. L'inventaire : tables, anomalies, lecture publiee
# ---------------------------------------------------------------------------

def texte_erreur(err):
    message = u"{0}".format(err).strip()
    nom = type(err).__name__
    return u"{0}: {1}".format(nom, message) if message else nom


class Inventaire(object):
    """Les tables du schema, remplies ligne a ligne par l'adaptateur."""

    def __init__(self):
        self.tables = OrderedDict([(cle, []) for cle, _f, _c in TABLES])
        self.modeles = []
        self._echecs = OrderedDict()

    def ajouter(self, table, source, valeurs):
        """Ajoute une ligne. Toutes les colonnes sont exigees, aucune autre :
        une colonne oubliee serait une cellule vide silencieuse."""
        attendues = colonnes(table)[1:]
        manquantes = [c for c in attendues if c not in valeurs]
        en_plus = [c for c in valeurs if c not in attendues]
        if manquantes or en_plus:
            raise ValueError(
                u"table {0} : colonnes manquantes {1}, inconnues {2}".format(
                    table, manquantes, en_plus))
        ligne = OrderedDict([(COLONNE_SOURCE, source)])
        for c in attendues:
            ligne[c] = valeurs[c]
        self.tables[table].append(ligne)
        return ligne

    def anomalie(self, source, table, ident, propriete, raison):
        return self.ajouter(u"anomalies", source, {
            u"Table": table, u"Id": ident, u"Propriete": propriete,
            u"Raison": raison})

    def lire(self, source, table, ident, propriete, fonction):
        """Appelle fonction() ; en cas d'erreur, publie l'anomalie et rend
        NON_LU. C'est le seul endroit ou une erreur de lecture est attrapee."""
        try:
            return fonction()
        except Exception as err:
            self.anomalie(source, table, ident, propriete, texte_erreur(err))
            return NON_LU

    def compter_echec(self, source, table, ident, propriete, err):
        """Echec de lecture repetitif (une valeur par element) : compte, pour
        une seule anomalie par (table, id, propriete) a la publication."""
        cle = (source, table, ident, propriete)
        if cle in self._echecs:
            self._echecs[cle][0] += 1
        else:
            self._echecs[cle] = [1, texte_erreur(err)]

    def publier_echecs(self):
        """Publie les echecs comptes, puis vide le compteur."""
        for (source, table, ident, propriete), (n, raison) in \
                self._echecs.items():
            self.anomalie(source, table, ident, propriete,
                          u"{0} lecture(s) en echec ; premiere : {1}".format(
                              n, raison))
        self._echecs = OrderedDict()

    def lignes(self, table, source=None):
        return [l for l in self.tables[table]
                if source is None or l[COLONNE_SOURCE] == source]

    def ajouter_modele(self, source, role, titre, chemin_visible, cloud,
                       workshared, statut, sous_projets_fermes, comptes=None):
        modele = OrderedDict([
            (u"source_modele", source), (u"role", role), (u"titre", titre),
            (u"chemin_visible", chemin_visible), (u"cloud", cloud),
            (u"workshared", workshared), (u"statut_lecture", statut),
            (u"sous_projets_fermes", list(sous_projets_fermes or [])),
            (u"comptes", OrderedDict(comptes or {})),
        ])
        self.modeles.append(modele)
        return modele

    def comptes_par_table(self, source):
        return OrderedDict([(cle, len(self.lignes(cle, source)))
                            for cle, _f, _c in TABLES])


# ---------------------------------------------------------------------------
# 8. Controles arithmetiques (table 99)
# ---------------------------------------------------------------------------

def _entier(valeur):
    if isinstance(valeur, bool):
        return None
    if isinstance(valeur, int):
        return valeur
    return None


def _statut(ok):
    return u"OK" if ok else u"ECART"


def calculer_controles(inv):
    """Ajoute les lignes de controle de chaque maquette lue, puis les rend.

    comptes attendus dans modele["comptes"] :
      elements_mep_lus, elements_multi_systemes, affectations_sup,
      elements_systeme_non_lu, affectations_systeme_inconnu,
      occurrences_categories_cibles."""
    produits = []
    for modele in inv.modeles:
        if modele[u"statut_lecture"] not in (LU, ERREUR):
            continue
        src = modele[u"source_modele"]
        comptes = modele[u"comptes"]

        # 1. Systemes : somme par systeme + sans systeme >= elements lus.
        somme = 0
        illisibles = 0
        for l in inv.lignes(u"systemes", src):
            n = _entier(l[u"Nb_elements_parametre"])
            if n is None:
                illisibles += 1
            else:
                somme += n
        sans = len(inv.lignes(u"elements_sans_systeme", src))
        lus = comptes.get(u"elements_mep_lus", 0)
        total = somme + sans
        explications = []
        sup = comptes.get(u"affectations_sup", 0)
        if sup:
            explications.append(
                u"+{0} affectation(s) d'elements presents dans plusieurs "
                u"systemes ({1} element(s))".format(
                    sup, comptes.get(u"elements_multi_systemes", 0)))
        non_lu = comptes.get(u"elements_systeme_non_lu", 0)
        if non_lu:
            explications.append(
                u"{0} element(s) au nom de systeme NON_LU".format(non_lu))
        inconnus = comptes.get(u"affectations_systeme_inconnu", 0)
        if inconnus:
            explications.append(
                u"{0} affectation(s) a un nom de systeme absent des systemes "
                u"du document".format(inconnus))
        if illisibles:
            explications.append(
                u"{0} systeme(s) au compte NON_LU".format(illisibles))
        mesure = u"{0} + {1} = {2}".format(somme, sans, total)
        if explications:
            mesure += u" ; " + u" ; ".join(explications)
        produits.append(inv.ajouter(u"controles", src, {
            u"Controle": u"Elements par systeme (cote element) + elements "
                         u"sans systeme >= elements MEP lus",
            u"Attendu": u">= {0}".format(lus),
            u"Mesure": mesure,
            u"Statut": _statut(total >= lus),
        }))

        # 2. Familles : somme des occurrences = occurrences des categories.
        somme_fam = 0
        illisibles = 0
        for l in inv.lignes(u"familles", src):
            n = _entier(l[u"Nb_occurrences"])
            if n is None:
                illisibles += 1
            else:
                somme_fam += n
        attendu = comptes.get(u"occurrences_categories_cibles", 0)
        mesure = u"{0}".format(somme_fam)
        if illisibles:
            mesure += u" ; {0} famille(s) au compte NON_LU".format(illisibles)
        produits.append(inv.ajouter(u"controles", src, {
            u"Controle": u"Somme des occurrences des familles = occurrences "
                         u"des categories cibles",
            u"Attendu": u"{0}".format(attendu),
            u"Mesure": mesure,
            u"Statut": _statut(somme_fam == attendu and not illisibles),
        }))

        # 3. Chaque filtre applique existe dans la table 30.
        noms_30 = set([l[u"Nom"] for l in inv.lignes(u"filtres", src)])
        appliques = set([l[u"Filtre"]
                         for l in inv.lignes(u"filtres_application", src)])
        absents = sorted([n for n in appliques if n not in noms_30],
                         key=lambda n: u"{0}".format(n))
        mesure = u"{0} filtre(s) applique(s), {1} absent(s) de la table 30".format(
            len(appliques), len(absents))
        if absents:
            mesure += u" : " + u", ".join([u"{0}".format(n) for n in absents])
        produits.append(inv.ajouter(u"controles", src, {
            u"Controle": u"Chaque filtre applique existe dans la table 30",
            u"Attendu": u"0 absent",
            u"Mesure": mesure,
            u"Statut": _statut(not absents),
        }))

    # 4. Anomalies, par maquette puis au total - compte AVANT ce controle.
    total = len(inv.tables[u"anomalies"])
    for modele in inv.modeles:
        src = modele[u"source_modele"]
        n = len(inv.lignes(u"anomalies", src))
        produits.append(inv.ajouter(u"controles", src, {
            u"Controle": u"Nombre d'anomalies (90_anomalies.csv)",
            u"Attendu": u"0",
            u"Mesure": u"{0} (toutes maquettes : {1})".format(n, total),
            u"Statut": _statut(n == 0),
        }))
    return produits


# ---------------------------------------------------------------------------
# 9. Serialisation
# ---------------------------------------------------------------------------

def formater_nombre(valeur):
    """Nombre -> texte a virgule decimale, sans notation scientifique."""
    if isinstance(valeur, bool):
        return OUI if valeur else NON
    if isinstance(valeur, int):
        return u"{0}".format(valeur)
    v = float(valeur)
    if v != v or v in (float("inf"), float("-inf")):
        return NON_LU
    if v == int(v) and abs(v) < 1e15:
        return u"{0}".format(int(v))
    texte = repr(v)
    if u"e" in texte or u"E" in texte:
        texte = (u"%.12f" % v).rstrip(u"0").rstrip(u".")
    return texte.replace(u".", u",")


def formater_texte(valeur):
    """Valeur d'une cellule CSV, avant echappement."""
    if valeur is None:
        return u""
    if isinstance(valeur, bool):
        return OUI if valeur else NON
    if isinstance(valeur, (int, float)):
        return formater_nombre(valeur)
    if isinstance(valeur, (list, tuple, set)):
        return SEPARATEUR_LISTE.join([formater_texte(v) for v in valeur])
    return u"{0}".format(valeur)


def echapper_csv(texte):
    """RFC 4180 : entre guillemets si ; " CR ou LF, guillemets doubles."""
    if (SEPARATEUR_CSV in texte or u'"' in texte or u"\r" in texte
            or u"\n" in texte):
        return u'"' + texte.replace(u'"', u'""') + u'"'
    return texte


def texte_csv(table, lignes):
    """Texte complet d'un CSV, SANS BOM : en-tete puis lignes, CRLF."""
    cols = colonnes(table)
    sortie = [SEPARATEUR_CSV.join([echapper_csv(c) for c in cols])]
    for ligne in lignes:
        sortie.append(SEPARATEUR_CSV.join(
            [echapper_csv(formater_texte(ligne.get(c))) for c in cols]))
    return FIN_DE_LIGNE_CSV.join(sortie) + FIN_DE_LIGNE_CSV


def document_json(inv, outil):
    racine = OrderedDict()
    racine[u"schema"] = SCHEMA
    racine[u"outil"] = outil
    racine[u"modeles"] = inv.modeles
    for cle, _f, _c in TABLES:
        racine[cle] = inv.tables[cle]
    return racine


def texte_json(inv, outil):
    """Texte JSON complet, SANS BOM ; decimale point. Un objet que json ne
    connait pas (type .NET egare) est ecrit par son texte plutot que de
    faire echouer l'ecriture en fin de lecture."""
    return json.dumps(document_json(inv, outil), ensure_ascii=False,
                      indent=1, default=lambda o: u"{0}".format(o)) + u"\n"


def contenus(inv, outil):
    """{nom de fichier: texte sans BOM} pour les 19 fichiers."""
    resultat = OrderedDict()
    resultat[FICHIER_JSON] = texte_json(inv, outil)
    for cle, fichier, _c in TABLES:
        resultat[fichier] = texte_csv(cle, inv.tables[cle])
    return resultat


def avec_bom(texte):
    """Le texte precede d'UN seul BOM, quel que soit son etat d'entree."""
    while texte.startswith(BOM):
        texte = texte[len(BOM):]
    return BOM + texte


def ecrire_texte(chemin, texte):
    """UNE seule ecriture, UTF-8 avec BOM, fins de ligne intactes.

    Pas de codec utf-8-sig : sous IronPython 3, il reecrit le BOM a chaque
    write(). Le BOM est donc ajoute au texte, et le tout ecrit d'un coup."""
    with io.open(chemin, "w", encoding="utf-8", newline="") as f:
        f.write(avec_bom(texte))


def ecrire_sorties(dossier, inv, outil):
    """Ecrit les 19 fichiers dans dossier ; rend leurs chemins."""
    chemins = []
    for fichier, texte in contenus(inv, outil).items():
        chemin = os.path.join(dossier, fichier)
        ecrire_texte(chemin, texte)
        chemins.append(chemin)
    return chemins
