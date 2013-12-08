"""Stream both changesets and objects to a database."""

import Queue
from threading import Thread, Event
from pyosm.parsing import iter_changeset_stream, iter_osm_stream
from pyosm.model import Changeset, Node, Way, Relation, Finished
import signal
import time
import psycopg2
import psycopg2.extras
import psycopg2.tz

"""
-- Table: osm.changesets

DROP TABLE osm.changesets;

CREATE TABLE osm.changesets
(
  id integer NOT NULL,
  uid integer,
  created_at timestamp with time zone NOT NULL,
  closed_at timestamp with time zone,
  tags hstore,
  bbox box,
  CONSTRAINT changesets_pkey PRIMARY KEY (id)
)
WITH (
  OIDS=FALSE
);
ALTER TABLE osm.changesets
  OWNER TO iandees;

-- Table: osm.nodes

DROP TABLE osm.nodes;

CREATE TABLE osm.nodes
(
  id bigint NOT NULL,
  version integer NOT NULL,
  visible boolean NOT NULL,
  changeset_id integer NOT NULL,
  "timestamp" timestamp with time zone NOT NULL,
  uid integer,
  tags hstore,
  loc point,
  CONSTRAINT nodes_pkey PRIMARY KEY (id, version)
)
WITH (
  OIDS=FALSE
);
ALTER TABLE osm.nodes
  OWNER TO iandees;

-- Table: osm.ways

DROP TABLE osm.ways;

CREATE TABLE osm.ways
(
  id bigint NOT NULL,
  version integer NOT NULL,
  visible boolean NOT NULL,
  changeset_id integer NOT NULL,
  "timestamp" timestamp with time zone NOT NULL,
  uid integer,
  tags hstore,
  nds bigint[],
  CONSTRAINT ways_pkey PRIMARY KEY (id, version)
)
WITH (
  OIDS=FALSE
);
ALTER TABLE osm.ways
  OWNER TO iandees;

-- Table: osm.relations

DROP TABLE osm.relations;

CREATE TABLE osm.relations
(
  id bigint NOT NULL,
  version integer NOT NULL,
  visible boolean NOT NULL,
  changeset_id integer NOT NULL,
  "timestamp" timestamp with time zone NOT NULL,
  uid integer,
  tags hstore,
  members character varying[],
  CONSTRAINT relations_pkey PRIMARY KEY (id, version)
)
WITH (
  OIDS=FALSE
);
ALTER TABLE osm.relations
  OWNER TO iandees;

-- Table: osm.users

DROP TABLE osm.users;

CREATE TABLE osm.users
(
  id integer NOT NULL,
  display_name character varying(255) NOT NULL,
  "timestamp" timestamp with time zone NOT NULL,
  CONSTRAINT users_pkey PRIMARY KEY (id, display_name)
)
WITH (
  OIDS=FALSE
);
ALTER TABLE osm.users
  OWNER TO iandees;

"""

def database_write(q, lock):
    print "Database write starting"
    conn = psycopg2.connect(database='iandees', user='iandees', host='localhost')
    conn.autocommit = True
    psycopg2.extras.register_hstore(conn)
    cur = conn.cursor()
    cur.execute("SET TIME ZONE 'UTC';")

    # Wait til we get Finishes for both changeset and object streams before
    # closing the database writer
    finishes_received = 0

    nodes = 0
    ways = 0
    relations = 0
    changesets = 0
    users = 0

    user_buffer = {}
    nodes_buffer = []
    ways_buffer = []
    relations_buffer = []

    while True:
        thing = q.get()

        if lock.isSet():
            if type(thing) == Finished:
                print "Received finish"
                finishes_received += 1

            if finishes_received >= 2:
                break

        if type(thing) in (Node, Way, Relation, Changeset):
            tags = dict([(t.key, t.value) for t in thing.tags])

            user_buffer[thing.uid] = thing.user

            if len(user_buffer) > 10:
                for (uid, uname) in user_buffer.iteritems():
                    cur.execute("SELECT * FROM osm.users WHERE id=%s and display_name=%s", [uid, uname])
                    existing = cur.fetchone()
                    if not existing:
                        cur.execute("INSERT INTO osm.users (id, display_name, timestamp) VALUES (%s, %s, NOW())", [uid, uname])
                        users += 1
                user_buffer = {}

        if type(thing) == Changeset:
            bbox = None
            if thing.min_lon is not None:
                bbox = "%0.7f, %0.7f, %0.7f, %0.7f" % (thing.min_lon, thing.min_lat, thing.max_lon, thing.max_lat)

            try:
                cur.execute("INSERT INTO osm.changesets (id, uid, created_at, closed_at, bbox, tags) VALUES (%s, %s, %s, %s, %s, %s)",
                    [thing.id, thing.uid, thing.created_at, thing.closed_at, bbox, tags])
            except psycopg2.IntegrityError:
                cur.execute("UPDATE osm.changesets SET uid=%s, created_at=%s, closed_at=%s, bbox=%s, tags=%s WHERE id=%s",
                    [thing.uid, thing.created_at, thing.closed_at, bbox, tags, thing.id])

            changesets += 1
        elif type(thing) == Node:
            loc = "%0.7f, %0.7f" % (thing.lon, thing.lat)

            nodes_buffer.append(cur.mogrify('(%s,%s,%s,%s,%s,%s,%s,%s)', [thing.id, thing.version, thing.visible, thing.changeset, thing.timestamp, thing.uid, tags, loc]))
            nodes += 1

            if nodes % 1000 == 0:
                args_str = ','.join(nodes_buffer)
                cur.execute("INSERT INTO osm.nodes (id, version, visible, changeset_id, timestamp, uid, tags, loc) VALUES " + args_str)
                nodes_buffer = []

        elif type(thing) == Way:
            ways_buffer.append(cur.mogrify('(%s,%s,%s,%s,%s,%s,%s,%s)', [thing.id, thing.version, thing.visible, thing.changeset, thing.timestamp, thing.uid, tags, thing.nds]))
            ways += 1

            if ways % 1000 == 0:
                args_str = ','.join(ways_buffer)
                cur.execute("INSERT INTO osm.ways (id, version, visible, changeset_id, timestamp, uid, tags, nds) VALUES " + args_str)
                ways_buffer = []

        elif type(thing) == Relation:
            members = [[m.type, str(m.ref), m.role] for m in thing.members]

            relations_buffer.append(cur.mogrify('(%s,%s,%s,%s,%s,%s,%s,%s)', [thing.id, thing.version, thing.visible, thing.changeset, thing.timestamp, thing.uid, tags, members]))
            relations += 1

            if relations % 1000 == 0:
                args_str = ','.join(relations_buffer)
                cur.execute("INSERT INTO osm.relations (id, version, visible, changeset_id, timestamp, uid, tags, members) VALUES " + args_str)
                relations_buffer = []

        if (changesets + nodes + ways + relations + users) % 1000 == 0:
            print "%10d changesets, %10d nodes, %10d ways, %5d relations, %5d users, %d queue" % (changesets, nodes, ways, relations, users, q.qsize())

    if nodes_buffer:
        args_str = ','.join(nodes_buffer)
        cur.execute("INSERT INTO osm.nodes (id, version, visible, changeset_id, timestamp, uid, tags, loc) VALUES " + args_str)
    if ways_buffer:
        args_str = ','.join(ways_buffer)
        cur.execute("INSERT INTO osm.ways (id, version, visible, changeset_id, timestamp, uid, tags, nds) VALUES " + args_str)
    if relations_buffer:
        args_str = ','.join(relations_buffer)
        cur.execute("INSERT INTO osm.relations (id, version, visible, changeset_id, timestamp, uid, tags, members) VALUES " + args_str)

    for (uid, uname) in user_buffer.iteritems():
        cur.execute("SELECT * FROM osm.users WHERE id=%s and display_name=%s", [uid, uname])
        existing = cur.fetchone()
        if not existing:
            cur.execute("INSERT INTO osm.users (id, display_name, timestamp) VALUES (%s, %s, NOW())", [uid, uname])
            users += 1
    user_buffer = {}

    print "%10d changesets, %10d nodes, %10d ways, %5d relations, %5d users, %d queue" % (changesets, nodes, ways, relations, users, q.qsize())

    print "Database finished"

def iterate_changesets(q, lock):
    print "Changesets starting"
    for changeset in iter_changeset_stream(state_dir='state'):
        if type(changeset) == Finished and stop.isSet():
            q.put(changeset)
            break
        q.put(changeset)
    print "Changesets finished"

def iterate_objects(q, lock):
    print "Objects starting"
    for (action, thing) in iter_osm_stream(state_dir='state'):
        if type(thing) == Finished:
            if stop.isSet():
                q.put(thing)
                break
        else:
            thing = thing._replace(visible=False if action == 'delete' else True)
        q.put(thing)
    print "Objects finished"

if __name__ == '__main__':
    print "Main starting"
    stop = Event()
    db_q = Queue.Queue()

    def shutdown_handler(signum, frame):
        print "Shutting down."
        stop.set()
    signal.signal(signal.SIGINT, shutdown_handler)

    d = Thread(target=database_write, args=(db_q, stop,))
    c = Thread(target=iterate_changesets, args=(db_q, stop,))
    o = Thread(target=iterate_objects, args=(db_q, stop,))

    d.start()
    c.start()
    o.start()

    while not stop.isSet():
        time.sleep(5)

    print "Main finished"
