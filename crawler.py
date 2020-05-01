import codecs
import json
import os
from concurrent.futures.thread import ThreadPoolExecutor
from datetime import datetime
from math import radians, sin, cos, sqrt, atan2

from requests import Session

common_headers = {
    'Content-Type': 'application/json'
}
base_url = 'https://fp.trafikverket.se/boka'
session = Session()

timeslots_per_city = {}
mailjet_token = os.environ["MAILJET_TOKEN"]
ssn = os.environ['SSN']
from_email = os.environ['FROM_EMAIL']
to_email = os.environ['TO_EMAIL']


def crawl():
    with ThreadPoolExecutor(max_workers=30) as executor:
        executor.map(get_timeslot_for_location, get_locations())
        executor.shutdown(wait=True)
    with codecs.open('data/timeslots_per_city.json', 'r', "utf-8") as file:
        old_timeslots_per_city = json.load(file)
        new_times = compare_times(old_timeslots_per_city, timeslots_per_city)
        send_email(new_times)
    with codecs.open('data/timeslots_per_city.json', 'w', "utf-8") as file:
        json.dump(timeslots_per_city, file, ensure_ascii=False)


def send_email(new_times):
    if not new_times:
        return
    email_data = {
        "Messages": [
            {
                "From": {
                    "Email": from_email,
                    "Name": "Driving times"
                },
                "To": [
                    {
                        "Email": to_email,
                        "Name": "Anon"
                    }
                ],
                "Subject": "New times available",
                "CustomID": "driving_test_times"
            }
        ]
    }
    html_part = get_html_part(new_times)
    email_data['Messages'][0]['HTMLPart'] = html_part
    email_data['Messages'][0]['TextPart'] = json.dumps(new_times, indent=4)
    mail_headers = {
        'Content-Type': 'application/json',
        'Authorization': f"Basic {mailjet_token}"
    }
    session.post("https://api.mailjet.com/v3.1/send", json=email_data, headers=mail_headers)


def get_html_part(times):
    with codecs.open("email_template/city-template.html", 'r', 'utf-8') as city_file:
        complete_city_template = ""
        city_template = city_file.read()
        for city_name, timeslots in times.items():
            formatted_timeslots = [f"<li>{timeslot}</li>" for timeslot in timeslots]
            complete_city_template += city_template % (city_name, "".join(formatted_timeslots))
        with codecs.open("email_template/email-template.html", 'r', 'utf-8') as email_file:
            return email_file.read().replace("city_templates", complete_city_template)


def compare_times(old_timeslots_per_city, new_timeslots_per_city):
    better_times = {}
    for city_name, old_timeslot in old_timeslots_per_city.items():
        if city_name in new_timeslots_per_city:
            for new_timeslot in new_timeslots_per_city[city_name]:
                if new_timeslot < old_timeslot[0]:
                    if new_timeslot < datetime(year=2020, month=6, day=26).isoformat(' '):
                        if city_name in better_times:
                            better_times[city_name].append(new_timeslot)
                        else:
                            better_times[city_name] = [new_timeslot]
    return better_times


def get_timeslot_for_location(location):
    stockholm_coord = {
        'latitude': 59.3295887,
        'longitude': 18.0669343
    }
    category_found = False
    for category in location['examinationCategories']:
        if category['value'] == 1:
            category_found = True
    if calc_distance(location['location']['coordinates'], stockholm_coord) > 200:
        category_found = False
    if category_found:
        timeslots = get_timeslots(location)
        timeslots_per_city[location['location']['name']] = timeslots


def calc_distance(coord1, coord2):
    # approximate radius of earth in km
    R = 6373.0

    lat1 = radians(abs(coord1['latitude']))
    lon1 = radians(abs(coord1['longitude']))
    lat2 = radians(abs(coord2['latitude']))
    lon2 = radians(abs(coord2['longitude']))

    dlon = lon2 - lon1
    dlat = lat2 - lat1

    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))

    return R * c


def get_timeslots(location):
    with open('data/timeslot-query.json') as file:
        data = json.load(file)
        data['socialSecurityNumber'] = ssn
        data['occasionBundleQuery']['startDate'] = datetime.now().astimezone().isoformat()
        data['occasionBundleQuery']['locationId'] = location['location']['id']
        print(data['occasionBundleQuery']['startDate'])
        response = session.post(f'{base_url}/occasion-bundles', json=data, headers=common_headers).json()['data']
        return [f"{occasion['date']} {occasion['time']}" for occasions in response for occasion in
                occasions['occasions']][:5]


def get_locations():
    location_file_path = 'data/locations.json'
    if not os.path.exists(location_file_path):
        with open('data/location-query.json') as file:
            data = json.load(file)
            data['socialSecurityNumber'] = ssn
            response = session.post(f'{base_url}/search-information', json=data, headers=common_headers).json()
            locations = response['data']['locations']
            with open(location_file_path, 'w') as location_file:
                json.dump(locations, location_file)
                return locations
    else:
        with open(location_file_path) as file:
            return json.load(file)


if __name__ == "__main__":
    crawl()
