from flask_smorest import Blueprint

from .schemas import MessageSchema

bp = Blueprint('main', __name__, description='Service health / hello world')


@bp.get('/')
@bp.response(200, MessageSchema)
def index():
    """Hello world"""
    return {'message': 'Hello, World!'}
