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
def preprocess_image(img):
    # Conversion en niveaux de gris
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    cv2.imwrite("debug_images/1_gray.jpg", gray)

    # Réduction du bruit avec un filtre bilatéral (préserve les bords)
    blurred = cv2.bilateralFilter(gray, d=9, sigmaColor=75, sigmaSpace=75)
    cv2.imwrite("debug_images/2_blurred.jpg", blurred)

    # Binarisation adaptative (meilleure pour les fonds non uniformes)
    thresh = cv2.adaptiveThreshold(
        blurred, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV, 11, 2
    )
    cv2.imwrite("debug_images/3_adaptive_threshold.jpg", thresh)

    # Fermeture morphologique pour combler les trous dans les lettres
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    closed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel, iterations=2)
    cv2.imwrite("debug_images/4_closed.jpg", closed)

    # Dilatation pour connecter les caractères fragmentés
    dilated = cv2.dilate(closed, kernel, iterations=1)
    cv2.imwrite("debug_images/5_dilated.jpg", dilated)

    return dilated, gray

processed_img, gray_img = preprocess_image(original_img)

# --- 4. Visualisation des colonnes ---
# Dessiner les lignes verticales pour séparer les 6 colonnes
debug_columns = original_img.copy()
col_width = img_width // 6
for i in range(1, 6):
    x = i * col_width
    cv2.line(debug_columns, (x, 0), (x, img_height), (0, 0, 255), 2)
cv2.imwrite("debug_images/6_columns_overlay.jpg", debug_columns)
print("✅ Images de débogage sauvegardées dans le dossier 'debug_images'")

# --- 5. Extraire le texte par colonne ---
headers = [
    "Nom/Prénom/Demeure 1",
    "Folios 1",
    "Nom/Prénom/Demeure 2",
    "Folios 2",
    "Nom/Prénom/Demeure 3",
    "Folios 3"
]

tesseract_config = r'--oem 3 --psm 6 -l fra+eng -c tessedit_char_whitelist=0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyzÀÂÄÇÉÈÊËÎÏÔÖÙÛÜÑàâäçéèêëîïôöùûüñ.,-'

# Diviser l'image en 6 colonnes
col_ranges = [
    (0, col_width),
    (col_width, 2 * col_width),
    (2 * col_width, 3 * col_width),
    (3 * col_width, 4 * col_width),
    (4 * col_width, 5 * col_width),
    (5 * col_width, img_width)
]

# Extraire le texte de chaque colonne
col_texts = []
for i, (start, end) in enumerate(col_ranges):
    col_img = processed_img[:, start:end]
    # Sauvegarder chaque colonne pour vérification
    cv2.imwrite(f"debug_images/col_{i+1}.jpg", col_img)
    text = pytesseract.image_to_string(col_img, config=tesseract_config)
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
df.to_csv("extracted_data_final.csv", index=False, encoding="utf-8-sig")
print("✅ Données exportées vers 'extracted_data_final.csv'")
print(f"📊 {len(structured_data)} lignes extraites")
