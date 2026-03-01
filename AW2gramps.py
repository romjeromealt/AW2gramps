# -*- coding: utf-8 -*-

import csv
import re
import argparse
from xml.etree import ElementTree as ET
from datetime import datetime
import os
import mimetypes
import sys
from xml.dom import minidom

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

def extract_architects(text):
    """Extrait les noms des architectes depuis une balise {{Infobox actualité}}."""
    pattern = r'\|\s*architecte\s*=\s*([^\n|]+)'
    match = re.search(pattern, text)
    architects = set()
    if match:
        architects_list = [a.strip() for a in match.group(1).replace('\;', ';').split(';')]
        architects.update(architects_list)
        print(f"Architectes extraits : {architects}")
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

def create_xml_element(parent, tag, text=None, **attrs):
    """Crée un élément XML avec des attributs et du texte."""
    element = ET.SubElement(parent, tag, **attrs)
    if text is not None:
        element.text = text
    return element

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

    # Création de la structure XML de base
    database = ET.Element('database', xmlns="http://gramps-project.org/xml/1.7.1/")
    header = create_xml_element(database, 'header')
    create_xml_element(header, 'created', date=datetime.now().strftime("%Y-%m-%d %H:%M:%S"), version="5.2.0")
    create_xml_element(header, 'researcher', name="Generated by script")

    # Création des sections principales dans l'ordre requis par Gramps
    events = create_xml_element(database, 'events')
    people = create_xml_element(database, 'people')
    places = create_xml_element(database, 'places')
    objects = create_xml_element(database, 'objects')
    notes = create_xml_element(database, 'notes')

    # Dictionnaires pour éviter les doublons
    media_handles = {}
    person_handles = {}
    source_handles = {}
    place_handles = {}
    note_handles = {}

    # Compteurs pour les handles
    place_id = 100000000
    note_id = 400000000
    event_id = 700000000
    media_id = 600000000
    person_id = 200000000
    source_id = 500000000

    # Dictionnaires pour stocker les données avant création XML
    events_data = []
    people_data = {}
    places_data = {}
    objects_data = []
    notes_data = []

    for i, row in enumerate(data, 1):
        print_progress(i, total_rows)

        title = row.get('Titre', '').strip()
        if not title:
            title = "Lieu sans nom"

        # Extraction des architectes
        architects = extract_architects(row.get('Description', ''))
        for architect in architects:
            if architect not in people_data:
                people_data[architect] = {
                    'handle': f"_{person_id}",
                    'surname': architect.split()[-1] if architect.split() else 'Inconnu',
                    'firstname': ' '.join(architect.split()[:-1]) if len(architect.split()) > 1 else 'Inconnu'
                }
                person_handles[architect] = f"_{person_id}"
                person_id += 1

        # Extraction des références
        refs = extract_refs(row.get('Description', ''))
        for ref in refs:
            url, meta, sources = parse_ref(ref)
            if url and url not in source_handles:
                source_handles[url] = {
                    'handle': f"_{source_id}",
                    'title': url,
                    'pubinfo': meta.get("consulté", "")
                }
                source_id += 1

            for source_model in sources:
                if source_model not in source_handles:
                    source_handles[source_model] = {
                        'handle': f"_{source_id}",
                        'title': source_model,
                        'pubinfo': ""
                    }
                    source_id += 1

        # Création des lieux
        coords_pairs = parse_coords(row.get('Coordonnées', ''))
        for j, (lat, lon) in enumerate(coords_pairs, 1):
            place_key = f"{title} (coordonnées {j})"
            places_data[place_key] = {
                'handle': f"_{place_id}",
                'title': place_key,
                'lat': lat,
                'lon': lon,
                'architects': architects
            }
            place_handles[place_key] = f"_{place_id}"
            place_id += 1

        # Création des événements
        events_list = extract_infobox_events(row.get('Description', ''))
        for event_info in events_list:
            events_data.append({
                'handle': f"_{event_id}",
                'type': event_info.get('type', 'Construction'),
                'date': event_info.get('date', ''),
                'description': f"Événement lié à {title}",
                'place_handle': place_handles.get(f"{title} (coordonnées 1)"),
                'architects': architects if isinstance(architects, set) else set()
            })
            event_id += 1

        # Création des médias
        files = extract_gallery(row.get('Description', ''))
        for file_name, file_desc in files:
            if file_name not in media_handles:
                media_handles[file_name] = {
                    'handle': f"_{media_id}",
                    'file_name': file_name,
                    'mime': get_mime_type(file_name),
                    'description': file_desc
                }
                media_id += 1

        # Création des notes
        if 'Description' in row and row['Description']:
            note_handle = f"_{note_id}"
            notes_data.append({
                'handle': note_handle,
                'text': row['Description'],
                'media_handles': [media_handles[file_name]['handle'] for file_name, _ in files if file_name in media_handles],
                'source_handles': []
            })

            for ref in refs:
                url, meta, sources = parse_ref(ref)
                if url and url in source_handles:
                    notes_data[-1]['source_handles'].append(source_handles[url]['handle'])
                for source_model in sources:
                    if source_model in source_handles:
                        notes_data[-1]['source_handles'].append(source_handles[source_model]['handle'])

            # Stocke la note dans note_handles avec son handle comme clé
            note_handles[note_handle] = note_handle
            note_id += 1

    # Associe les notes aux objets (événements, lieux, etc.)
    for event in events_data:
        # Trouve la note associée à cet événement (exemple : via le titre)
        for note in notes_data:
            if event['description'] in note['text']:
                event['note_handle'] = note['handle']
                break

    for place_key, place in places_data.items():
        # Trouve la note associée à ce lieu (exemple : via le titre)
        for note in notes_data:
            if place['title'] in note['text']:
                place['note_handle'] = note['handle']
                break

    # Création des éléments XML à partir des données collectées
    for event in events_data:
        event_elem = create_xml_element(events, 'event',
            handle=event['handle'],
            change=str(int(datetime.now().timestamp())))

        create_xml_element(event_elem, 'type', text=event['type'])

        if event['date']:
            date = create_xml_element(event_elem, 'dateval')
            date.set('val', event['date'])
            date.set('type', 'Span')

        create_xml_element(event_elem, 'description', text=event['description'])

        # Référence au lieu
        if event['place_handle']:
            create_xml_element(event_elem, 'place', hlink=event['place_handle'])

        # Référence aux architectes
        for architect in event['architects']:
            if architect in person_handles:
                create_xml_element(event_elem, 'personref',
                hlink=person_handles[architect],
                role='Architect')

        # Ajoute une référence à la note si elle existe
        if 'note_handle' in event and event['note_handle'] in note_handles:
            noteref = create_xml_element(event_elem, 'noteref')
            noteref.set('hlink', event['note_handle'])

    for architect, person in people_data.items():
        person_elem = create_xml_element(people, 'person',
            handle=person['handle'],
            change=str(int(datetime.now().timestamp())))

        name = create_xml_element(person_elem, 'name', type="Birth Name")
        create_xml_element(name, 'surname', text=person['surname'])
        create_xml_element(name, 'first', text=person['firstname'])

        # Ajoute une référence à la note si elle existe
        for note in notes_data:
            if architect in note['text']:
                noteref = create_xml_element(person_elem, 'noteref')
                noteref.set('hlink', note['handle'])
                break

    for place_key, place in places_data.items():
        place_elem = create_xml_element(places, 'placeobj',
            handle=place['handle'],
            change=str(int(datetime.now().timestamp())))

        create_xml_element(place_elem, 'ptitle', text=place['title'])
        pname = create_xml_element(place_elem, 'pname')
        pname.set('value', place['title'])

        if place['lat'] is not None and place['lon'] is not None:
            coord = create_xml_element(place_elem, 'coord')
            coord.set('lat', f"{place['lat']:.6f}")
            coord.set('long', f"{place['lon']:.6f}")

        # Ajoute une référence à la note si elle existe
        if 'note_handle' in place and place['note_handle'] in note_handles:
            noteref = create_xml_element(place_elem, 'noteref')
            noteref.set('hlink', place['note_handle'])

    for media in media_handles.values():
        media_elem = create_xml_element(objects, 'object',
            handle=media['handle'],
            change=str(int(datetime.now().timestamp())),
            type='Media')

        file_elem = create_xml_element(media_elem, 'file')
        file_elem.set('src', media['file_name'])
        file_elem.set('mime', media['mime'])
        file_elem.set('description', media['description'])

        # Ajoute une référence à la note si elle existe
        for note in notes_data:
            if media['file_name'] in note['text']:
                noteref = create_xml_element(media_elem, 'noteref')
                noteref.set('hlink', note['handle'])
                break

    for source in source_handles.values():
        source_elem = create_xml_element(objects, 'source',
            handle=source['handle'],
            change=str(int(datetime.now().timestamp())))

        create_xml_element(source_elem, 'stitle', text=source['title'])
        if source['pubinfo']:
            create_xml_element(source_elem, 'spubinfo', text=source['pubinfo'])

        # Ajoute une référence à la note si elle existe
        for note in notes_data:
            if source['title'] in note['text']:
                noteref = create_xml_element(source_elem, 'noteref')
                noteref.set('hlink', note['handle'])
                break

    for note in notes_data:
        note_elem = create_xml_element(notes, 'note',
            handle=note['handle'],
            change=str(int(datetime.now().timestamp())),
            type='Html code')

        # Traitement des références dans le texte de la note
        text_with_refs = note['text']
        ref_pattern = re.compile(r'<ref>(.*?)</ref>', re.DOTALL)
        refs = ref_pattern.findall(text_with_refs)

        for ref in refs:
            ref_replacement = []
            url, meta, sources = parse_ref(ref)

            if url and url in source_handles:
                ref_replacement.append(f'<sourceref hlink="{source_handles[url]["handle"]}"/>')

            for source_model in sources:
                if source_model in source_handles:
                    ref_replacement.append(f'<sourceref hlink="{source_handles[source_model]["handle"]}"/>')

            if ref_replacement:
                text_with_refs = text_with_refs.replace(f'<ref>{ref}</ref>', " ".join(ref_replacement), 1)

        create_xml_element(note_elem, 'text', text=text_with_refs)

        # Ajout des références aux médias
        for media_handle in note['media_handles']:
            create_xml_element(note_elem, 'objref', hlink=media_handle)

        # Ajout des références aux sources
        for source_handle in note['source_handles']:
            create_xml_element(note_elem, 'sourceref', hlink=source_handle)

    output_dir = os.path.dirname(output_xml_file_path)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)

    # Convertir en chaîne XML bien formatée
    xml_str = ET.tostring(database, encoding='utf-8')
    xml_pretty = minidom.parseString(xml_str).toprettyxml(indent="  ", encoding="utf-8")
    xml_pretty = xml_pretty.decode('utf-8')

    # Déclaration DOCTYPE et XML
    xml_declaration = '<?xml version="1.0" encoding="utf-8"?>\n'
    doctype_declaration = '''<!DOCTYPE database PUBLIC "-//Gramps//DTD Gramps XML 1.7.1//EN"
"http://gramps-project.org/xml/1.7.1/grampsxml.dtd">'''

    # On extrait le contenu entre <database> et </database> pour éviter la duplication
    start_tag = xml_pretty.find('<database')
    end_tag = xml_pretty.rfind('</database>') + len('</database>')
    content = xml_pretty[start_tag:end_tag]

    # On reconstruit le fichier XML complet
    xml_pretty = f"{xml_declaration}{doctype_declaration}\n{content}"

    # Écriture dans le fichier
    with open(output_xml_file_path, 'w', encoding='utf-8') as f:
        f.write(xml_pretty)

    print(f"\nConversion terminée avec succès ! Le fichier a été enregistré sous : {output_xml_file_path}")

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

def main():
    args = parse_arguments()
    csv_to_gramps_xml(args.input_csv, args.output_xml)

if __name__ == "__main__":
    main()
