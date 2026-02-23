# -*- coding: utf-8 -*-

import csv
import re
import argparse
from xml.sax.saxutils import escape
from datetime import datetime
import os
import mimetypes
import sys
import uuid

def parse_arguments():
    """Parse les arguments de la ligne de commande."""
    parser = argparse.ArgumentParser(description="Convertit un fichier CSV en format Gramps XML.")
    parser.add_argument("input_csv", help="Chemin vers le fichier CSV d'entrée.")
    parser.add_argument("output_xml", help="Chemin vers le fichier XML de sortie.")
    parser.add_argument("--wikipedia", "-w", action="store_true", help="Activer la recherche Wikipedia.")
    parser.add_argument("--batch-size", type=int, default=10, help="Nombre d'entrées à traiter par lot.")
    args = parser.parse_args()

    if not args.input_csv or not args.output_xml:
        parser.error("Les chemins d'entrée et de sortie doivent être spécifiés et non vides.")

    print(f"Chemin d'entrée : {args.input_csv}")
    print(f"Chemin de sortie : {args.output_xml}")
    print(f"Taille des lots : {args.batch_size}")

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
        return (None, None)
    parts = [p.strip() for p in coords_str.split(',') if p.strip()]
    if len(parts) >= 2:
        lat = dms_to_decimal(parts[0])
        lon = dms_to_decimal(parts[1])
        return (lat, lon)
    return (None, None)

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

def format_date_for_gramps(date_range):
    """Formate une date pour Gramps."""
    if not date_range:
        return "0000-00-00", None

    date_range = date_range.strip()
    if not date_range:
        return "0000-00-00", None

    if date_range.isdigit():
        return f"{date_range}-00-00", None

    return "0000-00-00", None

def create_event(xml_file, event_info, event_id, place_handle, current_timestamp):
    """Crée un événement Gramps à partir des informations extraites."""
    event_handle = f"_{uuid.uuid4().hex}"

    xml_file.write(f'    <event handle="{event_handle}" id="E{event_id:04d}" change="{current_timestamp}">\n')

    event_type = event_info.get("type", "Événement")
    xml_file.write(f'      <type>{escape(event_type)}</type>\n')

    date_range = event_info.get('date', '')
    date_value, _ = format_date_for_gramps(date_range)
    xml_file.write(f'      <dateval val="{date_value}"/>\n')

    description = event_info.get("description", "")
    xml_file.write(f'      <description>{escape(description)}</description>\n')

    if place_handle:
        xml_file.write(f'      <place hlink="{place_handle}"/>\n')

    xml_file.write(f'    </event>\n')

    return event_id + 1

def create_person(xml_file, architect, person_id, current_timestamp):
    """Crée une personne Gramps à partir des informations extraites."""
    person_handle = f"_{uuid.uuid4().hex}"

    surname = architect.split()[-1] if architect.split() else 'Inconnu'
    firstname = ' '.join(architect.split()[:-1]) if len(architect.split()) > 1 else 'Inconnu'

    xml_file.write(f'    <person handle="{person_handle}" id="I{person_id:04d}" change="{current_timestamp}">\n')
    xml_file.write(f'      <name type="Birth Name">\n')
    xml_file.write(f'        <surname>{escape(surname)}</surname>\n')
    xml_file.write(f'        <first>{escape(firstname)}</first>\n')
    xml_file.write(f'      </name>\n')
    xml_file.write(f'    </person>\n')

def create_place(xml_file, title, place_id, lat, lon, current_timestamp):
    """Crée un lieu Gramps à partir des informations extraites."""
    place_handle = f"_{uuid.uuid4().hex}"

    xml_file.write(f'    <place handle="{place_handle}" id="P{place_id:04d}" change="{current_timestamp}">\n')
    xml_file.write(f'      <ptitle>{escape(title)}</ptitle>\n')
    xml_file.write(f'      <pname value="{escape(title)}"/>\n')
    if lat and lon:
        xml_file.write(f'      <coord lat="{lat}" long="{lon}"/>\n')
    xml_file.write(f'    </place>\n')

    return place_handle

def create_note(xml_file, text, note_id, current_timestamp):
    """Crée une note Gramps à partir des informations extraites."""
    note_handle = f"_{uuid.uuid4().hex}"

    xml_file.write(f'    <note handle="{note_handle}" id="N{note_id:04d}" change="{current_timestamp}" type="Note">\n')
    xml_file.write(f'      <text>{escape(text)}</text>\n')
    xml_file.write(f'    </note>\n')

    return note_handle

def create_media(xml_file, file_name, file_desc, media_id, current_timestamp):
    """Crée un média Gramps à partir des informations extraites."""
    media_handle = f"_{uuid.uuid4().hex}"
    mime_type = get_mime_type(file_name)

    xml_file.write(f'    <object handle="{media_handle}" id="O{media_id:04d}" type="Media" change="{current_timestamp}">\n')
    xml_file.write(f'      <file src="{escape(file_name)}" mime="{mime_type}" description="{escape(file_desc)}"/>\n')
    xml_file.write(f'    </object>\n')

def process_row(row, events_data, persons_data, places_data, notes_data, medias_data, current_timestamp, next_event_id, next_person_id, next_place_id, next_note_id, next_media_id):
    """Traite une seule ligne de données et prépare les données pour l'écriture XML."""
    lat, lon = parse_coords(row.get('Coordonnées', ''))

    # Vérification du titre
    title = row.get('Titre', '').strip()
    if not title:
        title = "Lieu sans nom"

    # Extraction et conversion des architectes
    architects = extract_architects(row.get('Description', ''))
    for architect in architects:
        if architect not in persons_data:
            persons_data[architect] = next_person_id
            next_person_id += 1

    # Extraction des événements
    events_in_row = extract_infobox_events(row.get('Description', ''))
    for event_info in events_in_row:
        event_info['description'] = row.get('Description', '')
        events_data.append((event_info, next_event_id, title))
        next_event_id += 1

    # Extraction des notes
    if 'Description' in row and row['Description']:
        notes_data.append((row['Description'], next_note_id))
        next_note_id += 1

    # Ajout du lieu
    places_data.append((title, lat, lon, next_place_id))
    next_place_id += 1

    # Extraction des médias
    files = extract_gallery(row.get('Description', ''))
    for file_name, file_desc in files:
        if file_name not in medias_data:
            medias_data[file_name] = (file_desc, next_media_id)
            next_media_id += 1

    return next_event_id, next_person_id, next_place_id, next_note_id, next_media_id

def csv_to_gramps_xml(csv_file_path, output_xml_file_path, use_wikipedia, batch_size):
    """Convertit un fichier CSV en format Gramps XML."""
    print(f"Début de la conversion. Sortie vers : {output_xml_file_path}")

    try:
        with open(csv_file_path, mode='r', encoding='utf-8') as csv_file:
            csv_reader = csv.DictReader(csv_file, delimiter=',', quotechar='"')
            validate_csv_columns(csv_reader)
            data = list(csv_reader)
    except Exception as e:
        print(f"Erreur lors de la lecture du CSV : {e}")
        return

    total_rows = len(data)
    print(f"Conversion de {total_rows} entrées...")

    output_dir = os.path.dirname(output_xml_file_path)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)
        print(f"Création du répertoire : {output_dir}")

    current_timestamp = str(int(datetime.now().timestamp()))

    events_data = []
    persons_data = {}
    places_data = []
    notes_data = []
    medias_data = {}

    next_event_id = 1
    next_person_id = 1
    next_place_id = 1
    next_note_id = 1
    next_media_id = 1

    for i, row in enumerate(data):
        print_progress(i + 1, total_rows)
        next_event_id, next_person_id, next_place_id, next_note_id, next_media_id = process_row(
            row, events_data, persons_data, places_data, notes_data, medias_data, current_timestamp,
            next_event_id, next_person_id, next_place_id, next_note_id, next_media_id
        )

    with open(output_xml_file_path, 'w', encoding='utf-8') as xml_file:
        xml_file.write('''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE database PUBLIC "-//Gramps//DTD Gramps XML 1.7.1//EN"
"http://gramps-project.org/xml/1.7.1/grampsxml.dtd">
<database xmlns="http://gramps-project.org/xml/1.7.1/">
  <header>
    <created date="''' + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + '''" version="5.2.0"/>
    <researcher name="Generated by script"/>
  </header>
''')

        # Écriture des événements
        xml_file.write('  <events>\n')
        for event_info, event_id, place_title in events_data:
            place_handle = None
            create_event(xml_file, event_info, event_id, place_handle, current_timestamp)
        xml_file.write('  </events>\n')

        # Écriture des personnes
        xml_file.write('  <people>\n')
        for architect, person_id in persons_data.items():
            create_person(xml_file, architect, person_id, current_timestamp)
        xml_file.write('  </people>\n')

        # Écriture des lieux
        xml_file.write('  <places>\n')
        for title, lat, lon, place_id in places_data:
            create_place(xml_file, title, place_id, lat, lon, current_timestamp)
        xml_file.write('  </places>\n')

        # Écriture des notes
        xml_file.write('  <notes>\n')
        for text, note_id in notes_data:
            create_note(xml_file, text, note_id, current_timestamp)
        xml_file.write('  </notes>\n')

        # Écriture des médias
        xml_file.write('  <objects>\n')
        for file_name, (file_desc, media_id) in medias_data.items():
            create_media(xml_file, file_name, file_desc, media_id, current_timestamp)
        xml_file.write('  </objects>\n')

        xml_file.write('</database>\n')

    print(f"\nConversion terminée avec succès ! Le fichier a été enregistré sous : {output_xml_file_path}")

def main():
    args = parse_arguments()
    csv_to_gramps_xml(args.input_csv, args.output_xml, args.wikipedia, args.batch_size)

if __name__ == "__main__":
    main()
