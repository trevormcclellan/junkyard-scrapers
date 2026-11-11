from flask import abort, request


def required(name):
    value = request.args.get(name, '').strip()
    if not value:
        abort(400, description=f'{name} is required.')
    return value


def yard_name(allowed):
    yard = required('yard_name')
    if yard not in allowed:
        abort(400, description='Unknown yard.')
    return yard


def location(allowed):
    value = required('location')
    if value.lower() not in {str(item).lower() for item in allowed}:
        abort(400, description='Unknown location.')
    return value
