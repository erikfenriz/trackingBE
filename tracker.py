import os
import dateutil.parser
import names
import random
import logging
import sys
from datetime import datetime
from flask import Flask, Response, request, jsonify
from flask_cors import CORS
from flask_basicauth import BasicAuth
from flask_socketio import SocketIO, emit
from flask_sqlalchemy import SQLAlchemy, Model
from marshmallow import (Schema, fields, pre_load, post_load, post_dump,
    ValidationError)
from sqlalchemy import event, Column, Integer
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from werkzeug.exceptions import (HTTPException, UnprocessableEntity,
    BadRequest, NotFound)


class Base(Model):

    id = Column(Integer, primary_key=True)

    def __init__(self, *args, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)

    __table_args__ = {
        'sqlite_autoincrement': True
    }


class APIResponse(Response):

    @classmethod
    def force_type(cls, response, environ=None):
        """Converts dict or list response to json Response."""
        if isinstance(response, dict) or isinstance(response, list):
            response = jsonify(response)
        return super(APIResponse, cls).force_type(response, environ)


# setup logging similar to Flask default as gevent will attempt to reconfigure
# everything resulting in no messages at all
logging.basicConfig(level=logging.INFO, format='%(message)s')
# create a logger
logger = logging.getLogger('tracker')
# database file path
database = os.path.join(os.getcwd(), 'tracker.db')
# swagger spec and UI
swagger = os.path.join(os.getcwd(), 'swagger')
# create application
app = Flask('tracker', static_url_path='/swagger', static_folder=swagger)
# configure application
app.response_class = APIResponse
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///{}'.format(database)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['BASIC_AUTH_USERNAME'] = 'username'
app.config['BASIC_AUTH_PASSWORD'] = 'password'
# enable extensions
db = SQLAlchemy(app, model_class=Base)
basicauth = BasicAuth(app)
socketio = SocketIO(app, logger=logger)
CORS(app, resources={r'/*': {"origins": '*'}})


class Event(db.Model):
    """Sports event."""


class Reader(db.Model):
    """Sports event tag reader."""

    # reader 'position' could just mean one is before the other(s)
    # or in a real world scenario something like meters
    position = db.Column(db.Integer, unique=True, nullable=False)
    name = db.Column(db.String, nullable=False)
    event_id = db.Column(db.Integer, db.ForeignKey('event.id'), nullable=False)

    event = db.relationship('Event')


class Athlete(db.Model):
    """Sports event participant"""

    number = db.Column(db.Integer, unique=True, nullable=False)
    name = db.Column(db.Integer, nullable=False)


class Capture(db.Model):
    """Sports event reader capture."""

    athlete_id = db.Column(
        db.Integer,
        db.ForeignKey('athlete.id'), 
        nullable=False)
    
    reader_id = db.Column(
        db.Integer,
        db.ForeignKey('reader.id'), 
        nullable=False)

    # timestamp from reader
    timestamp = db.Column(db.DateTime, nullable=False)

    # timestamp for filtering
    captured = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    athlete = db.relationship('Athlete')
    reader = db.relationship('Reader')

    # allow only one capture per athlete and reader
    db.UniqueConstraint('athlete_id', 'reader_id')


class DateutilDateTime(fields.DateTime):

    DATEFORMAT_DESERIALIZATION_FUNCS = {
        'iso': dateutil.parser.parse,
        'iso8601': dateutil.parser.parse,
        'rfc': dateutil.parser.parse,
        'rfc822': dateutil.parser.parse,
    }


class BaseSchema(Schema):

    id = fields.Integer(dump_only=True)


class AthleteSchema(BaseSchema):

    number = fields.Integer()
    name = fields.String()

    @post_load()
    def make_object(self, data):
        return Athlete(**data)


class ReaderSchema(BaseSchema):

    position = fields.Integer()
    name = fields.String()
    event_id = fields.Integer()

    @post_load()
    def make_object(self, data):
        return Reader(**data)


class CaptureSchema(BaseSchema):

    athlete_id = fields.Integer(required=True)
    reader_id = fields.Integer(required=True)

    # use dateutil.parse because python standard library tools used in
    # marshmallow appear to be losing fractions from ISO8601 dates
    timestamp = DateutilDateTime(required=True)
    captured = DateutilDateTime(dump_only=True)

    athlete = fields.Nested(AthleteSchema(), dump_only=True)

    @post_load()
    def make_object(self, data):
        return Capture(**data)


def request_timestamp():
    param = request.args.get('timestamp', None)
    if param is not None:
        try:
            return datetime.utcfromtimestamp(int(param))
        except:
            raise BadRequest()
    return None


@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()

@app.errorhandler(IntegrityError)
def handle_integrityerror(error):
    app.logger.exception(error)
    raise UnprocessableEntity()


@app.route('/athletes')
def all_athletes():
    athletes = Athlete.query.all()
    return AthleteSchema(many=True).dump(athletes).data


@app.route('/athletes/<athlete_id>')
def get_athlete(athlete_id):
    athlete = Athlete.query.get(athlete_id)
    if not athlete:
        raise NotFound()
    return AthleteSchema().dump(athlete).data


@app.route('/readers')
def all_readers():
    readers = Reader.query.all()
    return ReaderSchema(many=True).dump(readers).data


@app.route('/readers/<reader_id>')
def get_reader(reader_id):
    reader = Reader.query.get(reader_id)
    return ReaderSchema().dump(reader).data


@socketio.on('connect')
def handle_connect():
    # emit all readers to connected client
    reader_schema = ReaderSchema(many=True)
    readers = Reader.query.all()
    emit('readers', reader_schema.dump(readers).data)

    # emit all captures to connected client
    capture_schema = CaptureSchema(load_only=('athlete_id',), many=True)
    captures = Capture.query.all()
    emit('captures', capture_schema.dump(captures).data)

@app.route('/captures')
def all_captures():
    timestamp = request_timestamp()
    schema = CaptureSchema(load_only=('athlete_id',), many=True)
    query = Capture.query
    if timestamp is not None:
        query = query.filter(Capture.captured > timestamp)    
    captures = query.all()
    return schema.dump(captures).data


@app.route('/captures/<capture_id>')
def get_capture(capture_id):
    schema = CaptureSchema(load_only=('athlete_id',))
    capture = Capture.query.get(capture_id)
    if not capture:
        raise NotFound()
    return schema.dump(capture).data


@app.route('/captures', methods=['POST'])
@basicauth.required
def create_capture():
    json_data = request.get_json() or {}
    schema = CaptureSchema(load_only=('athlete_id',))
    
    # deserialize
    capture, errors = schema.load(json_data)
    if errors:
        return errors, 400

    try:
        # try to save
        db.session.add(capture)
        db.session.commit()
    except IntegrityError as e:
        # violation of some constraint ocurred
        raise UnprocessableEntity()

    # serialize created object
    data, errors = schema.dump(capture)
    
    # try to publish socketio clients
    try:
        socketio.emit('captures', [data])
    except Exception as e:
        app.logger.exception(e)
    
    return data, 202


@app.cli.command()
def initdb():
    db.create_all()


@app.cli.command()
def seed():
    # empty all tables
    for table in reversed(db.metadata.sorted_tables):
        db.session.execute(table.delete())

    numbers = set()
    # create 100 athletes
    for i in range(100):
        # generate random name
        name = names.get_full_name()
        
        # generate 'sporty' looking bib number
        number = None
        while (number is None or number in numbers):
            number = random.randrange(1000, 9999)
        
        # avoid collisions
        numbers.add(number)
        db.session.add(Athlete(number=number, name=name))

    # new sports event
    event = Event()

    db.session.add_all([
        Reader(position=0, name='Finišikoridori algus', event=event),
        Reader(position=1000, name='Finišikoridori lõpp', event=event)])

    db.session.commit()
    db.session.remove()