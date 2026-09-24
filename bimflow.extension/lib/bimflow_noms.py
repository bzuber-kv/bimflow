# -*- coding: utf-8 -*-
"""bimflow_noms - decoupage du nom de famille d'un volume de zone.

Un seul endroit decoupe ce nom, pour que les outils ne puissent pas diverger
sur ce qu'ils lisent : les boutons d'audit, de renommage et d'ecriture, et
le convertisseur hors Revit appellent tous ce module.

    VOL_nnn__<REF_Zone>__<REF_Etage>__<CLS_Nature_volume>[__<cle>]
    ex. VOL_007__JU_Bj-Fj-1j-5j__FLOOR_3__ETAGE
        VOL_092__MI_Amg_Emg_1m_3m__ROOF__TOITURE__sup
        VOL_140__SC_Fp_Amg_7m_4p__ROOF__ENTRETOIT__MI

Separateur : DOUBLE underscore. Un underscore SIMPLE appartient au segment
(JU_Bj-Fj-1j-5j, FLOOR_2_Mezzanine) et ne se decoupe jamais.

LES CINQ SEGMENTS (motif etendu le 2026-09-24)
  0  VOL_nnn   numero sequentiel a TROIS chiffres, pose par le bouton
               Renommer volumes. L'ordre n'est pas decoratif : il suit
               l'espace (voir bimflow_volumes).
  1  REF_Zone  forme <BAT>_<xx>_<yy>_<nn>_<mm>, BAT parmi JU MI SC SE EXT.
               Une forme libre (SE_office) est ACCEPTEE : seul le prefixe
               avant le premier underscore simple est exploite.
  2  REF_Etage liste OUVERTE. Vues au 2026-09-24 : BASEMENT, FLOOR_1,
               FLOOR_1_Mezzanine, FLOOR_2, FLOOR_2_Mezzanine, FLOOR_3,
               FLOOR_4, FLOOR_5, ROOF.
  3  CLS_Nature_volume  liste FERMEE : ETAGE, TOITURE, ENTRETOIT,
               EXTERIEUR, ENVELOPPE.
               ENTRETOIT s'ecrit en UN mot (decision Bruno 2026-09-24) ;
               ENTRE_TOIT est retire, aucun volume ne le portait.
  4  cle       OPTIONNEL, parmi sup, JU, MI, SC, SE.
               - cle dans {JU,MI,SC,SE} : elle donne REF_Batiment et
                 SURCHARGE le prefixe de la zone. Mesure du 2026-09-24 :
                 44 volumes portent une telle cle, dont 18 ou elle differe
                 effectivement du prefixe - c'est exactement sa raison
                 d'etre.
               - cle == "sup" : discriminant d'unicite. Elle n'alimente
                 AUCUN parametre, et ne change ni le groupe ni l'etage.

PYTHON PUR, stdlib seulement, sans aucun import de l'API Revit : ce fichier
tourne sous IronPython 3.4 dans Revit (pyRevit ajoute ce dossier lib\\ au
chemin) ET sous CPython 3 hors Revit (tools/), qui l'ajoute a sys.path par
un chemin relatif. Ne rien y importer qui ne soit disponible des deux cotes.

bimflow - Keovia Solutions inc. - 2026-09-22, etendu le 2026-09-24
"""

import re

SEPARATEUR = "__"
NB_SEGMENTS_MINI = 4
NB_SEGMENTS_MAXI = 5

# Segment 0 : VOL_ suivi de TROIS chiffres.
MOTIF_PREFIXE = re.compile(r"^VOL_\d{3}$")
GABARIT_PREFIXE = "VOL_{0:03d}"

# Ancien prefixe, sans numero : les volumes de la premiere campagne le
# portent encore. Ils sont renommes, pas rejetes.
PREFIXE_SANS_NUMERO = "VOL"

# Liste FERMEE de CLS_Nature_volume, telle qu'elle est au socle de
# parametres partages.
NATURES = ("ETAGE", "TOITURE", "ENTRETOIT", "EXTERIEUR", "ENVELOPPE")

# Ce qui part vers Ivion. ENVELOPPE en est exclue : un volume d'enveloppe
# LOD100 n'est ni un etage ni une toiture, il n'a rien a y faire.
NATURES_EXPORTEES = ("ETAGE", "TOITURE", "ENTRETOIT", "EXTERIEUR")

# Valeur portee par les volumes de la toute premiere campagne.
NATURE_A_RENOMMER = "0"

# Cles admises au 5e segment.
CLE_SUP = "sup"
CLES_BATIMENT = ("JU", "MI", "SC", "SE")
CLES = (CLE_SUP,) + CLES_BATIMENT

# Batiments, et leur ordre de parcours : alphabetique, EXT en dernier.
BATIMENTS = ("JU", "MI", "SC", "SE", "EXT")

# Etages connus au 2026-09-24. Liste OUVERTE : elle sert a signaler
# l'inattendu, jamais a rejeter.
ETAGES_CONNUS = ("BASEMENT", "FLOOR_1", "FLOOR_1_Mezzanine", "FLOOR_2",
                 "FLOOR_2_Mezzanine", "FLOOR_3", "FLOOR_4", "FLOOR_5", "ROOF")

# Etage des toitures, et natures qui y sont legitimes. MESURE le 2026-09-24
# sur les 201 volumes : a ROOF, 41 TOITURE et 13 ENTRETOIT - l'entretoit
# EST a l'etage ROOF, et n'est donc pas une anomalie. Un seul volume y
# porte ETAGE, et c'est lui l'anomalie.
ETAGE_TOITURE = "ROOF"
NATURES_DE_ROOF = ("TOITURE", "ENTRETOIT")

# Rang des segments, pour que personne n'ecrive segments[1] a la main.
RANG_PREFIXE = 0
RANG_ZONE = 1
RANG_ETAGE = 2
RANG_NATURE = 3
RANG_CLE = 4


def decouper(nom):
    """(segments ou None, liste de defauts).

    Tolerant : il rend les segments des que leur NOMBRE est bon, et liste a
    cote tout ce qui cloche. C'est ce qu'il faut a un AUDIT, qui decrit sans
    juger."""
    if not nom:
        return None, [u"nom de famille vide"]
    segments = nom.split(SEPARATEUR)
    if not (NB_SEGMENTS_MINI <= len(segments) <= NB_SEGMENTS_MAXI):
        return None, [u"{0} segment(s), attendu {1} ou {2}".format(
            len(segments), NB_SEGMENTS_MINI, NB_SEGMENTS_MAXI)]

    defauts = []
    prefixe = segments[RANG_PREFIXE]
    if not MOTIF_PREFIXE.match(prefixe):
        if prefixe == PREFIXE_SANS_NUMERO:
            defauts.append(
                u"segment 0 = \"{0}\" sans numero : volume de la premiere "
                u"campagne, a renommer (bouton Renommer volumes)".format(
                    prefixe))
        else:
            defauts.append(
                u"segment 0 = \"{0}\" : attendu VOL_nnn, trois chiffres"
                .format(prefixe))

    for rang, segment in enumerate(segments):
        if segment == u"":
            defauts.append(u"segment {0} vide".format(rang))
        elif segment.startswith(u"_") or segment.endswith(u"_"):
            defauts.append(
                u"segment {0} (\"{1}\") commence ou finit par un underscore "
                u"- triple underscore probable".format(rang, segment))
        elif u" " in segment:
            defauts.append(u"segment {0} (\"{1}\") contient un espace".format(
                rang, segment))

    nature = segments[RANG_NATURE]
    if nature == NATURE_A_RENOMMER:
        defauts.append(
            u"segment 3 = \"{0}\" : volume de la premiere campagne, a "
            u"renommer (bouton Renommer volumes)".format(NATURE_A_RENOMMER))
    elif nature and nature not in NATURES:
        defauts.append(
            u"segment 3 (\"{0}\") hors de la liste fermee de "
            u"CLS_Nature_volume ({1})".format(nature, u", ".join(NATURES)))

    if len(segments) > RANG_CLE:
        cle = segments[RANG_CLE]
        if cle not in CLES:
            defauts.append(
                u"segment 4 (\"{0}\") hors des cles admises ({1})".format(
                    cle, u", ".join(CLES)))

    return segments, defauts


def lire(nom):
    """((zone, etage, nature, cle), None) ou (None, motif du refus).

    cle vaut None quand le 5e segment est absent.

    Strict : au moindre defaut il refuse - nature hors liste comprise. C'est
    ce qu'il faut a un outil qui ECRIT, ou qui convertit : un nom douteux ne
    se devine pas."""
    segments, defauts = decouper(nom)
    if segments is None:
        return None, defauts[0]
    if defauts:
        return None, defauts[0]
    cle = segments[RANG_CLE] if len(segments) > RANG_CLE else None
    return (segments[RANG_ZONE],
            segments[RANG_ETAGE],
            segments[RANG_NATURE],
            cle), None


def extraire(nom, corrections=None):
    """Lecture TOLERANTE d'un nom quelconque, pour le renommage.

    ((zone, etage, nature, cle), None) ou (None, motif du refus).

    Elle accepte n'importe quel segment 0 - "VOL", "VOL_007" ou le nom que
    Revit donne d'office a une famille in situ ("Volume 019") - parce que
    c'est justement ce segment que le renommage va refaire. Tout le reste
    est lu STRICTEMENT : une nature hors liste, une cle inconnue ou une
    nature absente ne se devinent pas, elles sortent en NON RESOLU.

    corrections : {nom exact : (zone, etage, nature, cle)}, pour les typos
    releves a la main. Elles sont appliquees AVANT toute analyse, et le
    tableau qui les porte se lit dans le bouton - pas ici."""
    if corrections and nom in corrections:
        return tuple(corrections[nom]), None
    if not nom:
        return None, u"nom de famille vide"

    segments = nom.split(SEPARATEUR)
    utiles = segments[1:]          # le segment 0 sera refait par le renommage
    if len(utiles) < 3:
        return None, (u"{0} segment(s) apres le prefixe, attendu 3 ou 4 - "
                      u"nature manquante ?".format(len(utiles)))
    if len(utiles) > 4:
        return None, u"{0} segment(s) apres le prefixe, attendu 3 ou 4".format(
            len(utiles))

    zone, etage, nature = utiles[0], utiles[1], utiles[2]
    cle = utiles[3] if len(utiles) > 3 else None

    if not zone:
        return None, u"REF_Zone vide"
    if not etage:
        return None, u"REF_Etage vide"
    if nature == NATURE_A_RENOMMER:
        return None, (u"nature \"{0}\" : volume de la premiere campagne, "
                      u"nature a poser a la main".format(NATURE_A_RENOMMER))
    if nature not in NATURES:
        return None, u"nature \"{0}\" hors de la liste fermee ({1})".format(
            nature, u", ".join(NATURES))
    if cle is not None and cle not in CLES:
        return None, u"cle \"{0}\" hors des cles admises ({1})".format(
            cle, u", ".join(CLES))
    return (zone, etage, nature, cle), None


def prefixe_de_zone(zone):
    """Prefixe d'une zone : ce qui precede le premier underscore SIMPLE."""
    return zone.split("_")[0] if zone else ""


def ref_batiment(zone, cle):
    """REF_Batiment : la cle si elle designe un batiment, sinon le prefixe
    de la zone.

    C'est LA regle d'affectation, et elle n'est ecrite qu'ici. La cle
    surcharge le prefixe parce qu'un volume peut appartenir a un batiment
    tout en portant le maillage d'un autre - 18 cas mesures le 2026-09-24."""
    if cle in CLES_BATIMENT:
        return cle
    return prefixe_de_zone(zone)


def nom_de_famille(numero, zone, etage, nature, cle=None):
    """Assemble le nom final. numero est un entier."""
    morceaux = [GABARIT_PREFIXE.format(numero), zone, etage, nature]
    if cle:
        morceaux.append(cle)
    return SEPARATEUR.join(morceaux)


def nature_attendue(etage):
    """Nature deduite du seul etage. Ne sert qu'a proposer une valeur de
    depart : ENTRETOIT, EXTERIEUR et ENVELOPPE ne se devinent pas."""
    if etage == ETAGE_TOITURE:
        return "TOITURE"
    return "ETAGE"


def incoherence_etage_nature(etage, nature):
    """Motif d'incoherence entre etage et nature, ou None.

    Signale, jamais bloquant : c'est la redondance du nom qui sert de
    garde-fou, pas une regle metier. A ROOF, TOITURE et ENTRETOIT sont
    legitimes toutes les deux (mesure du 2026-09-24)."""
    if etage == ETAGE_TOITURE and nature not in NATURES_DE_ROOF:
        return (u"etage {0} mais nature {1} - attendu {2}".format(
            ETAGE_TOITURE, nature, u" ou ".join(NATURES_DE_ROOF)))
    if nature == "TOITURE" and etage != ETAGE_TOITURE:
        return (u"nature TOITURE mais etage {0} - une toiture est attendue "
                u"a l'etage {1}".format(etage, ETAGE_TOITURE))
    return None


def batiment_du(zone, table):
    """(batiment, None) ou (None, motif). Traduit un prefixe en nom complet
    de batiment. Un prefixe absent de la table n'est JAMAIS devine."""
    prefixe = prefixe_de_zone(zone)
    if prefixe in table:
        return table[prefixe], None
    return None, u"prefixe de zone \"{0}\" absent de la table ({1})".format(
        prefixe, u", ".join(sorted(table.keys())))
