# -*- coding: utf-8 -*-

import csv
import re
import argparse
from xml.sax.saxutils import escape
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

def extract_architects(text):
    """Extrait les noms des architectes à partir des balises {{Infobox actualité}}."""
    infobox_pattern = re.compile(r'\{\{\s*Infobox\s+actualité\s*\|\s*(.*?)\}\}', re.DOTALL)
    architect_pattern = re.compile(r'\|\s*architecte\s*=\s*([^\n\|]+)')

    architects = set()
    infobox_matches = infobox_pattern.findall(text)
    for match in infobox_matches:
        architect_matches = architect_pattern.findall(match)
        for architect in architect_matches:
            architects.add(architect.strip())

    return list(architects)

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

def create_event(xml_file, event_info, event_handle, place_handle, architect_handles, current_timestamp):
    """Crée un événement Gramps à partir des informations extraites."""
    xml_file.write(f'    <event handle="_{event_handle}" id="E{event_handle}" change="{current_timestamp}">\n')
    xml_file.write(f'      <type>{escape(event_info.get("type", "Événement"))}</type>\n')

    # Date de l'événement
    date_range = event_info.get('date', '')
    date_value, date_type = format_date_for_gramps(date_range)

    if date_value and date_type:
        xml_file.write(f'      <dateval val="{date_value}" type="{date_type}"/>\n')
    else:
        xml_file.write(f'      <dateval val="0000" type="Span"/>\n')

    # Description de l'événement
    xml_file.write(f'      <description>{escape(event_info.get("description", ""))}</description>\n')

    # Lien vers le lieu
    xml_file.write(f'      <placeref hlink="_{place_handle}"/>\n')

    # Lien vers l'architecte
    for architect in architect_handles:
        xml_file.write(f'      <personref hlink="_{architect_handles[architect]}" role="Architect"/>\n')

    # Attributs supplémentaires
    for key, value in event_info.items():
        if key not in ['date', 'type', 'description']:
            xml_file.write(f'      <attribute type="{key}" value="{escape(value)}"/>\n')

    xml_file.write(f'    </event>\n')

    return event_handle + 1

def process_row(row, xml_file, place_handles, note_handles, person_handles, event_handles, architect_handles, source_handles, media_handles, current_timestamp, use_wikipedia):
    """Traite une seule ligne de données et écrit directement dans le fichier XML."""
    lat, lon = parse_coords(row.get('Coordonnées', ''))[0]

    # Écrire le lieu
    place_handle = f"_{len(place_handles) + 100000000}"
    place_handles[place_handle] = row.get('Titre', 'Inconnu')

    xml_file.write(f'    <place handle="{place_handle}" id="P{place_handle[1:]}" change="{current_timestamp}">\n')
    xml_file.write(f'      <ptitle>{escape(place_handles[place_handle])}</ptitle>\n')
    xml_file.write(f'      <pname value="{escape(place_handles[place_handle])}"/>\n')
    if lat and lon:
        xml_file.write(f'      <coord lat="{lat}" long="{lon}"/>\n')

    # Extraction des architectes
    architects = extract_architects(row.get('Description', ''))
    for architect in architects:
        if architect not in architect_handles:
            # Écrire l'architecte
            person_handle = f"_{len(person_handles) + 200000000}"
            person_handles[person_handle] = architect
            architect_handles[architect] = person_handle
            xml_file.write(f'    <person handle="{person_handle}" id="I{person_handle[1:]}" change="{current_timestamp}">\n')
            xml_file.write(f'      <name type="Birth Name">\n')
            surname = architect.split()[-1] if architect.split() else 'Inconnu'
            firstname = ' '.join(architect.split()[:-1]) if len(architect.split()) > 1 else 'Inconnu'
            xml_file.write(f'        <surname>{escape(surname)}</surname>\n')
            xml_file.write(f'        <first>{escape(firstname)}</first>\n')
            xml_file.write(f'      </name>\n')
            xml_file.write(f'    </person>\n')

        # Ajouter une référence à l'architecte dans le lieu
        xml_file.write(f'      <personref hlink="{architect_handles[architect]}" role="Architect"/>\n')

    # Ajouter une note (description)
    if 'Description' in row and row['Description']:
        note_handle = f"_{len(note_handles) + 400000000}"
        note_handles[note_handle] = row['Description']
        xml_file.write(f'      <noteref hlink="{note_handle}"/>\n')
        xml_file.write(f'    </place>\n')
        xml_file.write(f'    <note handle="{note_handle}" id="N{note_handle[1:]}" change="{current_timestamp}" type="Note">\n')
        xml_file.write(f'      <text>{escape(note_handles[note_handle])}</text>\n')
        xml_file.write(f'    </note>\n')
    else:
        xml_file.write(f'    </place>\n')

    # Extraction des événements
    events = extract_infobox_events(row.get('Description', ''))
    for event_info in events:
        event_info['description'] = row.get('Description', '')
        event_handles.add(create_event(xml_file, event_info, len(event_handles) + 300000000, place_handle, architect_handles, current_timestamp))

    # Extraction des références
    refs = extract_refs(row.get('Description', ''))
    for ref in refs:
        url, meta, sources = parse_ref(ref)
        if url and url not in source_handles:
            source_handle = f"_{len(source_handles) + 500000000}"
            source_handles[url] = source_handle
            xml_file.write(f'    <source handle="{source_handle}" id="S{source_handle[1:]}" change="{current_timestamp}">\n')
            xml_file.write(f'      <stitle>{escape(url)}</stitle>\n')
            if meta.get("consulté"):
                xml_file.write(f'      <spubinfo>{escape(meta["consulté"])}</spubinfo>\n')
            xml_file.write(f'    </source>\n')
        for source_model in sources:
            if source_model not in source_handles:
                source_handle = f"_{len(source_handles) + 500000000}"
                source_handles[source_model] = source_handle
                xml_file.write(f'    <source handle="{source_handle}" id="S{source_handle[1:]}" change="{current_timestamp}">\n')
                xml_file.write(f'      <stitle>{escape(source_model)}</stitle>\n')
                xml_file.write(f'    </source>\n')

    # Extraction des galeries
    files = extract_gallery(row.get('Description', ''))
    for file_name, file_desc in files:
        if file_name not in media_handles:
            media_handle = f"_{len(media_handles) + 600000000}"
            media_handles[file_name] = media_handle
            mime_type = get_mime_type(file_name)
            xml_file.write(f'    <object handle="{media_handle}" id="O{media_handle[1:]}" type="Media" change="{current_timestamp}">\n')
            xml_file.write(f'      <file src="{escape(file_name)}" mime="{mime_type}" description="{escape(file_desc)}"/>\n')
            xml_file.write(f'    </object>\n')

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

    # Vérifie que le chemin de sortie est valide
    output_dir = os.path.dirname(output_xml_file_path)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)
        print(f"Création du répertoire : {output_dir}")

    current_timestamp = str(int(datetime.now().timestamp()))

    # Dictionnaires pour stocker les handles et éviter les doublons
    place_handles = {}
    note_handles = {}
    person_handles = {}
    event_handles = set()
    architect_handles = {}
    source_handles = {}
    media_handles = {}

    # Écrire le fichier XML par morceaux
    with open(output_xml_file_path, 'w', encoding='utf-8') as xml_file:
        xml_file.write('''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE database PUBLIC "-//Gramps//DTD Gramps XML 1.7.1//EN"
"http://gramps-project.org/xml/1.7.1/grampsxml.dtd">
<database xmlns="http://gramps-project.org/xml/1.7.1/">
  <header>
    <created date="''' + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + '''" version="5.2.0"/>
    <researcher name="Generated by script"/>
  </header>
  <objects>
''')

        # Traitement des données par lots
        for i, row in enumerate(data):
            print_progress(i + 1, total_rows)
            process_row(row, xml_file, place_handles, note_handles, person_handles, event_handles, architect_handles, source_handles, media_handles, current_timestamp, use_wikipedia)

        xml_file.write('  </objects>\n</database>\n')

    print(f"\nConversion terminée avec succès ! Le fichier a été enregistré sous : {output_xml_file_path}")

def main():
    args = parse_arguments()
    csv_to_gramps_xml(args.input_csv, args.output_xml, args.wikipedia, args.batch_size)

if __name__ == "__main__":
    main()
