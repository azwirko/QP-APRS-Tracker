import re
import sys


kmlfile = sys.argv[1]

coord = 0
n = 1

with open('county.geojson', 'w') as fo:
    fo.write('{"type": "FeatureCollection", "features": [\n')

with open(kmlfile, 'r') as fi:
    for line in fi:
        match = re.search('<name>([A-Za-z0-9=\s]+)</name>', line)
        if match:
            name = match.group(1)

            match = re.search('(\w+)=(\w+)', name)
            county = match.group(1)
            abbrev = match.group(2)

            with open('county.geojson', 'a') as fo:
                if n != 1:
                    fo.write(',\n')

                fo.write('    {"type": "Feature",\n'
                         '      "id": "' + str(n) + '",\n'
                         '      "properties": {"name": "' + str(abbrev) + "=" + str(county) + '"},\n'
                         '      "geometry": {\n'
                         '        "type": "Polygon",\n')

            first = 0
            n = n + 1

        if re.search('<coordinates>', line):
            coord = 1
            with open('county.geojson', 'a') as fo:
                fo.write('          "coordinates": [[\n')

            continue

        if coord == 1:
            match = re.search('([\.\-0-9]+)\s*,\s*([\.\-0-9]+)', line)
            if match:
                lat = match.group(1)
                lon = match.group(2)

                if first == 1:
                    with open('county.geojson', 'a') as fo:
                        fo.write(',\n')

                with open('county.geojson', 'a') as fo:
                    fo.write('            [' + str(lat) + ', ' + str(lon) + ']')

            first = 1

        if re.search('</coordinates>', line):
            coord = 0

            with open('county.geojson', 'a') as fo:
                fo.write(']]}}')

with open('county.geojson', 'a') as fo:
    fo.write(']}\n')
