# -*- coding: utf-8 -*-
"""Retire les parametres de projet morts, apres migration des valeurs a garder.

Outil ORANGE : il ecrit dans la maquette, et une suppression de liaison EFFACE
les valeurs. Rien n'est supprime sans avoir ete affiche d'abord.

Trois protections, cumulees :
  1. un parametre qui porte au moins une valeur n'est jamais propose ;
  2. un parametre utilise comme champ de nomenclature ou dans un filtre de vue
     n'est jamais propose ;
  3. un parametre nomme dans PROTEGES n'est jamais propose.

Les parametres de MIGRATIONS font exception a la protection 1 : leurs valeurs
sont d'abord recopiees vers le parametre du socle, puis l'ancien est retire.

pyRevit v6.5.5 / IronPython 3.4.2 (IPY342) - pas de f-string, pas de shebang.
"""

__title__ = "Nettoyage\nparametres"
__author__ = "Keovia Solutions inc."

VERSION = u"2026-09-19n"

from pyrevit import revit, forms, script

from Autodesk.Revit.DB import (
    FilteredElementCollector, ParameterFilterElement, StorageType,
    Transaction, View, ViewSchedule,
)

doc = revit.doc
out = script.get_output()

# ---------------------------------------------------------------------------
# Socle Keovia. Modifier ici, jamais dans le corps du script.
# ---------------------------------------------------------------------------

# Partages : un GUID a vie, dans keovia_socle_parametres.txt.
SOCLE_PARTAGE = [
    "REF_Batiment", "REF_Etage", "REF_Id",
    "CLS_Usage", "CLS_Nature_volume",
]

# De projet : portes par le gabarit, absents du fichier partage. Rien hors du
# document ne doit les reconnaitre.
SOCLE_PROJET = [
    "DOC_Classement_vue", "DOC_Classement_feuille", "DOC_Sous_discipline",
]

SOCLE = SOCLE_PARTAGE + SOCLE_PROJET

# (ancien parametre local, parametre du socle) : les valeurs sont recopiees,
# puis l'ancien est retire. Le parametre du socle doit deja etre lie.
# Vide depuis le 2026-09-19 : la migration des « Classement » est abandonnee.
# Mesure a l'origine de la decision — 171 vues recopiees, 67 miroirs (fenetre
# de vue, camera, repere) et 35 vraies vues dont la cible restait en lecture
# seule, sans explication. Le gain etait un nom ; le risque, le classement de
# 35 vues. « Classement Vues » et « Classement Feuille » restent maitres.
MIGRATIONS = []

# Jamais propose a la suppression, meme vide. A garder court et justifie.
PROTEGES = set(SOCLE) | set([a for a, _b in MIGRATIONS]) | set([
    u"DOC_Classement_vue",      # maitre du classement de l'arborescence
    u"DOC_Classement_feuille",
    u"DOC_Sous_discipline",
    u"Classement Vues",         # noms d'avant le renommage, au cas ou
    u"Classement Feuille",
    u"Sous-discipline",
])

# SACRIFICES — retires MALGRE leurs valeurs, parce qu'on l'a decide en
# connaissance de cause. Chaque ligne porte le compte mesure : perdre une
# valeur exige de l'avoir nommee et chiffree d'abord. Vider cette liste
# remet la protection 1 en vigueur.
SACRIFICES = {
    u"Niveau": u"1311 valeurs, 5 niveaux sur 23 — collision de nom avec le "
               u"natif Niveau, aucune nomenclature ni filtre ne le lit, et "
               u"l'audit B18 porte deja la vraie reference de niveau",
    u"NGF.Reference": u"3 valeurs a zero sur 1354 porteurs — une altitude de "
                      u"reference dans un parametre, ce que la §7.8 ecarte",
    u"CLASSIFICATION": u"3 valeurs (CVC) sur 1294 porteurs, 81 categories — "
                       u"et collision de nom avec le natif Classification",
    u"CLASSIFICATION_Type": u"3 valeurs (CVC) sur 1294 porteurs, 81 categories",
}


def retirer(definition, voie_forte=True):
    """Retire un parametre de projet. Retourne (reussi, comment).

    Deux voies, et il en faut deux — correlation mesuree sur thestudy_CO_BAT
    le 2026-09-19 : les 47 parametres PARTAGES sont partis par Remove(), les
    11 parametres de projet NON PARTAGES ont tous ete refuses par Remove() et
    partent en supprimant leur element de definition, exactement comme le fait
    le bouton Supprimer de la boite de dialogue Parametres du projet.
    """
    try:
        if doc.ParameterBindings.Remove(definition):
            return True, u"liaison retiree"
    except Exception as err:
        return False, u"retrait de liaison : " + str(err)

    if not voie_forte:
        # Supprimer la definition contourne les protections de Revit et
        # pourrait casser en silence le classement de l'arborescence.
        # On s'arrete et on laisse la main.
        return False, u"retrait de liaison refuse, et la voie forte est "\
                      u"interdite ici"

    try:
        efface = doc.Delete(definition.Id)
    except Exception as err:
        return False, u"suppression de la definition refusee : " + str(err)

    n = 0
    try:
        n = efface.Count
    except Exception:
        try:
            n = len(efface)
        except Exception:
            n = 1 if efface is not None else 0
    if n > 0:
        return True, u"definition supprimee (parametre non partage)"
    return False, u"Revit a refuse les deux voies"


def nom_sur(binding):
    noms = []
    try:
        for c in binding.Categories:
            noms.append(c.Name)
    except Exception:
        pass
    return sorted(noms)


# ---------------------------------------------------------------------------
# 1. Liaisons, et ce qui les utilise
# ---------------------------------------------------------------------------

try:
    if doc.IsWorkshared and not doc.IsDetached:
        if not forms.alert(
            u"Cette maquette est COLLABORATIVE et n'est pas detachee.\n\n"
            u"Si le modele central est inaccessible, Revit refusera les "
            u"suppressions AU MOMENT DE LA VALIDATION, et certaines passeront "
            u"quand meme : la maquette se retrouve a moitie nettoyee.\n\n"
            u"Un essai se fait sur une copie detachee :\n"
            u"Ouvrir → cocher « Detacher du central ».\n\n"
            u"Continuer quand meme ?",
            title=u"Maquette collaborative", yes=True, no=True,
        ):
            script.exit()
except Exception:
    pass

params = {}
it = doc.ParameterBindings.ForwardIterator()
it.Reset()
while it.MoveNext():
    d = it.Key
    params[d.Name] = {
        "definition": d,
        "id": d.Id,
        "categories": nom_sur(it.Current),
        "remplis": 0,
        "total": 0,
    }

if not params:
    forms.alert(u"Aucun parametre de projet dans cette maquette.", exitscript=True)

ids_utilises = set()
detail_usage = {}

for vs in list(FilteredElementCollector(doc).OfClass(ViewSchedule).ToElements()):
    try:
        definition = vs.Definition
        ordre = definition.GetFieldOrder()
    except Exception:
        continue
    for fid in ordre:
        try:
            pid = definition.GetField(fid).ParameterId
        except Exception:
            continue
        if pid is None:
            continue
        ids_utilises.add(pid.Value)
        try:
            nom_vs = vs.Name
        except Exception:
            nom_vs = u"?"
        detail_usage.setdefault(pid.Value, set()).add(
            u"nomenclature « " + nom_vs + u" »")

arbo_lue = True
try:
    from Autodesk.Revit.DB import BrowserOrganization, View
    orgs = []
    for accesseur in ("GetCurrentBrowserOrganizationForViews",
                      "GetCurrentBrowserOrganizationForSheets"):
        try:
            o = getattr(BrowserOrganization, accesseur)(doc)
        except Exception:
            continue
        if o is not None:
            orgs.append(o)
    vues = [v for v in list(FilteredElementCollector(doc).OfClass(View).ToElements())
            if not v.IsTemplate]
    for o in orgs:
        lue = False
        for v in vues:
            try:
                for info in o.GetFolderItems(v.Id):
                    pid = info.ElementId
                    if pid is None:
                        continue
                    ids_utilises.add(pid.Value)
                    detail_usage.setdefault(pid.Value, set()).add(u"arborescence")
                lue = True
                break
            except Exception:
                continue
        if not lue:
            arbo_lue = False
    if not orgs:
        arbo_lue = False
except Exception:
    arbo_lue = False

def ids_de_regles(regles, acc):
    for r in regles:
        interne = r
        try:
            interne = r.GetInnerRule()      # FilterInverseRule
        except Exception:
            pass
        try:
            acc.add(interne.GetRuleParameter().Value)
        except Exception:
            continue


def ids_de_filtre(ef, acc):
    """Descend l'arbre d'un ElementFilter et releve les parametres cites."""
    if ef is None:
        return
    try:
        sous = ef.GetFilters()               # Logical And / Or
    except Exception:
        sous = None
    if sous:
        for s in sous:
            ids_de_filtre(s, acc)
        return
    try:
        ids_de_regles(ef.GetRules(), acc)    # ElementParameterFilter
    except Exception:
        return


# Revit 2024+ a retire ParameterFilterElement.GetRules() au profit de
# GetElementFilter(). On tente l'ancien, puis le nouveau, filtre par filtre.
filtres_lus = True
try:
    for pfe in list(FilteredElementCollector(doc)
                    .OfClass(ParameterFilterElement).ToElements()):
        acc = set()
        lu = False
        try:
            ids_de_regles(pfe.GetRules(), acc)
            lu = True
        except Exception:
            lu = False
        if not lu:
            try:
                ids_de_filtre(pfe.GetElementFilter(), acc)
                lu = True
            except Exception:
                lu = False
        if not lu:
            filtres_lus = False
            continue
        try:
            nom_pfe = pfe.Name
        except Exception:
            nom_pfe = u"?"
        for v in acc:
            ids_utilises.add(v)
            detail_usage.setdefault(v, set()).add(
                u"filtre « " + nom_pfe + u" »")
except Exception:
    filtres_lus = False


# ---------------------------------------------------------------------------
# 2. Mesurer le remplissage
# ---------------------------------------------------------------------------

par_categorie = {}
for nom, p in params.items():
    for nom_cat in p["categories"]:
        par_categorie.setdefault(nom_cat, []).append(p)


def a_une_valeur(p):
    try:
        st = p.StorageType
    except Exception:
        return False
    if st == StorageType.String:
        v = p.AsString()
        return bool(v and v.strip())
    if st == StorageType.ElementId:
        try:
            eid = p.AsElementId()
        except Exception:
            return False
        return eid is not None and eid.Value >= 0
    try:
        if not p.HasValue:
            return False
        v = p.AsValueString()
    except Exception:
        return False
    return bool(v and v.strip())


tous_les_params = list(params.values())


def parcourir(collecteur):
    # R15 : materialiser AVANT de resoudre la moindre propriete.
    for el in list(collecteur.ToElements()):
        try:
            cat = el.Category
        except Exception:
            cat = None
        if cat is None:
            # Category vaut null sur beaucoup de vues, de feuilles et de
            # nomenclatures. Les ignorer sous-comptait le remplissage : on les
            # passe au crible complet, ils ne sont pas nombreux.
            cibles = tous_les_params
        else:
            cibles = par_categorie.get(cat.Name)
        if not cibles:
            continue
        for p in cibles:
            try:
                param = el.LookupParameter(p["definition"].Name)
            except Exception:
                continue
            if param is None:
                continue
            p["total"] += 1
            if a_une_valeur(param):
                p["remplis"] += 1


out.print_md(u"# Nettoyage des parametres de projet")
out.print_md(u"**Version de l'outil** : `" + VERSION + u"`")
out.print_md(u"**Maquette** : `" + doc.Title + u"`")
parcourir(FilteredElementCollector(doc).WhereElementIsNotElementType())
parcourir(FilteredElementCollector(doc).WhereElementIsElementType())


# ---------------------------------------------------------------------------
# 3. Le plan
# ---------------------------------------------------------------------------

a_migrer = []
for ancien, nouveau in MIGRATIONS:
    if ancien not in params:
        continue
    if nouveau not in params:
        out.print_md(
            u"⚠ `" + nouveau + u"` n'est pas lie dans cette maquette : la "
            u"migration de `" + ancien + u"` est **abandonnee**. Passer d'abord "
            u"le bouton *Socle parametres*."
        )
        continue
    a_migrer.append((ancien, nouveau))

noms_migres = set([a for a, _b in a_migrer])

a_supprimer = []
gardes = []
for nom in sorted(params.keys()):
    p = params[nom]
    if nom in noms_migres:
        continue
    if nom in PROTEGES:
        gardes.append((nom, u"protege par le socle"))
        continue
    if p["id"].Value in ids_utilises:
        usages = u" + ".join(sorted(detail_usage.get(p["id"].Value, set())))
        gardes.append((nom, u"utilise : " + usages))
        continue
    if p["remplis"] > 0 and nom not in SACRIFICES:
        gardes.append((nom, u"porte " + str(p["remplis"]) + u" valeurs"))
        continue
    a_supprimer.append(nom)

if a_migrer:
    out.print_md(u"## Migrations — les valeurs sont recopiees avant retrait")
    for ancien, nouveau in a_migrer:
        out.print_md(u"- `" + ancien + u"` → `" + nouveau + u"` (" +
                     str(params[ancien]["remplis"]) + u" valeurs)")

out.print_md(u"## A supprimer — vides, inutilises, non proteges")
if a_supprimer:
    lignes = [[n, str(len(params[n]["categories"])), str(params[n]["total"])]
              for n in a_supprimer]
    out.print_table(table_data=lignes,
                    columns=[u"Parametre", u"Categories", u"Objets porteurs"])
else:
    out.print_md(u"*Aucun.*")

sacrifies = [n for n in a_supprimer if n in SACRIFICES]
if sacrifies:
    out.print_md(u"## Sacrifices — des valeurs vont etre perdues, en connaissance de cause")
    out.print_table(
        table_data=[[n, str(params[n]["remplis"]) + u" valeurs", SACRIFICES[n]]
                    for n in sacrifies],
        columns=[u"Parametre", u"Ce qui est perdu", u"Pourquoi on l'accepte"],
    )

out.print_md(u"## Gardes — et pourquoi")
if gardes:
    out.print_table(table_data=[[n, m] for n, m in gardes],
                    columns=[u"Parametre", u"Motif"])

if not filtres_lus:
    out.print_md(u"---")
    out.print_md(
        u"## ARRET — les filtres de vue n'ont pas pu etre lus\n\n"
        u"Sans cette lecture, l'outil ne sait pas si un parametre vide alimente "
        u"un filtre, et supprimer ce parametre casserait le filtre en silence. "
        u"**Rien n'a ete ecrit.**\n\n"
        u"Dire quelle version de Revit, pour corriger le lecteur."
    )
    forms.alert(
        u"Les filtres de vue n'ont pas pu etre lus.\n\n"
        u"L'outil s'arrete : il ne supprime rien tant qu'il ne peut pas "
        u"garantir qu'un filtre ne sera pas casse.",
        title=u"Nettoyage — arret", exitscript=True,
    )
if not arbo_lue:
    out.print_md(
        u"> ⚠ **La lecture de l'arborescence du projet a echoue.** Verifier a "
        u"la main qu'aucun parametre supprime ne sert au classement des vues "
        u"ou des feuilles."
    )
out.print_md(
    u"> **Ce qui n'est pas lu** : les etiquettes des familles d'annotation. "
    u"Le risque est nul ici — tous les candidats sont vides partout, donc une "
    u"etiquette qui les afficherait affiche deja du vide. Apres la migration "
    u"des `Classement`, **repointer le classement de l'arborescence**."
)

if not a_supprimer and not a_migrer:
    forms.alert(u"Rien a faire : la maquette est deja propre.",
                title=u"Nettoyage", exitscript=True)

message = u""
if a_migrer:
    message += u"%d migration(s)\n" % len(a_migrer)
if a_supprimer:
    message += u"%d suppression(s) — les valeurs de ces parametres sont " \
               u"perdues, sans retour.\n" % len(a_supprimer)
if sacrifies:
    message += u"\nDont %d SACRIFICE(S) qui portent des valeurs :\n" % len(sacrifies)
    for n in sacrifies:
        message += u"  - %s (%d valeurs)\n" % (n, params[n]["remplis"])
message += u"\nLe detail est dans la fenetre de sortie.\n\nEcrire maintenant ?"

if not forms.alert(message, title=u"Nettoyage — confirmation",
                   yes=True, no=True):
    out.print_md(u"**Annule. Rien n'a ete ecrit.**")
    script.exit()


# ---------------------------------------------------------------------------
# 4. Ecriture
# ---------------------------------------------------------------------------

copies = []
supprimes = []
echecs = []

t = Transaction(doc, "Keovia - nettoyage des parametres de projet")
try:
    t.Start()

    for ancien, nouveau in a_migrer:
        n = 0
        herites = 0
        trouves = 0
        miroirs = 0
        attendu = params[ancien]["remplis"]
        motifs = {}
        portrait = {}   # classe / categorie -> compte, pour les cibles refusees
        noms_bloques = []
        # Pas de filtre par categorie : on cherche le champ sur chaque objet.
        # Filtrer par nom de categorie faisait perdre des objets en silence.
        tout = list(FilteredElementCollector(doc)
                    .WhereElementIsNotElementType().ToElements())
        tout += list(FilteredElementCollector(doc)
                     .WhereElementIsElementType().ToElements())
        for el in tout:
            try:
                src = el.LookupParameter(ancien)
            except Exception:
                continue
            if src is None or not a_une_valeur(src):
                continue
            trouves += 1
            try:
                dst = el.LookupParameter(nouveau)
            except Exception:
                dst = None
            if dst is None:
                motifs[u"champ cible absent"] = motifs.get(u"champ cible absent", 0) + 1
                continue
            if dst.IsReadOnly:
                # Une vue dependante herite de sa vue parente : le champ y est
                # en lecture seule, et recopier le parent suffit. Ce n'est pas
                # une perte.
                depend = False
                try:
                    pid = el.GetPrimaryViewId()
                    depend = pid is not None and pid.Value > 0
                except Exception:
                    depend = False
                if depend:
                    herites += 1
                    continue

                # Une fenetre de vue, une camera, un repere de coupe ne
                # portent pas leur propre valeur : ils REFLETENT celle de leur
                # vue, en lecture seule. Ecrire la vue suffit, il n'y a rien a
                # recopier chez eux. Mesure du 2026-09-19 : 32 fenetres de vue
                # + 35 elements associes, soit 67 des 102 refus.
                est_vue = False
                try:
                    est_vue = isinstance(el, View)
                except Exception:
                    est_vue = False
                if not est_vue:
                    miroirs += 1
                    continue

                motifs[u"vue dont la cible est en lecture seule"] = \
                    motifs.get(u"vue dont la cible est en lecture seule", 0) + 1
                try:
                    classe = el.GetType().Name
                except Exception:
                    classe = u"?"
                try:
                    c = el.Category
                    ncat = c.Name if c is not None else u"(sans categorie)"
                except Exception:
                    ncat = u"(sans categorie)"
                gabarit = u""
                try:
                    if el.IsTemplate:
                        gabarit = u" [gabarit de vue]"
                except Exception:
                    pass
                portrait[classe + u" / " + ncat + gabarit] = \
                    portrait.get(classe + u" / " + ncat + gabarit, 0) + 1
                if len(noms_bloques) < 8:
                    try:
                        noms_bloques.append(el.Name)
                    except Exception:
                        pass
                continue
            try:
                v = src.AsString()
                if v is None:
                    v = src.AsValueString()
            except Exception:
                v = None
            if v is None:
                motifs[u"valeur illisible"] = motifs.get(u"valeur illisible", 0) + 1
                continue
            try:
                dst.Set(v)
                n += 1
            except Exception:
                motifs[u"ecriture refusee"] = motifs.get(u"ecriture refusee", 0) + 1

        copies.append((ancien, nouveau, n, herites, attendu, motifs,
                       trouves, portrait, miroirs, noms_bloques))

        # Regle : on ne supprime JAMAIS la source d'une migration incomplete.
        # Les vues dependantes comptent comme traitees : leur valeur suit
        # celle de leur parent.
        # Le juge est le nombre d'objets REELLEMENT porteurs d'une valeur,
        # pas le comptage de la passe de mesure.
        if (n + herites + miroirs) < trouves:
            echecs.append((ancien, u"migration incomplete (%d recopiees + %d "
                                   u"heritees + %d miroirs, sur %d objets "
                                   u"porteurs) — la source est CONSERVEE"
                                   % (n, herites, miroirs, trouves)))
            continue
        # voie_forte=False : un parametre migre sert souvent au classement de
        # l'arborescence, que Revit protege et que la suppression de la
        # definition contournerait en silence. On repointe d'abord, a la main.
        ok, comment = retirer(params[ancien]["definition"], voie_forte=False)
        if ok:
            supprimes.append(ancien)
        else:
            echecs.append((ancien, comment + u" — repointer le classement de "
                                             u"l'arborescence, puis relancer"))

    for nom in a_supprimer:
        ok, comment = retirer(params[nom]["definition"])
        if ok:
            supprimes.append(nom)
        else:
            echecs.append((nom, comment))

    t.Commit()
except Exception as err:
    if t.HasStarted() and not t.HasEnded():
        t.RollBack()
    forms.alert(u"Echec, transaction annulee, rien n'a ete ecrit :\n\n" + str(err),
                exitscript=True)

out.print_md(u"## Resultat")
for ancien, nouveau, n, herites, attendu, motifs, trouves, portrait, miroirs, noms_bloques in copies:
    ligne = u"- `" + ancien + u"` → `" + nouveau + u"` : **" + str(n) + \
            u"** recopiees"
    if herites:
        ligne += u" + **" + str(herites) + u"** heritees par des vues dependantes"
    if miroirs:
        ligne += u" + **" + str(miroirs) + u"** miroirs (fenetre de vue, camera, repere)"
    ligne += u" · " + str(trouves) + u" objets porteurs trouves"
    if (n + herites + miroirs) < trouves:
        ligne += u" — **INCOMPLET, la source est conservee**"
    out.print_md(ligne)
    for motif in sorted(motifs.keys()):
        out.print_md(u"    - " + str(motifs[motif]) + u" × " + motif)
    if noms_bloques:
        out.print_md(u"    - **vues concernees** : " +
                     u", ".join([u"`" + x + u"`" for x in noms_bloques]))
    if portrait:
        out.print_md(u"    - **qui sont les vues refusees** :")
        for k in sorted(portrait.keys(), key=lambda x: -portrait[x]):
            out.print_md(u"        - " + str(portrait[k]) + u" × `" + k + u"`")

# VERIFICATION APRES COUP : on relit la maquette au lieu de croire le script.
restants = set()
try:
    it2 = doc.ParameterBindings.ForwardIterator()
    it2.Reset()
    while it2.MoveNext():
        restants.add(it2.Key.Name)
except Exception:
    restants = None

if restants is None:
    out.print_md(u"- **" + str(len(supprimes)) + u" retrait(s) demandes** "
                 u"(verification impossible)")
else:
    reellement = [n for n in supprimes if n not in restants]
    fantomes = [n for n in supprimes if n in restants]
    out.print_md(u"- **" + str(len(reellement)) +
                 u" parametre(s) reellement retire(s)**, verifie dans la maquette")
    for nom in fantomes:
        out.print_md(u"- **NON APPLIQUE** `" + nom + u"` : le script l'a "
                     u"retire, la maquette le porte encore")
    if fantomes:
        forms.alert(
            u"%d suppression(s) n'ont PAS ete appliquees malgre un retrait "
            u"annonce.\n\nCause la plus frequente : modele collaboratif dont "
            u"le central est inaccessible.\n\n"
            u"Fermer SANS enregistrer, et recommencer sur une copie detachee."
            % len(fantomes),
            title=u"Suppressions non appliquees",
        )

for nom, motif in echecs:
    out.print_md(u"- **ECHEC** `" + nom + u"` : " + motif)

retenus_par_usage = [n for n, m in gardes if m.startswith(u"utilise")]
if retenus_par_usage:
    out.print_md(
        u"---\n"
        u"### %d parametre(s) ne sont retenus QUE par un usage\n\n"
        u"Ils sont vides, mais une nomenclature ou un filtre les cite, et les "
        u"retirer casserait cette nomenclature ou ce filtre. La colonne "
        u"**Motif** ci-dessus nomme le coupable.\n\n"
        u"Pour s'en debarrasser : **supprimer d'abord la nomenclature ou le "
        u"filtre**, puis relancer ce bouton — ils tomberont par la regle "
        u"normale, sans avoir a les sacrifier.\n\n"
        u"Si la nomenclature sert encore, alors ces parametres servent aussi : "
        u"on les garde, et la matrice du PGB doit les porter."
        % len(retenus_par_usage)
    )
else:
    out.print_md(
        u"---\n"
        u"Aucun parametre n'est retenu par un usage. La maquette ne porte plus "
        u"que le socle."
    )
