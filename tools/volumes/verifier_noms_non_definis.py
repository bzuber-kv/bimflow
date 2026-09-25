#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verifier_noms_non_definis.py - Cherche les noms utilises mais jamais definis
dans les scripts pyRevit, SANS Revit.

POURQUOI. Le 2026-09-24, un renommage de 202 familles s'est arrete sur
`NameError: name 'Family' is not defined` : une classe de l'API Revit
employee dans un garde-fou, mais absente de la liste d'imports. Le defaut
est invisible a la lecture, invisible a `ast.parse`, et ne se manifeste que
DANS Revit, au moment precis ou l'on croyait ecrire. Un clic de Bruno pour
l'apprendre.

Ce controle relit chaque script comme le ferait l'interpreteur : il note ce
qui est defini - imports, affectations, parametres, cibles de boucle, de
`with`, de `except`, de comprehension - et signale ce qui est LU sans avoir
ete defini nulle part.

CE QU'IL NE FAIT PAS. Il ne charge rien, n'execute rien, ne verifie aucun
type. Un nom defini conditionnellement lui parait defini. Il attrape la
faute d'import et la faute de frappe, pas la faute de logique.

Usage : python3 verifier_noms_non_definis.py [fichier.py ...]
        sans argument : tous les scripts de l'extension et du lib\\

Code de sortie : 0 si rien a signaler, 1 sinon.

bimflow - Keovia Solutions inc. - 2026-09-24
"""
import ast
import builtins
import pathlib
import sys

RACINE = pathlib.Path(__file__).resolve().parents[2]

# Noms que pyRevit ou l'environnement fournissent sans import visible.
FOURNIS = {"__title__", "__author__", "__doc__", "__name__", "__file__",
           "__context__", "__helpurl__", "__min_revit_ver__", "__persistentengine__"}


class Portee(object):
    def __init__(self, parent=None):
        self.parent = parent
        self.noms = set()

    def definir(self, nom):
        if nom:
            self.noms.add(nom)

    def connait(self, nom):
        p = self
        while p is not None:
            if nom in p.noms:
                return True
            p = p.parent
        return False


class Visiteur(ast.NodeVisitor):
    """Deux temps par portee : on releve d'abord TOUT ce qui y est defini,
    puis on verifie les lectures. Sans cela, une fonction appelee avant sa
    definition dans le fichier passerait pour inconnue."""

    def __init__(self, portee):
        self.portee = portee
        self.manquants = []

    # --- releve des definitions ---------------------------------------
    def relever(self, corps):
        for noeud in corps:
            for n in ast.walk(noeud):
                if isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store,
                                                                  ast.Del)):
                    self.portee.definir(n.id)
                elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef,
                                    ast.ClassDef)):
                    self.portee.definir(n.name)
                elif isinstance(n, (ast.Import, ast.ImportFrom)):
                    for a in n.names:
                        self.portee.definir(a.asname or a.name.split(".")[0])
                elif isinstance(n, ast.ExceptHandler) and n.name:
                    self.portee.definir(n.name)
                elif isinstance(n, ast.Global):
                    for nom in n.names:
                        self.portee.definir(nom)
                elif isinstance(n, ast.arg):
                    self.portee.definir(n.arg)

    def visit_Name(self, noeud):
        if isinstance(noeud.ctx, ast.Load):
            nom = noeud.id
            if (not self.portee.connait(nom)
                    and not hasattr(builtins, nom)
                    and nom not in FOURNIS):
                self.manquants.append((noeud.lineno, nom))

    def visit_FunctionDef(self, noeud):
        interne = Portee(self.portee)
        for a in (list(noeud.args.args) + list(noeud.args.kwonlyargs)
                  + ([noeud.args.vararg] if noeud.args.vararg else [])
                  + ([noeud.args.kwarg] if noeud.args.kwarg else [])):
            interne.definir(a.arg)
        v = Visiteur(interne)
        v.relever(noeud.body)
        for enfant in noeud.body:
            v.visit(enfant)
        self.manquants.extend(v.manquants)

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Lambda(self, noeud):
        interne = Portee(self.portee)
        for a in noeud.args.args:
            interne.definir(a.arg)
        v = Visiteur(interne)
        v.visit(noeud.body)
        self.manquants.extend(v.manquants)

    def _comprehension(self, noeud):
        interne = Portee(self.portee)
        for gen in noeud.generators:
            for n in ast.walk(gen.target):
                if isinstance(n, ast.Name):
                    interne.definir(n.id)
        v = Visiteur(interne)
        for gen in noeud.generators:
            v.visit(gen.iter)
            for si in gen.ifs:
                v.visit(si)
        for champ in ("elt", "key", "value"):
            if hasattr(noeud, champ):
                v.visit(getattr(noeud, champ))
        self.manquants.extend(v.manquants)

    visit_ListComp = _comprehension
    visit_SetComp = _comprehension
    visit_GeneratorExp = _comprehension
    visit_DictComp = _comprehension


def verifier(chemin):
    arbre = ast.parse(pathlib.Path(chemin).read_text(encoding="utf-8"),
                      filename=str(chemin))
    # `from X import *` rend l'analyse impossible : on ne sait pas ce qui
    # entre. Le dire, plutot que de rendre une liste de faux positifs.
    for n in ast.walk(arbre):
        if isinstance(n, ast.ImportFrom) and any(a.name == "*"
                                                 for a in n.names):
            return None
    portee = Portee()
    v = Visiteur(portee)
    v.relever(arbre.body)
    for noeud in arbre.body:
        v.visit(noeud)
    vus, sortie = set(), []
    for ligne, nom in v.manquants:
        if (ligne, nom) in vus:
            continue
        vus.add((ligne, nom))
        sortie.append((ligne, nom))
    return sorted(sortie)


EXCLUS = (".venv", "site-packages", "_a_supprimer", "_non_eprouve")


def defaut():
    """Le code de CE depot, et lui seul : ni environnement virtuel, ni
    bibliotheque tierce, ni dossier mis de cote."""
    cibles = list((RACINE / "bimflow.extension" / "lib").glob("*.py"))
    cibles += list((RACINE / "bimflow.extension").rglob("*.pushbutton/*.py"))
    cibles += list((RACINE / "tools").rglob("*.py"))
    return sorted(set([c for c in cibles
                       if not any(x in c.parts for x in EXCLUS)]))


def main():
    cibles = [pathlib.Path(a) for a in sys.argv[1:]] or defaut()
    total = 0
    for chemin in cibles:
        manquants = verifier(chemin)
        court = str(chemin).replace(str(RACINE) + "\\", "")
        if manquants is None:
            print("%-72s NON ANALYSE (import *)" % court)
        elif manquants:
            total += len(manquants)
            print("%s" % court)
            for ligne, nom in manquants:
                print("    ligne %-5d nom inconnu : %s" % (ligne, nom))
        else:
            print("%-72s OK" % court)
    print()
    if total:
        print("%d nom(s) utilise(s) sans avoir ete defini(s). Dans Revit, "
              "chacun est un\nNameError au moment ou la ligne s'execute - "
              "souvent au pire moment." % total)
        return 1
    print("Aucun nom non defini.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
