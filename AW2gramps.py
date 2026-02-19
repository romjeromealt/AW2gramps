# -*- coding: utf-8 -*-

import csv
import re
import argparse
from xml.dom.minidom import parseString
from xml.etree import ElementTree as ET
from datetime import datetime
import os
import mimetypes
import sys

def parse_arguments():
    """Parse les arguments de la ligne de commande."""
    parser = argparse.ArgumentParser(description="Convertit un fichier CSV en format Gramps XML.")
    parser.add_argument("input_csv", help="Chemin vers le fichier CSV d'entrée.")
    parser.add_argument("output_xml", help="Chemin vers le fichier XML de sortie.")
    parser.add_argument("--wikipedia", "-w", action="store_true", help="Activer la recherche Wikipedia.")
    args = parser.parse_args()

    if not args.input_csv or not args.output_xml:
        parser.error("Les chemins d'entrée et de sortie doivent être spécifiés et non vides.")

    print(f"Chemin d'entrée : {args.input_csv}")
    print(f"Chemin de sortie : {args.output_xml}")

    return args

def print_progress(current, total):
    """Affiche la progression avec une longueur fixe pour éviter les résidus."""
    progress = int((current / total) * 100)
    progress_bar = f"\rTraitement : {current}/{total} ({progress}%)" + " " * 10
    sys.stdout.write(progress_bar)
    sys.stdout.flush()

def validate_csv_columns(csv_reader):
    """Vérifie que les colonnes requises sont présentes dans le CSV."""
    required_columns = {'Titre', 'Coordonnées', 'Description'}
    actual_columns = set(csv_reader.fieldnames)
    missing_columns = required_columns - actual_columns
    if missing_columns:
        raise ValueError(f"Colonnes manquantes dans le CSV : {', '.join(missing_columns)}. Veuillez vérifier le fichier.")
    return True

def dms_to_decimal(dms):
    """Convertit les coordonnées DMS en décimal."""
    match = re.match(r"(\d+)° (\d+)' ([\d\.]+)\" ([NSEW])", dms.strip())
    if match:
        degrees, minutes, seconds, direction = match.groups()
        decimal = float(degrees) + float(minutes)/60 + float(seconds)/3600
        if direction in ('S', 'W'):
            decimal *= -1
        return decimal
    return None

def parse_coords(coords_str):
    """Extrait et convertit toutes les paires de coordonnées DMS en décimal."""
    if not coords_str:
        return [(None, None)]
    coords_pairs = []
    parts = [p.strip() for p in coords_str.split(',') if p.strip()]
    for i in range(0, len(parts), 2):
        if i + 1 < len(parts):
            lat = dms_to_decimal(parts[i])
            lon = dms_to_decimal(parts[i + 1])
            if lat is not None and lon is not None:
                coords_pairs.append((lat, lon))
    return coords_pairs if coords_pairs else [(None, None)]

def extract_refs(text):
    """Extrait les balises <ref>...</ref> d'un texte et retourne une liste de références."""
    ref_pattern = re.compile(r'<ref>(.*?)</ref>', re.DOTALL)
    refs = ref_pattern.findall(text)
    return refs

def extract_sources_from_ref(ref):
    """Extrait les sources des modèles {{Source|...}} dans une référence."""
    source_pattern = re.compile(r'\{\{Source\|(.*?)\}\}')
    sources = source_pattern.findall(ref)
    return sources

def parse_ref(ref):
    """Parse une référence pour extraire les sources et les métadonnées."""
    url = None
    meta = {}
    sources = extract_sources_from_ref(ref)
    if ref.strip().startswith("http"):
        parts = ref.split()
        url = parts[0]
        meta["consulté"] = " ".join(parts[1:]) if len(parts) > 1 else ""
    return url, meta, sources

def extract_gallery(text):
    """Extrait les fichiers d'une balise <gallery> et retourne une liste de tuples (fichier, description)."""
    gallery_pattern = re.compile(r'<gallery>(.*?)</gallery>', re.DOTALL)
    match = gallery_pattern.search(text)
    if not match:
        return []

    gallery_content = match.group(1)
    file_pattern = re.compile(r'Fichier:([^\|]+)\|([^\n]+)')
    files = file_pattern.findall(gallery_content)
    return files

def extract_internal_links(text):
    """Extrait les liens internes de type [[Adresse:...|...]] et retourne une liste de tuples (adresse, texte affiché)."""
    link_pattern = re.compile(r'\[\[Adresse:(.*?)\|(.*?)\]\]')
    links = link_pattern.findall(text)
    return links

def extract_infobox_events(text):
    """Extrait les événements d'une balise {{Infobox actualité|...}}."""
    infobox_pattern = re.compile(r'\{\{\s*Infobox\s+actualité\s*\|\s*(.*?)\}\}', re.DOTALL)
    matches = infobox_pattern.findall(text)
    events = []

    for match in matches:
        event = {}
        lines = re.split(r'\n|;', match)
        for line in lines:
            line = line.strip()
            if '=' in line:
                key, value = line.split('=', 1)
                key = key.strip()
                value = value.strip()
                event[key] = value
        if event:
            events.append(event)

    return events

def get_mime_type(filename):
    """Détermine le type MIME d'un fichier à partir de son extension."""
    mime_type, _ = mimetypes.guess_type(filename)
    if mime_type:
        return mime_type

    if filename.lower().endswith('.webp'):
        return 'image/webp'
    elif filename.lower().endswith('.pdf'):
        return 'application/pdf'
    return 'application/octet-stream'

def parse_date_range(date_str):
    """Parse une plage de dates au format 'YYYY-YYYY' ou 'YYYY à YYYY'."""
    if not date_str:
        return None, None

    date_str = date_str.strip()

    # Gestion des intervalles de dates avec un tiret (ex: 1906-1907)
    if '-' in date_str:
        parts = date_str.split('-')
        if len(parts) == 2 and parts[0].strip().isdigit() and parts[1].strip().isdigit():
            return f"{parts[0].strip()}-{parts[1].strip()}", "Range"

    # Gestion des intervalles de dates avec "à" (ex: 1906 à 1907)
    if 'à' in date_str:
        parts = date_str.split('à')
        if len(parts) == 2 and parts[0].strip().isdigit() and parts[1].strip().isdigit():
            return f"{parts[0].strip()}-{parts[1].strip()}", "Range"

    # Gestion des dates simples (ex: 1906)
    if date_str.isdigit():
        return date_str, "Span"

    return None, None

def format_date_for_gramps(date_range):
    """Formate une date pour Gramps."""
    if not date_range:
        return None, None

    date_range = date_range.strip()
    if not date_range:
        return None, None

    # Essayer de parser explicitement les intervalles de dates
    date_value, date_type = parse_date_range(date_range)
    if date_value and date_type:
        return date_value, date_type

    # Gestion des dates simples (ex: 1906)
    if date_range.isdigit():
        return date_range, "Span"

    # Si la date n'est pas reconnue, retourne une valeur par défaut
    return "0000", "Span"

def get_wikipedia_summary(title, use_wikipedia):
    """Récupère un résumé Wikipedia si l'option est activée."""
    if not use_wikipedia:
        return None
    try:
        import wikipedia
        wikipedia.set_lang("fr")
        return wikipedia.summary(title, sentences=3, auto_suggest=False)
    except ImportError:
        print("Le module 'wikipedia' n'est pas installé. Utilisez `pip3 install wikipedia` pour l'activer.")
        return None
    except wikipedia.exceptions.PageError:
        return None
    except wikipedia.exceptions.DisambiguationError as e:
        if e.options:
            return wikipedia.summary(e.options[0], sentences=3, auto_suggest=False)
        return None
    except Exception as e:
        print(f"Erreur Wikipedia pour {title}: {e}")
        return None

def create_event(objects, event_info, next_event_handle):
    """Crée un événement Gramps à partir des informations extraites."""
    event = ET.SubElement(
        objects, 'event',
        handle=f"_{next_event_handle}",
        id=f"E{next_event_handle}",
        change=str(int(datetime.now().timestamp()))
    )

    # Type d'événement
    event_type = ET.SubElement(event, 'type')
    event_type.text = event_info.get('type', 'Événement')

    # Date de l'événement
    date_range = event_info.get('date', '')
    date_value, date_type = format_date_for_gramps(date_range)

    if date_value and date_type:
        date = ET.SubElement(event, 'dateval')
        date.set('val', date_value)
        date.set('type', date_type)
    else:
        # Utilise une date par défaut si la date n'est pas reconnue
        date = ET.SubElement(event, 'dateval')
        date.set('val', '0000')
        date.set('type', 'Span')

    # Description de l'événement
    description = ET.SubElement(event, 'description')
    description.text = event_info.get('description', '')

    # Attributs supplémentaires
    for key, value in event_info.items():
        if key not in ['date', 'type', 'description']:
            attribute = ET.SubElement(event, 'attribute')
            attribute.set('type', key)
            attribute.set('value', value)

    return next_event_handle + 1

def csv_to_gramps_xml(csv_file_path, output_xml_file_path, use_wikipedia):
    """Convertit un fichier CSV en format Gramps XML."""
    print(f"Début de la conversion. Sortie vers : {output_xml_file_path}")

    try:
        with open(csv_file_path, mode='r', encoding='utf-8') as csv_file:
            csv_reader = csv.DictReader(csv_file, delimiter=',', quotechar='"')
            validate_csv_columns(csv_reader)
            data = [row for row in csv_reader]
    except Exception as e:
        print(f"Erreur lors de la lecture du CSV : {e}")
        return

    total_rows = len(data)
    print(f"Conversion de {total_rows} entrées...")

    # Initialisation de mimetypes
    mimetypes.init()

    # Création de la structure XML de base pour Gramps 5.2
    database = ET.Element('database', xmlns="http://gramps-project.org/xml/1.7.1/")
    header = ET.SubElement(database, 'header')
    ET.SubElement(header, 'created', date=datetime.now().strftime("%Y-%m-%d %H:%M:%S"), version="5.2.0")
    ET.SubElement(header, 'researcher', name="Generated by script")
    objects = ET.SubElement(database, 'objects')

    # Compteurs pour les handles
    place_handle = 100000000
    note_handle = 400000000
    source_handles = {}
    next_source_handle = 500000000
    media_handles = {}
    next_media_handle = 600000000
    note_handles = {}
    next_event_handle = 700000000

    # Traitement des lieux en premier pour obtenir les handles
    for i, row in enumerate(data, 1):
        print_progress(i, total_rows)

        # Pour chaque paire de coordonnées, créer un lieu
        coords_pairs = parse_coords(row.get('Coordonnées', ''))
        for j, (lat, lon) in enumerate(coords_pairs, 1):
            place = ET.SubElement(objects, 'placeobj', handle=f"_{place_handle}", change=str(int(datetime.now().timestamp())), id=f"P{place_handle}", type="Place")
            ptitle = ET.SubElement(place, 'ptitle')
            ptitle.text = f"{row.get('Titre', 'Inconnu')} (coordonnées {j})"
            pname = ET.SubElement(place, 'pname')
            pname.set('value', f"{row.get('Titre', 'Inconnu')} (coordonnées {j})")
            if lat is not None and lon is not None:
                coord = ET.SubElement(place, 'coord')
                coord.set('lat', f"{lat:.6f}")
                coord.set('long', f"{lon:.6f}")

            note_handles[f"{row['Titre']} (coordonnées {j})"] = f"_{place_handle}"
            place_handle += 1

    # Traitement des notes et événements
    for i, row in enumerate(data, 1):
        print_progress(i, total_rows)

        description = row.get('Description', '').strip()
        wiki_summary = get_wikipedia_summary(row['Titre'], use_wikipedia)

        if wiki_summary:
            description = f"{description}\n\n--- Wikipedia ---\n{wiki_summary}"

        # Extraction des événements
        events = extract_infobox_events(description)
        for event_info in events:
            next_event_handle = create_event(objects, event_info, next_event_handle)

        # Extraction des références
        refs = extract_refs(description)

        # Création des objets source pour chaque référence unique
        for ref in refs:
            url, meta, sources = parse_ref(ref)
            if url and url not in source_handles:
                source = ET.SubElement(objects, 'source', handle=f"_{next_source_handle}", id=f"S{next_source_handle}", change=str(int(datetime.now().timestamp())))
                stitle = ET.SubElement(source, 'stitle')
                stitle.text = url
                if meta.get("consulté"):
                    spubinfo = ET.SubElement(source, 'spubinfo')
                    spubinfo.text = meta["consulté"]
                source_handles[url] = f"_{next_source_handle}"
                next_source_handle += 1
            for source_model in sources:
                if source_model not in source_handles:
                    source = ET.SubElement(objects, 'source', handle=f"_{next_source_handle}", id=f"S{next_source_handle}", change=str(int(datetime.now().timestamp())))
                    stitle = ET.SubElement(source, 'stitle')
                    stitle.text = source_model
                    source_handles[source_model] = f"_{next_source_handle}"
                    next_source_handle += 1

        # Extraction des galeries
        files = extract_gallery(description)

        # Création des objets média pour chaque fichier
        for file_name, file_desc in files:
            if file_name not in media_handles:
                mime_type = get_mime_type(file_name)
                media = ET.SubElement(objects, 'object', handle=f"_{next_media_handle}", id=f"O{next_media_handle}", type="Media", change=str(int(datetime.now().timestamp())))
                file = ET.SubElement(media, 'file')
                file.set('src', file_name)
                file.set('mime', mime_type)
                file.set('description', file_desc)
                media_handles[file_name] = f"_{next_media_handle}"
                next_media_handle += 1

        # Pour chaque paire de coordonnées, ajouter la note
        coords_pairs = parse_coords(row.get('Coordonnées', ''))
        for j, (lat, lon) in enumerate(coords_pairs, 1):
            current_description = description

            # Remplacement des balises <ref> et {{Source|...}}
            for ref in refs:
                url, meta, sources = parse_ref(ref)
                ref_replacement = []
                if url and url in source_handles:
                    ref_replacement.append(f'<sourceref hlink="{source_handles[url]}"/>')
                for source_model in sources:
                    if source_model in source_handles:
                        ref_replacement.append(f'<sourceref hlink="{source_handles[source_model]}"/>')
                if ref_replacement:
                    current_description = current_description.replace(f'<ref>{ref}</ref>', " ".join(ref_replacement), 1)

            # Remplacement des balises <gallery>
            if files:
                media_refs = []
                for file_name, file_desc in files:
                    if file_name in media_handles:
                        media_refs.append(f'<objref hlink="{media_handles[file_name]}"/>')
                gallery_replacement = "\n".join(media_refs)
                current_description = re.sub(r'<gallery>.*?</gallery>', gallery_replacement, current_description, flags=re.DOTALL)

            # Extraction et remplacement des liens internes
            internal_links = extract_internal_links(current_description)
            for address, display_text in internal_links:
                place_key = f"{address} (coordonnées 1)"
                if place_key in note_handles:
                    link_replacement = f'<place hlink="{note_handles[place_key]}">{display_text}</place>'
                    current_description = current_description.replace(f'[[Adresse:{address}|{display_text}]]', link_replacement)

            if current_description:
                note = ET.SubElement(objects, 'note', handle=f"_{note_handle}", change=str(int(datetime.now().timestamp())), id=f"N{note_handle}", type="Html code")
                text = ET.SubElement(note, 'text')
                text.text = f"<b>{row['Titre']} (coordonnées {j})</b><p>{current_description.replace(chr(10), '<br>')}</p>"
                note_handles[f"{row['Titre']} (coordonnées {j})"] = f"_{note_handle}"
                note_handle += 1

                # Ajout de la référence à la note dans le lieu
                place_key = f"{row['Titre']} (coordonnées {j})"
                if place_key in note_handles:
                    for place in objects.findall('.//placeobj'):
                        if place.get('id') == f"P{place_handle - len(coords_pairs) + j}":
                            noteref = ET.SubElement(place, 'noteref')
                            noteref.set('hlink', note_handles[place_key])

    print("\nGénération du fichier XML...")

    # Vérifie que le chemin de sortie n'est pas vide
    if not output_xml_file_path:
        raise ValueError("Le chemin de sortie ne peut pas être vide.")

    print(f"Chemin de sortie final : {output_xml_file_path}")

    # Vérifie que le chemin de sortie est valide
    output_dir = os.path.dirname(output_xml_file_path)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)
        print(f"Création du répertoire : {output_dir}")

    # Convertir en chaîne XML
    xml_str = ET.tostring(database, encoding='utf-8').decode('utf-8')
    doctype_declaration = '''<!DOCTYPE database PUBLIC "-//Gramps//DTD Gramps XML 1.7.1//EN"
"http://gramps-project.org/xml/1.7.1/grampsxml.dtd">'''
    xml_str = f"{doctype_declaration}\n{xml_str}"

    try:
        dom = parseString(xml_str)
        with open(output_xml_file_path, 'w', encoding='utf-8') as f:
            dom.writexml(f, indent='  ', addindent='  ', newl='\n', encoding='utf-8')
        print(f"Conversion terminée avec succès ! Le fichier a été enregistré sous : {output_xml_file_path}")
    except Exception as e:
        print(f"Erreur lors de l'écriture du fichier XML : {e}")
        # Enregistre le XML brut en cas d'erreur
        with open(output_xml_file_path, 'w', encoding='utf-8') as f:
            f.write(xml_str)
        print(f"Fichier XML brut enregistré sous : {output_xml_file_path}")

def main():
    args = parse_arguments()
    csv_to_gramps_xml(args.input_csv, args.output_xml, args.wikipedia)

if __name__ == "__main__":
    main()
