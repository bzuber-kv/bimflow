# -*- coding: utf-8 -*-
"""bimflow_noms - decoupage du nom de famille d'un volume de zone.

Un seul endroit decoupe ce nom, pour que les outils ne puissent pas diverger
sur ce qu'ils lisent : le bouton d'audit, le bouton d'ecriture et le
convertisseur hors Revit appellent tous ce module.

    VOL__<REF_Zone>__<REF_Etage>__<CLS_Nature_volume>
    ex. VOL__JU_Bj-Fj-1j-5j__FLOOR_3__ETAGE

Separateur : DOUBLE underscore. Un underscore SIMPLE appartient au segment
(JU_Bj-Fj-1j-5j, FLOOR_3, ENTRE_TOIT) et ne se decoupe jamais.

QUATRIEME SEGMENT - arbitrage de Bruno du 2026-09-22. Ce n'est plus un
attribut libre : il porte EXACTEMENT la valeur de CLS_Nature_volume, en
majuscules, prise dans la liste fermee du socle. Le nom se recopie donc
dans le parametre sans aucune table de correspondance - et la destination
Ivion s'en deduit, ce qui a fait abandonner le champ CLS_Destination.
La valeur "0" des premiers volumes est desormais HORS MOTIF : c'est voulu,
le bouton RenommerVolumes les renomme.

PYTHON PUR, stdlib seulement, sans aucun import de l'API Revit : ce fichier
tourne sous IronPython 3.4 dans Revit (pyRevit ajoute ce dossier lib\\ au
chemin) ET sous CPython 3 hors Revit (tools/sitemodel/audit_to_zones.py, qui
l'ajoute a sys.path par un chemin relatif). Ne rien y importer qui ne soit
disponible des deux cotes.

bimflow - Keovia Solutions inc. - 2026-09-22
"""

SEPARATEUR = "__"
NB_SEGMENTS = 4
PREFIXE_ATTENDU = "VOL"

# Liste FERMEE de CLS_Nature_volume, telle qu'elle est au socle de
# parametres partages. Le 4e segment du nom porte l'une de ces valeurs, et
# rien d'autre.
NATURES = ("ETAGE", "TOITURE", "ENTRE_TOIT", "EXTERIEUR", "ENVELOPPE")

# Nature des volumes de la premiere campagne, a renommer.
NATURE_A_RENOMMER = "0"

# Ce qui part vers Ivion. ENVELOPPE en est exclue : un volume d'enveloppe
# LOD100 n'est ni un etage ni une toiture, il n'a rien a y faire.
NATURES_EXPORTEES = ("ETAGE", "TOITURE", "ENTRE_TOIT", "EXTERIEUR")

# Etage dont la nature attendue est TOITURE. La redondance entre le 3e et le
# 4e segment n'est pas une faute de conception : c'est un garde-fou, et les
# outils la controlent.
ETAGE_TOITURE = "ROOF"
NATURE_DE_ROOF = "TOITURE"

# Rang des segments, pour que personne n'ecrive segments[1] a la main.
RANG_PREFIXE = 0
RANG_ZONE = 1
RANG_ETAGE = 2
RANG_NATURE = 3


def decouper(nom):
    """(segments ou None, liste de defauts).

    Tolerant : il rend les segments des que leur NOMBRE est bon, et liste a
    cote tout ce qui cloche. C'est ce qu'il faut a un AUDIT, qui decrit sans
    juger."""
    if not nom:
        return None, [u"nom de famille vide"]
    segments = nom.split(SEPARATEUR)
    if len(segments) != NB_SEGMENTS:
        return None, [u"{0} segment(s) au lieu de {1}".format(
            len(segments), NB_SEGMENTS)]
    defauts = []
    if segments[RANG_PREFIXE] != PREFIXE_ATTENDU:
        defauts.append(u"segment 0 = \"{0}\" au lieu de \"{1}\"".format(
            segments[RANG_PREFIXE], PREFIXE_ATTENDU))
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
    return segments, defauts


def lire(nom):
    """((zone, etage, nature), None) ou (None, motif du refus).

    Strict : au moindre defaut il refuse - nature hors liste comprise. C'est
    ce qu'il faut a un outil qui ECRIT, ou qui convertit : un nom douteux ne
    se devine pas."""
    segments, defauts = decouper(nom)
    if segments is None:
        return None, defauts[0]
    if defauts:
        return None, defauts[0]
    return (segments[RANG_ZONE],
            segments[RANG_ETAGE],
            segments[RANG_NATURE]), None


def nature_attendue(etage):
    """Nature deduite du seul etage - sert au RENOMMAGE des volumes "0",
    et au controle de coherence entre 3e et 4e segment."""
    if etage == ETAGE_TOITURE:
        return NATURE_DE_ROOF
    return "ETAGE"


def incoherence_etage_nature(etage, nature):
    """Motif d'incoherence entre etage et nature, ou None.

    Signale, jamais bloquant : c'est la redondance du nom qui sert de
    garde-fou, pas une regle metier."""
    if etage == ETAGE_TOITURE and nature != NATURE_DE_ROOF:
        return (u"etage {0} mais nature {1} - une toiture est attendue "
                u"ici".format(ETAGE_TOITURE, nature))
    if nature == NATURE_DE_ROOF and etage != ETAGE_TOITURE:
        return (u"nature {0} mais etage {1} - une toiture est attendue a "
                u"l'etage {2}".format(NATURE_DE_ROOF, etage, ETAGE_TOITURE))
    return None


def prefixe_de_zone(zone):
    """Prefixe d'une zone : ce qui precede le premier underscore SIMPLE."""
    return zone.split("_")[0]


def batiment_du(zone, table):
    """(batiment, None) ou (None, motif). Un prefixe absent de la table n'est
    JAMAIS devine."""
    prefixe = prefixe_de_zone(zone)
    if prefixe in table:
        return table[prefixe], None
    return None, u"prefixe de zone \"{0}\" absent de la table ({1})".format(
        prefixe, u", ".join(sorted(table.keys())))
