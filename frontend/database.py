from flask import abort, current_app


def collection(yard):
    config = current_app.config
    name = config.get(f'MONGO_COLLECTION_NAME_{yard.upper()}')
    if not config.get('MONGO_URI') or not config.get('MONGO_DB_NAME') or not name:
        abort(503, description='Saved inventory is not configured.')
    if 'mongo' not in current_app.extensions:
        from pymongo import MongoClient
        current_app.extensions['mongo'] = MongoClient(config['MONGO_URI'], serverSelectionTimeoutMS=10000)
    return current_app.extensions['mongo'][config['MONGO_DB_NAME']][name]


def saved_cars(yard):
    from pymongo.errors import PyMongoError
    try:
        return list(collection(yard).find())
    except PyMongoError:
        current_app.logger.exception('Saved inventory unavailable')
        abort(503, description='Saved inventory is temporarily unavailable.')
