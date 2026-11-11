from flask import Blueprint, abort, jsonify, render_template, request

from frontend.database import saved_cars
from frontend.validation import location, required, yard_name
from junkyard.providers import pullnsave, tearapart, utpap

utah_bp = Blueprint('utah', __name__, template_folder='templates')
YARDS = ('tearapart', 'pullnsave', 'utpap')


@utah_bp.get('/')
def index():
    return render_template('utah/index.html', **{f'cars_{yard}': saved_cars(yard) for yard in YARDS})


@utah_bp.get('/api/images/pullnsave/<stock_num>/<yard>')
def pullnsave_image(stock_num, yard):
    if yard not in ('1', '6'):
        abort(400, description='Unknown location.')
    images = pullnsave.images(stock_num, yard)
    return jsonify(count=len(images), images=images)


@utah_bp.get('/junkyard/<yard_name>')
def junkyard_page(yard_name):
    if yard_name not in YARDS:
        abort(404)
    makes = {'tearapart': tearapart.get_makes_from_tearapart,
             'pullnsave': pullnsave.get_makes_from_pullnsave,
             'utpap': utpap.get_modelmap_from_utpap}[yard_name]()
    return render_template(f'utah/{yard_name}.html', yard_name=yard_name, makes=makes, models=[], results=[])


@utah_bp.get('/api/models')
def get_models():
    yard = yard_name(YARDS)
    make = required('make')
    if yard == 'tearapart':
        models = tearapart.get_models_from_tearapart(make)
    elif yard == 'pullnsave':
        models = pullnsave.get_models_from_pullnsave(make)
    else:
        models = utpap.get_modelmap_from_utpap().get(make, [])
    return jsonify(models=models)


@utah_bp.get('/api/search')
def search_inventory():
    yard = yard_name(YARDS)
    make, model = required('make'), request.args.get('model')
    if yard == 'tearapart':
        results = tearapart.search_tearapart_inventory(make, model)
    elif yard == 'pullnsave':
        results = pullnsave.search_pullnsave_inventory(make, model, location(('1', '6')))
    else:
        results = utpap.search_utpap_inventory(make, model)
    return jsonify(results=results)
