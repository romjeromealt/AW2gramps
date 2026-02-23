# -*- coding: utf-8 -*-

import csv
import re
import argparse
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

def extract_architects(text):
    """Extrait les noms des architectes depuis une balise {{Infobox actualité}}."""
    architect_pattern = re.compile(r'\|\\s*architecte\\s*=\\s*([^\\n\\|]+)')
    infobox_pattern = re.compile(r'\\{\\{\\s*Infobox\\s+actualité\\s*\\|(.*?)\\}\\}', re.DOTALL)
    infobox_matches = infobox_pattern.findall(text)

    architects = set()
    for match in infobox_matches:
        architect_matches = architect_pattern.findall(match)
        for architect in architect_matches:
            architects.add(architect.strip())
    return architects

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

def csv_to_gramps_xml(csv_file_path, output_xml_file_path):
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

    mimetypes.init()

    database = ET.Element('database', xmlns="http://gramps-project.org/xml/1.7.1/")
    header = ET.SubElement(database, 'header')
    ET.SubElement(header, 'created', date=datetime.now().strftime("%Y-%m-%d %H:%M:%S"), version="5.2.0")
    ET.SubElement(header, 'researcher', name="Generated by script")
    objects = ET.SubElement(database, 'objects')

    # Compteurs pour les handles
    place_handle = 100000000
    note_handle = 400000000
    event_handle = 700000000
    media_handle = 600000000
    person_handle = 200000000
    source_handle = 500000000

    # Dictionnaires pour éviter les doublons
    media_handles = {}
    person_handles = {}
    source_handles = {}

    for i, row in enumerate(data, 1):
        print_progress(i, total_rows)

        title = row.get('Titre', '').strip()
        if not title:
            title = "Lieu sans nom"

        # Extraction des architectes
        architects = extract_architects(row.get('Description', ''))
        for architect in architects:
            if architect not in person_handles:
                person = ET.SubElement(objects, 'person')
                person.set('handle', f"_{person_handle}")
                person.set('change', str(int(datetime.now().timestamp())))
                person.set('id', f"I{person_handle}")

                name = ET.SubElement(person, 'name')
                name.set('type', 'Birth Name')
                surname = architect.split()[-1] if architect.split() else 'Inconnu'
                firstname = ' '.join(architect.split()[:-1]) if len(architect.split()) > 1 else 'Inconnu'

                ET.SubElement(name, 'surname').text = surname
                ET.SubElement(name, 'first').text = firstname

                person_handles[architect] = f"_{person_handle}"
                person_handle += 1

        # Extraction des références
        refs = extract_refs(row.get('Description', ''))
        for ref in refs:
            url, meta, sources = parse_ref(ref)
            if url and url not in source_handles:
                source = ET.SubElement(objects, 'source')
                source.set('handle', f"_{source_handle}")
                source.set('change', str(int(datetime.now().timestamp())))
                source.set('id', f"S{source_handle}")

                stitle = ET.SubElement(source, 'stitle')
                stitle.text = url
                if meta.get("consulté"):
                    spubinfo = ET.SubElement(source, 'spubinfo')
                    spubinfo.text = meta["consulté"]

                source_handles[url] = f"_{source_handle}"
                source_handle += 1

            for source_model in sources:
                if source_model not in source_handles:
                    source = ET.SubElement(objects, 'source')
                    source.set('handle', f"_{source_handle}")
                    source.set('change', str(int(datetime.now().timestamp())))
                    source.set('id', f"S{source_handle}")

                    stitle = ET.SubElement(source, 'stitle')
                    stitle.text = source_model

                    source_handles[source_model] = f"_{source_handle}"
                    source_handle += 1

        # Création des lieux
        coords_pairs = parse_coords(row.get('Coordonnées', ''))
        for j, (lat, lon) in enumerate(coords_pairs, 1):
            place = ET.SubElement(objects, 'placeobj')
            place.set('handle', f"_{place_handle}")
            place.set('change', str(int(datetime.now().timestamp())))
            place.set('id', f"P{place_handle}")
            place.set('type', 'Place')

            ET.SubElement(place, 'ptitle').text = f"{title} (coordonnées {j})"
            pname = ET.SubElement(place, 'pname')
            pname.set('value', f"{title} (coordonnées {j})")

            if lat is not None and lon is not None:
                coord = ET.SubElement(place, 'coord')
                coord.set('lat', f"{lat:.6f}")
                coord.set('long', f"{lon:.6f}")

            # Ajout des références aux architectes
            for architect in architects:
                if architect in person_handles:
                    personref = ET.SubElement(place, 'personref')
                    personref.set('hlink', person_handles[architect])
                    personref.set('role', 'Architect')

            place_handle += 1

        # Création des événements
        events = extract_infobox_events(row.get('Description', ''))
        for event_info in events:
            event = ET.SubElement(objects, 'event')
            event.set('handle', f"_{event_handle}")
            event.set('change', str(int(datetime.now().timestamp())))
            event.set('id', f"E{event_handle}")

            ET.SubElement(event, 'type').text = event_info.get('type', 'Construction')

            date_range = event_info.get('date', '')
            if date_range:
                date = ET.SubElement(event, 'dateval')
                date.set('val', date_range)
                date.set('type', 'Span')

            ET.SubElement(event, 'description').text = f"Événement lié à {title}"

            # Référence au lieu
            place_ref = ET.SubElement(event, 'place')
            place_ref.set('hlink', f"_{place_handle - 1}")

            # Référence aux architectes
            for architect in architects:
                if architect in person_handles:
                    personref = ET.SubElement(event, 'personref')
                    personref.set('hlink', person_handles[architect])
                    personref.set('role', 'Architect')

            event_handle += 1

        # Création des médias
        files = extract_gallery(row.get('Description', ''))
        for file_name, file_desc in files:
            if file_name not in media_handles:
                media = ET.SubElement(objects, 'object')
                media.set('handle', f"_{media_handle}")
                media.set('change', str(int(datetime.now().timestamp())))
                media.set('id', f"O{media_handle}")
                media.set('type', 'Media')

                file_elem = ET.SubElement(media, 'file')
                file_elem.set('src', file_name)
                file_elem.set('mime', get_mime_type(file_name))
                file_elem.set('description', file_desc)

                media_handles[file_name] = f"_{media_handle}"
                media_handle += 1

        # Création des notes
        if 'Description' in row and row['Description']:
            note = ET.SubElement(objects, 'note')
            note.set('handle', f"_{note_handle}")
            note.set('change', str(int(datetime.now().timestamp())))
            note.set('id', f"N{note_handle}")
            note.set('type', 'Note')

            text = ET.SubElement(note, 'text')
            text.text = row['Description']

            # Ajout des références aux médias
            for file_name, file_desc in files:
                if file_name in media_handles:
                    objref = ET.SubElement(note, 'objref')
                    objref.set('hlink', media_handles[file_name])

            # Ajout des références aux sources
            for ref in refs:
                url, meta, sources = parse_ref(ref)
                if url and url in source_handles:
                    sourceref = ET.SubElement(note, 'sourceref')
                    sourceref.set('hlink', source_handles[url])
                for source_model in sources:
                    if source_model in source_handles:
                        sourceref = ET.SubElement(note, 'sourceref')
                        sourceref.set('hlink', source_handles[source_model])

            note_handle += 1

    output_dir = os.path.dirname(output_xml_file_path)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)

    xml_str = ET.tostring(database, encoding='utf-8').decode('utf-8')
    doctype_declaration = '''<!DOCTYPE database PUBLIC "-//Gramps//DTD Gramps XML 1.7.1//EN"
"http://gramps-project.org/xml/1.7.1/grampsxml.dtd">'''
    xml_str = f"{doctype_declaration}\n{xml_str}"

    with open(output_xml_file_path, 'w', encoding='utf-8') as f:
        f.write(xml_str)

    print(f"\nConversion terminée avec succès ! Le fichier a été enregistré sous : {output_xml_file_path}")

def main():
    args = parse_arguments()
    csv_to_gramps_xml(args.input_csv, args.output_xml)

if __name__ == "__main__":
    main()
