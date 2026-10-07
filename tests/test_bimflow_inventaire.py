# -*- coding: utf-8 -*-
"""Tests de bimflow_inventaire (logique pure du bouton Inventaire systemes).

Lancement, depuis la racine du depot :
    python -m pytest

La lib vise IronPython 3.4 dans Revit ; ces tests l'exercent sous CPython 3.
Le bouton lui-meme (script.py) ne s'execute que dans Revit : il n'est ici
que relu, pour les interdits du lecture seule.
"""

import datetime
import io
import json
import os
import re
import sys

import pytest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIB = os.path.join(RACINE, "bimflow.extension", "lib")
BOUTON = os.path.join(RACINE, "bimflow.extension", "bimflow.tab",
                      "Conformite.panel", "InventaireSystemes.pushbutton")
FIXTURES = os.path.join(RACINE, "tests", "fixtures", "inventaire")
sys.path.insert(0, LIB)

import bimflow_inventaire as inv_lib  # noqa: E402


def fixture(nom):
    with io.open(os.path.join(FIXTURES, nom), encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Code de nom et coherence nom / abreviation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("nom, attendu", [
    (u"EF_01", u"EF"),
    (u"EF 01", u"EF"),
    (u"EF-01", u"EF"),
    (u"ECA", u"ECA"),
    (u"  SOU_Nord", u"SOU"),
    (u"_EF", u""),
    (u"", u""),
    (None, u""),
    (u"NON_LU", u""),
    (u"Évent_2", u"Évent"),
])
def test_code_nom(nom, attendu):
    assert inv_lib.code_nom(nom) == attendu


@pytest.mark.parametrize("code, abrev, attendu", [
    (u"EF", u"EF", u"OUI"),
    (u"ef", u"EF", u"OUI"),               # casse
    (u"ÉV", u"EV", u"OUI"),          # accent
    (u"evac", u"ÉVAC", u"OUI"),
    (u"ECA", u"EF", u"NON"),
    (u"EF", u"", u"INDETERMINE"),         # abreviation vide
    (u"EF", u"   ", u"INDETERMINE"),
    (u"", u"EF", u"INDETERMINE"),
    (u"EF", None, u"INDETERMINE"),
    (u"EF", u"NON_LU", u"INDETERMINE"),
])
def test_code_coherent(code, abrev, attendu):
    assert inv_lib.code_coherent(code, abrev) == attendu


def test_normaliser():
    assert inv_lib.normaliser(u"  Eau  froide   domestique ") == \
        u"EAU FROIDE DOMESTIQUE"
    assert inv_lib.normaliser(u"œuvre évent") == u"OEUVRE EVENT"
    assert inv_lib.normaliser(None) == u""


def test_sans_accents_repli_identique():
    """Le repli (unicodedata absent) donne le meme resultat sur le francais."""
    texte = u"éèêëàâîïôùûüÿçÉÀ"
    assert inv_lib._sans_accents_repli(texte) == inv_lib.sans_accents(texte)


def test_note_parametre_partage():
    assert inv_lib.note_parametre_partage(u"IfcGUID") == u"EXPORTATEUR_IFC"
    assert inv_lib.note_parametre_partage(u"Exporter au format IFC") == \
        u"EXPORTATEUR_IFC"
    assert inv_lib.note_parametre_partage(
        u"Type prédéfini d’IFC") == u"EXPORTATEUR_IFC"
    assert inv_lib.note_parametre_partage(u"REF_Batiment") == u""


def test_identifiant_court():
    assert inv_lib.identifiant_court(u"autodesk.spec.aec:length-2.0.0") == \
        u"length"
    assert inv_lib.identifiant_court(u"autodesk.spec:spec.string-2.0.0") == \
        u"string"
    assert inv_lib.identifiant_court(
        u"autodesk.parameter.group:identityData-1.0.0") == u"identityData"
    assert inv_lib.identifiant_court(u"") == u""
    assert inv_lib.identifiant_court(u"NON_LU") == u"NON_LU"


@pytest.mark.parametrize("args, attendu", [
    ((True, False, False, None), u"INTEGRE"),
    ((False, True, False, None), u"PARTAGE"),
    ((False, False, True, None), u"PROJET"),
    ((False, False, False, None), u"FAMILLE"),
    ((False, False, True, True), u"PROJET"),
    ((False, False, False, False), u"FAMILLE"),
    ((False, False, True, False), u"INDETERMINE"),   # homonyme d'un parametre de projet
    ((False, False, False, True), u"INDETERMINE"),
    ((None, False, False, None), u"INDETERMINE"),
    ((False, None, False, None), u"INDETERMINE"),
    ((False, False, None, None), u"INDETERMINE"),
])
def test_origine_parametre(args, attendu):
    assert inv_lib.origine_parametre(*args) == attendu


def test_couleur():
    assert inv_lib.couleur(0, 127, 250, True) == {
        u"rvb": u"0 127 250", u"hex": u"#007FFA", u"remplace": u"OUI"}
    assert inv_lib.couleur(0, 0, 0, False) == {
        u"rvb": u"", u"hex": u"", u"remplace": u"NON"}


def test_nom_dossier_sortie():
    quand = datetime.datetime(2026, 10, 7, 14, 5)
    assert inv_lib.nom_dossier_sortie(u"thestudy_CO_EQU", quand) == \
        u"inventaire_thestudy_CO_EQU_20261007_1405"
    assert inv_lib.nom_dossier_sortie(u"a:b/c?.rvt", quand) == \
        u"inventaire_a_b_c__20261007_1405"
    assert inv_lib.nom_dossier_sortie(u"", quand) == \
        u"inventaire_maquette_20261007_1405"


def test_identifiants_sources():
    assert inv_lib.identifiants_sources([u"A", u"B", u"A", u""]) == \
        [u"A", u"B", u"A #2", u"(sans titre)"]


# ---------------------------------------------------------------------------
# Taux de remplissage
# ---------------------------------------------------------------------------

def test_remplissage_vide_tiret_valeur():
    r = inv_lib.Remplissage()
    for v in [None, u"", u"   ", u"-", u" - ", u"A", u"B ", u"A"]:
        r.ajouter_texte(v)
    c = r.colonnes()
    assert c[u"Nb_porteurs"] == 8
    assert c[u"Nb_renseignes"] == 3
    assert c[u"Nb_tiret"] == 2
    assert c[u"Taux_remplissage"] == 0.375
    assert c[u"Nb_valeurs_distinctes"] == 2
    assert c[u"Exemple_valeur"] == u"A"


def test_remplissage_sans_porteur():
    c = inv_lib.Remplissage().colonnes()
    assert c[u"Nb_porteurs"] == 0
    assert c[u"Taux_remplissage"] is None


def test_remplissage_numerique_hasvalue():
    r = inv_lib.Remplissage()
    r.ajouter_valeur(True, u"12,5 mm")
    r.ajouter_valeur(False, None)
    r.ajouter_valeur(True, u"Non")          # Oui/Non a Non : HasValue vrai
    r.ajouter_illisible(u"Exception: x")
    c = r.colonnes()
    assert (c[u"Nb_porteurs"], c[u"Nb_renseignes"], c[u"Nb_tiret"]) == (4, 2, 0)
    assert c[u"Taux_remplissage"] == 0.5
    assert r.nb_illisibles == 1


def test_exemple_tronque_a_60():
    r = inv_lib.Remplissage()
    r.ajouter_texte(u"x" * 100)
    assert len(r.colonnes()[u"Exemple_valeur"]) == 60


# ---------------------------------------------------------------------------
# Arbre de filtre ET / OU / inverse
# ---------------------------------------------------------------------------

def test_aplatir_filtre_et_ou_inverse():
    arbre = fixture("filtre_et_ou_inverse.json")["arbre"]
    lignes, texte, nb = inv_lib.aplatir_filtre(arbre)
    assert nb == 3
    assert [l[u"Chemin"] for l in lignes] == [
        u"ET/PARAM[1]/R1",
        u"ET/NON OU[2]/PARAM[1]/R1",
        u"ET/NON OU[2]/PARAM[2]/R1",
    ]
    assert [l[u"Operateur"] for l in lignes] == [
        u"commence par", u"superieur a", u"egal a"]
    assert [l[u"Inverse"] for l in lignes] == [False, False, True]
    assert lignes[1][u"Valeur_unites_internes"] is True
    assert lignes[2][u"Parametre_GUID"] == \
        u"0b6c7e2a-1111-4c2b-9a77-2f4f3d1e8a10"
    assert texte == (
        u'(Nom du système commence par "EF") ET '
        u'(NON ((Diamètre superieur a "0,164041994750656") OU '
        u'(NON (REF_Batiment egal a "Junior"))))')


def test_aplatir_filtre_vide_et_autre():
    assert inv_lib.aplatir_filtre(None) == ([], u"", 0)
    lignes, texte, nb = inv_lib.aplatir_filtre(
        {u"type": u"AUTRE", u"classe": u"ElementMulticategoryFilter"})
    assert (lignes, nb) == ([], 0)
    assert texte == u"[filtre ElementMulticategoryFilter]"


def test_operateur_inconnu_garde_son_nom():
    arbre = {u"type": u"PARAMETRES", u"regles": [
        {u"parametre": u"P", u"operateur": u"FilterNouveau2027",
         u"valeur": u"x"}]}
    lignes, _t, _n = inv_lib.aplatir_filtre(arbre)
    assert lignes[0][u"Operateur"] == u"FilterNouveau2027"
    assert lignes[0][u"Chemin"] == u"PARAM/R1"


def test_compter_applications():
    assert inv_lib.compter_applications(
        [(1, False), (1, True), (1, False), (2, True)]) == {
            1: (2, 1), 2: (0, 1)}


# ---------------------------------------------------------------------------
# Repartition par systeme et controles arithmetiques
# ---------------------------------------------------------------------------

def test_repartir_elements():
    f = fixture("elements_mep.json")
    r = inv_lib.repartir_elements(f["elements"], f["types_par_systeme"])
    assert r[u"total"] == 7
    assert r[u"par_systeme"] == {u"EF 1": 3, u"ECA 1": 1, u"SOU 1": 1,
                                 u"GAZ 9": 1}
    assert [e[u"id"] for e in r[u"sans_systeme"]] == [105]
    assert (r[u"multi"], r[u"affectations_sup"], r[u"non_lus"]) == (1, 1, 1)
    assert r[u"inconnus"] == {u"GAZ 9": 1}
    assert r[u"par_type_id"] == {11: 3, 21: 1, 12: 1}
    assert r[u"par_categorie"][
        (u"EF 1", u"Eau froide domestique", u"Canalisations")] == 2
    assert r[u"par_categorie"][(u"GAZ 9", u"INTROUVABLE", u"Canalisations")] == 1


def _inventaire_pour_controles():
    inv = inv_lib.Inventaire()
    src = u"thestudy_CO_EQU"
    base_sys = {u"Domaine": u"TUYAUTERIE", u"Prefixe_nom": u"EF",
                u"Type_systeme": u"Eau froide", u"Abreviation_type": u"EF",
                u"Classification": u"DomesticColdWater",
                u"Prefixe_coherent": u"OUI", u"Equipement_base": u"AUCUN",
                u"Nb_terminaux_api": 2, u"Nb_elements_reseau": 5}
    for i, (nom, n) in enumerate([(u"EF 1", 3), (u"ECA 1", 1)]):
        valeurs = dict(base_sys)
        valeurs.update({u"Id": i, u"Nom": nom, u"Nb_elements_parametre": n})
        inv.ajouter(u"systemes", src, valeurs)
    inv.ajouter(u"elements_sans_systeme", src, {
        u"Id": 105, u"Categorie": u"Bouches", u"Famille": u"D", u"Type": u"T",
        u"Niveau": u"", u"Sous_projet": u""})
    for fam, n in [(u"F1", 4), (u"F2", 2)]:
        inv.ajouter(u"familles", src, {
            u"Categorie": u"Equipements", u"Famille": fam, u"Id_famille": 1,
            u"In_situ": False, u"Nb_types": 1, u"Nb_occurrences": n,
            u"Nb_param_type": 0, u"Nb_param_occurrence": 0,
            u"Nb_param_partages": 0})
    inv.ajouter(u"filtres", src, {
        u"Id": 9, u"Nom": u"EF", u"Classe": u"REGLES", u"Categories": u"",
        u"Regles_texte": u"", u"Nb_regles": 0, u"Nb_vues": 1,
        u"Nb_gabarits": 0})
    for filtre in (u"EF", u"Fantome"):
        inv.ajouter(u"filtres_application", src, {
            u"Vue_id": 1, u"Vue": u"Plan", u"Est_gabarit": False,
            u"Filtre": filtre, u"Active": True, u"Visible": True,
            u"Proj_ligne_RVB": u"", u"Proj_motif_RVB": u"",
            u"Coupe_ligne_RVB": u"", u"Coupe_motif_RVB": u"",
            u"Transparence": 0, u"Demi_teinte": False})
    inv.anomalie(src, u"systemes", 3, u"Nom", u"Exception: x")
    inv.non_applicable(src, u"familles_parametres", u"F2 [1]",
                       u"Parametres d'occurrence", u"0 occurrence")
    inv.ajouter_modele(src, inv_lib.ROLE_HOTE, src, u"", True, True,
                       inv_lib.LU, [], {
                           u"elements_mep_lus": 4,
                           u"elements_multi_systemes": 1,
                           u"affectations_sup": 1,
                           u"occurrences_categories_cibles": 7})
    inv.ajouter_modele(u"lien_dechu", inv_lib.ROLE_LIEN, u"lien_dechu", u"",
                       False, False, inv_lib.NON_CHARGE, [])
    return inv, src


def test_controles_arithmetiques():
    inv, src = _inventaire_pour_controles()
    produits = inv_lib.calculer_controles(inv)
    sys_ = [c for c in produits if c[u"Controle"].startswith(u"Elements par")][0]
    assert sys_[u"Attendu"] == u">= 4"
    assert sys_[u"Mesure"].startswith(u"4 + 1 = 5")
    assert u"+1 affectation" in sys_[u"Mesure"]
    assert sys_[u"Statut"] == u"OK"
    fam = [c for c in produits if c[u"Controle"].startswith(u"Somme")][0]
    assert (fam[u"Attendu"], fam[u"Mesure"], fam[u"Statut"]) == \
        (u"7", u"6", u"ECART")
    filt = [c for c in produits if c[u"Controle"].startswith(u"Chaque")][0]
    assert filt[u"Statut"] == u"ECART"
    assert u"Fantome" in filt[u"Mesure"]
    reseau = [c for c in produits if c[u"Controle"].startswith(u"Cote")][0]
    assert reseau[u"Mesure"] == (u"0 systeme(s) NON_LU ; terminaux 4 + reseau "
                                 u"10 = 14 (cote element : 4, autre "
                                 u"instrument)")
    assert reseau[u"Statut"] == u"OK"
    anom = [c for c in produits if c[u"Controle"].startswith(u"Anomalies")]
    assert len(anom) == 2                      # une par maquette, lien compris
    assert anom[0][u"Mesure"] == (u"1 ERREUR (toutes maquettes : 1) ; "
                                  u"1 NON_APPLICABLE, hors ecart")
    assert anom[0][u"Statut"] == u"ECART"
    assert anom[1][u"Statut"] == u"OK"
    # le lien non charge ne recoit que le controle d'anomalies
    assert len([c for c in produits
                if c[u"Source_modele"] == u"lien_dechu"]) == 1


def test_controle_systeme_ecart_explique():
    inv = inv_lib.Inventaire()
    inv.ajouter_modele(u"m", inv_lib.ROLE_HOTE, u"m", u"", False, False,
                       inv_lib.LU, [], {u"elements_mep_lus": 10,
                                        u"elements_systeme_non_lu": 2})
    c = inv_lib.calculer_controles(inv)[0]
    assert c[u"Statut"] == u"ECART"
    assert u"2 element(s) au nom de systeme NON_LU" in c[u"Mesure"]


# ---------------------------------------------------------------------------
# Inventaire : colonnes exigees, lecture publiee
# ---------------------------------------------------------------------------

def test_ajouter_exige_toutes_les_colonnes():
    inv = inv_lib.Inventaire()
    with pytest.raises(ValueError):
        inv.ajouter(u"anomalies", u"m", {u"Table": u"x"})
    with pytest.raises(ValueError):
        inv.ajouter(u"anomalies", u"m", {u"Table": u"x", u"Id": 1,
                                         u"Propriete": u"p", u"Raison": u"r",
                                         u"Intrus": 1})


def test_lire_publie_l_anomalie():
    inv = inv_lib.Inventaire()

    def echoue():
        raise AttributeError(u"Abbreviation")

    assert inv.lire(u"m", u"types_systeme", 42, u"Abreviation", echoue) == \
        u"NON_LU"
    assert inv.lire(u"m", u"types_systeme", 42, u"Nom", lambda: u"EF") == u"EF"
    anomalies = inv.tables[u"anomalies"]
    assert len(anomalies) == 1
    assert anomalies[0][u"Raison"] == u"AttributeError: Abbreviation"
    assert anomalies[0][u"Id"] == 42


def test_echecs_repetitifs_publies_une_fois():
    inv = inv_lib.Inventaire()
    for _ in range(3):
        inv.compter_echec(u"m", u"familles_parametres", u"Fam", u"Valeur",
                          ValueError(u"x"))
    assert inv.tables[u"anomalies"] == []
    inv.publier_echecs()
    anomalies = inv.tables[u"anomalies"]
    assert len(anomalies) == 1
    assert anomalies[0][u"Raison"] == \
        u"3 lecture(s) en echec ; premiere : ValueError: x"
    inv.publier_echecs()
    assert len(inv.tables[u"anomalies"]) == 1


def test_nature_des_anomalies():
    inv = inv_lib.Inventaire()
    inv.anomalie(u"m", u"t", 1, u"p", u"r")
    inv.non_applicable(u"m", u"familles_parametres", u"F", u"p", u"0 occ.")
    inv.lire(u"m", u"elec_circuits", 7, u"Nom_charge",
             lambda: 1 / 0, inv_lib.NATURE_NON_APPLICABLE)
    assert [a[u"Nature"] for a in inv.tables[u"anomalies"]] == [
        u"ERREUR", u"NON_APPLICABLE", u"NON_APPLICABLE"]
    assert inv.nombre_anomalies(u"m", inv_lib.NATURE_ERREUR) == 1
    assert inv.nombre_anomalies(nature=inv_lib.NATURE_NON_APPLICABLE) == 2
    with pytest.raises(ValueError):
        inv.anomalie(u"m", u"t", 1, u"p", u"r", u"AVIS")


def test_non_applicable_seul_ne_fait_pas_ecart():
    inv = inv_lib.Inventaire()
    inv.non_applicable(u"m", u"familles_parametres", u"F", u"p", u"0 occ.")
    inv.ajouter_modele(u"m", inv_lib.ROLE_HOTE, u"m", u"", False, False,
                       inv_lib.LU, [], {})
    anom = [c for c in inv_lib.calculer_controles(inv)
            if c[u"Controle"].startswith(u"Anomalies")][0]
    assert anom[u"Statut"] == u"OK"
    assert anom[u"Mesure"] == (u"0 ERREUR (toutes maquettes : 0) ; "
                               u"1 NON_APPLICABLE, hors ecart")


def test_controle_reseau_non_lu():
    inv = inv_lib.Inventaire()
    valeurs = dict([(c, u"") for c in inv_lib.colonnes(u"systemes")[1:]])
    valeurs.update({u"Nb_elements_parametre": 2, u"Nb_terminaux_api": 1,
                    u"Nb_elements_reseau": u"NON_LU"})
    inv.ajouter(u"systemes", u"m", valeurs)
    inv.ajouter_modele(u"m", inv_lib.ROLE_HOTE, u"m", u"", False, False,
                       inv_lib.LU, [], {u"elements_mep_lus": 2})
    c = [c for c in inv_lib.calculer_controles(inv)
         if c[u"Controle"].startswith(u"Cote")][0]
    assert c[u"Statut"] == u"ECART"
    assert c[u"Mesure"].startswith(u"1 systeme(s) NON_LU")


# ---------------------------------------------------------------------------
# Electricite : tensions, tableaux, nature des echecs sur un circuit
# ---------------------------------------------------------------------------

def test_volt_en_unites_internes():
    """1 V = 1 kg.m2/(s3.A) = 10,7639 kg.ft2/(s3.A), unite interne Revit."""
    assert abs(inv_lib.VOLT_EN_UNITES_INTERNES - 10.763910416709722) < 1e-9
    assert inv_lib.volts(230 * inv_lib.VOLT_EN_UNITES_INTERNES, True) == 230.0


def test_tension_deja_en_volts_non_convertie():
    """Recette McGill 2026-10-07 : '230V AC' sortait 21,4. ActualValue est
    deja en volts ; le convertir comme une valeur interne divise par 10,76."""
    assert inv_lib.volts(230.0, False) == 230.0
    assert inv_lib.volts(230.0, True) == 21.4          # la signature du defaut
    assert inv_lib.volts(120.04, False) == 120.0


@pytest.mark.parametrize("propriete, type_circuit, type_systeme, attendu", [
    (u"Nom_charge", u"Spare", u"PowerCircuit", u"NON_APPLICABLE"),
    (u"Nb_elements", u"Space", u"PowerCircuit", u"NON_APPLICABLE"),
    (u"Tension_V", u"Circuit", u"Data", u"NON_APPLICABLE"),
    (u"Tension_V", u"Circuit", u"FireAlarm", u"NON_APPLICABLE"),
    (u"Tension_V", u"Circuit", u"PowerCircuit", u"ERREUR"),
    (u"Nom_charge", u"Circuit", u"Data", u"ERREUR"),
    (u"Tension_V", u"NON_LU", u"NON_LU", u"NON_APPLICABLE"),
])
def test_nature_propriete_circuit(propriete, type_circuit, type_systeme,
                                  attendu):
    assert inv_lib.nature_propriete_circuit(
        propriete, type_circuit, type_systeme) == attendu


@pytest.mark.parametrize("equipement, nom, attendu", [
    (True, u"TD-01", True),
    (True, u"   ", False),          # nom de tableau vide
    (True, u"", False),
    (True, None, False),            # parametre absent
    (False, u"TD-01", False),       # pas un ElectricalEquipment
])
def test_est_tableau(equipement, nom, attendu):
    assert inv_lib.est_tableau(equipement, nom) is attendu


def test_dix_neuf_fichiers():
    assert len(inv_lib.fichiers_attendus()) == 19
    assert inv_lib.fichiers_attendus()[0] == u"inventaire.json"
    for _cle, _f, cols in inv_lib.TABLES:
        assert len(cols) == len(set(cols))


# ---------------------------------------------------------------------------
# CSV
# ---------------------------------------------------------------------------

def test_csv_echappement_accents_crlf_virgule():
    inv = inv_lib.Inventaire()
    inv.anomalie(u"Maquette été", u"t;1", 3.5,
                 u'dit "oui"', u"ligne 1\nligne 2")
    texte = inv_lib.texte_csv(u"anomalies", inv.tables[u"anomalies"])
    assert texte == (
        u"Source_modele;Nature;Table;Id;Propriete;Raison\r\n"
        u'Maquette été;ERREUR;"t;1";3,5;"dit ""oui""";"ligne 1\nligne 2"'
        u"\r\n")
    assert not texte.startswith(inv_lib.BOM)


@pytest.mark.parametrize("valeur, attendu", [
    (True, u"OUI"), (False, u"NON"), (None, u""), (12, u"12"),
    (12.5, u"12,5"), (60.0, u"60"), (-0.0, u"0"), (1e-7, u"0,0000001"),
    (0.1 + 0.2, u"0,30000000000000004"), ([u"a", 1.5], u"a | 1,5"),
    (u"NON_LU", u"NON_LU"),
])
def test_formater_texte(valeur, attendu):
    assert inv_lib.formater_texte(valeur) == attendu


def test_ecriture_bom_unique_crlf(tmp_path):
    chemin = str(tmp_path / "x.csv")
    inv_lib.ecrire_texte(chemin, inv_lib.BOM + u"a;é\r\nb;c\r\n")
    with open(chemin, "rb") as f:
        brut = f.read()
    assert brut.startswith(b"\xef\xbb\xbf")
    assert brut.count(b"\xef\xbb\xbf") == 1
    assert brut == b"\xef\xbb\xbfa;\xc3\xa9\r\nb;c\r\n"   # CRLF non double


def test_ecrire_sorties_19_fichiers(tmp_path):
    inv, src = _inventaire_pour_controles()
    inv_lib.calculer_controles(inv)
    outil = {u"nom": u"Inventaire systèmes", u"version": u"t"}
    chemins = inv_lib.ecrire_sorties(str(tmp_path), inv, outil)
    assert sorted(os.path.basename(c) for c in chemins) == \
        sorted(inv_lib.fichiers_attendus())
    for c in chemins:
        with open(c, "rb") as f:
            brut = f.read()
        assert brut.count(b"\xef\xbb\xbf") == 1 and brut.startswith(
            b"\xef\xbb\xbf")
        if c.endswith(".csv"):
            assert b"\n" not in brut.replace(b"\r\n", b"")
    with io.open(os.path.join(str(tmp_path), "99_controles.csv"),
                 encoding="utf-8-sig", newline="") as f:
        entete = f.readline()
    assert entete == u"Source_modele;Controle;Attendu;Mesure;Statut\r\n"


# ---------------------------------------------------------------------------
# JSON
# ---------------------------------------------------------------------------

def test_json_schema_et_decimale_point(tmp_path):
    inv, src = _inventaire_pour_controles()
    inv.ajouter(u"types_systeme", src, dict(
        [(c, None) for c in inv_lib.colonnes(u"types_systeme")[1:]],
        Temperature_fluide_C=12.5, Nom=u"Eau froide domestique"))
    inv_lib.calculer_controles(inv)
    outil = {u"nom": u"x", u"duree_s": 1.25}
    chemin = str(tmp_path / "inventaire.json")
    inv_lib.ecrire_texte(chemin, inv_lib.texte_json(inv, outil))
    with io.open(chemin, encoding="utf-8-sig") as f:
        brut = f.read()
    assert u"12.5" in brut and u"12,5" not in brut
    doc = json.loads(brut)
    assert doc[u"schema"] == u"bimflow.inventaire/0.2"
    attendues = [u"schema", u"outil", u"modeles"] + \
        [cle for cle, _f, _c in inv_lib.TABLES]
    assert list(doc.keys()) == attendues
    for cle, _f, _c in inv_lib.TABLES:
        for ligne in doc[cle]:
            assert list(ligne.keys()) == list(inv_lib.colonnes(cle))
    assert doc[u"modeles"][1][u"statut_lecture"] == u"NON_CHARGE"
    assert doc[u"types_systeme"][0][u"Nom"] == u"Eau froide domestique"


# ---------------------------------------------------------------------------
# Relecture statique : lib pure, bouton en lecture seule, vocabulaire
# ---------------------------------------------------------------------------

def _lire(chemin):
    with io.open(chemin, encoding="utf-8") as f:
        return f.read()


def test_lib_n_importe_ni_autodesk_ni_clr_ni_pyrevit():
    source = _lire(os.path.join(LIB, "bimflow_inventaire.py"))
    imports = re.findall(r"^\s*(?:import|from)\s+([\w.]+)", source, re.M)
    for interdit in ("Autodesk", "clr", "pyrevit", "System"):
        assert not [i for i in imports if i.split(".")[0] == interdit], interdit


def test_bouton_sans_ecriture():
    source = _lire(os.path.join(BOUTON, "script.py"))
    for interdit in ("Transaction", "TransactionGroup", "SubTransaction",
                     "EditFamily", "SynchronizeWithCentral",
                     "CheckoutElements", ".IntegerValue", "#! python3"):
        assert interdit not in source, interdit


def test_categories_lues_comme_categories():
    """Recette du 2026-10-07 : 48 anomalies, parce que les ids de
    BuiltInCategory (negatifs) passaient par doc.GetElement."""
    source = _lire(os.path.join(BOUTON, "script.py"))
    assert u"Category.GetCategory(d, cid)" in source
    for ligne in source.splitlines():
        if u"GetCategories()" in ligne or u"CategoryId" in ligne:
            assert u"nom_par_id" not in ligne, ligne


@pytest.mark.parametrize("chemin", [
    os.path.join(LIB, "bimflow_inventaire.py"),
    os.path.join(BOUTON, "script.py"),
])
def test_vocabulaire_de_sortie(chemin):
    source = _lire(chemin).lower()
    for mot in (u"supprimable", u"inutile", u"en trop"):
        assert mot not in source, mot


def test_bundle_complet():
    assert os.path.isfile(os.path.join(BOUTON, "icon.png"))
    source = _lire(os.path.join(BOUTON, "script.py"))
    assert re.search(r'^__title__\s*=', source, re.M)
    assert source.lstrip().startswith(u"# -*- coding: utf-8 -*-")
    assert u'"""' in source.split(u"__title__")[0]     # docstring = infobulle
    assert all(ord(c) < 128 for c in os.path.basename(BOUTON))
