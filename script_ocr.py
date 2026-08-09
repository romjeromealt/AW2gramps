import cv2
import numpy as np
import pytesseract
import pandas as pd
import os
import re

# Créer un dossier pour les images de débogage
os.makedirs("debug_images", exist_ok=True)

# --- 1. Charger l'image ---
image_path = "A.JPG"
original_img = cv2.imread(image_path)
img_height, img_width = original_img.shape[:2]

# Sauvegarder l'image originale
cv2.imwrite("debug_images/0_original.jpg", original_img)

# --- 2. Prétraitement amélioré (version simple mais optimisée) ---
def preprocess_image(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Réduction du bruit avec un filtre bilatéral
    blurred = cv2.bilateralFilter(gray, d=15, sigmaColor=100, sigmaSpace=75)  # ✅ Paramètres renforcés

    # Binarisation adaptative avec des paramètres adaptés aux manuscrits
    thresh = cv2.adaptiveThreshold(
        blurred, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV, 15, 5  # ✅ blockSize=15, C=5 (fond jauni)
    )

    # Fermeture morphologique pour combler les trous
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
    closed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel, iterations=2)

    # Dilatation légère
    dilated = cv2.dilate(closed, kernel, iterations=1)

    return dilated

processed_img = preprocess_image(original_img)
cv2.imwrite("debug_images/1_processed.jpg", processed_img)

# --- 3. Découpage en 6 colonnes FIXES (ajustées pour ton image) ---
# ✅ CORRECTION 1: Utilise des limites en pixels au lieu de divisions égales
# À ajuster selon ton image (ex: 2480px de large)
col_ranges = [
    (0, 400),        # Colonne 1: Nom/Prénom/Demeure (0-400px)
    (400, 700),      # Colonne 2: Folios (400-700px)
    (700, 1300),     # Colonne 3: Nom/Prénom/Demeure (700-1300px)
    (1300, 1600),    # Colonne 4: Folios (1300-1600px)
    (1600, 2100),    # Colonne 5: Nom/Prénom/Demeure (1600-2100px)
    (2100, img_width) # Colonne 6: Folios (2100-fin)
]

# Dessiner les lignes verticales pour vérification
debug_columns = original_img.copy()
for i, (start, end) in enumerate(col_ranges):
    cv2.line(debug_columns, (start, 0), (start, img_height), (0, 0, 255), 2)
    cv2.line(debug_columns, (end, 0), (end, img_height), (0, 0, 255), 2)
cv2.imwrite("debug_images/2_columns_overlay.jpg", debug_columns)

# --- 4. Extraire le texte par colonne ---
headers = [
    "Nom/Prénom/Demeure 1",
    "Folios 1",
    "Nom/Prénom/Demeure 2",
    "Folios 2",
    "Nom/Prénom/Demeure 3",
    "Folios 3"
]

# ✅ CORRECTION 2: Configuration Tesseract optimisée
tesseract_config = (
    '--oem 1 '  # ✅ Moteur LSTM (meilleur pour les manuscrits)
    '--psm 6 '  # Bloc de texte
    '-l fra+eng '
    '-c tessedit_char_whitelist=0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyzÀÂÄÇÉÈÊËÎÏÔÖÙÛÜÑàâäçéèêëîïôöùûüñ.,-'
)

col_texts = []
for i, (start, end) in enumerate(col_ranges):
    col_img = processed_img[:, start:end]
    cv2.imwrite(f"debug_images/col_{i+1}.jpg", col_img)

    # ✅ CORRECTION 3: Nettoyer le texte extrait
    text = pytesseract.image_to_string(col_img, config=tesseract_config)
    if i % 2 == 1:  # Colonnes de folios (2, 4, 6)
        text = re.sub(r"[^0-9]", "", text)  # Garder uniquement les chiffres
    col_texts.append(text.strip())

# --- 5. Structurer les données ---
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

# --- 6. Exporter en CSV ---
df = pd.DataFrame(structured_data)
df.to_csv("extracted_data_final.csv", index=False, encoding="utf-8-sig")
print("✅ Données exportées vers 'extracted_data_final.csv'")
print(f"📊 {len(structured_data)} lignes extraites")
