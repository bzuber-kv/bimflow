#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verifier_sorties_apres_ecriture.py - Un script pyRevit qui a ECRIT ne doit
jamais sortir par script.exit().

POURQUOI. Mesure du 2026-09-24, sur The Study. Le bouton de renommage des
volumes commitait 202 renommages, les relisait - 202 sur 202 au nom voulu -
et tout etait revenu a l'ancien nom au clic suivant. Ni exception, ni
message, ni trace.

    script.exit() appelle sys.exit(), qui leve SystemExit.
    Une commande externe Revit qui se termine en rendant Cancelled fait
    ANNULER PAR REVIT tout ce qu'elle a modifie - transactions commitees
    comprises.

La correlation etait parfaite sur six executions : les deux modes qui
sortaient par script.exit() voyaient leur travail defait, les deux qui
tombaient a la fin du fichier persistaient. Six hypotheses sont mortes avant
celle-la - le document actif, l'element Family remplace, un porteur de nom
desynchronise, le TransactionGroup, la passe de noms temporaires, le partage
de projet - et j'etais a une reponse d'ecrire en fiche que renommer une
famille in situ par l'API ne persiste pas. C'etait faux.

CE QUE FAIT CE CONTROLE. Il signale tout appel a script.exit() situe, dans
le fichier, APRES le premier Commit(). C'est une heuristique de POSITION, pas
une analyse de flot : elle ne sait pas si la sortie suit reellement une
ecriture, ou si elle appartient a une branche d'echec ou tout a ete annule.
Elle designe les fichiers a LIRE. Le jugement reste humain.

Les sorties legitimes sont celles qui suivent un RollBack, un refus, une
annulation par l'utilisateur, un lot vide : la, rien n'a ete ecrit, et une
annulation par Revit n'enleve rien.

Usage : python3 verifier_sorties_apres_ecriture.py [fichier.py ...]
        sans argument : tous les boutons de l'extension

Code de sortie : 0 si rien a lire, 1 sinon. Un 1 n'est PAS un echec : c'est
une invitation a relire, et le message le dit.

bimflow - Keovia Solutions inc. - 2026-09-24
"""
import ast
import pathlib
import sys

RACINE = pathlib.Path(__file__).resolve().parents[2]
EXCLUS = (".venv", "site-packages", "_a_supprimer", "_non_eprouve")

# Ce qui compte comme "j'ai ecrit" et comme "je sors".
ECRITURES = ("Commit",)
SORTIES = ("exit",)

# Ce qui, sur la meme ligne ou juste avant, rend une sortie legitime.
INDICES_LEGITIMES = ("RollBack", "ECHEC", "Annule", "annule", "REFUSE",
                     "refus", "Rien a", "rien a", "aucune ecriture")


def appels(arbre, noms, module=None):
    """Lignes des appels a <module>.<nom>() ou a <nom>()."""
    trouves = []
    for n in ast.walk(arbre):
        if not isinstance(n, ast.Call):
            continue
        cible = n.func
        if isinstance(cible, ast.Attribute) and cible.attr in noms:
            if module is None or getattr(cible.value, "id", None) == module:
                trouves.append(n.lineno)
    return sorted(trouves)


def verifier(chemin):
    """(lignes a lire, nb de commits). Une ligne "a lire" est une sortie
    situee apres le premier commit, sans indice de legitimite alentour."""
    lignes = pathlib.Path(chemin).read_text(encoding="utf-8").splitlines()
    arbre = ast.parse(u"\n".join(lignes), filename=str(chemin))
    commits = appels(arbre, ECRITURES)
    sorties = appels(arbre, SORTIES, module="script")
    if not commits:
        return [], 0

    premier = min(commits)
    a_lire = []
    for ligne in sorties:
        if ligne <= premier:
            continue
        # Les lignes qui precedent disent ce qui s'est passe. La fenetre est
        # large : un message d'echec s'etale souvent sur dix lignes, et une
        # fenetre trop courte fait sortir en faux positif une sortie qui
        # suivait pourtant un RollBack.
        contexte = u" ".join(lignes[max(0, ligne - 15):ligne])
        if any(indice in contexte for indice in INDICES_LEGITIMES):
            continue
        a_lire.append(ligne)
    return a_lire, len(commits)


def defaut():
    cibles = list((RACINE / "bimflow.extension").rglob("*.pushbutton/*.py"))
    return sorted([c for c in cibles if not any(x in c.parts for x in EXCLUS)])


def main():
    cibles = [pathlib.Path(a) for a in sys.argv[1:]] or defaut()
    total = 0
    for chemin in cibles:
        a_lire, commits = verifier(chemin)
        court = chemin.parent.name
        if not commits:
            continue
        if a_lire:
            total += len(a_lire)
            print("%-36s %d commit(s) - A RELIRE, ligne(s) %s"
                  % (court, commits, ", ".join(str(l) for l in a_lire)))
        else:
            print("%-36s %d commit(s) - aucune sortie suspecte" % (court, commits))
    print()
    if total:
        print("%d sortie(s) a relire. Une sortie APRES une ecriture fait rendre\n"
              "Cancelled a la commande, et Revit annule tout - en silence.\n"
              "Verifier que chacune suit bien un RollBack ou un refus." % total)
        return 1
    print("Aucune sortie suspecte : tout script qui a commite laisse la\n"
          "commande se terminer normalement.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
