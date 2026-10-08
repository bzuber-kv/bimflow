# -*- coding: utf-8 -*-
"""Tests de bimflow_sous_projets (logique pure du bouton Table sous-projets).

Lancement, depuis la racine du depot :
    python -m pytest

Le bouton (script.py) ne s'execute que dans Revit : il n'est ici que relu.
"""

import io
import os
import re
import sys

import pytest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIB = os.path.join(RACINE, "bimflow.extension", "lib")
BOUTON = os.path.join(RACINE, "bimflow.extension", "bimflow.tab",
                      "Dev.panel", "TableSousProjets.pushbutton")
FIXTURES = os.path.join(RACINE, "tests", "fixtures", "sous_projets")
sys.path.insert(0, LIB)

import bimflow_sous_projets as S  # noqa: E402

ENTETE = u"Action;Nom_actuel;Nouveau_nom;Nb_elements;Proprietaire\r\n"

MODELE = {
    u"A_Menuiseries": {u"proprietaire": u"", u"editable": True},
    u"A_Sol": {u"proprietaire": u"", u"editable": True},
    u"ZW_Défaut": {u"proprietaire": u"", u"editable": True},
    u"Sous-projet 1": {u"proprietaire": u"", u"editable": True},
    u"Vues, niveaux et grilles partagés": {u"proprietaire": u"",
                                               u"editable": True},
    u"C_Chaud": {u"proprietaire": u"tony", u"editable": False},
    u"C_Froid": {u"proprietaire": u"bruno", u"editable": True},
    u"PB_EU": {u"proprietaire": u"", u"editable": False},
}


def table(*lignes):
    return ENTETE + u"".join(l + u"\r\n" for l in lignes)


def valider(texte, utilisateur=u"Bruno"):
    lignes, constats = S.lire_table(texte)
    if not S.bloquant(constats):
        constats = constats + S.valider(lignes, MODELE, utilisateur)
    return lignes, constats


def messages(constats, niveau):
    return [c.message for c in constats if c.niveau == niveau]


# ---------------------------------------------------------------------------
# CSV : export, ecriture, lecture
# ---------------------------------------------------------------------------

def test_export_garder_trie_et_echappe():
    texte = S.texte_export([
        {u"nom": u"b;x", u"nb_elements": 3, u"proprietaire": u""},
        {u"nom": u"A_Sol", u"nb_elements": u"NON_LU", u"proprietaire": u"tony"},
    ])
    assert texte == (ENTETE + u"GARDER;A_Sol;;NON_LU;tony\r\n"
                     u'GARDER;"b;x";;3;\r\n')


def test_ecriture_bom_unique_puis_relecture(tmp_path):
    chemin = str(tmp_path / "t.csv")
    texte = S.texte_export([{u"nom": u"ZW_Défaut", u"nb_elements": 1,
                             u"proprietaire": u""}])
    S.ecrire_texte(chemin, S.BOM + texte)
    with open(chemin, "rb") as f:
        brut = f.read()
    assert brut.count(b"\xef\xbb\xbf") == 1 and brut.startswith(b"\xef\xbb\xbf")
    relu, encodage = S.decoder(brut)
    assert encodage == u"utf-8" and relu == texte
    lignes, constats = S.lire_table(relu)
    assert constats == []
    assert lignes[0][u"nom_actuel"] == u"ZW_Défaut"


def test_decoder_cp1252_excel():
    octets = table(u"RENOMMER;ZW_Défaut;ZW_Defaut;;").encode("cp1252")
    texte, encodage = S.decoder(octets)
    assert encodage == u"cp1252"
    assert u"ZW_Défaut" in texte


def test_lire_csv_guillemets_et_lf():
    assert S.lire_csv(u'a;"b;c";"d ""e"""\n\nx;"y\nz";\n') == [
        [u"a", u"b;c", u'd "e"'], [u"x", u"y\nz", u""]]


def test_fixture_table_editee_valide():
    with open(os.path.join(FIXTURES, "table_editee.csv"), "rb") as f:
        texte, _enc = S.decoder(f.read())
    lignes, constats = valider(texte)
    assert not S.bloquant(constats)
    assert [l[u"action"] for l in lignes] == [
        u"GARDER", u"RENOMMER", u"RENOMMER", u"CREER", u"GARDER"]
    plan = S.plan(lignes)
    assert [(o[u"action"], o[u"nouveau_nom"]) for o in plan] == [
        (u"CREER", u"STRU_Fondations"), (u"RENOMMER", u"A_Sols"),
        (u"RENOMMER", u"ZW_Defaut")]


# ---------------------------------------------------------------------------
# Lignes mal formees
# ---------------------------------------------------------------------------

def test_entete_inattendu_bloque():
    _l, constats = valider(u"Action;Nom\r\nGARDER;A_Sol\r\n")
    assert S.bloquant(constats)
    assert u"en-tete inattendu" in constats[0].message


def test_fichier_vide_bloque():
    assert S.bloquant(valider(u"")[1])


@pytest.mark.parametrize("ligne, attendu", [
    (u"GARDER;A_Sol;;", u"4 colonne(s) au lieu de 5"),
    (u"VIDER;A_Sol;STRU;;", u"action \"VIDER\" inconnue"),
    (u"SUPPRIMER;A_Sol;;;", u"action \"SUPPRIMER\" inconnue"),
    (u"GARDER;;;;", u"GARDER sans Nom_actuel"),
    (u"GARDER;A_Sol;A_Sols;;", u"ecrire RENOMMER pour renommer"),
    (u"RENOMMER;A_Sol;;;", u"RENOMMER exige Nom_actuel ET Nouveau_nom"),
    (u"CREER;A_Sol;STRU;;", u"CREER ne prend que Nouveau_nom"),
    (u"CREER;;;;", u"CREER sans Nouveau_nom"),
    (u"CREER;;A{b};;", u"caractere(s) refuse(s) par Revit : { }"),
])
def test_ligne_mal_formee_bloque(ligne, attendu):
    _l, constats = valider(table(ligne))
    assert S.bloquant(constats)
    assert any(attendu in m for m in messages(constats, S.ERREUR)), \
        messages(constats, S.ERREUR)


def test_action_en_minuscules_acceptee():
    lignes, constats = valider(table(u"renommer;A_Sol;A_Sols;;"))
    assert not S.bloquant(constats)
    assert lignes[0][u"action"] == u"RENOMMER"


# ---------------------------------------------------------------------------
# Validation contre le modele
# ---------------------------------------------------------------------------

def test_source_absente_bloque_et_signale_la_casse():
    _l, constats = valider(table(u"RENOMMER;a_sol;A_Sols;;",
                                 u"GARDER;Inconnu;;;"))
    erreurs = messages(constats, S.ERREUR)
    assert any(u"\"a_sol\" absente du modele (casse differente : A_Sol)" in m
               for m in erreurs)
    assert any(u"\"Inconnu\" absente du modele" in m for m in erreurs)


def test_cible_existante_bloque():
    _l, constats = valider(table(u"RENOMMER;A_Sol;A_Menuiseries;;"))
    assert any(u"cible \"A_Menuiseries\" deja existante" in m
               for m in messages(constats, S.ERREUR))


def test_cible_deux_fois_bloque():
    _l, constats = valider(table(u"RENOMMER;A_Sol;STRU;;", u"CREER;;STRU;;"))
    assert any(u"presente deux fois dans la table (ligne 2)" in m
               for m in messages(constats, S.ERREUR))


def test_source_deux_fois_bloque():
    _l, constats = valider(table(u"GARDER;A_Sol;;;",
                                 u"RENOMMER;A_Sol;A_Sols;;"))
    assert any(u"source \"A_Sol\" deja traitee ligne 2" in m
               for m in messages(constats, S.ERREUR))


def test_permutation_refusee():
    """A -> B et B -> A : la cible existe au moment de la validation."""
    _l, constats = valider(table(u"RENOMMER;A_Sol;A_Menuiseries;;",
                                 u"RENOMMER;A_Menuiseries;A_Sol;;"))
    assert len(messages(constats, S.ERREUR)) == 2


def test_emprunte_par_un_autre_bloque():
    _l, constats = valider(table(u"RENOMMER;C_Chaud;M_CH;;"))
    assert any(u"\"C_Chaud\" est emprunte par tony" in m
               for m in messages(constats, S.ERREUR))


def test_emprunte_par_soi_passe_casse_ignoree():
    _l, constats = valider(table(u"RENOMMER;C_Froid;M_CH;;"),
                           utilisateur=u"BRUNO")
    assert not S.bloquant(constats)


def test_non_emprunte_avertit():
    _l, constats = valider(table(u"RENOMMER;PB_EU;M_PL;;"))
    assert not S.bloquant(constats)
    assert any(u"emprunt implicite attendu, non verifie" in m
               for m in messages(constats, S.AVERTISSEMENT))


def test_garder_un_sous_projet_emprunte_passe():
    _l, constats = valider(table(u"GARDER;C_Chaud;;;"))
    assert not S.bloquant(constats)


# ---------------------------------------------------------------------------
# Avertissements non bloquants
# ---------------------------------------------------------------------------

def test_ascii_sans_espace():
    _l, constats = valider(table(u"CREER;;Nuages de points;;",
                                 u"CREER;;Pièces;;"))
    assert not S.bloquant(constats)
    avert = messages(constats, S.AVERTISSEMENT)
    assert any(u"\"Nuages de points\" n'est pas en ASCII" in m for m in avert)
    assert any(u"\"Pièces\" n'est pas en ASCII" in m for m in avert)


def test_sous_projets_imposes():
    _l, constats = valider(table(
        u"RENOMMER;Sous-projet 1;ZW_Defaut_Revit;;",
        u"RENOMMER;Vues, niveaux et grilles partagés;ZG_Partages;;"))
    avert = messages(constats, S.AVERTISSEMENT)
    assert any(u"\"Sous-projet 1\"" in m and u"R14" in m for m in avert)
    assert any(u"\"Vues, niveaux et grilles partagés\"" in m
               for m in avert)
    assert not S.bloquant(constats)


def test_garder_un_impose_ne_l_avertit_pas():
    _l, constats = valider(table(u"GARDER;Sous-projet 1;;;"))
    assert not any(u"R14" in m for m in messages(constats, S.AVERTISSEMENT))


def test_espaces_de_bord_avertis():
    lignes, constats = valider(table(u"RENOMMER; A_Sol ;A_Sols;;"))
    assert lignes[0][u"nom_actuel"] == u"A_Sol"
    assert any(u"espaces en bord" in m
               for m in messages(constats, S.AVERTISSEMENT))


def test_renommer_vers_le_meme_nom_sans_effet():
    lignes, constats = valider(table(u"RENOMMER;A_Sol;A_Sol;;"))
    assert not S.bloquant(constats)
    assert S.plan(lignes) == []


def test_absents_de_la_table_listes():
    _l, constats = valider(table(u"GARDER;A_Sol;;;"))
    assert any(u"absent(s) de la table" in m
               for m in messages(constats, S.AVERTISSEMENT))


def test_casse_proche_avertie():
    _l, constats = valider(table(u"CREER;;a_menuiseries;;"))
    assert any(u"ne differe que par la casse de A_Menuiseries" in m
               for m in messages(constats, S.AVERTISSEMENT))


# ---------------------------------------------------------------------------
# Controle apres ecriture
# ---------------------------------------------------------------------------

def test_ecarts_apres():
    lignes, _c = S.lire_table(table(u"RENOMMER;A_Sol;A_Sols;;",
                                    u"CREER;;STRU;;"))
    operations = S.plan(lignes)
    assert S.ecarts_apres(operations, [u"A_Sols", u"STRU"]) == []
    ecarts = S.ecarts_apres(operations, [u"A_Sol", u"STRU"])
    assert ecarts == [u"ligne 2 : \"A_Sols\" absent apres ecriture",
                      u"ligne 2 : \"A_Sol\" encore present apres renommage"]


# ---------------------------------------------------------------------------
# Relecture statique
# ---------------------------------------------------------------------------

def _lire(chemin):
    with io.open(chemin, encoding="utf-8") as f:
        return f.read()


def test_lib_pure():
    source = _lire(os.path.join(LIB, "bimflow_sous_projets.py"))
    imports = re.findall(r"^\s*(?:import|from)\s+([\w.]+)", source, re.M)
    for interdit in ("Autodesk", "clr", "pyrevit", "System"):
        assert not [i for i in imports if i.split(".")[0] == interdit]


def test_bouton_ne_deplace_ni_ne_supprime():
    source = _lire(os.path.join(BOUTON, "script.py"))
    for interdit in ("DeleteWorkset", "ELEM_PARTITION_PARAM", "CheckoutElements",
                     "CheckoutWorksets", "SynchronizeWithCentral", ".IntegerValue",
                     "TransactionGroup", "#! python3"):
        assert interdit not in source, interdit
    assert source.count(u"Transaction(doc") == 1


def test_aucune_sortie_apres_ecriture():
    """docs\\ecrire_dans_revit.md §1 : script.exit() apres t.Start() fait
    tout annuler par Revit."""
    source = _lire(os.path.join(BOUTON, "script.py"))
    apres = source.split(u"t.Start()", 1)[1]
    assert u"script.exit(" not in apres
    assert u"exitscript=True" not in apres


@pytest.mark.parametrize("chemin", [
    os.path.join(LIB, "bimflow_sous_projets.py"),
    os.path.join(BOUTON, "script.py"),
])
def test_vocabulaire(chemin):
    source = _lire(chemin).lower()
    for mot in (u"supprimable", u"inutile", u"en trop"):
        assert mot not in source, mot


def test_bundle_complet():
    assert os.path.isfile(os.path.join(BOUTON, "icon.png"))
    source = _lire(os.path.join(BOUTON, "script.py"))
    assert re.search(r'^__title__\s*=', source, re.M)
    assert all(ord(c) < 128 for c in os.path.basename(BOUTON))
