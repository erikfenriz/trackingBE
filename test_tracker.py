import os
import tempfile
import pytest
import socketio
import tracker
import json
import base64
from dateutil.parser import parse 
from dateutil.tz import tzutc
from werkzeug.datastructures import Headers
from datetime import datetime
from unittest.mock import patch
from collections import namedtuple


Client = namedtuple('Client', ['app', 'socketio'])
now = datetime.utcnow().replace(tzinfo=tzutc())
iso = now.isoformat()
event = {'id': 1}
start = {'id': 1, 'position': 0, 'name': 'Start', 'event_id': 1}
finish = {'id': 2, 'position': 1, 'name': 'Finish', 'event_id': 1}
john = {'id': 1, 'number': 1234, 'name': 'John Doe'}
jane = {'id': 2, 'number': 4321, 'name': 'Jane Doe'}
capture = {'id': 1, 'athlete_id': 1, 'reader_id': 1, 'timestamp': now}


def make_auth():
    username = tracker.app.config['BASIC_AUTH_USERNAME']
    password = tracker.app.config['BASIC_AUTH_PASSWORD']
    token_bytes = (username + ':' + password).encode('utf-8')
    return base64.b64encode(token_bytes).decode('ascii')

@pytest.fixture(scope='session')
def client(request):
    tracker.app.testing = True
    tracker.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'

    # reinitialize Flask-SQLAlchemy with reconfigured Flask app
    tracker.db.init_app(tracker.app)
    
    with tracker.app.app_context():
        tracker.db.create_all()

        tracker.db.session.add_all([
            tracker.Event(**event),
            tracker.Reader(**start),
            tracker.Reader(**finish),
            tracker.Athlete(**john),
            tracker.Athlete(**jane),
            tracker.Capture(**capture)])

        tracker.db.session.commit()
        tracker.db.session.remove()

    return Client(
        tracker.app.test_client(),
        tracker.socketio.test_client(tracker.app))


def test_all_athletes(client):
    response = client.app.get('/athletes')
    athletes = json.loads(response.data)
    assert john in athletes
    assert jane in athletes


def test_all_readers(client):
    response = client.app.get('/readers')
    readers = json.loads(response.data)
    assert start in readers
    assert finish in readers


def test_all_captures(client):
    response = client.app.get('/captures')
    captures = json.loads(response.data)
    assert len(captures) == 1
    assert captures[0]['athlete'] == john
    assert captures[0]['reader_id'] == capture['reader_id']


def test_create_capture_auth(client):
    response = client.app.post('/captures')
    assert response.status_code == 401


def test_create_capture(client, mocker):
    mocker.patch('tracker.socketio.emit')
    
    headers = Headers()
    headers.add('Content-Type', 'application/json')
    headers.add('Authorization', 'Basic ' + make_auth())

    data = json.dumps({'athlete_id': 2, 'reader_id': 1, 'timestamp': iso})

    response = client.app.post('/captures', data=data, headers=headers)
    assert response.status_code == 202 

    result = json.loads(response.data)
    assert 'athlete' in result
    assert result['athlete'] == jane
    assert tracker.socketio.emit.called_once_with(result)


def test_handle_connect(client):
    response = client.socketio.get_received()
    assert response[0]['name'] == 'readers'
    assert start in response[0]['args'][0]
    assert finish in response[0]['args'][0]
    assert response[1]['name'] == 'captures'
    assert 'athlete' in response[1]['args'][0][0]
    assert response[1]['args'][0][0]['athlete'] == john
    assert response[1]['args'][0][0]['id'] == capture['id']
    assert response[1]['args'][0][0]['reader_id'] == capture['reader_id']
    assert parse(response[1]['args'][0][0]['timestamp']) == now