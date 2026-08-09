# 📖 Aide pour le script OCR avancé
*Extraction de données depuis des tableaux manuscrits ou imprimés avec Tesseract et OpenCV*
---
## 📌 Description
Ce script permet d'extraire automatiquement les données d'un **tableau structuré en colonnes** (ex: registres, listes, bases de données visuelles) depuis une image.
Il utilise :
- **OpenCV** pour le prétraitement d'image (binarisation, réduction de bruit, etc.)
- **Tesseract OCR** pour la reconnaissance de texte
- **Des profils de configuration** pour s'adapter à différents types de documents
---

## 🛠 Prérequis

### Logiciels requis
   Logiciel | Version | Installation | Vérification |
 |----------|---------|--------------|--------------|
 | **Python** | 3.8+ | [Télécharger Python](https://www.python.org/downloads/) | `python --version` |
 | **Tesseract OCR** | 4.0+ | **Linux**: `sudo apt install tesseract-ocr tesseract-ocr-fra`<br>**Mac**: `brew install tesseract`<br>**Windows**: [Tesseract Installer](https://github.com/UB-Mannheim/tesseract/wiki) | `tesseract --version` |
 | **Bibliothèques Python** | - | `pip install opencv-python numpy pandas pytesseract` | `pip list` |

### Configuration Tesseract pour Windows
Si tu utilises Windows, ajoute cette ligne **au début du script** (après les imports) :
```python
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
```

🚀 Installation
**Installer les dépendances Python :**
```python
pip install opencv-python numpy pandas pytesseract
```

**Installer Tesseract OCR (selon ton système, voir tableau ci-dessus).**

⚙️ Options de la ligne de commande

| Option | Description | Valeur par défaut | Exemple |
| --- | --- | --- | --- |
| --profile | Profil de configuration à utiliser | default | --profile ancien_manuscrit |
| --input | Image ou dossier d'images à traiter | A.JPG | --input images/*.jpg |
| --output | Dossier de sortie pour les résultats | output/ | --output resultats/ |
| --auto-columns | Détecte automatiquement les colonnes | Désactivé | --auto-columns |
| --preview | Génère une page HTML de prévisualisation | Désactivé | --preview |

📁 Fichiers de configuration (Profils)

**Profils prédéfinis**
| Profil | Description | Cas d'usage |
| --- | --- | --- |
| default | Paramètres pour les documents imprimés modernes | Factures, listes imprimées |
| ancien_manuscrit | Paramètres pour les manuscrits anciens | Registres historiques |

**Créer un profil personnalisé**

1.Crée un fichier dans profiles/ (ex: mon_document.json).
2. Exemple de contenu :
```json
{
    "name": "Mon document",
    "d": 12,
    "sigmaColor": 90,
    "blockSize": 15,
    "C": 1,
    "iterations_close": 2,
    "iterations_dilate": 3,
    "tesseract_lang": "fra",
    "whitelist_text": "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyzÀÂÄÇÉÈÊËÎÏÔÖÙÛÜÑàâäçéèêëîïôöùûüñ.,-",
    "whitelist_digits": "0123456789",
    "columns": [
        {"type": "text"},
        {"type": "digits"},
        {"type": "text"},
        {"type": "digits"},
        {"type": "text"},
        {"type": "digits"}
    ]
}
```
**Paramètres des profils**

| Paramètre | Description | Valeurs recommandées |
| --- | --- | --- |
| d | Taille du filtre bilatéral | 5 à 15 |
| sigmaColor | Sensibilité aux différences de couleur | 50 à 100 |
| blockSize | Taille des blocs pour la binarisation | 3, 5, 7, 9, 11, 15, 19 (impair) |
| C | Ajustement du seuil de binarisation | 0 à 10 |
| iterations_close | Itérations pour combler les trous | 1 à 3 |
| iterations_dilate | Itérations pour connecter les chiffres | 1 à 3 |
| tesseract_lang | Langue pour Tesseract | fra, eng, fra+eng |
| whitelist_text | Caractères autorisés pour le texte | Chaîne de caractères |
| whitelist_digits | Caractères autorisés pour les folios | 0123456789 |
| columns | Configuration par colonne | Liste de {"type": "text"} ou {"type": "digits"} |

📂 Sorties générées

| Fichier/Dossier | Description |
| --- | --- |
| output/<nom_image>.csv | Données extraites au format CSV |
| output/<nom_image>_config.json | Configuration utilisée |
| output/debug_<nom_image>/ | Images intermédiaires (prétraitement) |
| output/<nom_image>_preview.html | (Si --preview) Page HTML de prévisualisation |

🔍 Dépannage

**Problèmes courants**
| Problème | Solution |
| --- | --- |
| ModuleNotFoundError: No module named 'cv2' | pip install opencv-python |
| TesseractNotFoundError | Installe Tesseract (voir [Prérequis](#pr%C3%A9requis)) |
| Texte non reconnu | Ajuste les paramètres du profil ou utilise --preview |
| Chiffres non reconnus | Vérifie whitelist_digits dans ton profil |
| Colonnes mal alignées | Utilise --auto-columns ou ajuste les paramètres |

**Diagnostiquer les problèmes**

1. Vérifie les images de débogage dans output/debug_<nom_image>/ :

- 0_original.jpg : Image originale
- col_*.jpg : Chaque colonne avant/après traitement
  
2. Ajuste les paramètres :
   
- Texte trop clair → Diminue C (ex: C=0)
- Texte trop bruité → Augmente d et sigmaColor (ex: d=15, sigmaColor=100)
- Folios non reconnus → Augmente iterations_dilate (ex: 3)

🎨 Personnalisation avancée

**Modifier le prétraitement**

Édite la fonction preprocess_col() dans le script pour ajouter des étapes comme :

- Correction de la perspective
- Rotation automatique

**Traiter des PDF**
1. Installe pdf2image :
```shell
pip install pdf2image
```
2. Convertis le PDF en images avant traitement :
```python
from pdf2image import convert_from_path
images = convert_from_path("mon_document.pdf")
for i, img in enumerate(images):
    img.save(f"page_{i+1}.jpg", "JPEG")
```

📚 Ressources
- Documentation OpenCV
- Documentation Tesseract
- Tutoriel OCR avec OpenCV

🎯 Exemples d'utilisation

**Traiter une image**
```bash
python script_ocr.py --input A.JPG --output resultats/
```
**Traiter avec un profil personnalisé**
```bash
python script_ocr.py --input registre.jpg --profile ancien_manuscrit --output resultats/
```
**Traiter un dossier entier avec prévisualisation**
```bash
python script_ocr.py --input images/ --output resultats/ --preview
```
**Détecter automatiquement les colonnes**
```bash
python script_ocr.py --input tableau.jpg --auto-columns --output resultats/
```

## 🔤 **Fonctionnalité Phonex : Correction phonétique des noms**

### Description
L'algorithme **Phonex** permet de **comparer et corriger les noms** en se basant sur leur **prononciation** plutôt que leur orthographe.
Idéal pour :
✅ **Corriger les erreurs d'OCR** (ex: `"Danguyon"` → `"Danguyon"`)
✅ **Trouver des variantes d'un même nom** (ex: `"Ordonneau"` vs `"Ordonneau"`)
✅ **Normaliser les entrées** avant traitement

---
### Utilisation
1. **Calculer le code Phonex** d'un nom :
   ```python
   code = phonex_fr("Danguyon")  # Retourne "T120"
   ```











