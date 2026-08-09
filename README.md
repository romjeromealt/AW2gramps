Basic script which will generate a Gramps XML file:
* https://gramps-project.org
* https://www.grampsweb.org
  
from https://www.archi-wiki.org opendata (custom `export.csv`)

**Wikipedia syntax and content**

You may also want to install `wikipedia` python module.
Under linux:

```$ pip3 install wikipedia```

a more recent one: `wikipedia-api` from:  
https://github.com/martin-majlis/Wikipedia-API/

or a Mediawiki bot like: 
https://www.mediawiki.org/wiki/Manual:Pywikibot

**Usage**

You could try to use Gramps for displaying some of these records.

See also https://gramps-project.org/wiki/index.php/Events_manager

```
$ python3 AW2gramps.py export.csv output.gramps
Chemin d'entrée : export.csv
Chemin de sortie : output.gramps
Début de la conversion. Sortie vers : output.gramps
Conversion de 13839 entrées...
Traitement : 13839/13839 (100%)          
Conversion terminée avec succès ! Le fichier a été enregistré sous : output.gramps

```

Paramètres à ajuster si nécessaire
 
      Paramètre
      Où le trouver
      Effet
      Valeur recommandée  
    
      d=9 (filtre bilatéral)
      Ligne 20
      Plus la valeur est grande, plus le flou est fort
      5-15   
    
      sigmaColor=75
      Ligne 20
      Contrôle la sensibilité aux différences de couleur
      50-100
       
      blockSize=11 (binarisation)
      Ligne 24
      Taille du voisinage pour le seuil adaptatif
      Doit être impair (3, 5, 7, 11...)
       
      C=2 (binarisation)
      Ligne 25
      Ajuste le seuil (plus la valeur est petite, plus c'est strict)
      0-10
    
      iterations=2 (fermeture)
      Ligne 28
      Nombre de fois où l'opération est appliquée
      1-3
    
🎯 Exemple de résultats attendus

debug_images/5_dilated.jpg :
Exemple de binarisation (Image en noir et blanc avec le texte bien contrasté)
  








