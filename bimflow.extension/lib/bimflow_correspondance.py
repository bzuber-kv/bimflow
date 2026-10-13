# -*- coding: utf-8 -*-
"""bimflow_correspondance - logique pure du bouton Renommer selon table.

Le bouton applique une TABLE DE CORRESPONDANCE au modele actif : noms de
niveaux, de quadrillages, de types de quadrillage, de familles de volumes,
de vues, et les parametres qui en decoulent. La table dit quoi faire ; ce
module verifie qu'elle peut le faire SUR CE MODELE, ligne par ligne, et
calcule le plan. Il n'ecrit rien : le script du bouton est l'adaptateur
Revit.

    categorie;id_revit;ancien_nom;nouveau_nom;parametre;ancienne_valeur;
    nouvelle_valeur;statut;remarque

REGLES (toutes generiques, standard Keovia) :
- seules les lignes au statut « validé » s'appliquent ; les autres sont
  SANS OBJET ;
- controle d'entree : l'element `id_revit` doit porter EXACTEMENT
  `ancien_nom` (et, si la ligne la donne, `ancienne_valeur`), sinon la
  ligne est REFUSEE. Aucune recherche approchee, aucune casse ignoree ;
- un element absent du modele actif rend la ligne SANS OBJET : une meme
  table sert plusieurs maquettes d'un projet ;
- REF_Id n'est jamais ecrit, sauf sur une ligne de volume dont la remarque
  le demande (« REF_Id a regenerer ») ET dont la valeur actuelle est
  portee par au moins un autre volume du modele : un doublon MESURE, pas
  une intention ;
- vues : renommees seulement si leur nom contient un ancien nom de niveau
  renomme, borne par un caractere non alphanumerique ; rien d'autre n'est
  deduit d'un nom de vue. Gabarits de vue signales, jamais renommes.

PYTHON PUR, stdlib seulement, syntaxe 3.4 : tourne sous IronPython 3.4 dans
Revit ET sous CPython 3 pour les tests (tests\\test_bimflow_correspondance.py).

bimflow - Keovia Solutions inc. - 2026-10-13
"""

import re
from collections import OrderedDict

import bimflow_noms as noms
from bimflow_sous_projets import decoder, lire_csv

VERSION = u"2026-10-13b"

COLONNES = (u"categorie", u"id_revit", u"ancien_nom", u"nouveau_nom",
            u"parametre", u"ancienne_valeur", u"nouvelle_valeur", u"statut",
            u"remarque")

STATUT_A_APPLIQUER = u"validé"

NIVEAU = u"niveau"
QUADRILLAGE = u"quadrillage"
VOLUME = u"volume"
ZONE = u"zone"
VUE = u"vue"
TYPE_QUADRILLAGE = u"type de quadrillage"
CATEGORIES = (NIVEAU, QUADRILLAGE, VOLUME, ZONE)
CATEGORIES_RAPPORT = (NIVEAU, QUADRILLAGE, TYPE_QUADRILLAGE, VOLUME, VUE, ZONE)

APPLIQUEE = u"appliquee"
REFUSEE = u"refusee"
SANS_OBJET = u"sans objet"

# Parametres que le bouton sait lire et ecrire, par categorie. Les GUID
# viennent du socle (shared_parameters\keovia_socle_parametres.txt), lus par
# NOM dans le script : aucun GUID ici.
PARAMS_NIVEAU = (u"REF_Batiment", u"REF_Etage")
PARAMS_VOLUME = (u"REF_Zone", u"REF_Etage", u"REF_Batiment", u"REF_Id")
PARAM_TYPE = u"type"

# Caracteres refuses par Revit dans un nom (docs\ecrire_dans_revit.md §2).
CARACTERES_INTERDITS = u"\\:{}[]|;<>?`~"

PREFIXE_TEMPORAIRE = u"TMP_"

# Demande explicite de regeneration de REF_Id, portee par la remarque.
_DEMANDE_REF_ID = re.compile(u"REF_Id\\s+[àa]\\s+r[ée]g[ée]n[ée]rer",
                             re.IGNORECASE | re.UNICODE)

ORDRE_CONSEILLE = (
    u"1. la maquette qui porte les quadrillages : niveaux, quadrillages et "
    u"types de quadrillage ;",
    u"2. la maquette qui porte les volumes : niveaux et volumes ;",
    u"3. les autres maquettes du projet : niveaux et vues seulement.",
    u"Entre deux maquettes : synchroniser, puis relancer la photo maquette "
    u"(verification depuis l'exterieur, R19 fait 6).",
)


# ---------------------------------------------------------------------------
# 1. Lecture de la table
# ---------------------------------------------------------------------------

def lire_table(octets):
    """(lignes, erreurs, encodage). lignes : OrderedDict par ligne de donnees,
    cles = COLONNES + "numero" (numero de ligne du fichier, en-tete = 1).
    Une erreur d'en-tete rend une liste de lignes vide."""
    texte, encodage = decoder(octets)
    brutes = lire_csv(texte)
    if not brutes:
        return [], [u"table vide"], encodage
    entete = tuple(c.strip() for c in brutes[0])
    if entete != COLONNES:
        return [], [u"en-tete inattendu : {0} - attendu : {1}".format(
            u";".join(entete), u";".join(COLONNES))], encodage
    lignes = []
    erreurs = []
    for numero, brute in enumerate(brutes[1:], 2):
        if len(brute) != len(COLONNES):
            erreurs.append(u"ligne {0} : {1} colonne(s) au lieu de {2}".format(
                numero, len(brute), len(COLONNES)))
            continue
        ligne = OrderedDict([(u"numero", numero)])
        for cle, valeur in zip(COLONNES, brute):
            ligne[cle] = valeur.strip()
        lignes.append(ligne)
    return lignes, erreurs, encodage


def categorie_de(texte):
    """Categorie normalisee, ou None. « zone (REF_Zone) » -> zone."""
    t = (texte or u"").strip().lower()
    if t.startswith(ZONE):
        return ZONE
    return t if t in CATEGORIES else None


def demande_ref_id(remarque):
    return bool(_DEMANDE_REF_ID.search(remarque or u""))


def caracteres_interdits(nom):
    return [c for c in nom if c in CARACTERES_INTERDITS]


def _valeurs_multiples(texte):
    """« REF_Batiment / REF_Etage » -> [REF_Batiment, REF_Etage]."""
    return [v.strip() for v in texte.split(u"/")] if texte else []


def _texte(v):
    return u"" if v is None else v


# ---------------------------------------------------------------------------
# 2. Analyse contre le modele
# ---------------------------------------------------------------------------
#
# modele : dict construit par le script, sans aucun objet Revit.
#   niveaux            {id: {"nom", "params": {nom: {"valeur", "ecrivable"}},
#                            "surveillance": texte ou None}}
#   quadrillages       {id: {"nom", "type_id", "surveillance"}}
#   types_quadrillage  {type_id: nom}
#   volumes            {id: {"famille", "famille_id", "in_situ",
#                            "params": {nom: {"valeur", "ecrivable"}}}}
#   familles           {famille_id: nom}   toutes les familles du document
#   vues               {id: {"nom", "gabarit"}}
#   autres             {id: libelle de categorie}  ids de la table presents
#                      dans le modele hors des rubriques ci-dessus
# Un parametre absent de l'element n'a pas de cle dans "params".


class Resultat(object):
    """Verdict d'une ligne de la table (ou d'une vue, ou d'un type)."""

    def __init__(self, categorie, numero=None, id_revit=None, ancien=u"",
                 nouveau=u""):
        self.categorie = categorie
        self.numero = numero
        self.id_revit = id_revit
        self.ancien = ancien
        self.nouveau = nouveau
        self.verdict = APPLIQUEE
        self.motifs = []
        self.operations = []

    def refuser(self, motif):
        self.verdict = REFUSEE
        self.motifs.append(motif)

    def sans_objet(self, motif):
        if self.verdict != REFUSEE:
            self.verdict = SANS_OBJET
        self.motifs.append(motif)

    def en_dict(self):
        return OrderedDict([
            (u"categorie", self.categorie), (u"ligne", self.numero),
            (u"id", self.id_revit), (u"ancien_nom", self.ancien),
            (u"nouveau_nom", self.nouveau), (u"resultat", self.verdict),
            (u"motifs", list(self.motifs)),
            (u"operations", list(self.operations))])


class Analyse(object):
    def __init__(self):
        self.resultats = []          # Resultat, dans l'ordre de la table
        self.vues = []               # Resultat des vues
        self.types = []              # Resultat des types de quadrillage
        self.avertissements = []
        # Operations retenues, par espace de noms : {id: (avant, apres)}
        self.renommages = OrderedDict([
            (u"niveaux", OrderedDict()), (u"quadrillages", OrderedDict()),
            (u"types_quadrillage", OrderedDict()),
            (u"familles", OrderedDict()), (u"vues", OrderedDict())])
        self.retypages = OrderedDict()    # id quadrillage -> (type avant, type apres)
        self.parametres = []              # (id, nom, avant, apres)

    def refus(self):
        return [r for r in self.tous() if r.verdict == REFUSEE]

    def tous(self):
        return self.resultats + self.types + self.vues

    def comptes(self):
        c = OrderedDict()
        for cat in CATEGORIES_RAPPORT:
            c[cat] = OrderedDict([(APPLIQUEE, 0), (REFUSEE, 0),
                                  (SANS_OBJET, 0)])
        for r in self.tous():
            c.setdefault(r.categorie, OrderedDict([
                (APPLIQUEE, 0), (REFUSEE, 0), (SANS_OBJET, 0)]))
            c[r.categorie][r.verdict] += 1
        return c

    def nb_operations(self):
        return (sum(len(v) for v in self.renommages.values())
                + len(self.retypages) + len(self.parametres))


def _parametre(element, nom):
    return (element.get(u"params") or {}).get(nom)


_ENTIER = re.compile(u"^-?[0-9]+$")


def id_entier(texte):
    """Entier, ou None. Ne leve JAMAIS : sous IronPython interprete, une
    exception attrapee dans une boucle s'empile sur la precedente et finit
    par tuer Revit (mesure du 2026-10-13, docs\\ecrire_dans_revit.md §8)."""
    if texte is None or not _ENTIER.match(texte.strip()):
        return None
    return int(texte.strip())


def analyser(lignes, modele):
    """Analyse complete de la table contre le modele. Rend une Analyse."""
    a = Analyse()
    niveaux = modele.get(u"niveaux", {})
    quadrillages = modele.get(u"quadrillages", {})
    volumes = modele.get(u"volumes", {})
    autres = modele.get(u"autres", {})

    zones = OrderedDict()          # ancienne zone -> (nouvelle, numero)
    for l in lignes:
        if (categorie_de(l[u"categorie"]) == ZONE
                and l[u"statut"] == STATUT_A_APPLIQUER and l[u"ancien_nom"]):
            zones[l[u"ancien_nom"]] = (l[u"nouveau_nom"], l[u"numero"])

    ids_vus = {}
    grilles = []                   # (Resultat, ligne) des quadrillages retenus

    for l in lignes:
        cat = categorie_de(l[u"categorie"])
        r = Resultat(cat or l[u"categorie"], l[u"numero"], l[u"id_revit"],
                     l[u"ancien_nom"], l[u"nouveau_nom"])
        a.resultats.append(r)

        if l[u"statut"] != STATUT_A_APPLIQUER:
            r.sans_objet(u"statut « {0} »".format(l[u"statut"]))
            continue
        if cat is None:
            r.refuser(u"categorie « {0} » inconnue - admises : {1}".format(
                l[u"categorie"], u", ".join(CATEGORIES)))
            continue
        if cat == ZONE:
            r.sans_objet(u"table de reference des zones : aucun element, "
                         u"sert au controle des volumes")
            continue

        eid = id_entier(l[u"id_revit"])
        if eid is None:
            r.refuser(u"id_revit « {0} » absent ou non entier".format(
                l[u"id_revit"]))
            continue
        r.id_revit = eid
        if eid in ids_vus:
            r.refuser(u"id {0} deja traite ligne {1}".format(eid, ids_vus[eid]))
            continue
        ids_vus[eid] = l[u"numero"]

        rubrique = {NIVEAU: niveaux, QUADRILLAGE: quadrillages,
                    VOLUME: volumes}[cat]
        element = rubrique.get(eid)
        if element is None:
            if eid in autres:
                r.refuser(u"l'element {0} existe mais n'est pas un(e) {1} "
                          u"({2})".format(eid, cat, autres[eid]))
            else:
                r.sans_objet(u"element {0} absent de cette maquette".format(eid))
            continue

        actuel = element.get(u"famille") if cat == VOLUME else element.get(u"nom")
        if actuel != l[u"ancien_nom"]:
            r.refuser(u"l'element {0} porte « {1} », la table attend « {2} »"
                      .format(eid, _texte(actuel), l[u"ancien_nom"]))
            continue
        if not l[u"nouveau_nom"]:
            r.refuser(u"nouveau_nom vide")
            continue
        interdits = caracteres_interdits(l[u"nouveau_nom"])
        if interdits:
            r.refuser(u"nouveau_nom « {0} » : caractere(s) refuse(s) par Revit "
                      u": {1}".format(l[u"nouveau_nom"], u" ".join(interdits)))
            continue

        if cat == NIVEAU:
            _niveau(a, r, l, eid, element)
        elif cat == QUADRILLAGE:
            _quadrillage(a, r, l, eid, element, modele)
            if r.verdict == APPLIQUEE:
                grilles.append((r, l))
        else:
            _volume(a, r, l, eid, element, zones, modele)

    _types_quadrillage(a, grilles, modele)
    _vues(a, modele)
    _collisions(a, modele)
    _reporter_refus_des_operations(a)
    return a


def _surveillance(a, r, element, quoi):
    s = element.get(u"surveillance")
    if s:
        a.avertissements.append(
            u"{0} {1} « {2} » : relation Copier/Controler ({3}) - signalee, "
            u"non modifiee".format(quoi, r.id_revit, r.ancien, s))


def _niveau(a, r, l, eid, element):
    param = l[u"parametre"]
    if param:
        if param not in PARAMS_NIVEAU:
            r.refuser(u"parametre « {0} » non pris en charge pour un niveau "
                      u"({1})".format(param, u", ".join(PARAMS_NIVEAU)))
            return
        p = _parametre(element, param)
        if p is None:
            r.refuser(u"{0} absent du niveau (non lie, ou lie sous un autre "
                      u"GUID)".format(param))
            return
        if _texte(p.get(u"valeur")) != l[u"ancienne_valeur"]:
            r.refuser(u"{0} vaut « {1} », la table attend « {2} »".format(
                param, _texte(p.get(u"valeur")), l[u"ancienne_valeur"]))
            return
        if l[u"nouvelle_valeur"] != _texte(p.get(u"valeur")):
            if not p.get(u"ecrivable", True):
                r.refuser(u"{0} en lecture seule".format(param))
                return
            a.parametres.append((eid, param, _texte(p.get(u"valeur")),
                                 l[u"nouvelle_valeur"]))
            r.operations.append(u"{0} : « {1} » -> « {2} »".format(
                param, _texte(p.get(u"valeur")), l[u"nouvelle_valeur"]))
    if l[u"nouveau_nom"] != l[u"ancien_nom"]:
        a.renommages[u"niveaux"][eid] = (l[u"ancien_nom"], l[u"nouveau_nom"])
        r.operations.append(u"nom : « {0} » -> « {1} »".format(
            l[u"ancien_nom"], l[u"nouveau_nom"]))
    if not r.operations:
        r.sans_objet(u"deja conforme")
    _surveillance(a, r, element, u"niveau")


def _quadrillage(a, r, l, eid, element, modele):
    param = l[u"parametre"]
    if param and param != PARAM_TYPE:
        r.refuser(u"parametre « {0} » non pris en charge pour un quadrillage "
                  u"(seul « {1} »)".format(param, PARAM_TYPE))
        return
    if param:
        type_actuel = modele.get(u"types_quadrillage", {}).get(
            element.get(u"type_id"))
        if type_actuel != l[u"ancienne_valeur"]:
            r.refuser(u"type « {0} », la table attend « {1} »".format(
                _texte(type_actuel), l[u"ancienne_valeur"]))
            return
        if not l[u"nouvelle_valeur"]:
            r.refuser(u"nouvelle_valeur (type) vide")
            return
    if l[u"nouveau_nom"] != l[u"ancien_nom"]:
        a.renommages[u"quadrillages"][eid] = (l[u"ancien_nom"],
                                              l[u"nouveau_nom"])
        r.operations.append(u"nom : « {0} » -> « {1} »".format(
            l[u"ancien_nom"], l[u"nouveau_nom"]))
    _surveillance(a, r, element, u"quadrillage")


def _types_quadrillage(a, grilles, modele):
    """Plan des types de quadrillage, a partir des lignes retenues.

    Pour chaque type, les cibles demandees par ses quadrillages :
    - une seule cible : le type est RENOMME ;
    - plusieurs cibles : les quadrillages dont la cible est le nom final
      d'un AUTRE type (renomme, ou existant et non renomme) changent de
      type ; s'il reste exactement une cible, le type est renomme vers
      elle ; sinon les lignes restantes sont refusees.
    Deux types vers une meme cible : refuse, aucune fusion n'est deduite."""
    types = modele.get(u"types_quadrillage", {})
    quadrillages = modele.get(u"quadrillages", {})
    cibles = OrderedDict()        # type_id -> OrderedDict(cible -> [(r, l)])
    for r, l in grilles:
        if not l[u"parametre"]:
            continue
        tid = quadrillages[r.id_revit][u"type_id"]
        cibles.setdefault(tid, OrderedDict()).setdefault(
            l[u"nouvelle_valeur"], []).append((r, l))

    uniques = OrderedDict()       # type_id -> cible unique
    for tid, par_cible in cibles.items():
        if len(par_cible) == 1:
            uniques[tid] = list(par_cible.keys())[0]

    porteurs = {}                 # cible -> [type_id renommes vers elle]
    for tid, cible in uniques.items():
        porteurs.setdefault(cible, []).append(tid)
    for cible, tids in porteurs.items():
        if len(tids) > 1:
            for tid in tids:
                rt = Resultat(TYPE_QUADRILLAGE, None, tid, types.get(tid), cible)
                rt.refuser(u"{0} types demandent le meme nom final « {1} » : "
                           u"aucune fusion n'est deduite".format(len(tids),
                                                                 cible))
                a.types.append(rt)
                for r, l in cibles[tid][cible]:
                    r.refuser(u"type cible « {0} » demande par plusieurs types"
                              .format(cible))
                del uniques[tid]

    renommes = dict((tid, c) for tid, c in uniques.items())
    finaux = {}                   # nom final -> type_id qui le portera
    for tid, nom in types.items():
        if tid not in renommes and tid not in cibles:
            finaux[nom] = tid
    for tid, c in renommes.items():
        finaux[c] = tid

    for tid, par_cible in cibles.items():
        if tid in uniques or len(par_cible) == 1:
            continue
        restantes = []
        for cible, groupe in par_cible.items():
            dest = finaux.get(cible)
            if dest is not None and dest != tid:
                for r, l in groupe:
                    a.retypages[r.id_revit] = (tid, dest)
                    r.operations.append(
                        u"type : « {0} » -> type existant « {1} » (id {2}), "
                        u"qui portera ce nom".format(types.get(tid), cible,
                                                     dest))
            else:
                restantes.append(cible)
        if len(restantes) == 1:
            renommes[tid] = restantes[0]
            finaux[restantes[0]] = tid
        elif restantes:
            rt = Resultat(TYPE_QUADRILLAGE, None, tid, types.get(tid),
                          u" | ".join(restantes))
            rt.refuser(u"plusieurs cibles sans type pour les porter : {0}"
                       .format(u", ".join(restantes)))
            a.types.append(rt)
            for cible in restantes:
                for r, l in par_cible[cible]:
                    r.refuser(u"type « {0} » : cibles multiples non resolues"
                              .format(types.get(tid)))

    ids_retenus = set(r.id_revit for r, l in grilles if r.verdict == APPLIQUEE)
    for tid, cible in renommes.items():
        rt = Resultat(TYPE_QUADRILLAGE, None, tid, types.get(tid), cible)
        if cible == types.get(tid):
            rt.sans_objet(u"deja a son nom final")
        else:
            a.renommages[u"types_quadrillage"][tid] = (types.get(tid), cible)
            rt.operations.append(u"nom : « {0} » -> « {1} »".format(
                types.get(tid), cible))
            hors = sorted(q for q, d in quadrillages.items()
                          if d.get(u"type_id") == tid and q not in ids_retenus
                          and q not in a.retypages)
            if hors:
                a.avertissements.append(
                    u"type « {0} » renomme « {1} » : il porte aussi {2} "
                    u"quadrillage(s) hors table ou non retenus ({3})".format(
                        types.get(tid), cible, len(hors),
                        u", ".join(u"{0}".format(h) for h in hors)))
        a.types.append(rt)

    for r, l in grilles:
        if r.verdict == APPLIQUEE and not r.operations:
            tid = quadrillages[r.id_revit][u"type_id"]
            if tid in a.renommages[u"types_quadrillage"]:
                r.operations.append(u"type renomme avec les autres "
                                    u"quadrillages de ce type")
            else:
                r.sans_objet(u"deja conforme")


def _volume(a, r, l, eid, element, zones, modele):
    if element.get(u"in_situ") is not True:
        r.refuser(u"volume qui n'est pas une famille in situ")
        return
    lu, refus = noms.lire(l[u"nouveau_nom"])
    if lu is None:
        r.refuser(u"nouveau_nom hors motif : {0}".format(refus))
        return
    zone, etage, _nature, cle = lu
    if cle in noms.CLES_BATIMENT:
        r.refuser(u"cle de batiment « {0} » en fin de nom : regle caduque, "
                  u"REF_Batiment = secteur de la colonne".format(cle))
        return
    calcule = OrderedDict([(u"REF_Zone", zone), (u"REF_Etage", etage),
                           (u"REF_Batiment", noms.prefixe_de_zone(zone))])

    # La table et le nom doivent dire la meme chose.
    params = _valeurs_multiples(l[u"parametre"])
    avant = _valeurs_multiples(l[u"ancienne_valeur"])
    apres = _valeurs_multiples(l[u"nouvelle_valeur"])
    if params and not (len(params) == len(avant) == len(apres)):
        r.refuser(u"parametre / ancienne_valeur / nouvelle_valeur : nombres "
                  u"de valeurs differents ({0}, {1}, {2})".format(
                      len(params), len(avant), len(apres)))
        return
    for nom, v_avant, v_apres in zip(params, avant, apres):
        if nom not in calcule:
            r.refuser(u"parametre « {0} » non pris en charge pour un volume "
                      u"({1})".format(nom, u", ".join(calcule.keys())))
            return
        p = _parametre(element, nom)
        if p is None:
            r.refuser(u"{0} absent du volume".format(nom))
            return
        if _texte(p.get(u"valeur")) != v_avant:
            r.refuser(u"{0} vaut « {1} », la table attend « {2} »".format(
                nom, _texte(p.get(u"valeur")), v_avant))
            return
        if calcule[nom] != v_apres:
            r.refuser(u"{0} : la table dit « {1} », le nouveau nom donne "
                      u"« {2} »".format(nom, v_apres, calcule[nom]))
            return

    # Controle croise avec la table des zones, si elle existe.
    segments = l[u"ancien_nom"].split(noms.SEPARATEUR)
    ancienne_zone = segments[1] if len(segments) > 1 else None
    if zones:
        if ancienne_zone in zones:
            attendue = zones[ancienne_zone][0]
            if attendue != zone:
                r.refuser(u"zone « {0} » -> « {1} » selon la table des zones "
                          u"(ligne {2}), le nouveau nom donne « {3} »".format(
                              ancienne_zone, attendue, zones[ancienne_zone][1],
                              zone))
                return
        else:
            a.avertissements.append(
                u"volume {0} : zone « {1} » absente de la table des zones"
                .format(eid, _texte(ancienne_zone)))
    p_zone = _parametre(element, u"REF_Zone")
    if p_zone is not None and ancienne_zone is not None and \
            _texte(p_zone.get(u"valeur")) != ancienne_zone:
        a.avertissements.append(
            u"volume {0} : REF_Zone « {1} » differe du segment de zone de "
            u"l'ancien nom « {2} »".format(eid, _texte(p_zone.get(u"valeur")),
                                            ancienne_zone))

    ecritures = []
    for nom, valeur in calcule.items():
        p = _parametre(element, nom)
        if p is None:
            r.refuser(u"{0} absent du volume".format(nom))
            return
        if _texte(p.get(u"valeur")) == valeur:
            continue
        if not p.get(u"ecrivable", True):
            r.refuser(u"{0} en lecture seule".format(nom))
            return
        ecritures.append((eid, nom, _texte(p.get(u"valeur")), valeur))

    if demande_ref_id(l[u"remarque"]):
        p = _parametre(element, u"REF_Id")
        actuel = _texte(p.get(u"valeur")) if p else u""
        if p is None:
            r.refuser(u"REF_Id a regenerer, mais absent du volume")
            return
        if not p.get(u"ecrivable", True):
            r.refuser(u"REF_Id en lecture seule")
            return
        cle_id = actuel.strip().lower()
        autres = [vid for vid, v in modele.get(u"volumes", {}).items()
                  if vid != eid and cle_id and _texte(
                      (_parametre(v, u"REF_Id") or {}).get(u"valeur"))
                  .strip().lower() == cle_id]
        if not autres:
            r.refuser(u"REF_Id a regenerer, mais « {0} » n'est porte par "
                      u"aucun autre volume : pas de doublon mesure, REF_Id "
                      u"ne se regenere pas".format(actuel))
            return
        ecritures.append((eid, u"REF_Id", actuel, None))   # None = uuid4
        r.operations.append(u"REF_Id : doublon de {0} -> nouvel uuid4".format(
            u", ".join(u"{0}".format(x) for x in sorted(autres))))

    if l[u"nouveau_nom"] != l[u"ancien_nom"]:
        a.renommages[u"familles"][element[u"famille_id"]] = (
            l[u"ancien_nom"], l[u"nouveau_nom"])
        r.operations.insert(0, u"famille : « {0} » -> « {1} »".format(
            l[u"ancien_nom"], l[u"nouveau_nom"]))
    for e in ecritures:
        if e[1] != u"REF_Id":
            r.operations.append(u"{0} : « {1} » -> « {2} »".format(
                e[1], e[2], e[3]))
    a.parametres.extend(ecritures)
    if not r.operations:
        r.sans_objet(u"deja conforme")


def _motif_nom(ancien):
    return re.compile(u"(?<![A-Za-z0-9])" + re.escape(ancien) +
                      u"(?![A-Za-z0-9])")


def nouveau_nom_de_vue(nom, correspondances):
    """(nouveau nom ou None, motif de refus ou None).

    correspondances : {ancien nom de niveau: nouveau}. Un ancien nom compte
    s'il apparait borne par un caractere non alphanumerique (ou le debut, ou
    la fin). Deux occurrences qui se chevauchent : refus, rien n'est
    deduit."""
    trouves = []
    for ancien in correspondances:
        for m in _motif_nom(ancien).finditer(nom):
            trouves.append((m.start(), m.end(), ancien))
    if not trouves:
        return None, None
    trouves.sort()
    for (d1, f1, a1), (d2, f2, a2) in zip(trouves, trouves[1:]):
        if d2 < f1:
            return None, (u"« {0} » et « {1} » se chevauchent dans le nom : "
                          u"ambigu".format(a1, a2))
    resultat = nom
    for debut, fin, ancien in reversed(trouves):
        resultat = resultat[:debut] + correspondances[ancien] + resultat[fin:]
    return resultat, None


def _vues(a, modele):
    correspondances = OrderedDict(
        (avant, apres) for avant, apres in a.renommages[u"niveaux"].values())
    if not correspondances:
        return
    for vid, v in sorted(modele.get(u"vues", {}).items()):
        if not v.get(u"nom"):
            continue
        nouveau, refus = nouveau_nom_de_vue(v[u"nom"], correspondances)
        if nouveau is None and refus is None:
            continue
        r = Resultat(VUE, None, vid, v[u"nom"], nouveau or u"")
        if v.get(u"gabarit"):
            r.sans_objet(u"gabarit de vue : signale, jamais renomme")
            a.avertissements.append(
                u"gabarit de vue {0} « {1} » contient un ancien nom de niveau "
                u"- non renomme".format(vid, v[u"nom"]))
        elif refus:
            r.refuser(refus)
        else:
            a.renommages[u"vues"][vid] = (v[u"nom"], nouveau)
            r.operations.append(u"nom : « {0} » -> « {1} »".format(
                v[u"nom"], nouveau))
        a.vues.append(r)


def _noms_existants(modele, espace):
    """{id: nom} de tout l'espace de noms ou Revit impose l'unicite."""
    if espace == u"niveaux":
        return dict((i, d[u"nom"]) for i, d in modele.get(u"niveaux", {}).items())
    if espace == u"quadrillages":
        return dict((i, d[u"nom"])
                    for i, d in modele.get(u"quadrillages", {}).items())
    if espace == u"types_quadrillage":
        return dict(modele.get(u"types_quadrillage", {}))
    if espace == u"familles":
        return dict(modele.get(u"familles", {}))
    return dict((i, d[u"nom"]) for i, d in modele.get(u"vues", {}).items())


def nom_temporaire(eid):
    return u"{0}{1}".format(PREFIXE_TEMPORAIRE, eid)


def _collisions(a, modele):
    """Unicite des noms finaux, et des noms temporaires de la passe 1, AVANT
    toute transaction. Les vues se comparent a TOUTES les vues : plus strict
    que Revit, jamais moins."""
    for espace, renommages in a.renommages.items():
        existants = _noms_existants(modele, espace)
        finaux = {}
        for i, nom in existants.items():
            finaux[nom] = i
        for i in renommages:
            if finaux.get(existants.get(i)) == i:
                del finaux[existants[i]]
        conflits = {}
        for i, (avant, apres) in renommages.items():
            tenant = finaux.get(apres)
            if tenant is not None and tenant != i:
                conflits[i] = u"nom final « {0} » deja porte par {1}".format(
                    apres, tenant)
            else:
                finaux[apres] = i
        tous = set(existants.values()) | set(
            apres for avant, apres in renommages.values())
        for i in renommages:
            if nom_temporaire(i) in tous:
                conflits[i] = u"nom temporaire « {0} » deja pris".format(
                    nom_temporaire(i))
        for i, motif in conflits.items():
            _refuser_operation(a, espace, i, motif)


def _refuser_operation(a, espace, i, motif):
    for r in a.tous():
        if r.verdict != APPLIQUEE:
            continue
        if espace == u"familles" and r.categorie == VOLUME:
            if a.renommages[u"familles"].get(i, (None,))[0] == r.ancien:
                r.refuser(motif)
        elif (r.id_revit == i and
              {u"niveaux": NIVEAU, u"quadrillages": QUADRILLAGE,
               u"types_quadrillage": TYPE_QUADRILLAGE,
               u"vues": VUE}.get(espace) == r.categorie):
            r.refuser(motif)


def _reporter_refus_des_operations(a):
    """Une ligne refusee ne laisse aucune operation au plan : le plan ne
    contient que ce qui serait reellement ecrit."""
    refuses = dict()
    for r in a.tous():
        if r.verdict == REFUSEE and r.id_revit is not None:
            refuses.setdefault(r.categorie, set()).add(r.id_revit)
    for cat, espace in ((NIVEAU, u"niveaux"), (QUADRILLAGE, u"quadrillages"),
                        (TYPE_QUADRILLAGE, u"types_quadrillage"),
                        (VUE, u"vues")):
        for i in refuses.get(cat, ()):
            a.renommages[espace].pop(i, None)
    vol_refuses = set(r.ancien for r in a.resultats
                      if r.categorie == VOLUME and r.verdict == REFUSEE)
    for fid, (avant, apres) in list(a.renommages[u"familles"].items()):
        if avant in vol_refuses:
            del a.renommages[u"familles"][fid]
    exclus = refuses.get(NIVEAU, set()) | refuses.get(VOLUME, set())
    a.parametres = [p for p in a.parametres if p[0] not in exclus]
    for i in refuses.get(QUADRILLAGE, ()):
        a.retypages.pop(i, None)


# ---------------------------------------------------------------------------
# 3. Rapport
# ---------------------------------------------------------------------------

def rapport(analyse, en_tete, ecriture=None):
    """OrderedDict pret pour le JSON. en_tete : dict du script (outil,
    modele, date, mode, table...). ecriture : dict du resultat d'ecriture,
    ou None en simulation."""
    d = OrderedDict()
    d[u"en_tete"] = en_tete
    d[u"ordre_conseille"] = list(ORDRE_CONSEILLE)
    d[u"comptes"] = analyse.comptes()
    d[u"operations_prevues"] = OrderedDict([
        (u"renommages", OrderedDict((k, len(v)) for k, v in
                                    analyse.renommages.items())),
        (u"changements_de_type", len(analyse.retypages)),
        (u"parametres", len(analyse.parametres))])
    d[u"ecriture"] = ecriture
    d[u"avertissements"] = list(analyse.avertissements)
    d[u"refusees"] = [r.en_dict() for r in analyse.refus()]
    d[u"appliquees"] = [r.en_dict() for r in analyse.tous()
                        if r.verdict == APPLIQUEE]
    d[u"sans_objet"] = [r.en_dict() for r in analyse.tous()
                        if r.verdict == SANS_OBJET]
    return d


def nom_rapport(nom_table, titre_modele, horodatage, mode):
    """<table>_rapport_<modele>_<AAAA-MM-JJ_HHMM>_<simulation|reel>.json :
    une simulation et une ecriture ne portent jamais le meme nom (R19 fait 6,
    corollaire)."""
    base = nom_table
    if base.lower().endswith(u".csv"):
        base = base[:-4]
    modele = re.sub(u'[\\\\/:*?"<>|\\s]+', u"_", titre_modele or u"modele")
    return u"{0}_rapport_{1}_{2}_{3}.json".format(base, modele, horodatage, mode)
