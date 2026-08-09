import cv2
import numpy as np
import pytesseract
import pandas as pd
import os

# Créer un dossier pour les images de débogage
os.makedirs("debug_images", exist_ok=True)

# --- 1. Configuration ---
# pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'  # Windows

# --- 2. Charger l'image ---
image_path = "A.JPG"
original_img = cv2.imread(image_path)
img_height, img_width = original_img.shape[:2]

# Sauvegarder l'image originale
cv2.imwrite("debug_images/0_original.jpg", original_img)

# --- 3. Prétraitement amélioré ---
def preprocess_image(img, is_digit_column=False):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Pour les colonnes de nombres (folios), on utilise un prétraitement plus agressif
    if is_digit_column:
        # Binarisation simple avec seuil fixe (meilleure pour les chiffres)
        _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        # Dilatation pour connecter les chiffres
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        processed = cv2.dilate(thresh, kernel, iterations=2)
    else:
        # Pour le texte normal : binarisation adaptative
        blurred = cv2.bilateralFilter(gray, d=9, sigmaColor=75, sigmaSpace=75)
        thresh = cv2.adaptiveThreshold(
            blurred, 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV, 11, 2
        )
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
        processed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel, iterations=1)

    return processed

# --- 4. Diviser l'image en 6 colonnes ---
col_width = img_width // 6
col_ranges = [
    (0, col_width),                # Colonne 1 (Nom/Prénom/Demeure)
    (col_width, 2 * col_width),    # Colonne 2 (Folios) → NOMBRES SEULEMENT
    (2 * col_width, 3 * col_width),# Colonne 3 (Nom/Prénom/Demeure)
    (3 * col_width, 4 * col_width),# Colonne 4 (Folios) → NOMBRES SEULEMENT
    (4 * col_width, 5 * col_width),# Colonne 5 (Nom/Prénom/Demeure)
    (5 * col_width, img_width)     # Colonne 6 (Folios) → NOMBRES SEULEMENT
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
tesseract_digit_config = r'--oem 3 --psm 6 -l fra -c tessedit_char_whitelist=0123456789'  # UNIQUEMENT DES CHIFFRES

# --- 5. Extraire le texte de chaque colonne ---
col_texts = []
for i, (start, end) in enumerate(col_ranges):
    col_img = original_img[:, start:end]
    cv2.imwrite(f"debug_images/col_{i+1}.jpg", col_img)

    # Prétraiter en fonction du type de colonne
    is_digit_col = (i % 2 == 1)  # Les colonnes 2, 4, 6 sont des folios (nombres)
    processed_col = preprocess_image(col_img, is_digit_column=is_digit_col)
    cv2.imwrite(f"debug_images/col_{i+1}_processed.jpg", processed_col)

    # Utiliser la config adaptée
    config = tesseract_digit_config if is_digit_col else tesseract_text_config
    text = pytesseract.image_to_string(processed_col, config=config).strip()
    col_texts.append(text)

# --- 6. Structurer les données ---
# Diviser chaque colonne en lignes
lines = []
for text in col_texts:
    lines.append([line.strip() for line in text.split('\n') if line.strip()])

# Trouver le nombre maximum de lignes
max_lines = max(len(col_lines) for col_lines in lines)

# Reconstruire le tableau
structured_data = []
for i in range(max_lines):
    row_data = {}
    for j, header in enumerate(headers):
        if i < len(lines[j]):
            row_data[header] = lines[j][i]
        else:
            row_data[header] = ""
    structured_data.append(row_data)

# --- 7. Exporter en CSV ---
df = pd.DataFrame(structured_data)
df.to_csv("extracted_data_with_digits.csv", index=False, encoding="utf-8-sig")
print("✅ Données exportées vers 'extracted_data_with_digits.csv'")
print(f"📊 {len(structured_data)} lignes extraites")
print("✅ Images de débogage sauvegardées dans 'debug_images/'")
