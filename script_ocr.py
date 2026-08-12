import argparse
import cv2
import numpy as np
import pytesseract
import pandas as pd
import os
import json
import glob
import shutil
import re
import string
import unicodedata
import subprocess
import tempfile
import sys
from pathlib import Path
from collections import defaultdict
from datetime import datetime

# Vérification et import d'EasyOCR

# Ajoute les répertoires utilisateur et système à PYTHONPATH
user_site = os.path.expanduser("~/.local/lib/python3.6/site-packages")
sys_site = "/usr/local/lib/python3.6/dist-packages"

for path in [user_site, sys_site]:
    if os.path.exists(path) and path not in sys.path:
        sys.path.append(path)

# Vérification de easyocr
try:
    import easyocr
    EASYOCR_AVAILABLE = True
    print("✅ EasyOCR disponible (version {})".format(easyocr.__version__))
except ImportError as e:
    easyocr = None
    EASYOCR_AVAILABLE = False
    print("❌ EasyOCR non trouvé. Erreur :", e)
    print("   Vérifiez l'installation avec : pip3 install --user easyocr")
    print("   Essayez peut être : pip3 install --user --upgrade easyocr pillow")
    print("   ou pip3 install --user --force-reinstall python-bidi==0.21.0")

# Vérification de torchfree-ocr
try:
    import torchfree_ocr
    TORCHFREE_AVAILABLE = True
    print("✅ TorchFree OCR disponible (version {})".format(torchfree_ocr.__version__))
except ImportError as e:
    torchfreeocr = None
    TORCHFREE_AVAILABLE = False
    print("❌ TorchFree OCR non trouvé. Erreur :", e)
    print("   Vérifiez l'installation avec : pip3 install --user torchfree-ocr")
    print("   Si erreur de compilation : pip3 install --user --upgrade onnxruntime opencv-python")

# =============================================================================
# ALGORITHME PHONEX (pour la comparaison phonétique des noms)
# =============================================================================

IGNORE = "HW~!@#$%^&*()_+=-`[]\|;:'/?.,<>\" \t\f\v"
source = string.ascii_uppercase  # 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
destination = '01230120224550126230120200'
TABLE = str.maketrans(source, destination)

def phonex_fr(strval):
    """Retourne la valeur Phonex pour une chaîne (français)."""
    if strval is None:
        return "Z000"

    # 1. Remplacer les y par des i et normaliser les accents
    r = strval.upper().strip()
    r = r.replace('Y', 'I')
    r = r.replace(u'É', 'Y').replace(u'È', 'Y').replace(u'Ê', 'Y')

    # Normalisation Unicode
    r = unicodedata.normalize('NFKD', r).encode('ASCII', 'ignore').decode('ASCII')

    if not r:
        return "Z000"

    # 2. Supprimer les h non précédés de C, S ou P
    r = re.sub(r'([^P|C|S])H', r'\1', r)

    # 3. Remplacer PH par F
    r = r.replace('PH', 'F')

    # 4. Remplacer les groupes de lettres
    r = re.sub(r'G(AI?[N|M])', r'K\1', r)

    # 5. Remplacer les occurrences suivies de a, e, i, o, u
    r = re.sub(r'[A|E]I[N|M]([A|E|I|O|U])', r'YN\1', r)

    # 6. Remplacer les groupes de 3 lettres (sons 'o', 'oua', 'ein')
    r = r.replace('EAU', 'O')
    r = r.replace('OUA', '2')
    r = r.replace('EIN', '4')
    r = r.replace('AIN', '4')
    r = r.replace('EIM', '4')
    r = r.replace('AIM', '4')

    # 7. Remplacer le son É
    r = r.replace('AI', 'Y')
    r = r.replace('EI', 'Y')
    r = r.replace('ER', 'YR')
    r = r.replace('ESS', 'YS')
    r = r.replace('ET', 'YT')
    r = r.replace('EZ', 'YZ')

    # 8. Remplacer les groupes AN/ON/AM/EN/EM/IN (sauf suivis de a,e,i,o,u ou 1-4)
    r = re.sub(r'AN([^A|E|I|O|U|1|2|3|4])', r'1\1', r)
    r = re.sub(r'ON([^A|E|I|O|U|1|2|3|4])', r'1\1', r)
    r = re.sub(r'AM([^A|E|I|O|U|1|2|3|4])', r'1\1', r)
    r = re.sub(r'EN([^A|E|I|O|U|1|2|3|4])', r'1\1', r)
    r = re.sub(r'EM([^A|E|I|O|U|1|2|3|4])', r'1\1', r)
    r = re.sub(r'IN([^A|E|I|O|U|1|2|3|4])', r'4\1', r)

    # 9. Remplacer les S entre voyelles par Z
    r = re.sub(r'([A|E|I|O|U|Y|1|2|3|4])S([A|E|I|O|U|Y|1|2|3|4])', r'\1Z\2', r)

    # 10. Remplacer les groupes de 2 lettres
    r = r.replace('OE', 'E')
    r = r.replace('EU', 'E')
    r = r.replace('AU', 'O')
    r = r.replace('OI', '2')
    r = r.replace('OY', '2')
    r = r.replace('OU', '3')

    # 11. Remplacer les groupes de lettres (CH, SCH, SH, etc.)
    r = r.replace('CH', '5')
    r = r.replace('SCH', '5')
    r = r.replace('SH', '5')
    r = r.replace('SS', 'S')
    r = r.replace('SC', 'S')

    # 12. Remplacer C par S s'il est suivi de E ou I
    r = re.sub(r'C([E|I])', r'S\1', r)

    # 13. Remplacer les lettres ou groupes
    r = r.replace('C', 'K')
    r = r.replace('Q', 'K')
    r = r.replace('QU', 'K')
    r = r.replace('GU', 'K')
    r = r.replace('GA', 'KA')
    r = r.replace('GO', 'KO')
    r = r.replace('GY', 'KY')

    # 14. Remplacer les lettres
    r = r.replace('A', 'O')
    r = r.replace('D', 'T')
    r = r.replace('P', 'T')
    r = r.replace('J', 'G')
    r = r.replace('B', 'F')
    r = r.replace('V', 'F')
    r = r.replace('M', 'N')

    # 15. Supprimer les lettres dupliquées
    oldc = '#'
    newr = ''
    for c in r:
        if oldc != c:
            newr += c
        oldc = c
    r = newr

    # 16. Supprimer les terminaisons T, X
    r = re.sub(r'(.*)[T|X]$', r'\1', r)

    # 17. Appliquer la table de traduction
    str2 = r[0] if r else ''
    r = r.translate(TABLE)

    if not r:
        return "Z000"

    # 18. Supprimer les doublons consécutifs (sauf 0)
    prev = r[0]
    for character in r[1:]:
        if character != prev and character != "0":
            str2 += character
        prev = character

    # 19. Compléter avec des zéros
    str2 = str2 + "0000"
    return str2[:4]

def compare_phonex(str1, str2):
    """Compare deux chaînes phonétiquement (1 si similaires, 0 sinon)."""
    return phonex_fr(str1) == phonex_fr(str2)

def tesseract_ocr_raw(image, lang="fra", psm=6, whitelist=None, digits_only=False):
    """
    Appel direct à la commande `tesseract` via subprocess.
    Args:
        image: Chemin vers l'image (str) OU tableau numpy.
        lang: Langue(s) (ex: "fra" ou "fra,eng").
        psm: Mode de segmentation (6=bloc de texte, 13=ligne unique).
        whitelist: Caractères autorisés (ex: "0123456789ABC...").
        digits_only: Si True, force le mode "digits" (équivalent à `match digits`).
    Returns:
        Texte extrait (str).
    """
    # Sauvegarder l'image temporairement si c'est un tableau numpy
    if isinstance(image, np.ndarray):
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp_path = tmp.name
            cv2.imwrite(tmp_path, image)
    else:
        tmp_path = image

    # un fichier temporaire pour la sortie
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as tmp_out:
        tmp_out_path = tmp_out.name

    try:
        cmd = [
            "tesseract",
            tmp_path,
            "stdout", # sortie vers stdout
            "-l", lang.replace(",", "+"),  # Transforme "fra,eng" en "fra+eng" (valide)
            "--psm", str(psm),
            "--oem", "1",  # Moteur LSTM
        ]
        if whitelist:
            # Nettoyer la whitelist (enlever les caractères problématiques)
            clean_whitelist = "".join(c for c in whitelist if c.isalnum() or c in ".,-")
            cmd.extend(["-c", f"tessedit_char_whitelist={clean_whitelist}"])
        if digits_only:
            cmd.extend(["-c", "tessedit_char_whitelist=0123456789"])

        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,  # Capture stdout
            stderr=subprocess.PIPE,  # Capture stderr
            universal_newlines=True  # Équivalent à text=True
        )
        if result.returncode != 0:
            print(f"❌ Erreur Tesseract (code {result.returncode}) :")
            print(f"   Commande : {' '.join(cmd)}")
            print(f"   Erreur : {result.stderr.strip()}")
            return ""

        return result.stdout.strip()

    finally:
        if isinstance(image, np.ndarray) and os.path.exists(tmp_path):
            os.unlink(tmp_path)

def easyocr_text_extraction(image, languages=["fr"], detail=0, **kwargs):
    """
    Extrait le texte d'une image avec EasyOCR.
    Args:
        image: Chemin vers l'image (str) OU tableau numpy.
        languages: Liste des langues (ex: ["fr"], ["fr", "en"]).
        detail: Si 1, retourne les détails (coordonnées, confiance, etc.).
        **kwargs: Arguments supplémentaires pour EasyOCR (ex: `model_storage_directory`, `user_network_directory`).
    Returns:
        Texte extrait (str) ou liste de résultats détaillés si `detail=1`.
    """
    if not EASYOCR_AVAILABLE:
        raise RuntimeError("EasyOCR n'est pas installé ou non disponible.")

    # Gestion de l'entrée (chemin ou numpy array)
    if isinstance(image, np.ndarray):
        img = image.copy()
    elif isinstance(image, str) and os.path.exists(image):
        img = cv2.imread(image)
        if img is None:
            raise ValueError(f"Impossible de charger l'image : {image}")
    else:
        raise TypeError("L'image doit être un chemin (str) ou un tableau numpy.")

    # Initialiser le lecteur EasyOCR (cache le modèle pour éviter de le recharger)
    if not hasattr(easyocr_text_extraction, "reader"):
        easyocr_text_extraction.reader = easyocr.Reader(languages, **kwargs)
        # easyocr_text_extraction.reader = easyocr.Reader(languages, gpu=False, quantize=False, **kwargs)

    # Extraire le texte
    results = easyocr_text_extraction.reader.readtext(image, detail=0, batch_size=4)

    if detail == 1:
        return results

    texts = []
    for res in results:
        if isinstance(res, (list, tuple)) and len(res) >= 3:  # Format attendu : (bbox, text, confiance)
            if res[2] > 0.1:  # Seuil de confiance
                texts.append(res[1])  # Prend le texte (2ème élément)
        elif isinstance(res, str):  # Si EasyOCR retourne directement une chaîne
            texts.append(res)
        # Ignore les résultats mal formatés

    return " ".join(texts).strip() if texts else ""

def torchfreeocr_text_extraction(image, lang=["fr"], detail=0, **kwargs):
    """
    Extrait le texte avec torchfree-ocr (100% sans PyTorch).
    Args:
        image: Chemin ou tableau numpy (BGR).
        lang: Langue (ex: "fr", "en").
    Returns:
        Texte extrait (str).
    """
    if not TORCHFREE_AVAILABLE:
        raise RuntimeError("torchfree_ocr n'est pas installé ou non disponible.")

    # Gestion de l'entrée
    if isinstance(image, np.ndarray):
        img = image.copy()
    elif isinstance(image, str) and os.path.exists(image):
        img = cv2.imread(image)
        if img is None:
            raise ValueError(f"Impossible de charger {image}")
    else:
        raise TypeError("L'image doit être un chemin (str) ou un tableau numpy.")

    # Initialiser le lecteur (cache le modèle pour éviter de le recharger)
    if not hasattr(torchfreeocr_text_extraction, "reader"):
        torchfreeocr_text_extraction.reader = torchfree_ocr.Reader(lang, **kwargs)

    # Extraction du texte
    results = torchfreeocr_text_extraction.reader.readtext(img, detail=0, batch_size=4)

    if detail == 1:
        return results

    # Format des résultats : [{"text": "texte", "confidence": 0.99, ...}, ...]
    texts = [res.get("text", "") for res in results if isinstance(res, dict)]
    return " ".join(texts).strip()

# =============================================================================
# Dictionnaire de correction phonétique  (chargé depuis un fichier JSON)
# =============================================================================

DEFAULT_DICT_PATH = "dictionnaire_noms.json"  # Chemin par défaut

def charger_dictionnaire_noms(path=None):
    """
    Charge un dictionnaire de noms depuis un fichier JSON.
    Si le fichier n'existe pas, retourne un dictionnaire vide.
    {
    "Danguyon": ["Danguyon", "Danguyon", "Danguyon"],
    "Ordonneau": ["Ordonneau", "Ordonneau", "Ordonnau"],
    "Acker": ["Acker", "Acker", "Aker", "Accker"],
    "Albejard": ["Albejard", "Albejart", "Albejard"],
    "Barthélemy": ["Barthélemy", "Barthelemy", "Barthélémy"],
    "Aubert": ["Aubert", "Aubert", "Aubèrt"],
    "Boeuf": ["Boeuf", "Boeuf", "Bœuf"],
    "Chabert": ["Chabert", "Chabert", "Chabèrt"],
    "Dubois": ["Dubois", "Dubois", "Du Bois", "DuBois"],
    "Martin": ["Martin", "Martain", "Martain"],
    "Moreau": ["Moreau", "Moreau", "Morau"],
    "Roux": ["Roux", "Roux", "Rou"],
    "Simon": ["Simon", "Simond", "Simond"]
    }

    """
    if path is None:
        path = DEFAULT_DICT_PATH

    if not os.path.exists(path):
        print(f"⚠️ Fichier de dictionnaire introuvable : {path}")
        print("   Un dictionnaire vide sera utilisé.")
        return {}

    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        print(f"❌ Erreur dans le fichier {path} : {e}")
        return {}
    except Exception as e:
        print(f"❌ Impossible de charger {path} : {e}")
        return {}

def sauvegader_dictionnaire_noms(dictionnaire, path=None):
    """
    Sauvegarde un dictionnaire de noms dans un fichier JSON.
    """
    if path is None:
        path = DEFAULT_DICT_PATH

    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(dictionnaire, f, indent=4, ensure_ascii=False)
        print(f"✅ Dictionnaire sauvegardé dans {path}")
    except Exception as e:
        print(f"❌ Impossible de sauvegarder {path} : {e}")

# Charger le dictionnaire au démarrage
CORRECTIONS_PHONETIQUES = charger_dictionnaire_noms()

def corriger_nom(nom, dictionnaire=None):
    """Corrige un nom en utilisant Phonex et un dictionnaire de variantes."""
    if dictionnaire is None:
        dictionnaire = CORRECTIONS_PHONETIQUES

    if not nom:
        return nom

    nom = nom.strip().upper()  # Normaliser

    # Vérifier si le nom est déjà canonique ou dans les variantes
    for canonique, variantes in dictionnaire.items():
        if nom == canonique or nom in variantes:
            return canonique

    # Chercher une correspondance phonétique
    for canonique, variantes in dictionnaire.items():
        if compare_phonex(nom, canonique):
            return canonique
        for variante in variantes:
            if compare_phonex(nom, variante):
                return canonique

    return nom  # Retourner le nom original si aucune correspondance

# --- 1. Gestion des arguments en ligne de commande ---
parser = argparse.ArgumentParser(description="Extraction OCR de tableaux avec configuration avancée")
parser.add_argument("--profile", type=str, default="default", help="Profil de configuration à utiliser (ex: ancien_manuscrit)")
parser.add_argument("--input", type=str, default="A.JPG", help="Image ou dossier d'images à traiter (ex: images/*.jpg)")
parser.add_argument("--output", type=str, default="output", help="Dossier de sortie (défaut: output/)")
parser.add_argument("--preview", action="store_true", help="Générer une page HTML de prévisualisation")
parser.add_argument("--auto-columns", action="store_true", help="Détecter automatiquement les colonnes")
parser.add_argument("--dictionnaire", type=str, default=None, help="Chemin vers le fichier JSON du dictionnaire de noms (défaut: dictionnaire_noms.json)"
)
parser.add_argument("--update-dict", action="store_true", help="Mode édition interactive du dictionnaire de noms"
)
parser.add_argument("--raw-tesseract", action="store_true", help="Utiliser l'appel direct à `tesseract` (au lieu de pytesseract)"
)
parser.add_argument("--easyocr", action="store_true", help="Forcer l'utilisation d'EasyOCR (ignore la config du profil)"
)
parser.add_argument("--torchfree", action="store_true", help="Utiliser torchfree-ocr (sans PyTorch)")
args = parser.parse_args()

# --- 2. Charger la configuration ---
CONFIG_DIR = "profiles"
os.makedirs(CONFIG_DIR, exist_ok=True)
os.makedirs(args.output, exist_ok=True)

# Profils prédéfinis
DEFAULT_PROFILES = {
    "default": {
        "name": "Par défaut (documents imprimés)",
        "d": 9,
        "sigmaColor": 75,
        "blockSize": 11,
        "C": 2,
        "iterations_close": 1,
        "iterations_dilate": 2,
        "tesseract_lang": "fra+eng",
        "whitelist_text": "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyzÀÂÄÇÉÈÊËÎÏÔÖÙÛÜÑàâäçéèêëîïôöùûüñ.,-",
        "whitelist_digits": "0123456789IOO°¶-",
        "columns": [
            {"type": "text", "is_name": True},
            {"type": "digits", "is_name": False},
            {"type": "text", "is_name": True},
            {"type": "digits", "is_name": False},
            {"type": "text", "is_name": True},
            {"type": "digits", "is_name": False},
        ]
    },
    "ancien_manuscrit": {
        "name": "Manuscrits anciens (bruit, fond non uniforme)",
        "d": 15,
        "sigmaColor": 100,
        "blockSize": 19,
        "C": 0,
        "iterations_close": 2,
        "iterations_dilate": 3,
        "tesseract_lang": "fra",
        "whitelist_text": "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyzÀÂÄÇÉÈÊËÎÏÔÖÙÛÜÑàâäçéèêëîïôöùûüñ.,-",
        "whitelist_digits": "0123456789IOO°¶-",
        "columns": [
            {"type": "text", "is_name": True},
            {"type": "digits", "is_name": False},
            {"type": "text", "is_name": True},
            {"type": "digits", "is_name": False},
            {"type": "text", "is_name": True},
            {"type": "digits", "is_name": False}
         ]
    },
    "easyocr": {
        "name": "easyocr",
        "ocr_engine": "easyocr",  # Utilise EasyOCR pour ce profil
        "easyocr_languages": ["fr", "en"],  # Exemple avec plusieurs langues
        "sigmaColor": 75,
        "blockSize": 11,
        "C": 2,
        "iterations_close": 1,
        "iterations_dilate": 2,
        "whitelist_text": "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyzÀÂÄÇÉÈÊËÎÏÔÖÙÛÜÑàâäçéèêëîïôöùûüñ.,-",
        "whitelist_digits": "0123456789IOO°¶-",
        "columns": [
            {"type": "text", "is_name": True},
            {"type": "digits", "is_name": False},
            {"type": "text", "is_name": True},
            {"type": "digits", "is_name": False},
            {"type": "text", "is_name": True},
            {"type": "digits", "is_name": False},
        ]
    },
    "torchfree": {
    "name": "TorchFree OCR (ONNX Runtime)",
    "ocr_engine": "torchfree",
    "torchfree_lang": "fr",
    "columns": [...]
    }
}

# Charger ou créer le profil
def load_profile(profile_name):
    profile_path = os.path.join(CONFIG_DIR, f"{profile_name}.json")
    if os.path.exists(profile_path):
        with open(profile_path, "r") as f:
            return json.load(f)
    elif profile_name in DEFAULT_PROFILES:
        return DEFAULT_PROFILES[profile_name].copy()
    else:
        print(f"⚠️ Profil '{profile_name}' introuvable. Utilisation du profil 'default'.")
        return DEFAULT_PROFILES["default"].copy()

config = load_profile(args.profile)

# --- 3. Détection automatique des colonnes (optionnelle) ---
def detect_columns(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 150, apertureSize=3)
    lines = cv2.HoughLinesP(edges, 1, np.pi/180, threshold=100, minLineLength=50, maxLineGap=10)
    if lines is None:
        return []
    vertical_lines = []
    for line in lines:
        # Vérifier que line[0] est un tableau de 4 éléments
        if line is None or len(line) == 0:
            continue
        try:
            x1, y1, x2, y2 = line[0]
        except (TypeError, ValueError):
            # Si line[0] n'est pas itérable ou n'a pas 4 éléments, ignorer
            continue
        if abs(x1 - x2) < 20:  # Ligne verticale (tolérance de 20 pixels)
            vertical_lines.append((x1 + x2) // 2)
    vertical_lines = sorted(list(set(vertical_lines)))
    return vertical_lines

# --- 4. Traitement des images ---
def process_image(image_path, config, output_dir):
    original_img = cv2.imread(image_path)
    if original_img is None:
        print(f"❌ Impossible de charger {image_path}")
        return

    img_height, img_width = original_img.shape[:2]
    filename = os.path.splitext(os.path.basename(image_path))[0]

    # Créer un dossier de débogage pour cette image
    debug_dir = Path(output_dir) / f"debug_{Path(image_path).stem}"
    debug_dir.mkdir(parents=True, exist_ok=True)

    # Détecter ou utiliser les colonnes fixes
    if args.auto_columns:
        col_x_positions = detect_columns(original_img)
        if len(col_x_positions) < 2:
            print(f"⚠️ Impossible de détecter les colonnes pour {image_path}. Utilisation de 6 colonnes fixes.")
            col_x_positions = [i * img_width // 6 for i in range(1, 6)]
        col_x_positions = [0] + col_x_positions + [img_width]
    else:
        num_cols = max(1, len(config["columns"]))  # Au moins 1 colonne
        col_x_positions = [i * img_width // num_cols for i in range(num_cols + 1)]

    # Sauvegarder l'image originale
    cv2.imwrite(os.path.join(debug_dir, "0_original.jpg"), original_img)

    use_raw_tesseract = args.raw_tesseract
    # Détermine le moteur OCR (priorité : CLI > config)
    if args.easyocr:
        ocr_engine = "easyocr"
    elif args.torchfree:
        ocr_engine = "torchfree"
    else:
        ocr_engine = config.get("ocr_engine", "pytesseract")

    # Prétraitement
    def preprocess_col(img, col_type):
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        inverted_image = cv2.bitwise_not(gray)

        return inverted_image

    # Extraire le texte de chaque colonne
    col_texts = []
    for i in range(len(col_x_positions) - 1):
        start, end = col_x_positions[i], col_x_positions[i + 1]
        col_img = original_img[:, start:end]
        cv2.imwrite(os.path.join(debug_dir, f"col_{i+1}.jpg"), col_img)

        col_type = config["columns"][i]["type"] if i < len(config["columns"]) else "text"
        processed_col = preprocess_col(col_img, col_type)
        cv2.imwrite(os.path.join(debug_dir, f"col_{i+1}_processed.jpg"), processed_col)

        # Config Tesseract
        use_raw_tesseract = False

        tesseract_config = (
                '--oem 1 '  # Moteur LSTM (obligatoire pour les manuscrits)
                '--psm 6 '  # Bloc de texte
                '-l fra+eng '
                '-c  tessedit_char_whitelist=0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyzÀÂÄÇÉÈÊËÎÏÔÖÙÛÜÑàâäçéèêëîïôöùûüñ'
                '-c tessedit_unreject_ambig=true ' # Améliore la détection des caractères ambigus
            )

        # Utiliser le moteur OCR sélectionné
        text = ""
        if ocr_engine == "easyocr" and EASYOCR_AVAILABLE:
            try:
                text = easyocr_text_extraction(processed_col, languages=config.get("easyocr_languages", ["fr"]))
                if col_type == "digits":
                    text = re.sub(r"[^0-9]", "", text)
                print(f"[DEBUG EasyOCR] Colonne {i+1}: {text[:50]}...")
            except Exception as e:
                print(f"❌ Erreur EasyOCR: {e}")
                text = ""
        elif ocr_engine == "torchfree" and TORCHFREE_AVAILABLE:
            try:
                text = torchfreeocr_text_extraction(processed_col, lang=config.get("torchfree_lang", ["fr"]))
                if col_type == "digits":
                    text = re.sub(r"[^0-9]", "", text)
                print(f"[DEBUG TorchFree] Colonne {i+1}: {text[:50]}...")
            except Exception as e:
                print(f"❌ Erreur TorchFree: {e}")
                text = ""
        elif use_raw_tesseract:
            if col_type == "digits":
                text = tesseract_ocr_raw(
                    processed_col,
                    lang=config["tesseract_lang"],
                    psm=6,
                    digits_only=True  # Équivalent à `match digits`
                )
            else:
                text = tesseract_ocr_raw(
                    processed_col,
                    lang=config["tesseract_lang"],
                    psm=6,
                    whitelist=config.get("whitelist_text")
                )
        else:
            text = pytesseract.image_to_string(processed_col, config=tesseract_config).strip()
        col_texts.append(text)

    # Nettoyer les résultats aberrants
    for i in range(len(col_texts)):
        if i % 2 == 1:  # Colonnes de folios (2, 4, 6)
            col_texts[i] = re.sub(r"[^0-9]", "", col_texts[i])  # Garde UNIQUEMENT les chiffres
        else:  # Colonnes de noms
            col_texts[i] = re.sub(r"[^A-Za-zÀ-ÿ0-9\s-]", "", col_texts[i])  # Garde lettres, chiffres, espaces, -

    # Structurer les données
    lines = []
    for text in col_texts:
        lines.append([line.strip() for line in text.split('\n') if line.strip()])

    max_lines = max(len(col_lines) for col_lines in lines)
    structured_data = []
    headers = [f"Colonne {i+1}" for i in range(len(col_texts))]
    for i in range(max_lines):
        row_data = {}
        for j, header in enumerate(headers):
            if i < len(lines[j]):
                # Vérifier si c'est une colonne de nom ET si on a une config pour cette colonne
                is_name_col = False
                if j < len(config["columns"]):
                    is_name_col = config["columns"][j].get("is_name", True)
                if is_name_col:
                    row_data[header] = corriger_nom(lines[j][i], CORRECTIONS_PHONETIQUES)
                else:
                    row_data[header] = lines[j][i]  # Texte brut pour les non-noms
            else:
                row_data[header] = ""  # Cellule vide
        structured_data.append(row_data)

    # Exporter en CSV
    csv_path = os.path.join(output_dir, f"{filename}.csv")
    pd.DataFrame(structured_data).to_csv(csv_path, index=False, encoding="utf-8-sig")

    # Afficher les codes Phonex pour vérification ---
    print("\n🔍 Codes Phonex pour les noms (pour vérification) :")
    for row in structured_data[:5]:  # Affiche les 5 premières lignes
        for header in headers[::2]:  # Colonnes de noms (1, 3, 5)
            nom = row[header]
            if nom:
                print(f"{nom}: {phonex_fr(nom)}")

    # Sauvegarder la config utilisée
    with open(os.path.join(output_dir, f"{filename}_config.json"), "w") as f:
        json.dump(config, f, indent=4)

    # Générer une prévisualisation HTML si demandé
    if args.preview:
        generate_preview_html(debug_dir, config, structured_data, os.path.join(output_dir, f"{filename}_preview.html"))

    print(f"✅ {image_path} → {csv_path} ({len(structured_data)} lignes)")

    # Debug
    text_pytesseract = pytesseract.image_to_string(processed_col, config=tesseract_config).strip()
    text_raw = tesseract_ocr_raw(processed_col, lang='fra,eng,osd', psm=6, whitelist=config.get("whitelist_text"))

    print(f"[DEBUG] pytesseract:\n{text_pytesseract}")
    print(f"[DEBUG] raw tesseract:\n{text_raw}")

    return structured_data

# --- 5. Générer la prévisualisation HTML ---
def generate_preview_html(debug_dir, config, results, html_path):
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Prévisualisation OCR - {datetime.now().strftime("%Y-%m-%d %H:%M")}</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 20px; }}
            .container {{ display: flex; flex-wrap: wrap; }}
            .image {{ margin: 10px; border: 1px solid #ccc; max-width: 300px; }}
            .params {{ background: #f0f0f0; padding: 15px; margin: 10px; border-radius: 5px; }}
            table {{ border-collapse: collapse; width: 100%; margin: 20px 0; }}
            th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
            th {{ background-color: #f2f2f2; }}
        </style>
    </head>
    <body>
        <h1>Prévisualisation OCR</h1>
        <div class="params">
            <h2>Configuration utilisée</h2>
            <pre>{json.dumps(config, indent=2)}</pre>
        </div>
        <h2>Images intermédiaires</h2>
        <div class="container">
    """

    for img_file in sorted(os.listdir(debug_dir)):
        if img_file.endswith(('.jpg', '.png')):
            html += f'<div class="image"><h3>{img_file}</h3><img src="{img_file}" width="300"></div>'

    html += """
        </div>
        <h2>Résultats extraits</h2>
        <table>
            <thead><tr>
    """

    for header in (results[0].keys() if results else []):
        html += f"<th>{header}</th>"
    html += "</tr></thead><tbody>"

    for row in results:
        html += "<tr>"
        for value in row.values():
            html += f"<td>{value}</td>"
        html += "</tr>"

    html += """
        </tbody></table>
    </body>
    </html>
    """

    # Copier les images dans le dossier de sortie pour la prévisualisation
    for img_file in os.listdir(debug_dir):
        if img_file.endswith(('.jpg', '.png')):
            shutil.copy(os.path.join(debug_dir, img_file), os.path.join(os.path.dirname(html_path), img_file))

    with open(html_path, "w") as f:
        f.write(html)

# --- 6. Traitement des images ---
if os.path.isdir(args.input):
    # Traiter un dossier d'images
    image_paths = glob.glob(os.path.join(args.input, "*.jpg")) + glob.glob(os.path.join(args.input, "*.png"))
    for img_path in image_paths:
        process_image(img_path, config, args.output)
else:
    # Traiter une seule image
    process_image(args.input, config, args.output)

print("\n✅ Traitement terminé !")
print(f"📁 Résultats sauvegardés dans: {args.output}")
if args.preview:
    print("🌐 Ouvre les fichiers *_preview.html pour voir les résultats.")

# =============================================================================
# COMMANDE POUR METTRE À JOUR LE DICTIONNAIRE
# =============================================================================
if args.update_dict:
    print("\n📝 Mode édition du dictionnaire de noms")
    print("   Appuie sur Ctrl+C pour quitter.")

    # Charger le dictionnaire actuel
    current_dict = charger_dictionnaire_noms(args.dictionnaire)

    while True:
        print("\nOptions:")
        print("1. Ajouter un nom")
        print("2. Supprimer un nom")
        print("3. Afficher le dictionnaire")
        print("4. Quitter")
        choice = input("Choix (1-4): ").strip()

        if choice == "1":
            canonique = input("Nom canonique (ex: Danguyon): ").strip()
            if not canonique:
                print("❌ Nom vide ignoré.")
                continue
            variantes = input("Variantes (séparées par des virgules, ex: Danguyon,Danguyon): ").strip()
            variantes = [v.strip() for v in variantes.split(",") if v.strip()]
            variantes = list(set(variantes + [canonique]))  # Inclure le canonique
            current_dict[canonique] = variantes
            sauvegader_dictionnaire_noms(current_dict, args.dictionnaire)

        elif choice == "2":
            nom = input("Nom à supprimer: ").strip()
            if nom in current_dict:
                del current_dict[nom]
                sauvegader_dictionnaire_noms(current_dict, args.dictionnaire)
            else:
                print(f"❌ '{nom}' non trouvé dans le dictionnaire.")

        elif choice == "3":
            print("\nDictionnaire actuel:")
            for canonique, variantes in current_dict.items():
                print(f"  {canonique}: {variantes}")

        elif choice == "4":
            break
        else:
            print("❌ Choix invalide.")
