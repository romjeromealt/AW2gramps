# -*- coding: utf-8 -*-
# Gramps - a GTK+/GNOME based genealogy program
# Copyright (C) 2016      Paul Culley (some code by Nick Hall)

import csv
import re
import argparse
import html
from xml.etree import ElementTree as ET
from datetime import datetime
import os
import mimetypes
import sys
from xml.dom import minidom

def nettoyer_texte(texte):
    """Nettoie le texte en supprimant les ; == et == autour des titres."""
    texte = re.sub(r';\s*==\s*', '', texte)
    texte = re.sub(r'\s*==\s*;?', '', texte)
    return texte

def nettoyer_html(texte):
    """
    Nettoie le texte HTML pour le convertir en texte compatible avec Gramps.
    Préserve les balises spécifiques à Gramps et les références aux médias.
    """
    # Protège les balises spécifiques à Gramps
    protected_tags = [
        ('<ref>.*?</ref>', 'REF_TAG'),
        ('<noteref[^>]*?>', 'NOTEREF_TAG'),
        ('<sourceref[^>]*?>', 'SOURCEREF_TAG'),
        ('<objref[^>]*?>', 'OBJREF_TAG')
    ]

    # Remplace les balises spécifiques par des marqueurs temporaires
    protected = {}
    for pattern, marker in protected_tags:
        for i, match in enumerate(re.finditer(pattern, texte, re.DOTALL)):
            protected[f"{marker}_{i}"] = match.group(0)
            texte = texte.replace(match.group(0), f"{{{marker}_{i}}}")

    # Nettoyage du HTML
    texte = re.sub(r'<i>(.*?)</i>', r'/\1/', texte)  # Italique
    texte = re.sub(r'<b>(.*?)</b>', r'*\1*', texte)  # Gras
    texte = re.sub(r'<u>(.*?)</u>', r'_\1_', texte)  # Souligné
    texte = re.sub(r'<a\s+[^>]*href=["\']([^"\']*)["\'][^>]*>(.*?)</a>', r'\2 (\1)', texte)  # Liens
    texte = re.sub(r'<br\s*/?>', '\n', texte)  # Sauts de ligne
    texte = re.sub(r'<[^>]+>', '', texte)  # Supprime les autres balises HTML
    texte = html.unescape(texte)  # Convertit les entités HTML en caractères normaux

    # Restaure les balises spécifiques à Gramps
    for marker, tag in protected.items():
        texte = texte.replace(f"{{{marker}}}", tag)

    return texte

def ajouter_styles_texte(note_elem, note_text):
    """Ajoute les balises <style> pour les titres et sections dans le texte de la note."""
    titres_a_styliser = [
        "Historique du nom de la place",
        "Construction",
        "Description",
        "Galerie",
        "Événements",
        "Les maisons de l'Ecomusée",
        "La forêt des jeux"
    ]

    for titre in titres_a_styliser:
        if titre in note_text:
            start = note_text.find(titre)
            end = start + len(titre)
            style_bold = ET.SubElement(note_elem, 'style', name="bold")
            ET.SubElement(style_bold, 'range', start=str(start), end=str(end))
            style_underline = ET.SubElement(note_elem, 'style', name="underline")
            ET.SubElement(style_underline, 'range', start=str(start), end=str(end))

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
        if architects_list == ['}}']:
            architects.update({'bug AW'})
        if not architects_list == [{''}]:
            architects.update(architects_list)
        else:
            architects.update({'inconnu(e)s'})
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

def extract_note_refs(text):
    """Extrait les références aux notes depuis un texte."""
    return set(re.findall(r'<noteref hlink="([^"]+)"/>', text))

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

def extract_file_links(text):
    """Extrait les liens vers les fichiers de type [[Fichier:Nom|Description]]."""
    pattern = r'\[\[Fichier:([^\|]+)\|([^\]]+)\]\]'
    matches = re.findall(pattern, text)
    return matches

def process_media_links(note_text, media_handles):
    """
    Traite les liens vers les médias dans le texte et les remplace par des références simples.
    Retourne le texte modifié et une liste de tuples (nom_fichier, position_debut, position_fin).
    """
    file_links = extract_file_links(note_text)
    media_refs = []

    for file_name, file_desc in file_links:
        pattern = f"\[\[Fichier:{file_name}\|{file_desc}\]\]"
        start = note_text.find(pattern)
        if start != -1:
            end = start + len(pattern)
            media_refs.append((file_name, start, end))
            # Remplace le lien par la description du fichier
            note_text = note_text.replace(pattern, file_desc)

    return note_text, media_refs

def parse_event_field(event_str):
    """
    Extrait et structure les événements à partir du champ CSV "Événement".
    """
    events = []
    if not event_str:
        return events

    event_blocks = [e.strip() for e in event_str.split('),') if e.strip()]
    for block in event_blocks:
        block = block.strip('() ')
        parts = [p.strip().replace('\\', '') for p in block.split(',')]

        event = {
            'type': 'Inconnu',
            'date_range': '',
            'structure': 'Inconnu',
            'architectural_style': 'Inconnu',
            'start_date': '',
            'end_date': '',
            'event_num': None,
        }

        if len(parts) >= 1:
            event['type'] = parts[0].split('(')[0].strip()
            if '(' in parts[0]:
                date_part = parts[0].split('(')[1].strip()
                event['date_range'] = date_part

        if len(parts) >= 2:
            event['structure'] = parts[1]
        if len(parts) >= 3:
            event['architectural_style'] = parts[2]
        if len(parts) >= 4:
            event['start_date'] = parts[3]
        if len(parts) >= 5:
            event['end_date'] = parts[4]
        if len(parts) >= 6:
            event['event_num'] = parts[5]

        events.append(event)

    return events

def extract_year(date_str):
    """
    Extrait une année à partir d'une chaîne de caractères.
    """
    if not date_str:
        return None

    # Recherche d'une année à 4 chiffres
    year_match = re.search(r'\d{4}', date_str)
    if year_match:
        return year_match.group(0)

    # Recherche d'une année à 2 chiffres
    short_year_match = re.search(r'\b\d{2}\b', date_str)
    if short_year_match:
        short_year = short_year_match.group(0)
        year = int(short_year)
        if year < 50:
            return str(year + 2000)
        else:
            return str(year + 1900)

    return None

def format_date_for_gramps(date_str):
    """
    Convertit une date en format Gramps en extrayant au moins l'année.
    """
    if not date_str:
        return "0000-00-00"

    date_str = date_str.strip()
    year = extract_year(date_str)

    if year:
        return f"{year}-01-01"

    return "0000-00-00"

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

    mimetypes.init()

    # Création de la structure XML de base
    database = ET.Element('database', xmlns="http://gramps-project.org/xml/1.7.1/")
    header = create_xml_element(database, 'header')
    create_xml_element(header, 'created', date=datetime.now().strftime("%Y-%m-%d %H:%M:%S"), version="5.2.0")
    create_xml_element(header, 'researcher', name="Generated by script")

    # Création des sections principales dans l'ordre requis par Gramps
    events_elem = ET.SubElement(database, 'events')
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
    architect_events = {}

    # Compteurs pour les handles
    place_id = 100000000
    note_id = 400000000
    media_id = 600000000
    person_id = 200000000
    source_id = 500000000
    event_id = 700000000

    # Dictionnaires pour stocker les données avant création XML
    events_data = []
    people_data = {}
    places_data = {}
    objects_data = []
    notes_data = []

    total_rows = len(data)

    for i, row in enumerate(data, 1):
        print_progress(i, total_rows)

        title = row.get('Titre', '').strip()
        if not title:
            title = "Lieu sans nom"

        # Nettoyer le texte de la description
        row['Description'] = nettoyer_texte(row.get('Description', ''))

        # Extraction des notes depuis la description
        note_refs = extract_note_refs(row['Description'])

        # Extraction des architectes
        architects = extract_architects(row.get('Description', ''))
        for architect in architects:
            if architect not in people_data:
                people_data[architect] = {
                    'handle': f"_{person_id}",
                    'surname': architect.split()[-1] if architect.split() else 'Inconnu',
                    'firstname': ' '.join(architect.split()[:-1]) if len(architect.split()) > 1 else 'Inconnu',
                    'note_handles': set(note_refs),
                }
                person_handles[architect] = f"_{person_id}"
                person_id += 1
            else:
                people_data[architect]['note_handles'].update(note_refs)

        # Extraction des références
        refs = extract_refs(row.get('Description', ''))
        for ref in refs:
            url, meta, sources = parse_ref(ref)
            if url and url not in source_handles:
                source_handles[url] = {
                    'handle': f"_{source_id}",
                    'title': url,
                    'pubinfo': meta.get("consulté", ""),
                    'note_handles': set(note_refs),
                }
                source_id += 1

            for source_model in sources:
                if source_model not in source_handles:
                    source_handles[source_model] = {
                        'handle': f"_{source_id}",
                        'title': source_model,
                        'pubinfo': "",
                        'note_handles': set(note_refs),
                    }
                    source_id += 1

        # Extraction des événements
        events_list = parse_event_field(row.get('Événement', ''))
        for event in events_list:
            events_data.append({
                'handle': f"_{event_id}",
                'type': event.get('type', 'Inconnu'),
                'date': format_date_for_gramps(event.get('date_range', '')),
                'description': f"{event.get('type', 'Inconnu')} ({event.get('structure', 'Inconnu')}, {event.get('architectural_style', 'Inconnu')})",
                'place_handle': None,
                'architects': set(),
                'note_handles': set(note_refs),
                'event_num': event.get('event_num'),
            })
            event_id += 1

        # Création des lieux
        coords_pairs = parse_coords(row.get('Coordonnées', ''))
        for j, (lat, lon) in enumerate(coords_pairs, 1):
            place_key = f"{title} (coordonnées {j})"
            places_data[place_key] = {
                'handle': f"_{place_id}",
                'title': place_key,
                'lat': lat,
                'lon': lon,
                'architects': architects,
                'note_handles': set(note_refs),
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
                'architects': architects if isinstance(architects, set) else set(),
                'note_handles': set(note_refs),
            })
            # Stocke l'événement pour chaque architecte
            for architect in architects:
                if architect not in architect_events:
                    architect_events[architect] = []
                architect_events[architect].append(f"_{event_id}")
            event_id += 1

        # Création des médias
        files = extract_gallery(row.get('Description', ''))
        for file_name, file_desc in files:
            if file_name not in media_handles:
                media_handles[file_name] = {
                    'handle': f"_{media_id}",
                    'file_name': file_name,
                    'mime': get_mime_type(file_name),
                    'description': file_desc,
                    'note_handles': set(note_refs),
                }
                media_id += 1
            else:
                media_handles[file_name]['note_handles'].update(note_refs)

        # Création des notes
        if 'Description' in row and row['Description']:
            # Traite les liens vers les médias
            note_text, media_refs = process_media_links(row['Description'], media_handles)

            note_handle = f"_{note_id}"
            notes_data.append({
                'handle': note_handle,
                'text': nettoyer_html(note_text),
                'media_handles': [media_handles[file_name]['handle'] for file_name, _ in files if file_name in media_handles],
                'media_refs': media_refs,  # Ajoute les références aux médias
                'source_handles': [],
                'object_handles': {
                    'people': set(),
                    'places': set(),
                    'events': set(),
                    'media': set(),
                    'sources': set(),
                },
            })

            for ref in refs:
                url, meta, sources = parse_ref(ref)
                if url and url in source_handles:
                    notes_data[-1]['source_handles'].append(source_handles[url]['handle'])
                for source_model in sources:
                    if source_model in source_handles:
                        notes_data[-1]['source_handles'].append(source_handles[source_model]['handle'])

            note_handles[note_handle] = note_handle
            note_id += 1

    print(f"Conversion de {total_rows} entrées...")

    # Associe les notes aux objets et vice versa
    for note in notes_data:
        note_text = note['text']
        # Lier les personnes
        for architect, person in people_data.items():
            if architect in note_text:
                note['object_handles']['people'].add(person['handle'])
                person['note_handles'].add(note['handle'])
        # Lier les lieux
        for place_key, place in places_data.items():
            if place['title'] in note_text:
                note['object_handles']['places'].add(place['handle'])
                place['note_handles'].add(note['handle'])
        # Lier les événements
        for event in events_data:
            if event['description'] in note_text:
                note['object_handles']['events'].add(event['handle'])
                event['note_handles'].add(note['handle'])
        # Lier les médias
        for media in media_handles.values():
            if media['file_name'] in note_text:
                note['object_handles']['media'].add(media['handle'])
                media['note_handles'].add(note['handle'])
        # Lier les sources
        for source in source_handles.values():
            if source['title'] in note_text:
                note['object_handles']['sources'].add(source['handle'])
                source['note_handles'].add(note['handle'])

    # Création des éléments XML pour les événements
    for event in events_data:
        event_elem = ET.SubElement(events_elem, 'event',
            handle=event['handle'],
            change=str(int(datetime.now().timestamp()))
        )
        ET.SubElement(event_elem, 'type').text = event.get('type', 'Inconnu')

        # Formatage de la date
        date_val = event.get('date', '0000-00-00')

        # Si aucune date valide n'est trouvée, on essaie avec start_date
        if date_val == "0000-00-00" and event.get('start_date'):
            date_val = format_date_for_gramps(event.get('start_date'))

        # Si aucune date valide n'est trouvée, on essaie avec end_date
        if date_val == "0000-00-00" and event.get('end_date'):
            date_val = format_date_for_gramps(event.get('end_date'))

        date_elem = ET.SubElement(event_elem, 'dateval')
        if date_val != "":
            date_elem.set('val', date_val)
        date_elem.set('type', 'Span')

        desc = f"{event.get('structure', 'Inconnu')} ({event.get('architectural_style', 'Inconnu')})"
        ET.SubElement(event_elem, 'description').text = desc
        if event.get('place_handle'):
            ET.SubElement(event_elem, 'place', hlink=event['place_handle'])
        for note_handle in event.get('note_handles', set()):
            ET.SubElement(event_elem, 'noteref', hlink=note_handle)

    for architect, person in people_data.items():
        person_elem = create_xml_element(people, 'person',
            handle=person['handle'],
            change=str(int(datetime.now().timestamp())))

        name = create_xml_element(person_elem, 'name', type="Birth Name")
        create_xml_element(name, 'surname', text=person['surname'])
        create_xml_element(name, 'first', text=person['firstname'])

        # Ajoute les références aux événements
        if architect in architect_events:
            for event_handle in architect_events[architect]:
                create_xml_element(person_elem, 'eventref',
                    hlink=event_handle,
                    role='Architect')

        # Ajoute les références aux notes
        for note_handle in person.get('note_handles', set()):
            create_xml_element(person_elem, 'noteref', hlink=note_handle)

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

        # Ajoute les références aux notes
        for note_handle in place.get('note_handles', set()):
            create_xml_element(place_elem, 'noteref', hlink=note_handle)

    for media in media_handles.values():
        media_elem = create_xml_element(objects, 'object',
            handle=media['handle'],
            change=str(int(datetime.now().timestamp())),
            type='Media')

        file_elem = create_xml_element(media_elem, 'file')
        file_elem.set('src', media['file_name'])
        file_elem.set('mime', media['mime'])
        file_elem.set('description', media['description'])

        # Ajoute les références aux notes
        for note_handle in media.get('note_handles', set()):
            create_xml_element(media_elem, 'noteref', hlink=note_handle)

    for source in source_handles.values():
        source_elem = create_xml_element(objects, 'source',
            handle=source['handle'],
            change=str(int(datetime.now().timestamp())))

        create_xml_element(source_elem, 'stitle', text=source['title'])
        if source['pubinfo']:
            create_xml_element(source_elem, 'spubinfo', text=source['pubinfo'])

        # Ajoute les références aux notes
        for note_handle in source.get('note_handles', set()):
            create_xml_element(source_elem, 'noteref', hlink=note_handle)

    for note in notes_data:
        note_elem = create_xml_element(notes, 'note',
            handle=note['handle'],
            change=str(int(datetime.now().timestamp())),
            type='Html code',
            format='1')

        # Ajoute les balises <style> pour les titres
        ajouter_styles_texte(note_elem, note['text'])

        # Ajoute les références aux médias
        for file_name, start, end in note.get('media_refs', []):
            for media in media_handles.values():
                if media['file_name'] == file_name:
                    style = ET.SubElement(note_elem, 'style', name="link", value=f"gramps://Media/handle/{media['handle'][1:]}")
                    ET.SubElement(style, 'range', start=str(start), end=str(end))
                    note['object_handles']['media'].add(media['handle'])

        # Ajout des références aux médias
        for media_handle in note['media_handles']:
            create_xml_element(note_elem, 'objref', hlink=media_handle)

        # Ajout des références aux sources
        for source_handle in note['source_handles']:
            create_xml_element(note_elem, 'sourceref', hlink=source_handle)

        # Ajout des backréférences aux objets
        for obj_handle in note['object_handles']['people']:
            create_xml_element(note_elem, 'objref', hlink=obj_handle)
        for obj_handle in note['object_handles']['places']:
            create_xml_element(note_elem, 'objref', hlink=obj_handle)
        for obj_handle in note['object_handles']['events']:
            create_xml_element(note_elem, 'objref', hlink=obj_handle)
        for obj_handle in note['object_handles']['media']:
            create_xml_element(note_elem, 'objref', hlink=obj_handle)
        for obj_handle in note['object_handles']['sources']:
            create_xml_element(note_elem, 'objref', hlink=obj_handle)

        # Ajoute le texte de la note
        create_xml_element(note_elem, 'text', text=note['text'])

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

def main():
    args = parse_arguments()
    csv_to_gramps_xml(args.input_csv, args.output_xml)

if __name__ == "__main__":
    main()
