# Sports Day Time Tracking Backend

Sports day time tracking web server and time reader emulator. 

## Requirements

Python 3.5+.

## Installation

Navigate to project directory and create a new virtual environment

    python -m venv venv

or by using `pyvenv` (Python 3.5)
    
    pyvenv venv

_Note: when using Mac OSX and homebrew for Python installation, suitable Python executable will likely be named python3._

Activate virtual environment

    source venv/bin/activate

Install dependencies

    python setup.py install

_Note: installing dependencies might take couple of minutes._

## Running Web Server

Navigate to project directory and activate virtual environment.

Export flask environment variable 

    export FLASK_APP=tracker

Initialize the database

    flask initdb

_Note: sqlite database tracker.db will be created in project directory._

Seed database with initial data

    flask seed

_Note: this command creates new event, time readers and 100 random athletes and can be re-issued at any time to reset database state._

Run the application

    flask run

HTTP API can be explored via Swagger UI on [http://localhost:5000/swagger/index.html](http://localhost:5000/swagger/index.html). 

SocketIO server (both WebSockets and polling) is accessible via [//localhost:5000/]() and provides single endpoint which emits `readers` event with a list of time readers and `captures` event with a list of captures. Both events will be emitted upon connect with most recent data. `captures` will be emitted for ongoing sports day to all connected clients upon server receiving new data.

## Running Time Reader Emulator

With server running, navigate to project directory, activate virtual environment and execute

    python emulator.py

_Note: emulator takes additional parameters `mu` which is random average interval between athlete reaching readers and `sigma` which is standard deviation for the random values. Defaults to 40 seconds between timepoints with a standard deviation of 20 seconds.
It is recommended to use high standard deviation value for interesting "race".
Emulator can be ran once for sporting event (no pause/continue). When cancelling by keyboard interrupt, it is recommended to re-seed the database._

Default command parameterized

    python emulator.py --mu=40 --sigma=20

## Running Tests

Navigate to project directory, activate virtual environment and execute

    python setup.py test 