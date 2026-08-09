import argparse
import cv2
import numpy as np
import pytesseract
import pandas as pd
import os
import json
import glob
from datetime import datetime

# --- 1. Gestion des arguments en ligne de commande ---
parser = argparse.ArgumentParser(description="Extraction OCR de tableaux avec configuration avancée")
parser.add_argument("--profile", type=str, default="default", help="Profil de configuration à utiliser (ex: ancien_manuscrit)")
parser.add_argument("--input", type=str, default="A.JPG", help="Image ou dossier d'images à traiter (ex: images/*.jpg)")
parser.add_argument("--output", type=str, default="output", help="Dossier de sortie (défaut: output/)")
parser.add_argument("--preview", action="store_true", help="Générer une page HTML de prévisualisation")
parser.add_argument("--auto-columns", action="store_true", help="Détecter automatiquement les colonnes")
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
        "whitelist_digits": "0123456789",
        "columns": [
            {"type": "text"},
            {"type": "digits"},
            {"type": "text"},
            {"type": "digits"},
            {"type": "text"},
            {"type": "digits"}
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
        "whitelist_digits": "0123456789"
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
    lines = cv2.HoughLinesP(edges, 1, np.pi/180, threshold=100, minLineLength=100, maxLineGap=10)
    if lines is None:
        return []
    vertical_lines = []
    for line in lines:
        x1, y1, x2, y2 = line[0]
        if abs(x1 - x2) < 10:  # Ligne verticale
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
    debug_dir = os.path.join(output_dir, f"debug_{filename}")
    os.makedirs(debug_dir, exist_ok=True)

    # Détecter ou utiliser les colonnes fixes
    if args.auto_columns:
        col_x_positions = detect_columns(original_img)
        if len(col_x_positions) < 2:
            print(f"⚠️ Impossible de détecter les colonnes pour {image_path}. Utilisation de 6 colonnes fixes.")
            col_x_positions = [i * img_width // 6 for i in range(1, 6)]
        col_x_positions = [0] + col_x_positions + [img_width]
    else:
        num_cols = len(config["columns"])
        col_x_positions = [i * img_width // num_cols for i in range(num_cols + 1)]

    # Sauvegarder l'image originale
    cv2.imwrite(os.path.join(debug_dir, "0_original.jpg"), original_img)

    # Prétraitement
    def preprocess_col(img, col_type):
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        if col_type == "digits":
            _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
            processed = cv2.dilate(thresh, kernel, iterations=config.get("iterations_dilate", 2))
        else:
            blurred = cv2.bilateralFilter(gray, d=config.get("d", 9), sigmaColor=config.get("sigmaColor", 75), sigmaSpace=75)
            thresh = cv2.adaptiveThreshold(
                blurred, 255,
                cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY_INV, config.get("blockSize", 11), config.get("C", 2)
            )
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
            processed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel, iterations=config.get("iterations_close", 1))
        return processed

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
        if col_type == "digits":
            tesseract_config = f'--oem 3 --psm 6 -l {config.get("tesseract_lang", "fra")} -c tessedit_char_whitelist={config.get("whitelist_digits", "0123456789")}'
        else:
            tesseract_config = f'--oem 3 --psm 6 -l {config.get("tesseract_lang", "fra+eng")} -c tessedit_char_whitelist={config.get("whitelist_text", "")}'

        text = pytesseract.image_to_string(processed_col, config=tesseract_config).strip()
        col_texts.append(text)

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
            row_data[header] = lines[j][i] if i < len(lines[j]) else ""
        structured_data.append(row_data)

    # Exporter en CSV
    csv_path = os.path.join(output_dir, f"{filename}.csv")
    pd.DataFrame(structured_data).to_csv(csv_path, index=False, encoding="utf-8-sig")

    # Sauvegarder la config utilisée
    with open(os.path.join(output_dir, f"{filename}_config.json"), "w") as f:
        json.dump(config, f, indent=4)

    # Générer une prévisualisation HTML si demandé
    if args.preview:
        generate_preview_html(debug_dir, config, structured_data, os.path.join(output_dir, f"{filename}_preview.html"))

    print(f"✅ {image_path} → {csv_path} ({len(structured_data)} lignes)")
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

    for header in results[0].keys() if results else []:
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
import shutil

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
