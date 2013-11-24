import model
import datetime
import urllib2
import StringIO
import gzip
import time
import os.path
from lxml import etree

def isoToDatetime(s):
    """Parse a ISO8601-formatted string to a Python datetime."""
    if s is None:
        return s
    else:
        return datetime.datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ")

def maybeInt(s):
    return int(s) if s is not None else s

def maybeFloat(s):
    return float(s) if s is not None else s

def maybeBool(s):
    if s is not None:
        if s == 'true':
            return True
        else:
            return False
    else:
        return s

def readState(state_file, sep='='):
    state = {}

    for line in state_file:
        if line.startswith('---'):
            continue
        if line[0] == '#':
            continue
        (k, v) = line.split(sep)
        state[k] = v.strip().replace("\\:", ":")

    return state

def iter_changeset_stream(start_sqn=None, base_url='http://planet.openstreetmap.org/replication/changesets', expected_interval=60, parse_timestamps=True, state_dir=None):
    """Start processing an OSM changeset stream and yield one (action, primitive) tuple
    at a time to the caller."""

    # This is a lot like the other osm_stream except there's no
    # state file for each of the diffs, so just push ahead until
    # we run into a 404.

    # If the user specifies a state_dir, read the state from the statefile there
    if state_dir:
        if not os.path.exists(state_dir):
            raise Exception('Specified state_dir "%s" doesn\'t exist.' % state_dir)

        if os.path.exists('%s/state.yaml' % state_dir):
            with open('%s/state.yaml' % state_dir) as f:
                state = readState(f, ': ')
                start_sqn = state['sequence']

    # If no start_sqn, assume to start from the most recent changeset file
    if not start_sqn:
        u = urllib2.urlopen('%s/state.yaml' % base_url)
        state = readState(u, ': ')
        sequenceNumber = int(state['sequence'])
    else:
        sequenceNumber = int(start_sqn)

    interval_fudge = 0.0
    while True:
        sqnStr = str(sequenceNumber).zfill(9)
        url = '%s/%s/%s/%s.osm.gz' % (base_url, sqnStr[0:3], sqnStr[3:6], sqnStr[6:9])

        delay = 1.0
        while True:
            try:
                content = urllib2.urlopen(url)
                content = StringIO.StringIO(content.read())
                gzipper = gzip.GzipFile(fileobj=content)
                interval_fudge -= (interval_fudge / 2.0)
                break
            except urllib2.HTTPError, e:
                if e.code == 404:
                    time.sleep(delay)
                    delay = min(delay * 2, 13)
                    interval_fudge += delay

        obj = None
        for event, elem in etree.iterparse(gzipper, events=('start', 'end')):
            if event == 'start':
                if elem.tag == 'changeset':
                    obj = model.Changeset(
                        int(elem.attrib['id']),
                        isoToDatetime(elem.attrib.get('created_at')) if parse_timestamps else elem.attrib.get('created_at'),
                        isoToDatetime(elem.attrib.get('closed_at')) if parse_timestamps else elem.attrib.get('closed_at'),
                        maybeBool(elem.attrib['open']),
                        maybeFloat(elem.get('min_lat')),
                        maybeFloat(elem.get('max_lat')),
                        maybeFloat(elem.get('min_lon')),
                        maybeFloat(elem.get('max_lon')),
                        elem.attrib.get('user'),
                        maybeInt(elem.attrib.get('uid')),
                        []
                    )
                elif elem.tag == 'tag':
                    obj.tags.append(
                        model.Tag(
                            elem.attrib['k'],
                            elem.attrib['v']
                        )
                    )
            elif event == 'end':
                if elem.tag == 'changeset':
                    yield obj
                    obj = None

        yield model.Finished(sequenceNumber, None)

        sequenceNumber += 1

        if state_dir:
            with open('%s/state.yaml' % state_dir, 'w') as f:
                f.write('sequence: %d' % sequenceNumber)

def iter_osm_change_file(f, parse_timestamps=True):
    action = None
    obj = None
    for event, elem in etree.iterparse(f, events=('start', 'end')):
        if event == 'start':
            if elem.tag == 'node':
                obj = model.Node(
                    int(elem.attrib['id']),
                    int(elem.attrib['version']),
                    int(elem.attrib['changeset']),
                    elem.attrib.get('user'),
                    maybeInt(elem.attrib.get('uid')),
                    maybeBool(elem.attrib.get('visible')),
                    isoToDatetime(elem.attrib.get('timestamp')) if parse_timestamps else elem.attrib.get('timestamp'),
                    maybeFloat(elem.attrib.get('lat')),
                    maybeFloat(elem.attrib.get('lon')),
                    []
                )
            elif elem.tag == 'way':
                obj = model.Way(
                    int(elem.attrib['id']),
                    int(elem.attrib['version']),
                    int(elem.attrib['changeset']),
                    elem.attrib.get('user'),
                    maybeInt(elem.attrib.get('uid')),
                    maybeBool(elem.attrib.get('visible')),
                    isoToDatetime(elem.attrib.get('timestamp')) if parse_timestamps else elem.attrib.get('timestamp'),
                    [],
                    []
                )
            elif elem.tag == 'tag':
                obj.tags.append(
                    model.Tag(
                        elem.attrib['k'],
                        elem.attrib['v']
                    )
                )
            elif elem.tag == 'nd':
                obj.nds.append(int(elem.attrib['ref']))
            elif elem.tag == 'relation':
                obj = model.Relation(
                    int(elem.attrib['id']),
                    int(elem.attrib['version']),
                    int(elem.attrib['changeset']),
                    elem.attrib.get('user'),
                    maybeInt(elem.attrib.get('uid')),
                    maybeBool(elem.attrib.get('visible')),
                    isoToDatetime(elem.attrib.get('timestamp')) if parse_timestamps else elem.attrib.get('timestamp'),
                    [],
                    []
                )
            elif elem.tag == 'member':
                obj.members.append(
                    model.Member(
                        elem.attrib['type'],
                        int(elem.attrib['ref']),
                        elem.attrib['role']
                    )
                )
            elif elem.tag in ('create', 'modify', 'delete'):
                action = elem.tag
        elif event == 'end':
            if elem.tag == 'node':
                yield (action, obj)
                obj = None
            elif elem.tag == 'way':
                yield (action, obj)
                obj = None
            elif elem.tag == 'relation':
                yield (action, obj)
                obj = None
            elif elem.tag in ('create', 'modify', 'delete'):
                action = None

        elem.clear()
        while elem.getprevious() is not None:
            del elem.getparent()[0]

def iter_realtime_osm_stream(start_sqn=None, base_url='http://planet.openstreetmap.org/replication/streaming', parse_timestamps=True, state_dir=None):
    # If the user specifies a state_dir, read the state from the statefile there
    if state_dir:
        if not os.path.exists(state_dir):
            raise Exception('Specified state_dir "%s" doesn\'t exist.' % state_dir)

        if os.path.exists('%s/realtime_state.txt' % state_dir):
            with open('%s/realtime_state.txt' % state_dir) as f:
                state = readState(f)
                start_sqn = state['sequenceNumber']

    url = '%s/replicationData/%s/tail' % (base_url, start_sqn)
    content = urllib2.urlopen(url)

    while True:
        # Format is described here http://wiki.openstreetmap.org/wiki/Osmosis/Replication#Streaming_Replication_Wire_Protocol
        state_size = int(content.readline().strip())
        state_data = content.read(state_size)
        state = readState(state_data.strip().split('\n'))

        diff_size = int(content.readline().strip())
        diff_data = gzip.GzipFile(fileobj=StringIO.StringIO(content.read(diff_size)))

        for a in iter_osm_change_file(diff_data, parse_timestamps):
            yield a

        stateTs = datetime.datetime.strptime(state['timestamp'], "%Y-%m-%dT%H:%M:%SZ")
        yield (None, model.Finished(state['sequenceNumber'], stateTs))

        if state_dir:
            with open('%s/realtime_state.txt' % state_dir, 'w') as f:
                f.write(state_data)

def iter_osm_stream(start_sqn=None, base_url='http://planet.openstreetmap.org/replication/minute', expected_interval=60, parse_timestamps=True, state_dir=None):
    """Start processing an OSM diff stream and yield one changeset at a time to
    the caller."""

    # If the user specifies a state_dir, read the state from the statefile there
    if state_dir:
        if not os.path.exists(state_dir):
            raise Exception('Specified state_dir "%s" doesn\'t exist.' % state_dir)

        if os.path.exists('%s/state.txt' % state_dir):
            with open('%s/state.txt' % state_dir) as f:
                state = readState(f)
                start_sqn = state['sequenceNumber']

    # If no start_sqn, assume to start from the most recent diff
    if not start_sqn:
        u = urllib2.urlopen('%s/state.txt' % base_url)
        state = readState(u)
    else:
        sqnStr = str(start_sqn).zfill(9)
        u = urllib2.urlopen('%s/%s/%s/%s.state.txt' % (base_url, sqnStr[0:3], sqnStr[3:6], sqnStr[6:9]))
        state = readState(u)

    interval_fudge = 0.0

    while True:
        sqnStr = state['sequenceNumber'].zfill(9)
        url = '%s/%s/%s/%s.osc.gz' % (base_url, sqnStr[0:3], sqnStr[3:6], sqnStr[6:9])
        content = urllib2.urlopen(url)
        content = StringIO.StringIO(content.read())
        gzipper = gzip.GzipFile(fileobj=content)

        for a in iter_osm_change_file(gzipper, parse_timestamps):
            yield a

        # After parsing the OSC, check to see how much time is remaining
        stateTs = datetime.datetime.strptime(state['timestamp'], "%Y-%m-%dT%H:%M:%SZ")
        yield (None, model.Finished(state['sequenceNumber'], stateTs))

        nextTs = stateTs + datetime.timedelta(seconds=expected_interval + interval_fudge)
        if datetime.datetime.utcnow() < nextTs:
            timeToSleep = (nextTs - datetime.datetime.utcnow()).total_seconds()
        else:
            timeToSleep = 0.0
        time.sleep(timeToSleep)

        # Then try to fetch the next state file
        sqnStr = str(int(state['sequenceNumber']) + 1).zfill(9)
        url = '%s/%s/%s/%s.state.txt' % (base_url, sqnStr[0:3], sqnStr[3:6], sqnStr[6:9])
        delay = 1.0
        while True:
            try:
                u = urllib2.urlopen(url)
                interval_fudge -= (interval_fudge / 2.0)
                break
            except urllib2.HTTPError, e:
                if e.code == 404:
                    time.sleep(delay)
                    delay = min(delay * 2, 13)
                    interval_fudge += delay

        if state_dir:
            with open('%s/state.txt' % state_dir, 'w') as f:
                f.write(u.read())
            with open('%s/state.txt' % state_dir, 'r') as f:
                state = readState(f)
        else:
            state = readState(u)

def iter_osm_file(f, parse_timestamps=True):
    """Parse a file-like containing OSM XML and yield one OSM primitive at a time
    to the caller."""

    obj = None
    for event, elem in etree.iterparse(f, events=('start', 'end')):
        if event == 'start':
            if elem.tag == 'node':
                obj = model.Node(
                    int(elem.attrib['id']),
                    maybeInt(elem.get('version')),
                    maybeInt(elem.get('changeset')),
                    elem.attrib.get('user'),
                    maybeInt(elem.attrib.get('uid')),
                    maybeBool(elem.attrib.get('visible')),
                    isoToDatetime(elem.attrib.get('timestamp')) if parse_timestamps else elem.attrib.get('timestamp'),
                    maybeFloat(elem.get('lat')),
                    maybeFloat(elem.get('lon')),
                    []
                )
            elif elem.tag == 'way':
                obj = model.Way(
                    int(elem.attrib['id']),
                    maybeInt(elem.get('version')),
                    maybeInt(elem.get('changeset')),
                    elem.attrib.get('user'),
                    maybeInt(elem.attrib.get('uid')),
                    maybeBool(elem.attrib.get('visible')),
                    isoToDatetime(elem.attrib.get('timestamp')) if parse_timestamps else elem.attrib.get('timestamp'),
                    [],
                    []
                )
            elif elem.tag == 'tag':
                obj.tags.append(
                    model.Tag(
                        elem.attrib['k'],
                        elem.attrib['v']
                    )
                )
            elif elem.tag == 'nd':
                obj.nds.append(int(elem.attrib['ref']))
            elif elem.tag == 'relation':
                obj = model.Relation(
                    int(elem.attrib['id']),
                    maybeInt(elem.get('version')),
                    maybeInt(elem.get('changeset')),
                    elem.attrib.get('user'),
                    maybeInt(elem.attrib.get('uid')),
                    maybeBool(elem.attrib.get('visible')),
                    isoToDatetime(elem.attrib.get('timestamp')) if parse_timestamps else elem.attrib.get('timestamp'),
                    [],
                    []
                )
            elif elem.tag == 'member':
                obj.members.append(
                    model.Member(
                        elem.attrib['type'],
                        int(elem.attrib['ref']),
                        elem.attrib['role']
                    )
                )
            elif elem.tag == 'changeset':
                obj = model.Changeset(
                    int(elem.attrib['id']),
                    isoToDatetime(elem.attrib.get('created_at')) if parse_timestamps else elem.attrib.get('created_at'),
                    isoToDatetime(elem.attrib.get('closed_at')) if parse_timestamps else elem.attrib.get('closed_at'),
                    maybeBool(elem.attrib['open']),
                    maybeFloat(elem.get('min_lat')),
                    maybeFloat(elem.get('max_lat')),
                    maybeFloat(elem.get('min_lon')),
                    maybeFloat(elem.get('max_lon')),
                    elem.attrib.get('user'),
                    maybeInt(elem.attrib.get('uid')),
                    []
                )
        elif event == 'end':
            if elem.tag == 'node':
                yield obj
                obj = None
            elif elem.tag == 'way':
                yield obj
                obj = None
            elif elem.tag == 'relation':
                yield obj
                obj = None
            elif elem.tag == 'changeset':
                yield obj
                obj = None

        elem.clear()
        while elem.getprevious() is not None:
            del elem.getparent()[0]

def parse_osm_file(f, parse_timestamps=True):
    """Parse a file-like containing OSM XML into memory and return an object with
    the nodes, ways, and relations it contains. """

    nodes = []
    ways = []
    relations = []

    for p in iter_osm_file(f, parse_timestamps):

        if type(p) == model.Node:
            nodes.append(p)
        elif type(p) == model.Way:
            ways.append(p)
        elif type(p) == model.Relation:
            relations.append(p)

    return (nodes, ways, relations)