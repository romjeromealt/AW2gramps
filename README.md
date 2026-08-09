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
  








