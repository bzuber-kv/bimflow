# -*- coding: utf-8 -*-
"""Tests de bimflow_correspondance (logique pure du bouton Renommer selon
table).

Lancement, depuis la racine du depot :
    python -m pytest

Le bouton (script.py) ne s'execute que dans Revit : il n'est ici que relu.
"""

import os
import re
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIB = os.path.join(RACINE, "bimflow.extension", "lib")
BOUTON = os.path.join(RACINE, "bimflow.extension", "bimflow.tab",
                      "Dev.panel", "RenommerSelonTable.pushbutton")
sys.path.insert(0, LIB)

import bimflow_correspondance as C  # noqa: E402

ENTETE = u";".join(C.COLONNES)


def p(valeur, ecrivable=True):
    return {u"valeur": valeur, u"ecrivable": ecrivable}


def modele():
    """Petit modele : 3 niveaux, 4 quadrillages sur 3 types, 3 volumes,
    4 vues."""
    return {
        u"niveaux": {
            10: {u"nom": u"SC_N00", u"params": {u"REF_Batiment": p(u"Senior_Central"),
                                               u"REF_Etage": p(u"BASEMENT")},
                 u"surveillance": None},
            11: {u"nom": u"SC_N01", u"params": {u"REF_Batiment": p(u"Senior_Central"),
                                               u"REF_Etage": p(u"FLOOR_1")},
                 u"surveillance": u"surveille un element d'un lien"},
            12: {u"nom": u"EXT_BLVD", u"params": {u"REF_Batiment": p(u"Site")},
                 u"surveillance": None},
        },
        u"types_quadrillage": {100: u"Senior Central - L", 101: u"Senior parking - L",
                               102: u"Middle - L"},
        u"quadrillages": {
            20: {u"nom": u"1c", u"type_id": 100, u"surveillance": None},
            21: {u"nom": u"Gp", u"type_id": 100, u"surveillance": None},
            22: {u"nom": u"1p", u"type_id": 101, u"surveillance": None},
            23: {u"nom": u"m.1", u"type_id": 102, u"surveillance": None},
        },
        u"familles": {900: u"VOL_001__SC_Bc_Cc_1c_9m__FLOOR_1__ETAGE__SC",
                      901: u"VOL_002__SC_Bc_Cc_1c_9m__FLOOR_2_Mezzanine__ETAGE__SC",
                      902: u"VOL_003__SC_Bc_Cc_1c_9m__ROOF__TOITURE",
                      903: u"Autre famille"},
        u"volumes": {
            30: {u"famille": u"VOL_001__SC_Bc_Cc_1c_9m__FLOOR_1__ETAGE__SC",
                 u"famille_id": 900, u"in_situ": True,
                 u"params": {u"REF_Zone": p(u"SC_Bc_Cc_1c_9m"),
                             u"REF_Etage": p(u"FLOOR_1"),
                             u"REF_Batiment": p(u"Senior_Central"),
                             u"REF_Id": p(u"aaaa")}},
            31: {u"famille": u"VOL_002__SC_Bc_Cc_1c_9m__FLOOR_2_Mezzanine__ETAGE__SC",
                 u"famille_id": 901, u"in_situ": True,
                 u"params": {u"REF_Zone": p(u"SC_Bc_Cc_1c_9m"),
                             u"REF_Etage": p(u"FLOOR_2_Mezzanine"),
                             u"REF_Batiment": p(u"Senior_Central"),
                             u"REF_Id": p(u"bbbb")}},
            32: {u"famille": u"VOL_003__SC_Bc_Cc_1c_9m__ROOF__TOITURE",
                 u"famille_id": 902, u"in_situ": True,
                 u"params": {u"REF_Zone": p(u"SC_Bc_Cc_1c_9m"),
                             u"REF_Etage": p(u"ROOF"),
                             u"REF_Batiment": p(u"Senior_Central"),
                             u"REF_Id": p(u"BBBB ")}},
        },
        u"vues": {
            40: {u"nom": u"Plan SC_N00", u"gabarit": False},
            41: {u"nom": u"SC_N01_Coupe", u"gabarit": False},
            42: {u"nom": u"XSC_N00 essai", u"gabarit": False},
            43: {u"nom": u"Gabarit SC_N00", u"gabarit": True},
        },
        u"autres": {77: u"Murs"},
    }


TABLE = u"\n".join([
    ENTETE,
    u"niveau;10;SC_N00;KD_N00;REF_Batiment;Senior_Central;KD;validé;",
    u"niveau;11;SC_N01;KD_N01;REF_Batiment;Senior_Central;KD;validé;",
    u"niveau;12;EXT_BLVD;EXT_BLVD;REF_Batiment;Site;EXT;validé;",
    u"quadrillage;20;1c;1c;type;Senior Central - L;KC - L;validé;",
    u"quadrillage;21;Gp;Gd;type;Senior Central - L;KD - L;validé;",
    u"quadrillage;22;1p;1d;type;Senior parking - L;KD - L;validé;",
    u"quadrillage;23;m.1;1b;type;Middle - L;KB - L;validé;",
    u"zone (REF_Zone);;SC_Bc_Cc_1c_9m;KC_Bc-Cc-1c-9b;REF_Batiment;x;KC;validé;",
    u"volume;30;VOL_001__SC_Bc_Cc_1c_9m__FLOOR_1__ETAGE__SC;"
    u"VOL_001__KC_Bc-Cc-1c-9b__FLOOR_1__ETAGE;REF_Batiment / REF_Etage;"
    u"Senior_Central / FLOOR_1;KC / FLOOR_1;validé;",
    u"volume;31;VOL_002__SC_Bc_Cc_1c_9m__FLOOR_2_Mezzanine__ETAGE__SC;"
    u"VOL_002__KC_Bc-Cc-1c-9b__FLOOR_2__ETAGE__mez;REF_Batiment / REF_Etage;"
    u"Senior_Central / FLOOR_2_Mezzanine;KC / FLOOR_2;validé;",
    u"volume;32;VOL_003__SC_Bc_Cc_1c_9m__ROOF__TOITURE;"
    u"VOL_003__KC_Bc-Cc-1c-9b__ROOF__TOITURE;REF_Batiment / REF_Etage;"
    u"Senior_Central / ROOF;KC / ROOF;validé;REF_Id à régénérer (doublon)",
    u"volume;5532336;Volume 1;;;;;hors périmètre;",
    u"volume;99999;VOL_X;VOL_Y;;;;validé;",
]) + u"\n"


def analyse(table=TABLE, m=None):
    lignes, erreurs, _ = C.lire_table(table.encode("utf-8"))
    assert erreurs == []
    return C.analyser(lignes, m or modele())


def par_ligne(a, numero):
    return [r for r in a.resultats if r.numero == numero][0]


# --- lecture -----------------------------------------------------------------

def test_entete_inattendu_refuse_tout():
    lignes, erreurs, _ = C.lire_table(u"a;b\n1;2\n".encode("utf-8"))
    assert lignes == [] and u"en-tete inattendu" in erreurs[0]


def test_bom_et_cp1252():
    texte = (u"﻿" + TABLE).encode("utf-8")
    lignes, erreurs, enc = C.lire_table(texte)
    assert erreurs == [] and enc == u"utf-8" and len(lignes) == 13
    lignes, erreurs, enc = C.lire_table(TABLE.encode("cp1252"))
    assert enc == u"cp1252" and lignes[0][u"statut"] == u"validé"


def test_categorie_zone():
    assert C.categorie_de(u"zone (REF_Zone)") == C.ZONE
    assert C.categorie_de(u"Niveau ") == C.NIVEAU
    assert C.categorie_de(u"mur") is None


# --- controle d'entree ---------------------------------------------------------

def test_cas_nominal_aucun_refus():
    a = analyse()
    assert [r.motifs for r in a.refus()] == []


def test_nom_ancien_different_refuse():
    m = modele()
    m[u"niveaux"][10][u"nom"] = u"SC_N00 "
    a = analyse(m=m)
    r = par_ligne(a, 2)
    assert r.verdict == C.REFUSEE and u"porte" in r.motifs[0]
    assert 10 not in a.renommages[u"niveaux"]
    assert not [x for x in a.parametres if x[0] == 10]


def test_ancienne_valeur_differente_refuse():
    m = modele()
    m[u"niveaux"][10][u"params"][u"REF_Batiment"] = p(u"Junior")
    assert par_ligne(analyse(m=m), 2).verdict == C.REFUSEE


def test_element_absent_sans_objet_autre_categorie_refuse():
    a = analyse()
    assert par_ligne(a, 14).verdict == C.SANS_OBJET      # 99999
    t = TABLE.replace(u"volume;99999", u"volume;77")
    assert par_ligne(analyse(t), 14).verdict == C.REFUSEE


def test_statut_non_valide_et_zone_sans_objet():
    a = analyse()
    assert par_ligne(a, 13).verdict == C.SANS_OBJET
    assert par_ligne(a, 9).verdict == C.SANS_OBJET


def test_id_en_double_refuse():
    t = TABLE + u"niveau;10;SC_N00;KD_N00;;;;validé;\n"
    a = analyse(t)
    assert a.resultats[-1].verdict == C.REFUSEE


def test_caractere_interdit_refuse():
    t = TABLE.replace(u"KD_N00;REF", u"KD~N00;REF")
    assert par_ligne(analyse(t), 2).verdict == C.REFUSEE


# --- niveaux et vues -----------------------------------------------------------

def test_niveaux_plan():
    a = analyse()
    assert a.renommages[u"niveaux"] == {10: (u"SC_N00", u"KD_N00"),
                                        11: (u"SC_N01", u"KD_N01")}
    assert (12, u"REF_Batiment", u"Site", u"EXT") in a.parametres
    assert par_ligne(a, 4).verdict == C.APPLIQUEE    # EXT_BLVD : parametre seul


def test_copier_controler_signale():
    a = analyse()
    assert any(u"Copier/Controler" in x and u"SC_N01" in x
               for x in a.avertissements)


def test_vues_bornes_et_gabarits():
    a = analyse()
    assert a.renommages[u"vues"] == {40: (u"Plan SC_N00", u"Plan KD_N00"),
                                     41: (u"SC_N01_Coupe", u"KD_N01_Coupe")}
    gab = [r for r in a.vues if r.id_revit == 43][0]
    assert gab.verdict == C.SANS_OBJET
    assert not [r for r in a.vues if r.id_revit == 42]


def test_vue_chevauchement_refuse():
    nom, refus = C.nouveau_nom_de_vue(u"A_B_C", {u"A_B": u"x", u"B_C": u"y"})
    assert nom is None and u"chevauchent" in refus
    nom, refus = C.nouveau_nom_de_vue(u"A_B et B_C", {u"A_B": u"x", u"B_C": u"y"})
    assert nom == u"x et y" and refus is None


def test_collision_nom_final_vue():
    m = modele()
    m[u"vues"][44] = {u"nom": u"Plan KD_N00", u"gabarit": False}
    a = analyse(m=m)
    assert [r for r in a.vues if r.id_revit == 40][0].verdict == C.REFUSEE
    assert 40 not in a.renommages[u"vues"]


def test_permutation_admise_par_deux_passes():
    m = modele()
    m[u"niveaux"][11][u"nom"] = u"KD_N00"
    t = TABLE.replace(u"niveau;11;SC_N01;KD_N01", u"niveau;11;KD_N00;SC_N00")
    t = t.replace(u"niveau;10;SC_N00;KD_N00", u"niveau;10;SC_N00;KD_N00")
    a = analyse(t, m)
    assert par_ligne(a, 2).verdict == C.APPLIQUEE
    assert par_ligne(a, 3).verdict == C.APPLIQUEE


def test_nom_temporaire_pris_refuse():
    m = modele()
    m[u"niveaux"][13] = {u"nom": u"TMP_10", u"params": {}, u"surveillance": None}
    assert par_ligne(analyse(m=m), 2).verdict == C.REFUSEE


# --- quadrillages --------------------------------------------------------------

def test_types_renommes_et_changement_de_type():
    a = analyse()
    assert a.renommages[u"types_quadrillage"] == {
        100: (u"Senior Central - L", u"KC - L"),
        101: (u"Senior parking - L", u"KD - L"),
        102: (u"Middle - L", u"KB - L")}
    assert a.retypages == {21: (100, 101)}
    assert a.renommages[u"quadrillages"] == {21: (u"Gp", u"Gd"),
                                             22: (u"1p", u"1d"),
                                             23: (u"m.1", u"1b")}
    assert par_ligne(a, 5).verdict == C.APPLIQUEE    # 1c : type renomme


def test_type_ancien_different_refuse():
    t = TABLE.replace(u"1p;1d;type;Senior parking - L", u"1p;1d;type;Autre")
    assert par_ligne(analyse(t), 7).verdict == C.REFUSEE


def test_deux_types_meme_cible_refuse():
    t = TABLE.replace(u"Middle - L;KB - L", u"Middle - L;KD - L")
    a = analyse(t)
    assert par_ligne(a, 8).verdict == C.REFUSEE
    assert par_ligne(a, 7).verdict == C.REFUSEE


def test_cibles_multiples_non_resolues_refuse():
    t = TABLE.replace(u"Gp;Gd;type;Senior Central - L;KD - L",
                      u"Gp;Gd;type;Senior Central - L;KZ - L")
    a = analyse(t)
    assert par_ligne(a, 5).verdict == C.REFUSEE
    assert par_ligne(a, 6).verdict == C.REFUSEE


def test_type_partage_hors_table_signale():
    m = modele()
    m[u"quadrillages"][24] = {u"nom": u"9z", u"type_id": 102,
                              u"surveillance": u"surveille"}
    a = analyse(m=m)
    assert any(u"hors table" in x and u"24" in x for x in a.avertissements)


# --- volumes -------------------------------------------------------------------

def test_volumes_parametres_recalcules():
    a = analyse()
    ecr = dict(((i, n), v) for i, n, av, v in a.parametres)
    assert ecr[(30, u"REF_Zone")] == u"KC_Bc-Cc-1c-9b"
    assert ecr[(30, u"REF_Batiment")] == u"KC"
    assert (30, u"REF_Etage") not in ecr                 # deja FLOOR_1
    assert ecr[(31, u"REF_Etage")] == u"FLOOR_2"         # mezzanine
    assert a.renommages[u"familles"][901][1].endswith(u"__mez")


def test_ref_id_jamais_ecrit_sans_demande():
    a = analyse()
    ids = [x[0] for x in a.parametres if x[1] == u"REF_Id"]
    assert ids == [32]


def test_ref_id_sans_doublon_refuse():
    m = modele()
    m[u"volumes"][31][u"params"][u"REF_Id"] = p(u"cccc")
    r = par_ligne(analyse(m=m), 12)
    assert r.verdict == C.REFUSEE and u"doublon" in r.motifs[0]


def test_table_et_nom_divergent_refuse():
    t = TABLE.replace(u"KC / FLOOR_1;validé", u"KD / FLOOR_1;validé")
    r = par_ligne(analyse(t), 10)
    assert r.verdict == C.REFUSEE and u"nouveau nom donne" in r.motifs[0]


def test_table_des_zones_controle():
    t = TABLE.replace(u";KC_Bc-Cc-1c-9b;REF_Batiment;x", u";KC_Bc-Cc-1c-9z;REF_Batiment;x")
    assert par_ligne(analyse(t), 10).verdict == C.REFUSEE


def test_cle_de_batiment_refusee_dans_un_nouveau_nom():
    t = TABLE.replace(u"VOL_001__KC_Bc-Cc-1c-9b__FLOOR_1__ETAGE;",
                      u"VOL_001__KC_Bc-Cc-1c-9b__FLOOR_1__ETAGE__SC;")
    assert par_ligne(analyse(t), 10).verdict == C.REFUSEE


def test_comptes_et_rapport():
    a = analyse()
    c = a.comptes()
    assert c[C.NIVEAU][C.APPLIQUEE] == 3
    assert c[C.VOLUME] == {C.APPLIQUEE: 3, C.REFUSEE: 0, C.SANS_OBJET: 2}
    assert c[C.VUE][C.APPLIQUEE] == 2
    d = C.rapport(a, {u"mode": u"simulation"})
    assert d[u"refusees"] == [] and d[u"ordre_conseille"]


def test_nom_rapport_distingue_simulation_et_reel():
    s = C.nom_rapport(u"t.csv", u"thestudy G", u"2026-10-13_1200", u"simulation")
    r = C.nom_rapport(u"t.csv", u"thestudy G", u"2026-10-13_1200", u"reel")
    assert s == u"t_rapport_thestudy_G_2026-10-13_1200_simulation.json"
    assert s != r


# --- le script du bouton, relu ---------------------------------------------------

def _script():
    with open(os.path.join(BOUTON, "script.py"), encoding="utf-8") as f:
        return f.read()


def test_script_sans_exit_apres_ecriture():
    texte = _script()
    premier_commit = texte.find(u".Commit()")
    assert premier_commit > 0
    assert u"script.exit()" not in texte[premier_commit:]
    assert u"exitscript=True" not in texte[premier_commit:]


def test_script_sans_guid_en_dur_ni_tilde_temporaire():
    texte = _script()
    assert not re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-", texte)
    assert u"~TMP" not in texte


def test_id_entier_sans_exception():
    assert C.id_entier(u"") is None and C.id_entier(None) is None
    assert C.id_entier(u" 5526199 ") == 5526199 and C.id_entier(u"12a") is None


def test_aucun_try_dans_une_boucle_du_script():
    """IronPython interprete : un try/except place directement dans une
    boucle empile ses gestionnaires (crash Revit du 2026-10-13)."""
    import ast
    arbre = ast.parse(_script())
    for boucle in ast.walk(arbre):
        if isinstance(boucle, (ast.For, ast.While)):
            for noeud in ast.walk(boucle):
                assert not isinstance(noeud, ast.Try), (
                    u"try/except directement dans une boucle, ligne {0}"
                    .format(noeud.lineno))


def test_bouton_a_son_icone():
    assert os.path.exists(os.path.join(BOUTON, "icon.png"))
