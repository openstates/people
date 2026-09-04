import csv
import json
import glob
import os
import sys
import utils
from postal.parser import parse_address

def generate_legislator_json():
    #yaml filenames
    script_dir = os.path.dirname(os.path.abspath(__file__))
    datadir = os.path.join(script_dir, '../data/')

    #get argument for force refresh
    force_refresh = False
    if len(sys.argv) > 1 and sys.argv[1] == '--force-refresh':
        force_refresh = True

    for state in os.listdir(datadir): #for each state dir
        if state == 'us':
            continue
        statedir_path = os.path.join(datadir, state)
        if os.path.isdir(statedir_path):
            for filename in os.listdir(statedir_path): #for each dir in state dir
                statesub_dir = os.path.join(statedir_path, filename)
                if os.path.isdir(statesub_dir):
                    jsonDataList = []  # Reset for each directory
                    json_out_filename = os.path.join(script_dir,"../alternate_formats/json/", state, filename+'.json')
                    os.makedirs(os.path.dirname(json_out_filename), exist_ok=True)
                    if not force_refresh and os.path.exists(json_out_filename):
                        print(f"Skipping {json_out_filename}, already exists. Use --force-refresh to regenerate.")
                        continue

                    print("Processing directory: %s..." % statesub_dir)
                    place_names = load_place_names(statedir_path)
                    for filepath in glob.glob(os.path.join(statesub_dir, '*.yml')): #for each yaml file in dir
                        yaml_filename = os.path.basename(filepath)
                        print("Converting %s to JSON..." % yaml_filename)
                        data = utils.load_data(filepath)
                        
                        # Translate from open states format to legislators-current format
                        person = {}

                        person['id'] = {}
                        if 'id' in data:
                            person['id']['openstates'] = data['id']
                            
                        person['name'] = {}
                        if 'name' in data:
                            person['name']['official_full'] = data['name']
                        if 'given_name' in data:
                            person['name']['first'] = data['given_name']
                        if 'family_name' in data:
                            person['name']['last'] = data['family_name']
                            
                        person['bio'] = {}
                        if 'gender' in data:
                            person['bio']['gender'] = 'M' if data['gender'] == 'Male' else 'F' if data['gender'] == 'Female' else data['gender']
                        if 'birth_date' in data and data['birth_date']:
                            person['bio']['birthday'] = data['birth_date']
                        if 'image' in data:
                            person['image_url'] = data['image']

                        person['terms'] = []
                        if 'roles' in data:
                            for role in data['roles']:
                                # start a new term and always give it an addresses list
                                term = {'addresses': []}
                                term['type'] = role['type']
                                term['state'] = utils.states[state.upper()]
                                if 'district' in role:
                                    term['district'] = role['district']
                                if 'start_date' in role:
                                    term['start'] = str(role['start_date'])
                                if 'end_date' in role:
                                    term['end'] = str(role['end_date'])
                                # Municipal roles carry an OCD jurisdiction instead of a
                                # district; pass it through with a display name so
                                # clients can label the seat (e.g. "Mayor • Hawthorne").
                                if 'jurisdiction' in role:
                                    term['jurisdiction'] = role['jurisdiction']
                                    term['place'] = jurisdiction_place_name(
                                        role['jurisdiction'], place_names)

                                # try to find party
                                if 'party' in data and len(data['party']) > 0:
                                     term['party'] = data['party'][0].get('name')

                                # try to find offices
                                if 'offices' in data and len(data['offices']) > 0:
                                    for office in data['offices']:
                                        term['addresses'].append(parse_office_address(office))

                                if 'email' in data:
                                    term['contact_form'] = data['email']

                                if 'links' in data and len(data['links']) > 0:
                                    term['url'] = data['links'][-1].get('url')  # Use the last link as the URL

                                person['terms'].append(term)
                                person['terms'].reverse()  # Reverse to have most recent term last, to match congressional format

                        jsonDataList.append(person)

                # Write immediately after processing each directory
                    utils.write(
                        json.dumps(jsonDataList, default=utils.format_datetime, indent=2),
                        json_out_filename)

def load_place_names(statedir_path):
    """Map OCD jurisdiction ids to display names from <state>/municipalities.yml."""
    path = os.path.join(statedir_path, 'municipalities.yml')
    if not os.path.exists(path):
        return {}
    try:
        entries = utils.load_data(path) or []
    except Exception as e:
        print("Could not load %s: %s" % (path, e))
        return {}
    return {e['id']: e['name'] for e in entries if 'id' in e and 'name' in e}


def jurisdiction_place_name(jurisdiction, place_names):
    """Display name for an OCD jurisdiction id.

    Prefers municipalities.yml; falls back to the `place:` segment of the id
    (e.g. .../place:los_angeles/government -> "Los Angeles").
    """
    if jurisdiction in place_names:
        return place_names[jurisdiction]
    for segment in jurisdiction.split('/'):
        if segment.startswith('place:'):
            return segment[len('place:'):].replace('_', ' ').title()
    return None


def parse_office_address(office):

    # run libpostal; it always returns lower‑cased components
    parsed_items = parse_address(office.get('address', ''))

    # restore capitalisation – e.g. “pennsylvania” → “Pennsylvania”
    # you can tweak this if you need to preserve “USA”, “McFoo” etc.
    parsed_items = [(component.title(), label) for component, label in parsed_items]

    # parse_address() returns a list of (component, label) tuples,
    # turn it into a dict keyed by label for easier lookup
    comps = {label: component for component, label in parsed_items}

                                        # first line: house number + road (+ road type if present)
    addr1_parts = []
    if 'house_number' in comps:
        addr1_parts.append(comps['house_number'])
    if 'road' in comps:
        addr1_parts.append(comps['road'])
    if 'road_type' in comps:          # e.g. "St", "Ave"
        addr1_parts.append(comps['road_type'])
    address1 = ' '.join(addr1_parts) if addr1_parts else None

                                        # second line: any unit/room/level/suite/PO‑box info
    secondary = []
    if 'room' in comps:
        secondary.append('Room ' + comps['room'])
    if 'unit' in comps:
        secondary.append(comps['unit'])
    if 'level' in comps:
        secondary.append('Level ' + comps['level'])
    if 'suite' in comps:
        secondary.append('Suite ' + comps['suite'])
    if 'po_box' in comps:
        secondary.append('P.O. Box ' + comps['po_box'])
    address2 = ', '.join(secondary) if secondary else None
    newOffice = {}
    newOffice['address1'] = address1
    newOffice['address2'] = address2
    newOffice['city'] = comps.get('city')
    newOffice['state'] = comps.get('state')
    newOffice['zip'] = comps.get('postcode')

    if 'voice' in office:
        newOffice['phone'] = office['voice']
    if 'classification' in office:
        newOffice['title'] = office['classification']

    return newOffice

if __name__ == '__main__':
    print("Generating alternate bulk formats for People...")
    # Use absolute path based on script location to avoid permission issues in debugger
    script_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(script_dir, '../data/')
    output_dir = os.path.join(script_dir, "..", "alternate_formats")

    # get argument for remove pickle files
    remove_pickles = False
    if len(sys.argv) > 1 and sys.argv[1] == '--remove-pickles':
        remove_pickles = True

    if remove_pickles:
        utils.remove_pickles(data_dir)
    else:
        os.makedirs(os.path.join(output_dir, "json"), exist_ok=True)
        generate_legislator_json()
