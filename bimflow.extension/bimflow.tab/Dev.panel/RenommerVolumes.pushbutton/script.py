# -*- coding: utf-8 -*-
"""renommer_volumes - Porte la nature dans le NOM des volumes de zone.

Ecrit le 2026-09-22.

OBJET. Renommer la FAMILLE des volumes in situ dont le 4e segment vaut
encore "0", en y portant leur nature :

    VOL__<REF_Zone>__<REF_Etage>__0
                                  -> VOL__<REF_Zone>__<REF_Etage>__ETAGE
                                  -> VOL__<REF_Zone>__<REF_Etage>__TOITURE

La nature se deduit du seul etage : REF_Etage == "ROOF" donne TOITURE, tout
le reste donne ETAGE. Les autres valeurs de la liste fermee - ENTRE_TOIT,
EXTERIEUR, ENVELOPPE - ne se devinent PAS depuis le nom : elles se posent a
la main, dans Revit.

#############################################################################
# STATUT : NON EPROUVE - JAMAIS EXECUTE DANS REVIT au 2026-09-22.           #
# Ce script ECRIT dans le modele : il renomme des familles. Essai sur       #
# COPIE DETACHEE uniquement (R17). Le succes affiche ici NE PROUVE RIEN :   #
# la verification se fait dans l'arborescence du projet et en nomenclature. #
#############################################################################

POURQUOI UN BOUTON SEPARE DE "MAJ params volumes". Le nom de famille est la
SOURCE de verite : c'est lui qui porte la zone, l'etage et la nature, et
tous les autres outils le lisent. On n'ecrit pas la source dans la meme
transaction qu'on la lit - sans quoi un meme clic deciderait de la verite
et en tirerait les consequences, sans que personne puisse regarder entre
les deux. Ordre d'emploi : ce bouton, PUIS Audit volumes pour verifier,
PUIS MAJ params volumes.

CE QU'IL NE FAIT PAS : il ne touche ni a la geometrie, ni aux parametres,
ni aux noms deja conformes. Il ne devine aucune nature autre que les deux
citees plus haut.

UNICITE. Revit exige un nom de famille unique. Si l'un des noms voulus
existe deja - dans le modele, ou en double dans le lot - RIEN n'est
renomme, et le conflit est nomme. Un renommage partiel laisserait la
maquette a moitie dans l'ancien motif et a moitie dans le nouveau.

bimflow - volumes de zone, mode ecriture - Keovia Solutions inc.
"""

__title__ = "Renommer\nvolumes"
__author__ = "Keovia Solutions inc."

# --------------------------------------------------------------------------
# PARAMETRES
# --------------------------------------------------------------------------

# Une maquette collaborative doit etre traitee sur une COPIE DETACHEE (R17).
AUTORISER_NON_DETACHE = False

# --------------------------------------------------------------------------

from pyrevit import revit, script, forms

# Le decoupage du nom vit dans UN seul module, partage avec les autres
# outils (dossier lib\ de l'extension, ajoute au chemin par pyRevit).
try:
    from bimflow_noms import (
        decouper,
        nature_attendue,
        SEPARATEUR,
        NATURE_A_RENOMMER,
        NATURES,
        RANG_ZONE,
        RANG_ETAGE,
        RANG_NATURE,
        PREFIXE_ATTENDU,
    )
except ImportError:
    from pyrevit import forms as _formulaires
    _formulaires.alert(
        u"Module partage bimflow_noms introuvable.\n\n"
        u"Il doit se trouver dans bimflow.extension\\lib\\. Sans lui, le "
        u"decoupage des noms de volumes n'est pas disponible et ce script "
        u"ne s'execute pas.",
        exitscript=True,
    )

from Autodesk.Revit.DB import (
    FilteredElementCollector,
    BuiltInCategory,
    Family,
    FamilyInstance,
    Transaction,
    TransactionStatus,
)
from Autodesk.Revit.UI import TaskDialog, TaskDialogCommonButtons, TaskDialogResult

doc = revit.doc
out = script.get_output()


def id_de(eid):
    """R15 fait 7 : ElementId.Value en Revit 2024+, .IntegerValue avant."""
    if eid is None:
        return -1
    try:
        return int(eid.Value)
    except AttributeError:
        return int(eid.IntegerValue)


def texte(valeur):
    return u"" if valeur is None else u"{0}".format(valeur)


def lien_de(eid):
    try:
        return out.linkify(eid)
    except Exception:
        return u"`{0}`".format(id_de(eid))


# --------------------------------------------------------------------------
# 0. Garde-fous
# --------------------------------------------------------------------------

if doc.IsFamilyDocument:
    forms.alert(u"Document famille : rien a renommer.", exitscript=True)

collaboratif = bool(doc.IsWorkshared)
detache = None
try:
    detache = bool(doc.IsDetached)
except Exception:
    detache = None

if collaboratif and detache is not True and not AUTORISER_NON_DETACHE:
    forms.alert(
        u"Maquette collaborative, et ce n'est pas une copie detachee.\n\n"
        u"Ce script RENOMME des familles : il ne tourne que sur une copie "
        u"detachee (R17).\n\n"
        u"Rouvrir la maquette avec \"Detacher du fichier central\", puis "
        u"relancer.",
        exitscript=True,
    )

# --------------------------------------------------------------------------
# 1. Passage 1 - LECTURE SEULE : quels noms, et vers quoi
# --------------------------------------------------------------------------

ids = list(
    FilteredElementCollector(doc)
    .OfCategory(BuiltInCategory.OST_Mass)
    .WhereElementIsNotElementType()
    .ToElementIds()
)
# R15 fait 8 : le collecteur est consomme AVANT toute resolution de propriete.

# Tous les noms de famille du document : c'est contre EUX que l'unicite se
# verifie, pas seulement contre les volumes.
noms_pris = set()
for fid in list(FilteredElementCollector(doc).OfClass(Family).ToElementIds()):
    f = doc.GetElement(fid)
    if f is None:
        continue
    try:
        noms_pris.add(f.Name)
    except Exception:
        continue

prevus = {}         # id de FAMILLE -> (nom avant, nom apres, [ids volumes])
element_famille = {}  # id de FAMILLE -> son ElementId, pour le passage 2
conformes = []      # (eid, nom) - deja au nouveau motif
ignores = []        # (eid, nom, motif)
conflits = []       # (nom voulu, motif)

for eid in ids:
    el = doc.GetElement(eid)
    if el is None:
        continue

    if not isinstance(el, FamilyInstance):
        ignores.append((eid, None, u"volume qui n'est pas une instance de famille"))
        continue

    try:
        famille = el.Symbol.Family
        nom = famille.Name
        in_situ = bool(famille.IsInPlace)
        fid = id_de(famille.Id)
    except Exception as err:
        ignores.append((eid, None, u"identite illisible : {0}".format(err)))
        continue

    if not in_situ:
        ignores.append((eid, nom, u"volume qui n'est pas in situ"))
        continue

    segments, _defauts = decouper(nom)
    if segments is None:
        ignores.append((eid, nom, u"nom indecoupable : {0} n'est pas un motif "
                                  u"a 4 segments".format(nom)))
        continue
    if segments[0] != PREFIXE_ATTENDU:
        ignores.append((eid, nom, u"segment 0 = \"{0}\" au lieu de \"{1}\"".format(
            segments[0], PREFIXE_ATTENDU)))
        continue

    nature = segments[RANG_NATURE]
    if nature in NATURES:
        conformes.append((eid, nom))
        continue
    if nature != NATURE_A_RENOMMER:
        ignores.append((eid, nom, u"4e segment \"{0}\" : ni \"{1}\", ni une "
                                  u"valeur de la liste fermee - ce script ne "
                                  u"devine pas".format(nature, NATURE_A_RENOMMER)))
        continue

    zone = segments[RANG_ZONE]
    etage = segments[RANG_ETAGE]
    if not zone or not etage:
        ignores.append((eid, nom, u"zone ou etage vide : rien a en deduire"))
        continue

    nouveau = SEPARATEUR.join([PREFIXE_ATTENDU, zone, etage,
                               nature_attendue(etage)])

    if fid in prevus:
        prevus[fid][2].append(eid)
    else:
        prevus[fid] = (nom, nouveau, [eid])
        element_famille[fid] = famille.Id

# --------------------------------------------------------------------------
# 2. Unicite - AVANT toute transaction, et en bloc
# --------------------------------------------------------------------------

anciens = set([avant for avant, apres, liste in prevus.values()])
voulus = {}
for fid, (avant, apres, liste) in prevus.items():
    # un nom libere par ce meme lot n'est pas un conflit
    if apres in noms_pris and apres not in anciens:
        conflits.append((apres, u"ce nom existe deja dans le modele "
                                u"(famille non concernee par ce lot)"))
    voulus.setdefault(apres, []).append(avant)

for apres, sources in voulus.items():
    if len(sources) > 1:
        conflits.append((apres, u"{0} familles y menent : {1}".format(
            len(sources), u", ".join(sorted(sources)))))

# --------------------------------------------------------------------------
# 3. Rapport du passage 1
# --------------------------------------------------------------------------

out.print_md(u"# Renommage des volumes - passage 1, LECTURE SEULE")
out.print_md(
    u"Maquette : **{0}** &nbsp;|&nbsp; {1} &nbsp;|&nbsp; **rien n'est encore "
    u"renomme**".format(
        doc.Title,
        u"copie detachee" if detache else
        (u"collaborative NON detachee" if collaboratif else u"non collaborative"))
)
out.print_md(
    u"- **{0}** element(s) de categorie Volumes\n"
    u"- **{1}** famille(s) a renommer\n"
    u"- **{2}** volume(s) deja au nouveau motif\n"
    u"- **{3}** volume(s) ignore(s)".format(
        len(ids), len(prevus), len(conformes), len(ignores))
)

out.print_md(u"## Renommages prevus")
if not prevus:
    out.print_md(u"*Aucun. Rien a renommer, la transaction ne sera pas ouverte.*")
else:
    lignes = [u"| Famille | Avant | Apres | Volumes |", u"|---|---|---|---|"]
    for fid in sorted(prevus.keys()):
        avant, apres, liste = prevus[fid]
        lignes.append(u"| `{0}` | `{1}` | **`{2}`** | {3} |".format(
            fid, avant, apres,
            u" ".join([lien_de(e) for e in liste])))
    out.print_md(u"\n".join(lignes))

if ignores:
    out.print_md(u"## Volumes ignores - aucun ne sera renomme")
    for eid, nom, motif in ignores:
        out.print_md(u"- {0} `{1}` : {2}".format(
            lien_de(eid), texte(nom), motif))

if conflits:
    out.print_md(u"## CONFLITS DE NOM - rien ne sera renomme")
    for nom, motif in conflits:
        out.print_md(u"- `{0}` : {1}".format(nom, motif))
    out.print_md(
        u"> **Arret.** Un nom de famille doit etre unique dans le document. "
        u"Le lot est refuse EN BLOC : renommer une partie laisserait la "
        u"maquette a moitie dans l'ancien motif, a moitie dans le nouveau. "
        u"Traiter ces conflits a la main dans Revit, puis relancer."
    )
    script.exit()

if not prevus:
    out.print_md(
        u"---\n**Fin.** Aucune transaction n'a ete ouverte, rien n'a ete "
        u"renomme."
    )
    script.exit()

# --------------------------------------------------------------------------
# 4. Confirmation explicite
# --------------------------------------------------------------------------

nb_volumes = sum([len(liste) for avant, apres, liste in prevus.values()])

dialogue = TaskDialog(u"bimflow - Renommage des volumes de zone")
dialogue.MainInstruction = u"Renommer {0} famille(s), portant {1} volume(s) ?".format(
    len(prevus), nb_volumes)
dialogue.MainContent = (
    u"Maquette : {0}\n"
    u"Fichier : {1}\n\n"
    u"Le detail (nom avant, nom apres) est affiche dans la fenetre de "
    u"sortie.\n\n"
    u"Le nom de famille est la SOURCE de verite des volumes de zone : c'est "
    u"lui que les autres outils lisent. Un seul commit pour tout le lot ; si "
    u"un renommage echoue, TOUT est annule.\n\n"
    u"Script NON EPROUVE. Verifier ensuite dans l'arborescence du projet, "
    u"puis avec le bouton Audit volumes.".format(
        doc.Title, doc.PathName or u"(jamais enregistree)")
)
dialogue.CommonButtons = (TaskDialogCommonButtons.Yes |
                          TaskDialogCommonButtons.No)
dialogue.DefaultButton = TaskDialogResult.No

if dialogue.Show() != TaskDialogResult.Yes:
    out.print_md(
        u"---\n**Annule par l'utilisateur.** Aucune transaction n'a ete "
        u"ouverte, rien n'a ete renomme."
    )
    script.exit()

# --------------------------------------------------------------------------
# 5. Passage 2 - ECRITURE : une transaction, un commit, tout ou rien
# --------------------------------------------------------------------------

renommees = 0
echec = None

transaction = Transaction(doc, u"bimflow - renommage des volumes de zone")
if transaction.Start() != TransactionStatus.Started:
    forms.alert(
        u"Revit a refuse d'ouvrir la transaction. Rien n'a ete renomme.",
        exitscript=True,
    )

try:
    for fid in sorted(prevus.keys()):
        avant, apres, liste = prevus[fid]
        # le compteur AVANT l'appel qui peut lever
        renommees += 1
        famille = doc.GetElement(element_famille[fid])
        if famille is None:
            raise Exception(
                u"famille {0} introuvable au moment de renommer".format(fid))
        famille.Name = apres
except Exception as err:
    echec = err

if echec is None:
    etat = transaction.Commit()
    if etat != TransactionStatus.Committed:
        echec = u"Commit refuse par Revit (etat : {0})".format(etat)
        renommees = 0
else:
    transaction.RollBack()
    renommees = 0

# --------------------------------------------------------------------------
# 6. Rapport final
# --------------------------------------------------------------------------

out.print_md(u"---")
out.print_md(u"# Passage 2 - renommage")

if echec is not None:
    out.print_md(
        u"## ECHEC - tout a ete annule\n"
        u"`{0}`\n\n"
        u"**La maquette est dans l'etat ou elle etait avant le clic** : la "
        u"transaction a ete annulee en bloc, aucun nom n'a survecu. A "
        u"diagnostiquer avant de relancer.".format(echec)
    )
    script.exit()

out.print_md(
    u"| Resultat | Nombre | Motif |\n|---|---:|---|\n"
    u"| **Renommees** | {0} | 4e segment \"{1}\" remplace par la nature |\n"
    u"| **Deja conformes** | {2} | 4e segment deja dans la liste fermee |\n"
    u"| **Ignores** | {3} | nom indecoupable, volume non in situ, ou 4e "
    u"segment que ce script ne devine pas |".format(
        len(prevus), NATURE_A_RENOMMER, len(conformes), len(ignores))
)
out.print_md(
    u"**{0} famille(s) renommee(s)**, portant {1} volume(s), en un seul "
    u"commit.".format(renommees, nb_volumes)
)
out.print_md(
    u"> **Suite.** Passer **Audit volumes** pour verifier les noms, puis "
    u"**MAJ params volumes** pour porter la nature dans "
    u"`CLS_Nature_volume`.\n\n"
    u"> **Ce que ce resultat ne prouve pas.** Le script rapporte ce que "
    u"l'API lui a rendu. La verification se fait dans l'**arborescence du "
    u"projet** (Familles > Volumes) et en **nomenclature de Volumes**.\n\n"
    u"> **ENTRE_TOIT, EXTERIEUR et ENVELOPPE ne se devinent pas** : ce "
    u"script ne pose que ETAGE et TOITURE. Les autres natures se corrigent "
    u"a la main dans Revit, sur le nom de famille."
)
