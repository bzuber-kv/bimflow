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
            # seule exception admise : WorksetId (w.Id).IntegerValue
            assert set(re.findall(r"([\w.]+)\.IntegerValue",
                                  sans_commentaires)) <= set(["w.Id"])
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
    # la boite est ouverte sans condition : l'appel est au niveau du module
    appels = [l for l in code.splitlines() if "choisir_dossier(" in l
              and not l.startswith("def ")]
    assert len(appels) == 1 and not appels[0].startswith(" ")
    # pick_folder ne sert plus que de repli, dans choisir_dossier
    assert code.count("forms.pick_folder(") == 1
    assert "dlg.SelectedPath = initial" in code
    assert not os.path.exists(os.path.join(BOUTON, "config.py"))


def _appels(code, fonction):
    """Texte de chaque appel `fonction(...)`, parentheses equilibrees."""
    res = []
    i = code.find(fonction + "(")
    while i >= 0:
        j = i + len(fonction)
        prof = 0
        while True:
            prof += {"(": 1, ")": -1}.get(code[j], 0)
            j += 1
            if prof == 0:
                break
        res.append(code[i:j])
        i = code.find(fonction + "(", j)
    return res


def test_bouton_n_affiche_pas_de_texte_entre_backticks():
    # un texte formate entre backticks s'afficherait mal : dans du code, les
    # entites d'echapper_md restent brutes. Les signalements, eux, gardent
    # leurs backticks dans le JSON et sont echappes en entier a l'affichage.
    code = _code("script.py")
    appels = _appels(code, "sortie.print_md") + _appels(code,
                                                         "sortie.print_table")
    assert len(appels) > 10
    for a in appels:
        assert "`{" not in a, a


def test_bouton_volumes_publient_nom_type():
    code = _code("script.py")
    assert '("nom_type", nom_de(el))' in code


def _v(i, famille, ref, nom_type="Volume Ivion"):
    return OrderedDict([("id", i), ("nom_type", nom_type), ("famille", famille),
                        ("REF_Id", ref)])


def test_doublons_ref_id():
    v = [_v(1, "VOL_090", "a"), _v(2, "VOL_091", "a"), _v(3, "VOL_092", "b"),
         _v(4, "Volume 1", None, "Volume 1"), _v(5, "Volume 2", None, "Volume 2"),
         _v(6, "x", ph.NON_LU, "x"), _v(7, "y", ph.NON_LU, "y")]
    g = ph.doublons(v, "REF_Id")
    assert len(g) == 1 and g[0]["valeur"] == "a" and g[0]["nombre"] == 2
    assert [e["id"] for e in g[0]["elements"]] == [1, 2]
    assert g[0]["elements"][0] == OrderedDict(
        [("id", 1), ("nom_type", "Volume Ivion"), ("famille", "VOL_090")])
    comptes, sig = ph.bilan(OrderedDict([("volumes", v)]))
    assert comptes["volumes"]["unicite_REF_Id"]["doublons"] == g
    assert comptes["volumes"]["unicite_REF_Id"]["valeurs_controlees"] == 3
    assert any("EN DOUBLE" in s and "`VOL_090` (id 1)" in s and "`VOL_091` (id 2)" in s
               for s in sig)


def test_message_unicite_rubrique_vide():
    # maquette sans volume (cas G_AN, 2026-10-13) : rien a controler, ni
    # « non controlee » a l'ecran, ni signalement
    comptes, sig = ph.bilan(OrderedDict([("volumes", [])]))
    m = ph.message_unicite("volumes", comptes["volumes"]["nombre"],
                           comptes["volumes"]["unicite_REF_Id"])
    assert m == u"Rien a controler : aucun volume dans la maquette."
    assert "Non controlee" not in m
    assert sig == []


def test_message_unicite_non_controlee_et_compte():
    v = [_vol(1, None), _vol(2, ph.NON_LU)]
    ctrl = ph.controle_unicite(v, "REF_Id")
    assert "Non controlee" in ph.message_unicite("volumes", 2, ctrl)
    v = [_vol(1, "a"), _vol(2, "a"), _vol(3, "b")]
    ctrl = ph.controle_unicite(v, "REF_Id")
    assert ph.message_unicite("volumes", 3, ctrl) == \
        u"3 valeur(s) controlee(s), 1 en double."


def test_aucun_doublon_liste_vide():
    comptes, sig = ph.bilan(OrderedDict())
    assert comptes["volumes"]["unicite_REF_Id"]["doublons"] == []
    assert not any("EN DOUBLE" in s or "NON CONTROLEE" in s for s in sig)


def _vol(i, v, porteur="instance"):
    return OrderedDict([("id", i), ("nom_type", "Volume Ivion"), ("famille", "F%d" % i),
                        ("REF_Id", v), ("parametres", OrderedDict([
                            ("REF_Id", OrderedDict([("valeur", v), ("statut", "lu"),
                                                    ("porteur", porteur)]))]))])


def test_unicite_non_controlee_si_rien_lu():
    v = [_vol(1, None), _vol(2, ph.NON_LU)]
    comptes, sig = ph.bilan(OrderedDict([("volumes", v)]))
    assert comptes["volumes"]["unicite_REF_Id"]["valeurs_controlees"] == 0
    assert any("NON CONTROLEE" in s for s in sig)


def test_valeur_portee_par_le_type_n_est_pas_un_doublon():
    v = [_vol(1, "a", "type"), _vol(2, "a", "type"), _vol(3, "b")]
    ctrl = ph.controle_unicite(v, "REF_Id")
    assert ctrl["doublons"] == [] and ctrl["portees_par_type"] == 2
    assert ctrl["valeurs_controlees"] == 1
    comptes, sig = ph.bilan(OrderedDict([("volumes", v)]))
    assert any("TYPE" in s for s in sig)


def test_doublon_insensible_casse_et_blancs():
    v = [_vol(1, "ABC-1"), _vol(2, " abc-1 ")]
    g = ph.doublons(v, "REF_Id")
    assert len(g) == 1 and g[0]["valeur"] == "ABC-1"


def test_famille_non_lue_signalee():
    v = [OrderedDict([("id", 1), ("famille", ph.NON_LU), ("boite_mm", {})])]
    comptes, sig = ph.bilan(OrderedDict([("volumes", v)]))
    assert comptes["volumes"]["champs_nuls"] == OrderedDict([("famille (NON_LU)", 1)])


def test_designation_famille_puis_nom_type_puis_nom():
    assert ph.designation({"famille": "VOL_1", "nom_type": "T"}) == "VOL_1"
    assert ph.designation({"famille": None, "nom_type": "T"}) == "T"
    assert ph.designation({"nom": "Axe A"}) == "Axe A"


def test_doublon_sans_famille_designe_par_nom_type():
    v = [_v(1, None, "a", "T1"), _v(2, None, "a", "T2")]
    comptes, sig = ph.bilan(OrderedDict([("volumes", v)]))
    assert any("`T1` (id 1)" in s and "`T2` (id 2)" in s for s in sig)


# --- echappement Markdown du rapport ------------------------------------------

def test_echapper_md_rend_les_speciaux_inertes():
    s = ph.echapper_md(u"VOL_090__SC_Bp_Amg_1p_3p__FLOOR_2__ETAGE")
    assert "_" not in s and s.count("&#95;") == 12
    brut = u"a\\b`c*d_e[f]g#h|i<j>k&l"
    e = ph.echapper_md(brut)
    reste = re.sub(r"&#\d+;", "", e)
    assert reste == u"abcdefghijkl"
    # aucune perte : le texte se relit a l'identique une fois les entites
    # decodees
    import html
    assert html.unescape(e) == brut


def test_echapper_md_ne_touche_pas_au_texte_ordinaire():
    assert ph.echapper_md(u"Étage 2 : 23 niveaux") == u"Étage 2 : 23 niveaux"
    assert ph.echapper_md(None) == u""
    assert ph.echapper_md(5530844) == u"5530844"


def test_le_json_n_est_pas_echappe():
    v = [_v(1, "VOL_090__A", "a"), _v(2, "VOL_091__B", "a")]
    comptes, sig = ph.bilan(OrderedDict([("volumes", v)]))
    assert comptes["volumes"]["unicite_REF_Id"]["doublons"][0]["elements"][0][
        "famille"] == "VOL_090__A"
    assert any("VOL_090__A" in s for s in sig)
    assert not any("&#" in s for s in sig)


# --- date ISO avec fuseau ----------------------------------------------------

def test_date_iso_avec_fuseau():
    t = datetime.datetime(2026, 10, 13, 0, 40, 12)
    assert ph.date_iso(t, -240) == u"2026-10-13T00:40:12-04:00"
    assert ph.date_iso(t, 0) == u"2026-10-13T00:40:12+00:00"
    assert ph.date_iso(t, 330) == u"2026-10-13T00:40:12+05:30"
    assert ph.date_iso(t, -570) == u"2026-10-13T00:40:12-09:30"


def test_decalage_minutes_arrondi():
    local = datetime.datetime(2026, 10, 13, 0, 40, 12, 900)
    utc = datetime.datetime(2026, 10, 13, 4, 40, 12, 400)
    assert ph.decalage_minutes(local, utc) == -240


# --- ecriture atomique -------------------------------------------------------

def test_ecrire_json_ne_laisse_que_le_fichier(tmp_path):
    f = str(tmp_path / "p.json")
    ph.ecrire_json(f, OrderedDict([("a", 1)]))
    assert os.listdir(str(tmp_path)) == ["p.json"]


def test_ecrire_json_echec_au_renommage_ne_laisse_rien(tmp_path):
    f = str(tmp_path / "p.json")

    def casse(a, b):
        raise OSError("disque plein")

    with pytest.raises(OSError):
        ph.ecrire_json(f, OrderedDict([("a", 1)]), renommer=casse)
    assert os.listdir(str(tmp_path)) == []


def test_ecrire_json_donnees_invalides_ne_laisse_rien(tmp_path):
    f = str(tmp_path / "p.json")
    with pytest.raises(TypeError):
        ph.ecrire_json(f, OrderedDict([("a", object())]))
    assert os.listdir(str(tmp_path)) == []


def test_ecrire_json_n_ecrase_pas_une_photo(tmp_path):
    f = tmp_path / "p.json"
    f.write_text(u"ancienne", encoding="utf-8")
    if os.name == "nt":
        with pytest.raises(OSError):
            ph.ecrire_json(str(f), OrderedDict([("a", 1)]))
        assert f.read_text(encoding="utf-8") == u"ancienne"
        assert os.listdir(str(tmp_path)) == ["p.json"]
