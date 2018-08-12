import argparse
import asyncio
import functools
import json
import random
import requests
from datetime import datetime
from urllib.parse import urljoin


parser = argparse.ArgumentParser(description='Simulate reader work')
parser.add_argument('--url', default='http://127.0.0.1:5000')
parser.add_argument('--username', default='username', dest='username')
parser.add_argument('--password', default='password', dest='password')
parser.add_argument('--mu', default=40, type=int, dest='mu')
parser.add_argument('--sigma', default=20, type=int, dest='sigma')


async def sleep_and_post(athlete, reader, url, auth, sleep):
    await asyncio.sleep(sleep)
    
    timestamp = datetime.utcnow().isoformat()
    
    print('{}\t{}\t{}'.format(reader['name'], timestamp, athlete['name']))
    
    # build message
    data = {
        'athlete_id': athlete['id'],
        'reader_id': reader['id'],
        'timestamp': timestamp
    }
    
    # run_in_executor does not support kwargs
    request = functools.partial(requests.post, url, json=data, auth=auth)
    await asyncio.get_event_loop().run_in_executor(None, request)


if __name__ == '__main__':
    args = parser.parse_args()

    # fetch athletes list
    athletes_response = requests.get(urljoin(args.url, '/athletes'))
    readers_response = requests.get(urljoin(args.url, '/readers'))
    
    athletes = athletes_response.json()
    readers = sorted(readers_response.json(),
        key=lambda x: x['position'])
    
    # basic auth tuple for /captures endpoint
    auth = (args.username, args.password)

    # captures submit endpoint url
    url = urljoin(args.url, '/captures')

    # simulate 'running'
    tasks = []
    for athlete in athletes:
        sleep = 0
        for reader in readers:
            sleep += random.normalvariate(args.mu, args.sigma)
            future = sleep_and_post(athlete, reader, url, auth, sleep)
            tasks.append(asyncio.ensure_future(future))

    asyncio.get_event_loop().run_until_complete(asyncio.gather(*tasks))