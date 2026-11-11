from flask import Blueprint, abort, jsonify, render_template, request

from frontend.database import saved_cars
from frontend.validation import location, required, yard_name
from junkyard.providers import lkq, picknpull, pullapart, upullandsave

main_bp = Blueprint('main', __name__, template_folder='templates')
PROVIDERS = {'lkq': lkq, 'picknpull': picknpull, 'pullapart': pullapart, 'upullandsave': upullandsave}
LOCATIONS = {'lkq': ('Dayton', 'Cincinnati'), 'pullapart': ('18', '8', '35'),
             'upullandsave': ('232', '265', '595')}


@main_bp.get('/')
def index():
    return render_template('main/index.html', **{f'cars_{yard}': saved_cars(yard)
                                               for yard in ('jacks', *PROVIDERS)})


@main_bp.get('/junkyard/<yard_name>')
def junkyard_page(yard_name):
    if yard_name not in (*PROVIDERS, 'jacks'):
        abort(404)
    makes = [] if yard_name in ('lkq', 'jacks') else PROVIDERS[yard_name].get_makes()
    return render_template(f'main/{yard_name}.html', yard_name=yard_name, makes=makes, models=[], results=[])


@main_bp.get('/api/models')
def get_models():
    yard = yard_name(PROVIDERS)
    if yard == 'lkq':
        return jsonify(models=[])
    make = required('make')
    if yard == 'picknpull':
        models = picknpull.get_models(make)
    else:
        models = PROVIDERS[yard].get_models(make, location(LOCATIONS[yard]))
    return jsonify(models=models)


@main_bp.get('/api/search')
def search_inventory():
    yard = yard_name(PROVIDERS)
    if yard == 'lkq':
        results = lkq.search_inventory(required('query'), location(LOCATIONS[yard]).title())
    elif yard == 'picknpull':
        results = picknpull.search_inventory(required('make'), request.args.get('model'))
    else:
        results = PROVIDERS[yard].search_inventory(required('make'), request.args.get('model'),
                                                    location(LOCATIONS[yard]))
    return jsonify(results=results)
