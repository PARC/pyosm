import pyosm.model
from pyosm.parsing import iter_osm_file
import sys
import unicodecsv
import gzip
import re

n = 0
nodes = 0
nodes_buffer = []
ways = 0
ways_buffer = []
relations = 0
relations_buffer = []
changesets = 0
changesets_buffer = []

size_of_buffer = 1000
size_of_slice = 1000000

changesets_gz = gzip.GzipFile('changesets.csv.%05d.gz' % (ways / size_of_slice), 'w')
changesets_csv = unicodecsv.DictWriter(changesets_gz, ['id', 'created_at', 'closed_at', 'user', 'uid', 'tags', 'bbox'])
nodes_gz = gzip.GzipFile('nodes.csv.%05d.gz' % (nodes / size_of_slice), 'w')
nodes_csv = unicodecsv.DictWriter(nodes_gz, ['id', 'version', 'changeset', 'user', 'uid', 'visible', 'timestamp', 'tags', 'loc'])
ways_gz = gzip.GzipFile('ways.csv.%05d.gz' % (ways / size_of_slice), 'w')
ways_csv = unicodecsv.DictWriter(ways_gz, ['id', 'version', 'changeset', 'user', 'uid', 'visible', 'timestamp', 'tags', 'nds', 'line'])
relations_gz = gzip.GzipFile('relations.csv.%05d.gz' % (relations / size_of_slice), 'w')
relations_csv = unicodecsv.DictWriter(relations_gz, ['id', 'version', 'changeset', 'user', 'uid', 'visible', 'timestamp', 'tags', 'members'])

changesets_csv.writeheader()
nodes_csv.writeheader()
ways_csv.writeheader()
relations_csv.writeheader()

sys.stdout.write('%8d changesets, %10d nodes, %8d ways, %5d relations' % (changesets, nodes, ways, relations))
for p in iter_osm_file(open(sys.argv[1], 'r'), parse_timestamps=False):

    if type(p) == pyosm.model.Node:
        data = {
            'id': p.id,
            'version': p.version,
            'changeset': p.changeset,
            'timestamp': p.timestamp,
            'user': p.user,
            'uid': p.uid,
            'tags': ','.join(['"%s"=>"%s"' % (re.escape(tag.key), re.escape(tag.value)) for tag in p.tags])
        }
        if p.lat:
            data['loc'] = '%0.7f, %0.7f' % (p.lon, p.lat)
        nodes_buffer.append(data)
        nodes += 1

        if nodes % size_of_buffer == 0:
            nodes_csv.writerows(nodes_buffer)
            nodes_buffer = []

        if nodes % size_of_slice == 0:
            nodes_gz.close()
            nodes_gz = gzip.GzipFile('nodes.csv.%05d.gz' % (nodes / size_of_slice), 'w')
            nodes_csv = unicodecsv.DictWriter(nodes_gz, ['id', 'version', 'changeset', 'user', 'uid', 'visible', 'timestamp', 'tags', 'loc'])

    elif type(p) == pyosm.model.Way:
        data = {
            'id': p.id,
            'version': p.version,
            'changeset': p.changeset,
            'timestamp': p.timestamp,
            'user': p.user,
            'uid': p.uid,
            'tags': ','.join(['"%s"=>"%s"' % (re.escape(tag.key), re.escape(tag.value)) for tag in p.tags]),
            'nds': p.nds
        }
        ways_buffer.append(data)
        ways += 1

        if ways % size_of_buffer == 0:
            ways_csv.writerows(ways_buffer)
            ways_buffer = []

        if ways % size_of_slice == 0:
            ways_gz.close()
            ways_gz = gzip.GzipFile('ways.csv.%05d.gz' % (ways / size_of_slice), 'w')
            ways_csv = unicodecsv.DictWriter(ways_gz, ['id', 'version', 'changeset', 'user', 'uid', 'visible', 'timestamp', 'tags', 'nds', 'line'])

    elif type(p) == pyosm.model.Relation:
        data = {
            'id': p.id,
            'version': p.version,
            'changeset': p.changeset,
            'timestamp': p.timestamp,
            'user': p.user,
            'uid': p.uid,
            'tags': ','.join(['"%s"=>"%s"' % (re.escape(tag.key), re.escape(tag.value)) for tag in p.tags]),
            'members': '[%s]' % (','.join(['["%s","%s","%s"]' % (r.type, r.ref, r.role) for r in p.members]))
        }
        relations_buffer.apend(data)
        relations += 1

        if relations % size_of_buffer == 0:
            relations_csv.writerows(relations_buffer)
            relations_buffer = []

        if relations % size_of_slice == 0:
            relations_gz.close()
            relations_gz = gzip.GzipFile('relations.csv.%05d.gz' % (relations / size_of_slice), 'w')
            relations_csv = unicodecsv.DictWriter(relations_gz, ['id', 'version', 'changeset', 'user', 'uid', 'visible', 'timestamp', 'tags', 'members'])

    elif type(p) == pyosm.model.Changeset:
        data = {
            'id': p.id,
            'created_at': p.created_at,
            'closed_at': p.closed_at,
            'user': p.user,
            'uid': p.uid,
            'tags': ','.join(['"%s"=>"%s"' % (re.escape(tag.key), re.escape(tag.value)) for tag in p.tags]),
        }
        if p.min_lon:
            data['bbox'] = '%0.7f, %0.7f, %0.7f, %0.7f' % (p.min_lon, p.max_lat, p.max_lon, p.min_lat)

        changesets_buffer.append(data)
        changesets += 1

        if changesets % size_of_buffer == 0:
            changesets_csv.writerows(changesets_buffer)
            changesets_buffer = []

        if changesets % size_of_slice == 0:
            changesets_gz.close()
            changesets_gz = gzip.GzipFile('changesets.csv.%05d.gz' % (changesets / size_of_slice), 'w')
            changesets_csv = unicodecsv.DictWriter(changesets_gz, ['id', 'created_at', 'closed_at', 'user', 'uid', 'tags', 'bbox'])

    data = None
    n += 1

    if n % size_of_buffer == 0:
        sys.stdout.write('\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b')
        sys.stdout.write('%8d changesets, %10d nodes, %8d ways, %5d relations' % (changesets, nodes, ways, relations))
        sys.stdout.flush()

changesets_csv.writerows(changesets_buffer)
changesets_gz.close()
changesets_buffer = []
nodes_csv.writerows(nodes_buffer)
nodes_gz.close()
nodes_buffer = []
ways_csv.writerows(ways_buffer)
ways_gz.close()
ways_buffer = []
relations_csv.writerows(relations_buffer)
relations_gz.close()
relations_buffer = []


sys.stdout.write('\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b')
sys.stdout.write('%10d nodes, %8d ways, %5d relations\n' % (nodes, ways, relations))
sys.stdout.write('%8d changesets, %10d nodes, %8d ways, %5d relations' % (changesets, nodes, ways, relations))
sys.stdout.flush()
