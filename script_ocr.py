import cv2
import numpy as np
import pytesseract
import pandas as pd
import os
import json

# --- 1. Gestion du fichier de configuration ---
CONFIG_FILE = "config.json"
DEFAULT_CONFIG = {
    "d": 9,
    "sigmaColor": 75,
    "blockSize": 11,
    "C": 2,
    "iterations_close": 1,
    "iterations_dilate": 2
}

# Charger ou créer le fichier de configuration
def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    else:
        return DEFAULT_CONFIG.copy()

def save_config(config):
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=4)

# Charger la config existante
config = load_config()

# --- 2. Demander à l'utilisateur s'il veut modifier la config ---
print("🔧 Configuration actuelle (fichier: config.json):")
for key, value in config.items():
    print(f"  {key}: {value}")

modify = input("\nVoulez-vous modifier les paramètres ? (o/n, défaut=n): ").strip().lower()
if modify == "o":
    print("\nEntrez les nouvelles valeurs (laisser vide pour garder la valeur actuelle):")
    for key in DEFAULT_CONFIG:
        new_value = input(f"  {key} (actuel={config[key]}, défaut={DEFAULT_CONFIG[key]}): ").strip()
        if new_value:
            config[key] = int(new_value)
    save_config(config)
    print(f"\n✅ Configuration sauvegardée dans {CONFIG_FILE}")

# --- 3. Charger l'image ---
image_path = "A.JPG"
original_img = cv2.imread(image_path)
img_height, img_width = original_img.shape[:2]

# Créer un dossier pour les images de débogage
os.makedirs("debug_images", exist_ok=True)
cv2.imwrite("debug_images/0_original.jpg", original_img)

# --- 4. Prétraitement personnalisé ---
def preprocess_image(img, is_digit_column=False):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    if is_digit_column:
        # Pour les folios : binarisation simple + dilatation
        _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        processed = cv2.dilate(thresh, kernel, iterations=config["iterations_dilate"])
    else:
        # Pour le texte : filtre bilatéral + binarisation adaptative + fermeture
        blurred = cv2.bilateralFilter(gray, d=config["d"], sigmaColor=config["sigmaColor"], sigmaSpace=75)
        thresh = cv2.adaptiveThreshold(
            blurred, 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV, config["blockSize"], config["C"]
        )
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
        processed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel, iterations=config["iterations_close"])

    return processed

# --- 5. Diviser l'image en 6 colonnes ---
col_width = img_width // 6
col_ranges = [
    (0, col_width),
    (col_width, 2 * col_width),
    (2 * col_width, 3 * col_width),
    (3 * col_width, 4 * col_width),
    (4 * col_width, 5 * col_width),
    (5 * col_width, img_width)
]

headers = [
    "Nom/Prénom/Demeure 1",
    "Folios 1",
    "Nom/Prénom/Demeure 2",
    "Folios 2",
    "Nom/Prénom/Demeure 3",
    "Folios 3"
]

# Configurations Tesseract
tesseract_text_config = r'--oem 3 --psm 6 -l fra+eng -c tessedit_char_whitelist=0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyzÀÂÄÇÉÈÊËÎÏÔÖÙÛÜÑàâäçéèêëîïôöùûüñ.,-'
tesseract_digit_config = r'--oem 3 --psm 6 -l fra -c tessedit_char_whitelist=0123456789'

# --- 6. Extraire le texte de chaque colonne ---
col_texts = []
for i, (start, end) in enumerate(col_ranges):
    col_img = original_img[:, start:end]
    cv2.imwrite(f"debug_images/col_{i+1}.jpg", col_img)

    is_digit_col = (i % 2 == 1)  # Colonnes 2, 4, 6 = folios
    processed_col = preprocess_image(col_img, is_digit_column=is_digit_col)
    cv2.imwrite(f"debug_images/col_{i+1}_processed.jpg", processed_col)

    config_ocr = tesseract_digit_config if is_digit_col else tesseract_text_config
    text = pytesseract.image_to_string(processed_col, config=config_ocr).strip()
    col_texts.append(text)

# --- 7. Structurer les données ---
lines = []
for text in col_texts:
    lines.append([line.strip() for line in text.split('\n') if line.strip()])

max_lines = max(len(col_lines) for col_lines in lines)
structured_data = []
for i in range(max_lines):
    row_data = {}
    for j, header in enumerate(headers):
        row_data[header] = lines[j][i] if i < len(lines[j]) else ""
    structured_data.append(row_data)

# --- 8. Exporter en CSV ---
df = pd.DataFrame(structured_data)
df.to_csv("extracted_data_final.csv", index=False, encoding="utf-8-sig")
print("\n✅ Données exportées vers 'extracted_data_final.csv'")
print(f"📊 {len(structured_data)} lignes extraites")
print("✅ Images de débogage sauvegardées dans 'debug_images/'")
