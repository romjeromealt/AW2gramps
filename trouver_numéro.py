import os
import cv2
import pytesseract
import re
from PIL import Image

# Assurez-vous que Tesseract est installé et que le chemin est correctement configuré
# pytesseract.pytesseract.tesseract_cmd = r'<chemin_vers_tesseract_executable>'

def preprocess_image(image_path):
    """Prétraite une image pour améliorer la précision de l'OCR."""
    img = cv2.imread(image_path)
    gray_img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    denoised_img = cv2.GaussianBlur(gray_img, (5, 5), 0)
    enhanced_img = cv2.equalizeHist(denoised_img)
    binary_img = cv2.adaptiveThreshold(enhanced_img, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
    return binary_img

def extract_text(image_path):
    """Extrait le texte d'une image en utilisant Tesseract OCR."""
    processed_img = preprocess_image(image_path)
    config = '--psm 6'
    text = pytesseract.image_to_string(processed_img, config=config)
    return text

def parse_second_column(text):
    """Parse le texte extrait pour obtenir les valeurs de la deuxième colonne."""
    lines = text.split('\n')
    second_column_values = []
    for line in lines:
        if line.strip():
            columns = line.split()
            if len(columns) >= 2:
                second_column_values.append(columns[1])
    return second_column_values

def find_target_number(second_column_values, target_number):
    """Recherche un chiffre cible dans la liste des valeurs de la deuxième colonne."""
    matches = [value for value in second_column_values if value == str(target_number)]
    return matches

def process_jpeg_folder(folder_path, target_number):
    """Traite tous les fichiers JPEG dans un dossier pour rechercher un chiffre cible."""
    results = {}
    for filename in os.listdir(folder_path):
        if filename.lower().endswith(('.jpeg', '.jpg')):
            image_path = os.path.join(folder_path, filename)
            try:
                text = extract_text(image_path)
                second_column_values = parse_second_column(text)
                matches = find_target_number(second_column_values, target_number)
                if matches:
                    results[filename] = matches
                else:
                    results[filename] = "Aucune correspondance"
            except Exception as e:
                results[filename] = f"Erreur : {str(e)}"
    return results

# Exemple d'utilisation
folder_path = "chemin/vers/vos/images/jpeg"
target_number = "75015"
results = process_jpeg_folder(folder_path, target_number)
for filename, matches in results.items():
    print(f"Fichier : {filename} → Correspondances : {matches}")
