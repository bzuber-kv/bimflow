# -*- coding: utf-8 -*-
"""Tests de tools/marquages (chaine « marquages plans », CPython hors Revit).

Lancement, depuis la racine du depot, dans un environnement qui a les
dependances de tools/marquages/requirements.txt :
    python -m pytest tests/test_marquages.py

Sans OpenCV, ces tests sont sautes : le reste de la suite n'en depend pas.

Jeux d'essai : tests/fixtures/marquages/, SYNTHETIQUES (grain aleatoire,
texte « KEOVIA TEST ») - aucune photo ni aucun nom d'affaire. Les seuils
viennent du fichier de parametres, donc du bordereau du pilote (F5, F6).
"""

import csv
import json
import re
import sys
from pathlib import Path

import pytest

cv2 = pytest.importorskip("cv2")

RACINE = Path(__file__).resolve().parent.parent
OUTIL = RACINE / "tools" / "marquages"
FIXTURES = RACINE / "tests" / "fixtures" / "marquages"
PARAMETRES = OUTIL / "parametres_dallage_300x600.json"
sys.path.insert(0, str(OUTIL))
sys.path.insert(0, str(FIXTURES))

import synthese  # noqa: E402
from controle import controler  # noqa: E402
from empreintes import Empreintes  # noqa: E402
from marquages import main  # noqa: E402
from parametres import lire_parametres  # noqa: E402
from redressement import redresser  # noqa: E402
from tables import NON_LU, construire, regrouper  # noqa: E402

VALIDE = FIXTURES / "vue_valide_pave.jpg"
ZOOM = FIXTURES / "vue_zoom_pave.jpg"
DOUBLON = FIXTURES / "vue_doublon_pave.jpg"


@pytest.fixture(scope="module")
def p():
    return lire_parametres(PARAMETRES)


# --- parametres ---------------------------------------------------------------

def test_parametres_lus(p):
    assert (p.largeur_mm, p.longueur_mm) == (300.0, 600.0)
    assert p.rapport_module == 2.0
    assert p.echelle == 1.0


def test_parametres_cle_manquante(tmp_path):
    d = json.loads(PARAMETRES.read_text(encoding="utf-8"))
    del d["empreinte"]["seuil_meme_pave"]
    f = tmp_path / "p.json"
    f.write_text(json.dumps(d), encoding="utf-8")
    with pytest.raises(ValueError, match="seuil_meme_pave"):
        lire_parametres(f)


def test_aucun_chemin_ni_pas_en_dur():
    """Le pilote lisait rect/ et fixait 300 x 600 dans le code : plus maintenant."""
    for f in OUTIL.glob("*.py"):
        texte = f.read_text(encoding="utf-8").replace("300x600", "")  # nom du fichier d'exemple
        assert "rect/" not in texte, f.name
        assert not re.search(r"(?<![\d.])(300|600)(\.0)?(?!\d)", texte), f.name


# --- controle du cadrage (F5) ---------------------------------------------------

def test_controle_cadrage_valide(p):
    c = controler(VALIDE, p)
    assert c["ok"], c["raison"]
    assert c["joints"] == 4
    assert c["coupees"] == 0


def test_controle_zoom_refuse(p):
    c = controler(ZOOM, p)
    assert not c["ok"]
    assert "zoom" in c["raison"]
    assert max(c["capitales_mm"]) > p.capitale_max_mm


def test_controle_vue_illisible(p, tmp_path):
    c = controler(tmp_path / "absente_pave.jpg", p)
    assert c == {"vue": "absente_pave.jpg", "ok": False, "raison": "vue illisible"}


# --- empreinte (F6) -------------------------------------------------------------

def test_empreinte_doublon_detecte(p):
    e = Empreintes(p)
    meme, _ = e.apparier(VALIDE, DOUBLON)
    autre, _ = e.apparier(VALIDE, ZOOM)
    # F6 : 150 a 440 points pour un meme pave, 10 au plus pour deux paves differents
    assert meme >= 150
    assert meme >= p.seuil_meme_pave
    assert autre <= 10


# --- tables (C-MP2, C-MP4) ------------------------------------------------------

def test_regrouper_union_des_paires():
    paires = [{"a": "a", "b": "b", "meme_pave": True},
              {"a": "b", "b": "c", "meme_pave": True},
              {"a": "a", "b": "d", "meme_pave": False}]
    assert regrouper(["a", "b", "c", "d"], paires) == [["a", "b", "c"], ["d"]]


def test_tables(p, tmp_path):
    red = [{"photo": "P1.jpg", "ok": True, "vue": VALIDE.name, "mode": "4 joints", "ratio": 2.0},
           {"photo": "P2.jpg", "ok": True, "vue": DOUBLON.name, "mode": "4 joints", "ratio": 2.0},
           {"photo": "P3.jpg", "ok": True, "vue": ZOOM.name, "mode": "4 joints", "ratio": 2.0},
           {"photo": "P4.jpg", "ok": False, "raison": "peu de joints"}]
    ctl = [controler(v, p) for v in (VALIDE, DOUBLON, ZOOM)]
    e = Empreintes(p)
    n, _ = e.apparier(VALIDE, DOUBLON)
    paires = [{"a": DOUBLON.name, "b": VALIDE.name, "points": n, "meme_pave": n >= p.seuil_meme_pave}]
    photos, marquages = construire(red, ctl, paires, p.px_par_mm, tmp_path)
    assert photos.read_bytes().startswith(b"\xef\xbb\xbf")
    with open(photos, encoding="utf-8-sig") as f:
        lp = {r["photo"]: r for r in csv.DictReader(f, delimiter=";")}
    with open(marquages, encoding="utf-8-sig") as f:
        lm = list(csv.DictReader(f, delimiter=";"))
    assert lp["P1.jpg"]["statut"] == "ACCEPTE"
    assert lp["P3.jpg"]["statut"] == "A_VALIDER_A_LA_MAIN"
    assert lp["P4.jpg"]["statut"] == "ECHEC_REDRESSEMENT"
    assert lp["P1.jpg"]["id_marquage"] == lp["P2.jpg"]["id_marquage"] == "M001"
    assert len(lm) == 1
    assert lm[0]["n_vues"] == "2"
    assert lm[0]["texte"] == lm[0]["format"] == NON_LU


# --- redressement et chaine complete, sur photos synthetiques -------------------

def test_redressement_photo_inclinee(p, tmp_path):
    ph = tmp_path / "photo.jpg"
    cv2.imwrite(str(ph), synthese.photo_dallage(inclinaison_deg=12, lacet_deg=4))
    r = redresser(ph, tmp_path / "vues", p)
    assert r["ok"], r
    assert r["mode"] == "4 joints"
    assert abs(r["ratio"] - p.rapport_module) < 0.06  # F2 : rapport mesure a ~1 %
    assert controler(tmp_path / "vues" / r["vue"], p)["ok"]


def test_chaine_complete_detecte_le_doublon(tmp_path, capsys):
    """Deux prises du meme module sous deux angles : la chaine en fait un seul marquage."""
    photos = tmp_path / "photos"
    photos.mkdir()
    for nom, (incl, lacet) in {"A.jpg": (12, 4), "B.jpg": (20, -8)}.items():
        cv2.imwrite(str(photos / nom), synthese.photo_dallage(inclinaison_deg=incl, lacet_deg=lacet))
    travail = tmp_path / "travail"
    assert main(["chaine", "-p", str(PARAMETRES), "-t", str(travail), str(photos)]) == 0
    for f in ("redressement.json", "controle.json", "empreintes.json", "photos.csv", "marquages.csv"):
        assert (travail / f).exists(), f
    with open(travail / "marquages.csv", encoding="utf-8-sig") as f:
        lm = list(csv.DictReader(f, delimiter=";"))
    assert len(lm) == 1 and lm[0]["n_vues"] == "2"
    assert "MEME MODULE" in capsys.readouterr().out


def test_etape_sans_la_precedente_s_arrete(tmp_path):
    with pytest.raises(SystemExit, match="redresser"):
        main(["controler", "-p", str(PARAMETRES), "-t", str(tmp_path)])
