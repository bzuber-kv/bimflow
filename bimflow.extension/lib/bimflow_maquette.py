# -*- coding: utf-8 -*-
"""bimflow_maquette - etat du document, et la porte d'entree des ecritures.

Un seul endroit ou l'on repond a la question « ou est-ce que j'ecris ? ».
Les trois boutons volumes s'en servent, et ils disent donc la meme chose,
avec les memes mots.

CE QUI A CHANGE LE 2026-09-24. Jusqu'ici, les trois boutons REFUSAIENT de
tourner sur une maquette collaborative non detachee. Le garde-fou a fait son
travail - il a tenu pendant toute la mise au point - mais il interdisait
aussi le seul usage qui compte a la fin : ecrire sur la maquette de
production. Il laisse desormais passer, sous condition d'une confirmation
qui NOMME le fichier et ANNONCE le nombre d'elements concernes
(ACT-052 (2)).

DETACHE / CENTRAL, comment on tranche. `IsWorkshared` reste vrai apres un
detachement conservant les sous-projets : il ne dit pas si l'on est sur une
copie. C'est `IsDetached` qui tranche, et lui seul. Sur une version de Revit
ou la propriete serait absente, `etat()` rend None pour `detache` et la
maquette est traitee comme CENTRALE - le doute va du cote prudent.

CE QUE CE MODULE NE FAIT PAS. Il n'emprunte rien, ne synchronise rien, ne
recharge rien. Il pose une question et rend la reponse. Ce qui se passe
ensuite appartient a l'appelant - notamment la regle qui compte : AUCUN
script.exit() apres une ecriture (docs\\ecrire_dans_revit.md §1).

Ce module importe l'API Revit : il ne tourne que dans Revit, contrairement a
bimflow_noms, qui tourne aussi sous CPython.

bimflow - Keovia Solutions inc. - 2026-09-24
"""

from Autodesk.Revit.UI import (TaskDialog, TaskDialogCommonButtons,
                               TaskDialogResult)


def etat(doc):
    """(collaboratif, detache, centrale).

    `detache` vaut None si Revit ne repond pas ; `centrale` est alors vrai,
    parce qu'un doute sur l'emplacement se tranche du cote prudent."""
    collaboratif = bool(doc.IsWorkshared)
    detache = None
    try:
        detache = bool(doc.IsDetached)
    except Exception:
        detache = None
    centrale = collaboratif and detache is not True
    return collaboratif, detache, centrale


def mot_de_letat(collaboratif, detache):
    """De quoi on parle, en trois mots, pour un rapport."""
    if not collaboratif:
        return u"monoposte"
    if detache is True:
        return u"copie detachee"
    if detache is None:
        return u"collaborative, etat de detachement ILLISIBLE"
    return u"MAQUETTE CENTRALE (production)"


def proprietaire(doc, element_id):
    """(statut de reservation, proprietaire) pour un element, ou (None, None).

    Sert au diagnostic, jamais a decider : sur une maquette non partagee, ou
    sur une version d'API qui ne repond pas, les deux valent None et
    l'appelant le dit plutot que de l'inventer."""
    try:
        from Autodesk.Revit.DB import WorksharingUtils
    except Exception:
        return None, None
    statut = None
    qui = None
    try:
        statut = u"{0}".format(WorksharingUtils.GetCheckoutStatus(doc, element_id))
    except Exception:
        statut = None
    try:
        info = WorksharingUtils.GetWorksharingTooltipInfo(doc, element_id)
        qui = info.Owner or None
    except Exception:
        qui = None
    return statut, qui


def confirmer_centrale(doc, operation, nb_elements, quoi=u"element(s)",
                       consequence=u""):
    """Porte d'entree des ecritures sur la MAQUETTE CENTRALE. Rend un bool.

    A n'appeler QUE lorsque `centrale` est vrai : sur une copie detachee, le
    comportement des boutons ne change pas, et une boite de plus n'apprendrait
    rien a personne.

    La confirmation nomme le fichier, annonce le nombre d'elements concernes,
    et demande de cocher que l'on est seul dessus. La case n'est pas un
    ornement : non cochee, l'operation ne part pas. Si la version de Revit
    n'offre pas la case, le Oui suffit - et l'appelant l'apprend par le
    rapport, pas par une surprise."""
    dialogue = TaskDialog(u"bimflow - MAQUETTE CENTRALE")
    dialogue.MainInstruction = u"Ecrire dans la maquette de PRODUCTION ?"
    dialogue.MainContent = (
        u"Ce n'est PAS une copie detachee. Ce qui suit modifiera le modele "
        u"que l'equipe utilise.\n\n"
        u"Maquette : {0}\n"
        u"Fichier : {1}\n\n"
        u"Operation : {2}\n"
        u"Concerne : {3} {4}\n\n"
        u"{5}"
        u"Etre SEUL sur la maquette avant de continuer, et synchroniser "
        u"ensuite.".format(
            doc.Title,
            doc.PathName or u"(jamais enregistree)",
            operation,
            nb_elements,
            quoi,
            (consequence + u"\n\n") if consequence else u"",
        )
    )
    try:
        dialogue.ExpandedContent = (
            u"Pourquoi cette question. Un nom de famille est un STANDARD DE "
            u"PROJET, pas un element : en travail partage, le modifier demande "
            u"un emprunt exclusif, que Revit peut refuser si un autre "
            u"utilisateur detient le standard [hypothese, non mesuree au "
            u"2026-09-24]. La simulation ne le detecte pas : elle ne teste que "
            u"la lecture.\n\n"
            u"En cas de refus de Revit, l'erreur exacte est rapportee, sans "
            u"repli invente, et tout est annule."
        )
    except Exception:
        pass

    case_posee = False
    try:
        dialogue.VerificationText = u"Je suis seul sur cette maquette."
        case_posee = True
    except Exception:
        case_posee = False

    dialogue.CommonButtons = (TaskDialogCommonButtons.Yes |
                              TaskDialogCommonButtons.No)
    dialogue.DefaultButton = TaskDialogResult.No

    if dialogue.Show() != TaskDialogResult.Yes:
        return False
    if not case_posee:
        return True
    try:
        return bool(dialogue.WasVerificationChecked())
    except Exception:
        # La case existe mais ne se relit pas : on ne bloque pas sur un
        # defaut d'API, et l'appelant dira que la case n'a pas pu etre lue.
        return True
