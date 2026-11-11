"""Personal watch rules, persistence and notifications; no upstream parsing."""
import argparse
import logging
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.parse import urlparse

from junkyard.common import InventoryError, optional, request, unique, vin_series
from junkyard.providers import jacks, lkq, picknpull, pullapart, pullnsave, tearapart, upullandsave, utpap

LOG = logging.getLogger(__name__)
DEFAULT_YARDS = 'jacks,lkq,picknpull,pullapart,upullandsave'
YARDS = ('jacks', 'lkq', 'picknpull', 'pullapart', 'upullandsave', 'tearapart', 'utpap', 'pullnsave')
HEALTH_NAMES = {'lkq': 'LKQ', 'utpap': 'UTPAP'}
ROOT = Path(__file__).resolve().parent.parent


def interested(yard, car):
    year, model = car['year'], car['model']
    e_class = model.startswith('E') if yard == 'lkq' else (
        'E-CLASS' in model if yard == 'pullnsave' else model == 'E-CLASS')
    return 1976 <= year <= 1985 or (1996 <= year <= 2002 and e_class)


def watch_results(yard, cars):
    selected = []
    for original in cars:
        car = dict(original)
        interest = interested(yard, car)
        if yard in ('tearapart', 'utpap', 'pullnsave'):
            if not interest:
                continue
        else:
            car['interest_level'] = int(interest)
        selected.append(car)
    return selected


def searches(yard):
    """Scopes match existing collections; each location succeeds independently."""
    if yard == 'lkq':
        return [({'location': loc}, lambda loc=loc: lkq.search_inventory('mercedes', loc))
                for loc in ('Dayton', 'Cincinnati')]
    if yard == 'utpap':
        return [({'location': loc}, lambda loc=loc: utpap.search_utpap_inventory('MERCEDES-BENZ', location=loc))
                for loc in ('Orem', 'Ogden')]
    if yard == 'pullnsave':
        return [({'yard': loc}, lambda loc=loc: pullnsave.search_pullnsave_inventory(
            'Mercedes-Benz', None, loc, year=1976, end_year=2002)) for loc in (1, 6)]
    if yard == 'pullapart':
        return [({'location_id': loc}, lambda loc=loc: pullapart.search_inventory(37, None, loc))
                for loc in (18, 8, 35)]
    fetch = {
        'jacks': lambda: jacks.search_inventory('MERCEDES'),
        'picknpull': lambda: picknpull.search_inventory(182),
        'upullandsave': lambda: upullandsave.search_inventory('MERCEDES-BENZ', None, 232),
        'tearapart': lambda: tearapart.search_tearapart_inventory('MERCEDES-BENZ', location=None),
    }
    return [({}, fetch[yard])]


def identity(car, scope):
    # Use location as well as stock number; old documents already contain it,
    # except Jack's, whose synthetic stock number is the existing identity.
    key = {**scope, 'stock_num': car['stock_num']}
    if car.get('location') and car['location'] != "Jack's":
        key['location'] = car['location']
    return key


def valid_image(value):
    parsed = urlparse(value or '')
    return parsed.scheme in ('http', 'https') and bool(parsed.netloc)


def validate_snapshot(scope, cars):
    unique(cars)
    for car in cars:
        if any(car.get(key) != value for key, value in scope.items()):
            raise InventoryError('Inventory response contains a vehicle outside the requested location')


def sync_snapshot(collection, scope, cars, notify, yard):
    """Called only after ALL pages and rows have validated. Never delete on fetch failure."""
    validate_snapshot(scope, cars)
    existing = list(collection.find(scope))
    current_keys = {tuple(sorted(identity(car, scope).items())) for car in cars}
    for car in cars:
        key = identity(car, scope)
        old = collection.find_one(key)
        if old is None:
            if yard in ('tearapart', 'pullnsave'):
                series = optional(vin_series, car.get('vin', ''))
                if series:
                    car['series'] = series
            notify(dict(car))
            collection.insert_one(dict(car))
        else:
            changes = dict(car)
            # Preserve previous optional enrichment if an auxiliary service is down.
            for field in ('image', 'image_urls', 'series', 'trim', 'engine', 'transmission', 'color', 'style'):
                if not changes.get(field) or changes.get(field) == 'Unknown':
                    changes.pop(field, None)
            if yard in ('pullapart', 'upullandsave') and not valid_image(old.get('image')) and valid_image(car.get('image')):
                notify({**{k: v for k, v in old.items() if k != '_id'}, **changes})
            collection.update_one(key, {'$set': changes})
    # Notification or write failures above prevent removal of stale records.
    for old in existing:
        if tuple(sorted(identity(old, scope).items())) not in current_keys:
            collection.delete_one({'_id': old['_id']} if '_id' in old else identity(old, scope))


def run_checks(yard, collection, notify):
    success = True
    for scope, fetch in searches(yard):
        try:
            fetched = list(fetch())
            validate_snapshot(scope, fetched)
            cars = watch_results(yard, fetched)
            sync_snapshot(collection, scope, cars, notify, yard)
        except Exception:
            LOG.exception('%s inventory check failed for %s', yard, scope)
            success = False
    return success


def health_file(yard):
    return Path('/tmp') / HEALTH_NAMES.get(yard, yard) / 'health_status.txt'


def write_health(yard, success):
    path = health_file(yard)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text('healthy' if success else 'unhealthy')
    temporary.replace(path)


def run_yard(yard):
    # Lazy imports keep parser tests and frontend imports independent of worker configuration.
    from dotenv import load_dotenv
    from pymongo import MongoClient

    load_dotenv(ROOT / yard / '.env')
    load_dotenv(ROOT / '.env')
    success = False
    try:
        collection_name = os.getenv(f'MONGO_COLLECTION_NAME_{yard.upper()}') or os.environ['MONGO_COLLECTION_NAME']
        webhook = os.getenv(f'HOME_ASSISTANT_WEBHOOK_URL_{yard.upper()}') or os.getenv('HOME_ASSISTANT_WEBHOOK_URL')
        if not webhook:
            webhook_id = os.getenv(f'HOME_ASSISTANT_WEBHOOK_ID_{yard.upper()}') or os.environ['HOME_ASSISTANT_WEBHOOK_ID']
            webhook = f'https://ha.tsmcclel.top/api/webhook/{webhook_id}'

        def notify(car):
            request('POST', webhook, json=car)

        with MongoClient(os.environ['MONGO_URI'], serverSelectionTimeoutMS=10000) as client:
            collection = client[os.environ['MONGO_DB_NAME']][collection_name]
            success = run_checks(yard, collection, notify)
    except Exception:
        LOG.exception('%s worker failed', yard)
    write_health(yard, success)
    return success


def configured_yards():
    yards = os.getenv('SCRAPER_YARDS', DEFAULT_YARDS).split(',')
    yards = [yard.strip() for yard in yards if yard.strip()]
    if not yards or any(yard not in YARDS for yard in yards):
        raise ValueError('SCRAPER_YARDS must contain known yard names')
    return list(dict.fromkeys(yards))


def healthcheck():
    max_age = int(os.getenv('SCRAPER_INTERVAL_SECONDS', '3600')) + int(os.getenv('SCRAPER_TIMEOUT_SECONDS', '1800')) + 300
    for yard in configured_yards():
        path = health_file(yard)
        if not path.exists() or path.read_text() != 'healthy' or time.time() - path.stat().st_mtime > max_age:
            return False
    return True


def run_cycle():
    success = True
    # Subprocesses isolate legacy per-yard .env settings and cap stalled jobs.
    for yard in configured_yards():
        try:
            result = subprocess.run([sys.executable, '-m', 'junkyard.worker', yard],
                                    timeout=int(os.getenv('SCRAPER_TIMEOUT_SECONDS', '1800')), check=False)
            ok = result.returncode == 0
        except subprocess.TimeoutExpired:
            LOG.error('%s worker timed out', yard)
            ok = False
        if not ok:
            write_health(yard, False)
        success = ok and success
    return success


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('yard', nargs='?', choices=YARDS)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--loop', action='store_true', help='Run configured yards hourly, including on startup')
    mode.add_argument('--healthcheck', action='store_true')
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    if args.healthcheck:
        return 0 if healthcheck() else 1
    if args.yard:
        return 0 if run_yard(args.yard) else 1
    while True:
        started = time.monotonic()
        success = run_cycle()
        if not args.loop:
            return 0 if success else 1
        interval = max(60, int(os.getenv('SCRAPER_INTERVAL_SECONDS', '3600')))
        time.sleep(max(1, interval - (time.monotonic() - started)))


if __name__ == '__main__':
    raise SystemExit(main())
