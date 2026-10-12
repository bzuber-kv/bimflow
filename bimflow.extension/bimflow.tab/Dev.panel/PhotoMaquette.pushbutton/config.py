# -*- coding: utf-8 -*-
"""Photo maquette - Maj+clic : choisir le dossier de sortie.

Ecrit %APPDATA%\\bimflow\\photo_maquette.json (cle "dossier_sortie").
Rien n'est lu ni ecrit dans la maquette. Le fichier peut aussi s'editer a
la main, avec des %VAR% (ex. %USERPROFILE%) qui seront developpees a
l'execution.
"""

from pyrevit import forms

import bimflow_photo as photo

fichier = photo.chemin_config()
actuel, brut, motif = photo.lire_config(fichier)
choisi = forms.pick_folder(title=u"Photo maquette - dossier de sortie")
if choisi:
    photo.ecrire_config(fichier, choisi)
    forms.alert(u"Dossier de sortie retenu :\n{0}\n\nConfiguration : {1}"
                .format(choisi, fichier))
else:
    forms.alert(u"Rien de change.\n\nDossier actuel : {0}".format(
        actuel or motif))
