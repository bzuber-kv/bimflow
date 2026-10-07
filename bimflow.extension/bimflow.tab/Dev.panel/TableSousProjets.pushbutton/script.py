# -*- coding: utf-8 -*-
"""ORANGE - ecrit dans la maquette, apres plan affiche et confirmation.

Renomme et cree des sous-projets utilisateur selon une table CSV.

Deux modes :
- Exporter la table : un CSV, une ligne par sous-projet, Action = GARDER ;
- Appliquer une table : GARDER, RENOMMER (Nom_actuel -> Nouveau_nom),
  CREER (Nouveau_nom seul).

Aucune action ne deplace d'element : pas de vidage, pas de suppression.
La table est validee en entier AVANT toute ecriture ; une seule erreur
bloquante = rien n'est ecrit. Detail : docs\\sous_projets.md
"""

__title__ = "Table\nsous-projets"
__author__ = "Keovia Solutions inc."

VERSION = u"2026-10-07a"

# NON EPROUVE dans Revit au 2026-10-07 - d'ou le panneau Dev.
#
# pyRevit v6.5.5 / IronPython 3.4.2 (IPY342) - pas de f-string, pas de
# shebang, syntaxe 3.4. La lecture et la validation de la table, le plan et
# le controle final vivent dans lib\bimflow_sous_projets.py, testes hors
# Revit. Ce script lit le modele, affiche, demande, ecrit.
#
# Forme d'ecriture : plan affiche en entier, puis confirmation nommant la
# maquette (docs\organisation_ruban.md §4, forme b). Une transaction unique,
# annulee en bloc a la moindre erreur. AUCUN script.exit() apres l'ecriture
# (docs\ecrire_dans_revit.md §1).

import io

from pyrevit import revit, forms, script

from Autodesk.Revit.DB import (
    ElementWorksetFilter, FilteredElementCollector, FilteredWorksetCollector,
    Transaction, TransactionStatus, Workset, WorksetKind, WorksetTable,
)

import bimflow_maquette
import bimflow_sous_projets as S


doc = revit.doc
out = script.get_output()

EXPORTER = u"Exporter la table"
APPLIQUER = u"Appliquer une table"


def lire_sous_projets():
    """{nom: dict} des sous-projets utilisateur. La liste est materialisee
    avant toute lecture de propriete."""
    worksets = list(FilteredWorksetCollector(doc)
                    .OfKind(WorksetKind.UserWorkset).ToWorksets())
    resultat = {}
    for ws in worksets:
        ouvert = bool(ws.IsOpen)
        resultat[ws.Name] = {
            u"id": ws.Id,
            u"ouvert": ouvert,
            u"proprietaire": ws.Owner or u"",
            u"editable": bool(ws.IsEditable),
            # Un sous-projet ferme n'est pas charge : il compterait zero.
            u"nb_elements": compter(ws) if ouvert else u"NON_LU",
        }
    return resultat


def compter(ws):
    return (FilteredElementCollector(doc)
            .WherePasses(ElementWorksetFilter(ws.Id))
            .WhereElementIsNotElementType()
            .GetElementCount())


def tableau(titre, lignes, colonnes):
    if lignes:
        out.print_table(table_data=lignes, title=titre, columns=colonnes)


def entete(mode):
    out.print_md(u"# Table des sous-projets - {0}".format(mode))
    out.print_md(u"**Version de l'outil** : `{0}` · **Maquette** : `{1}`"
                 .format(VERSION, doc.Title))
    collaboratif, detache, _centrale = bimflow_maquette.etat(doc)
    out.print_md(u"**Etat** : {0}".format(
        bimflow_maquette.mot_de_letat(collaboratif, detache)))


def avertir_fermes(existants):
    fermes = sorted([n for n, sp in existants.items() if not sp[u"ouvert"]])
    if fermes:
        out.print_md(
            u"> **{0} sous-projet(s) ferme(s)** : {1}. Leurs elements ne sont "
            u"pas charges ; leur nombre d'elements est ecrit NON_LU.".format(
                len(fermes), u", ".join(fermes)))


# ---------------------------------------------------------------------------
# 0. Preconditions et choix du mode
# ---------------------------------------------------------------------------

if doc is None or doc.IsFamilyDocument:
    forms.alert(u"Ouvrir une maquette de projet (pas une famille).",
                exitscript=True)
if not doc.IsWorkshared:
    forms.alert(u"Cette maquette n'est pas en travail partage : elle n'a pas "
                u"de sous-projets. Rien n'a ete lu ni ecrit.", exitscript=True)

mode = forms.CommandSwitchWindow.show(
    [EXPORTER, APPLIQUER],
    message=u"Table des sous-projets - {0}".format(doc.Title))
if not mode:
    script.exit()


# ---------------------------------------------------------------------------
# 1. Exporter la table
# ---------------------------------------------------------------------------

if mode == EXPORTER:
    entete(EXPORTER)
    existants = lire_sous_projets()
    avertir_fermes(existants)
    chemin = forms.save_file(
        file_ext="csv",
        default_name=u"sous_projets_{0}".format(doc.Title))
    if not chemin:
        forms.alert(u"Aucun fichier choisi. Rien n'a ete ecrit.",
                    exitscript=True)
    texte = S.texte_export([
        {u"nom": nom, u"nb_elements": sp[u"nb_elements"],
         u"proprietaire": sp[u"proprietaire"]}
        for nom, sp in existants.items()])
    S.ecrire_texte(chemin, texte)
    tableau(u"Sous-projets utilisateur",
            [[nom, u"{0}".format(existants[nom][u"nb_elements"]),
              existants[nom][u"proprietaire"]]
             for nom in sorted(existants, key=lambda n: n.lower())],
            [u"Sous-projet", u"Elements", u"Emprunte par"])
    out.print_md(u"**{0} sous-projet(s)** ecrits dans `{1}`.".format(
        len(existants), chemin))
    out.print_md(u"Editer la colonne Action (GARDER, RENOMMER, CREER) et "
                 u"Nouveau_nom, enregistrer en CSV UTF-8 a separateur `;`, "
                 u"puis relancer en mode « {0} ».".format(APPLIQUER))
    script.exit()


# ---------------------------------------------------------------------------
# 2. Appliquer une table : lecture et validation, AVANT toute ecriture
# ---------------------------------------------------------------------------

entete(APPLIQUER)
chemin = forms.pick_file(file_ext="csv")
if not chemin:
    forms.alert(u"Aucun fichier choisi. Rien n'a ete lu ni ecrit.",
                exitscript=True)
out.print_md(u"**Table** : `{0}`".format(chemin))

with io.open(chemin, "rb") as f:
    texte, encodage = S.decoder(f.read())
lignes, constats = S.lire_table(texte)
if encodage != u"utf-8":
    constats.insert(0, S.Constat(
        S.AVERTISSEMENT, None, u"fichier lu en {0}, pas en UTF-8 : verifier "
        u"les accents des noms ci-dessous".format(encodage)))

existants = lire_sous_projets()
avertir_fermes(existants)
utilisateur = doc.Application.Username
if not S.bloquant(constats):
    constats.extend(S.valider(lignes, existants, utilisateur))

tableau(u"Validation de la table",
        [c.colonnes() for c in constats],
        [u"Niveau", u"Ligne", u"Constat"])
nb_erreurs = len([c for c in constats if c.niveau == S.ERREUR])

if nb_erreurs:
    out.print_md(u"## {0} erreur(s) bloquante(s) : rien n'a ete ecrit"
                 .format(nb_erreurs))
    out.print_md(u"Corriger la table et relancer. Pour repartir des noms "
                 u"exacts du modele : mode « {0} ».".format(EXPORTER))
    script.exit()

operations = S.plan(lignes)
if not operations:
    out.print_md(u"## Rien a faire : la table ne cree ni ne renomme rien. "
                 u"Rien n'a ete ecrit.")
    script.exit()

nb_creations = len([o for o in operations if o[u"action"] == S.CREER])
nb_renommages = len(operations) - nb_creations
tableau(u"Plan - {0} creation(s), {1} renommage(s), aucun element deplace"
        .format(nb_creations, nb_renommages),
        [[u"{0}".format(o[u"ligne"]), o[u"action"], o[u"nom_actuel"],
          o[u"nouveau_nom"]] for o in operations],
        [u"Ligne", u"Action", u"Nom actuel", u"Nouveau nom"])


# ---------------------------------------------------------------------------
# 3. Confirmation nommant la maquette
# ---------------------------------------------------------------------------

_collaboratif, _detache, centrale = bimflow_maquette.etat(doc)
operation = u"Table sous-projets : {0} creation(s), {1} renommage(s)".format(
    nb_creations, nb_renommages)
if centrale:
    accord = bimflow_maquette.confirmer_centrale(
        doc, operation, len(operations), quoi=u"sous-projet(s)",
        consequence=u"Aucun element n'est deplace.")
else:
    accord = forms.alert(
        u"Maquette : {0}\n\n{1}.\nAucun element n'est deplace, aucun "
        u"sous-projet n'est supprime.\n\nAppliquer ?".format(
            doc.Title, operation),
        yes=True, no=True)
if not accord:
    out.print_md(u"## Annule avant ecriture. Rien n'a ete ecrit.")
    script.exit()


# ---------------------------------------------------------------------------
# 4. Ecriture : une transaction, annulee en bloc a la moindre erreur.
#    A partir d'ici, plus aucune sortie anticipee.
# ---------------------------------------------------------------------------

echec = None
statut = None
en_cours = u"ouverture"
t = Transaction(doc, u"bimflow - Table sous-projets")
t.Start()
try:
    for op in operations:
        en_cours = u"ligne {0} ({1} \"{2}\")".format(
            op[u"ligne"], op[u"action"], op[u"nouveau_nom"])
        if op[u"action"] == S.CREER:
            Workset.Create(doc, op[u"nouveau_nom"])
        else:
            WorksetTable.RenameWorkset(
                doc, existants[op[u"nom_actuel"]][u"id"], op[u"nouveau_nom"])
    en_cours = u"validation de la transaction"
    statut = t.Commit()
except Exception as err:
    echec = u"{0} : {1}".format(en_cours, err)
    if t.HasStarted() and not t.HasEnded():
        t.RollBack()

if echec is not None:
    out.print_md(u"## ECHEC - tout a ete annule, rien n'est modifie")
    out.print_md(u"`{0}`".format(echec))
elif statut != TransactionStatus.Committed:
    out.print_md(u"## Revit n'a pas valide l'ecriture (statut {0}) : rien "
                 u"n'est modifie".format(statut))
else:
    # Relecture : ce que le modele porte, pas ce que le script croit.
    relus = lire_sous_projets()
    ecarts = S.ecarts_apres(operations, relus.keys())
    tableau(u"Sous-projets relus apres ecriture",
            [[nom, u"{0}".format(relus[nom][u"nb_elements"])]
             for nom in sorted(relus, key=lambda n: n.lower())],
            [u"Sous-projet", u"Elements"])
    if ecarts:
        out.print_md(u"## {0} ecart(s) entre la table et le modele relu"
                     .format(len(ecarts)))
        for e in ecarts:
            out.print_md(u"- " + e)
    else:
        out.print_md(u"## {0} operation(s) faites, relecture conforme a la "
                     u"table".format(len(operations)))
    out.print_md(u"Synchroniser pour publier. Puis relancer l'export pour "
                 u"garder la table a jour.")
