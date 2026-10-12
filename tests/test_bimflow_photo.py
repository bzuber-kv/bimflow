# -*- coding: utf-8 -*-
"""Tests de bimflow_photo (logique pure du bouton Photo maquette).

Lancement, depuis la racine du depot :
    python -m pytest tests/test_bimflow_photo.py

Le bouton (script.py) ne s'execute que dans Revit : il n'est ici que relu,
pour les interdits du lecture seule.
"""

import datetime
import io
import json
import os
import re
import sys
from collections import OrderedDict

import pytest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIB = os.path.join(RACINE, "bimflow.extension", "lib")
BOUTON = os.path.join(RACINE, "bimflow.extension", "bimflow.tab",
                      "Dev.panel", "PhotoMaquette.pushbutton")
sys.path.insert(0, LIB)

import bimflow_photo as ph  # noqa: E402


# --- socle -----------------------------------------------------------------

def test_socle_du_depot_porte_tous_les_parametres_lus():
    socle = ph.lire_socle(ph.chemin_socle(LIB))
    trouves, manquants = ph.guids_requis(
        socle, ph.PARAMS_NIVEAU + ph.PARAMS_VOLUME)
    assert manquants == []
    assert trouves["REF_Id"] == "7414d6b1-6083-4145-9c1c-784e03243895"
    assert trouves["REF_Zone"] == "499a73ab-e323-42bf-807b-465c9165e62b"


def test_socle_colonnes_lues_dans_l_en_tete():
    texte = (u"*PARAM\tNAME\tGUID\tDATATYPE\n"
             u"PARAM\tREF_X\tABCD-1\tTEXT\n")
    assert ph.lire_socle_texte(texte) == OrderedDict([("REF_X", "abcd-1")])


def test_socle_utf16(tmp_path):
    f = tmp_path / "s.txt"
    f.write_bytes((u"*PARAM\tGUID\tNAME\nPARAM\tg-1\tREF_A\n")
                  .encode("utf-16"))
    assert ph.lire_socle(str(f)) == OrderedDict([("REF_A", "g-1")])


def test_guids_requis_signale_les_absents():
    trouves, manquants = ph.guids_requis({"A": "1"}, ("A", "B"))
    assert list(trouves) == ["A"] and manquants == ["B"]


# --- rappel du dernier dossier -----------------------------------------------

def test_developper_variables_windows():
    env = {"USERPROFILE": "C:\\Users\\bz"}
    assert ph.developper("%USERPROFILE%\\OneDrive\\x", env) == \
        "C:\\Users\\bz\\OneDrive\\x"
    assert ph.developper("%userprofile%\\x", env) == "C:\\Users\\bz\\x"


def test_developper_variable_inconnue_laissee():
    assert ph.developper("%INCONNUE%\\x", {}) == "%INCONNUE%\\x"


def test_config_aller_retour(tmp_path):
    f = str(tmp_path / "bimflow" / "photo_maquette.json")
    assert ph.lire_config(f)[0] is None
    ph.ecrire_config(f, "%TEMP%\\photos")
    dossier, brut, motif = ph.lire_config(f, {"TEMP": "D:\\t"})
    assert (dossier, brut, motif) == ("D:\\t\\photos", "%TEMP%\\photos", None)


def test_config_sans_cle(tmp_path):
    f = tmp_path / "c.json"
    f.write_text(u'{"autre": 1}', encoding="utf-8")
    dossier, brut, motif = ph.lire_config(str(f))
    assert dossier is None and "dossier_sortie" in motif


def test_config_illisible(tmp_path):
    f = tmp_path / "c.json"
    f.write_text(u"{pas du json", encoding="utf-8")
    assert "illisible" in ph.lire_config(str(f))[2]



# --- nom du fichier ----------------------------------------------------------

def test_nom_fichier():
    t = datetime.datetime(2026, 10, 12, 16, 5)
    assert ph.nom_fichier(u"thestudy_G_AN", t) == \
        u"thestudy_G_AN_2026-10-12_1605.json"
    assert ph.nom_fichier(u"a b:c.rvt", t) == u"a_b_c_2026-10-12_1605.json"
    assert ph.nom_fichier(u"", t).startswith(u"sans_titre_")


def test_chemin_libre_n_ecrase_jamais():
    pris = set([os.path.join("d", "m.json"), os.path.join("d", "m_2.json")])
    assert ph.chemin_libre("d", "m.json", lambda c: c in pris) == \
        os.path.join("d", "m_3.json")
    assert ph.chemin_libre("d", "n.json", lambda c: False) == \
        os.path.join("d", "n.json")


# --- geometrie ---------------------------------------------------------------

@pytest.mark.parametrize("dx,dy,az,direction", [
    (0, 1, 0.0, 0.0), (1, 0, 90.0, 90.0), (0, -1, 180.0, 0.0),
    (-1, 0, 270.0, 90.0), (1, 1, 45.0, 45.0), (-1, -1, 225.0, 45.0),
])
def test_azimut_et_direction(dx, dy, az, direction):
    assert ph.azimut_deg(dx, dy) == az
    assert ph.direction_deg(ph.azimut_deg(dx, dy)) == direction


def test_azimut_vecteur_nul():
    assert ph.azimut_deg(0, 0) is None and ph.direction_deg(None) is None


def test_choisir_sens():
    assert ph.choisir_sens([("directe", 5000.0), ("inverse", 0.2)], 1.0) == \
        ("inverse", 0.2)
    nom, motif = ph.choisir_sens([("directe", 3.0), ("inverse", 9.0)], 1.0)
    assert nom is None and "tolerance" in motif
    assert ph.choisir_sens([("directe", None)], 1.0)[0] is None


# --- bilan -------------------------------------------------------------------

def _param(statut, valeur=None):
    return OrderedDict([("valeur", valeur), ("statut", statut)])


def test_bilan_compte_et_signale():
    photo = OrderedDict([
        ("niveaux", [
            OrderedDict([("elevation_pbp_mm", 0.0), ("parametres", OrderedDict([
                ("REF_Batiment", _param(ph.LU, "SC")),
                ("REF_Etage", _param(ph.ABSENT))]))]),
            OrderedDict([("elevation_pbp_mm", None), ("parametres", OrderedDict([
                ("REF_Batiment", _param(ph.VIDE)),
                ("REF_Etage", _param(ph.ILLISIBLE, ph.NON_LU))]))]),
        ]),
        ("liens", [OrderedDict([("type", "Revit"), ("epingle", ph.NON_LU)])]),
    ])
    comptes, sig = ph.bilan(photo)
    n = comptes["niveaux"]
    assert n["nombre"] == 2
    assert n["champs_nuls"] == OrderedDict([("elevation_pbp_mm", 1)])
    assert n["parametres"]["REF_Etage"] == OrderedDict(
        [(ph.LU, 0), (ph.VIDE, 0), (ph.ABSENT, 1), (ph.ILLISIBLE, 1)])
    assert comptes["liens"]["champs_nuls"] == OrderedDict(
        [("epingle (NON_LU)", 1)])
    assert comptes["volumes"]["nombre"] == 0
    assert any("REF_Etage" in s and "absent 1" in s for s in sig)
    assert any("REF_Batiment" in s and "vide 1" in s for s in sig)


def test_bilan_rien_a_signaler():
    comptes, sig = ph.bilan(OrderedDict())
    assert list(comptes) == ["niveaux", "quadrillages", "volumes", "pieces",
                             "sous_projets", "liens"]
    assert sig == []


def test_ecrire_json_utf8_sans_bom(tmp_path):
    f = str(tmp_path / "p.json")
    ph.ecrire_json(f, OrderedDict([("nom", u"Étage")]))
    octets = open(f, "rb").read()
    assert not octets.startswith(b"\xef\xbb\xbf")
    assert json.loads(octets.decode("utf-8")) == {"nom": u"Étage"}


# --- le bouton, relu ---------------------------------------------------------

def _code(nom):
    with io.open(os.path.join(BOUTON, nom), encoding="utf-8") as f:
        return f.read()


@pytest.mark.parametrize("fichier", ["script.py"])
def test_bouton_lecture_seule(fichier):
    code = _code(fichier)
    sans_commentaires = "\n".join(
        l.split("#")[0] for l in code.splitlines())
    for interdit in ("Transaction(", "TransactionGroup", "SubTransaction",
                     "SynchronizeWithCentral", "CheckoutElements",
                     ".IntegerValue", "script.exit"):
        if interdit == ".IntegerValue":
            # seule exception admise : WorksetId.IntegerValue
            assert re.findall(r"(\w+)\.IntegerValue", sans_commentaires) \
                in ([], ["Id"])
            continue
        assert interdit not in sans_commentaires, interdit


def test_bouton_aucun_guid_ni_affaire_en_dur():
    code = _code("script.py")
    assert not re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}", code)
    # Les chaines litterales seules : l'en-tete peut citer la recette.
    litteraux = " ".join(re.findall(r'u?"([^"\\n]*)"', code)).lower()
    for affaire in ("a_049", "thestudy"):
        assert affaire not in litteraux


def test_bouton_icone_96_argb():
    Image = pytest.importorskip("PIL.Image")
    im = Image.open(os.path.join(BOUTON, "icon.png"))
    assert im.size == (96, 96) and im.mode == "RGBA"
    assert im.getpixel((0, 0))[3] == 0


def test_bouton_demande_toujours_le_dossier():
    code = _code("script.py")
    assert code.count("forms.pick_folder(") == 1
    # le choix ne depend d'aucune condition : l'appel est au niveau du module
    ligne = [l for l in code.splitlines() if "forms.pick_folder(" in l][0]
    assert not ligne.startswith(" ")
    assert not os.path.exists(os.path.join(BOUTON, "config.py"))
