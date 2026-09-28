from flask import Blueprint, jsonify

bp = Blueprint('main', __name__)


@bp.get('/')
def index():
    return jsonify(message='Hello, World!')
