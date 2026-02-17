Basic script which will generate a Gramps XML file:
* https://gramps-project.org
* https://www.grampsweb.org
  
from https://www.archi-wiki.org opendata (custom `export.csv`)

**Wikipedia syntax and content**

You may also want to install `wikipedia` python module.
Under linux:

```$ pip3 install wikipedia```

or the more recent one: `wikipedia-api` from:  
https://github.com/martin-majlis/Wikipedia-API/

**Usage**

```
$ python3 AW2gramps.py export.csv output.gramps
Conversion de 13839 entrées...
Traitement des notes : 13839/13839 (100%)
Traitement des lieux : 13839/13839 (100%)
```

*Very slow*
```
$ python3 AW2gramps.py export.csv output.gramps --wikipedia
Conversion de 13839 entrées...
Traitement des notes : 677/13839 (4%)
...
```

