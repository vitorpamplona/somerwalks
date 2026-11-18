"""The faint OpenStreetMap base map shared by the data pages: streets (major, minor, paths), commuter rail, parks and
green land, water, street-name anchors and building footprints, fetched through Overpass, simplified and packed in
whole map metres. Used by analysis/transit-trends/build.py (the housing pipeline map) and analysis/bus-trips/build.py
(the "Where bus riders go" map). Python standard library only. © OpenStreetMap contributors, ODbL: every page that
draws it credits them on the map and in its sources."""
import json, math, os, re, sys, urllib.parse, urllib.request
from collections import defaultdict

OVERPASS = ['https://overpass-api.de/api/interpreter', 'https://maps.mail.ru/osm/tools/overpass/api/interpreter',
            'https://overpass.kumi.systems/api/interpreter']             # servers come and go: tried in turn
ROAD = {'motorway': 'M', 'trunk': 'M', 'primary': 'M', 'secondary': 'M', 'motorway_link': 'M', 'trunk_link': 'M',
        'primary_link': 'M', 'secondary_link': 'M', 'tertiary': 'm', 'tertiary_link': 'm', 'unclassified': 'm',
        'residential': 'm', 'living_street': 'm', 'pedestrian': 'p', 'cycleway': 'p', 'path': 'p', 'footway': 'p', 'track': 'p'}
GREEN = {('leisure', 'park'), ('leisure', 'playground'), ('leisure', 'pitch'), ('leisure', 'garden'), ('leisure', 'recreation_ground'),
         ('leisure', 'nature_reserve'), ('landuse', 'cemetery'), ('landuse', 'grass'), ('landuse', 'recreation_ground'),
         ('landuse', 'village_green'), ('landuse', 'meadow'), ('landuse', 'forest'), ('natural', 'wood'), ('natural', 'wetland')}
OSM_BASE = ('('
            'way["highway"~"^(' + '|'.join(ROAD) + ')$"]["footway"!~"sidewalk|crossing"](BBOX);'
            'way["railway"="rail"](BBOX);'
            'way["leisure"~"^(park|playground|pitch|garden|recreation_ground|nature_reserve)$"](BBOX);'
            'relation["leisure"~"^(park|nature_reserve)$"](BBOX);'
            'way["landuse"~"^(cemetery|grass|recreation_ground|village_green|meadow|forest)$"](BBOX);'
            'way["natural"~"^(water|wood|wetland)$"](BBOX);'
            'relation["natural"="water"](BBOX);'
            'way["waterway"="riverbank"](BBOX);'
            ');')
OSM_BUILDINGS = 'way["building"](BBOX);'


def overpass_tiles(path, box, n, body, ua):
    """OpenStreetMap features in `box` (lon0, lat0, lon1, lat1), fetched as n × n tiles (big queries time out), cached
    whole at `path`. Delete it to pick up new OpenStreetMap edits."""
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    els = {}
    for i in range(n):
        for j in range(n):
            x0, x1 = box[0] + (box[2] - box[0]) * i / n, box[0] + (box[2] - box[0]) * (i + 1) / n
            y0, y1 = box[1] + (box[3] - box[1]) * j / n, box[1] + (box[3] - box[1]) * (j + 1) / n
            q = '[out:json][timeout:300];' + body.replace('BBOX', f'{y0:.4f},{x0:.4f},{y1:.4f},{x1:.4f}') + 'out geom;'
            for attempt in range(8):
                url = OVERPASS[attempt % len(OVERPASS)]
                try:
                    req = urllib.request.Request(url, data=urllib.parse.urlencode({'data': q}).encode(), headers={'User-Agent': ua})
                    with urllib.request.urlopen(req, timeout=400) as r:
                        for e in json.loads(r.read())['elements']:
                            els[(e['type'], e['id'])] = e
                    break
                except Exception as e:  # noqa: BLE001 - busy servers answer 504 or reset; try the next
                    print(f'  overpass {url[:40]}… tile {i},{j}: {e}', file=sys.stderr)
            else:
                print(f'  OpenStreetMap: tile {i},{j} of {os.path.basename(path)} failed; the base map will have a hole', file=sys.stderr)
    out = list(els.values())
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        json.dump(out, f)
    return out


def simplify(pts, tol):
    """Douglas-Peucker on [x, y] in metres."""
    if len(pts) < 3:
        return pts
    keep, stack = {0, len(pts) - 1}, [(0, len(pts) - 1)]
    while stack:
        a, b = stack.pop()
        (ax, ay), (bx, by) = pts[a], pts[b]
        L = math.hypot(bx - ax, by - ay)
        far, k = 0, None
        for i in range(a + 1, b):                      # a closed ring (a = b): distance to the point itself
            d = (abs((bx - ax) * (ay - pts[i][1]) - (ax - pts[i][0]) * (by - ay)) / L if L > 1e-6
                 else math.hypot(pts[i][0] - ax, pts[i][1] - ay))
            if d > far:
                far, k = d, i
        if k is not None and far > tol:
            keep.add(k)
            stack += [(a, k), (k, b)]
    return [pts[i] for i in sorted(keep)]


def packed(pts):
    """[x0, y0, dx1, dy1, …] in whole metres: deltas keep the JSON small."""
    out, px, py = [], 0, 0
    for x, y in pts:
        x, y = round(x), round(y)
        if out and x == px and y == py:
            continue
        out += [x - px, y - py] if out else [x, y]
        px, py = x, y
    return out


def short_street(n):
    for a, b in (('Street', 'St'), ('Avenue', 'Ave'), ('Road', 'Rd'), ('Place', 'Pl'), ('Terrace', 'Ter'), ('Highway', 'Hwy'),
                 ('Parkway', 'Pkwy'), ('Boulevard', 'Blvd'), ('Square', 'Sq'), ('Court', 'Ct'), ('Drive', 'Dr'), ('Lane', 'Ln')):
        n = re.sub(rf'\b{a}\b', b, n)
    return n


def layers(els, xy, near_box, names_everywhere=False):
    """Streets in three classes, rail, green land, water and street-name anchors from the Overpass elements, in the
    page's map metres (`xy(lon, lat)` → [x, y], y down). Paths only within `near_box` (lon0, lat0, lon1, lat1); street
    names within it too, unless `names_everywhere`. Names: the middle of each named way 120 m or longer, one per 300 m."""
    line = lambda g: [xy(p['lon'], p['lat']) for p in g]
    rings = lambda e: ([line(e['geometry'])] if e['type'] == 'way' and e.get('geometry') else
                       [line(m['geometry']) for m in e.get('members', []) if m.get('role') == 'outer' and m.get('geometry')])
    roads, rail, green, water, named = {'M': [], 'm': [], 'p': []}, [], [], [], defaultdict(list)
    near = lambda g: any(near_box[0] <= p['lon'] <= near_box[2] and near_box[1] <= p['lat'] <= near_box[3] for p in g)
    for e in els:
        tg = e.get('tags', {})
        if e['type'] == 'way' and tg.get('highway') in ROAD and e.get('geometry'):
            c = ROAD[tg['highway']]
            if c == 'p' and (tg['highway'] == 'track' or not near(e['geometry'])):
                continue                               # paths only in and by Somerville
            pts = simplify(line(e['geometry']), 1.5 if c != 'p' else 3)
            roads[c].append(packed(pts))
            if tg.get('name') and c != 'p' and (names_everywhere or near(e['geometry'])):
                named[short_street(tg['name'])].append(pts)
        elif e['type'] == 'way' and tg.get('railway') == 'rail' and e.get('geometry'):
            rail.append(packed(simplify(line(e['geometry']), 2)))
        elif tg.get('natural') == 'water' or tg.get('waterway') == 'riverbank':
            water += [packed(simplify(r, 2)) for r in rings(e) if len(r) > 3]
        elif any((k, v) in GREEN for k, v in tg.items()):
            green += [packed(simplify(r, 1.5)) for r in rings(e) if len(r) > 3]
    names = []
    for nm, ways in named.items():
        got = []
        for pts in sorted(ways, key=lambda p: -sum(math.dist(a, b) for a, b in zip(p, p[1:]))):
            L = sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))
            if L < 120:
                break
            half, run, x, y, ang = L / 2, 0, pts[0][0], pts[0][1], 0
            for a, b in zip(pts, pts[1:]):
                d = math.dist(a, b)
                if run + d >= half:
                    f = (half - run) / d if d else 0
                    x, y = a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f
                    ang = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))
                    break
                run += d
            ang = ang - 180 if ang > 90 else ang + 180 if ang < -90 else ang      # text reads left to right
            if all(math.hypot(x - gx, y - gy) > 300 for gx, gy in got):
                got.append((x, y))
                names.append([nm, round(x), round(y), round(ang)])
    return {'roads': roads, 'rail': rail, 'green': green, 'water': water, 'names': names}


def buildings(els, xy, cell=400):
    """Building footprints grouped by `cell` m square, so a page draws only what's in view."""
    line = lambda g: [xy(p['lon'], p['lat']) for p in g]
    grid = defaultdict(list)
    for e in els:
        if e['type'] != 'way' or not e.get('geometry') or len(e['geometry']) < 4:
            continue
        pts = simplify(line(e['geometry']), 0.7)
        if len(pts) < 4:
            continue
        cx, cy = sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)
        grid[f'{int(cx // cell)},{int(cy // cell)}'].append(packed(pts))
    return {'cell': cell, 'g': grid}


def write(path, obj):
    """Compact JSON beside the published page; returns its size in bytes."""
    blob = json.dumps(obj, separators=(',', ':'))
    with open(path, 'w') as f:
        f.write(blob)
    return len(blob)
