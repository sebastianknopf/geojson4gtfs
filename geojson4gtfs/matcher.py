import csv
import io
import json
import os
import zipfile

from shapely import frechet_distance
from shapely.geometry import Point, LineString
from shapely.ops import nearest_points

from pyproj import Geod

class GeojsonMatcher:

    def __init__(self, geojson_input):
        self._geojson_linestrings = list()

        self._gtfs_trip_patterns = dict()
        self._gtfs_trip_patterns_trip_ids = dict()

        self._geod = Geod(ellps='WGS84')
        
        # read all geojson linestrings to internal storage
        if geojson_input.lower().endswith('.zip'):
            with zipfile.ZipFile(geojson_input) as geojson_zip_file:
                for geojson_filename in geojson_zip_file.namelist():
                    with io.TextIOWrapper(geojson_zip_file.open(geojson_filename), encoding='utf-8') as geojson_file:
                        self._read_geojson_file(geojson_file)
        else:
            for geojson_filename in os.listdir(geojson_input):
                if geojson_filename.lower().endswith('.geojson'):
                    with open(os.path.join(geojson_input, geojson_filename), 'r', encoding='utf-8') as geojson_file:
                        self._read_geojson_file(geojson_file)

    def run(self, gtfs_input, gtfs_output):
        
        # read trip patterns of input GTFS feed into working index
        self._read_gtfs_index(gtfs_input)

        # iterate over each trip pattern and find best matching shape
        for trip_pattern_id, trip_pattern_coordinates in self._gtfs_trip_patterns.items():
            start_point = trip_pattern_coordinates[0]
            end_point = trip_pattern_coordinates[-1]

            line_string_candidates = dict()

            for index, line_string in enumerate(self._geojson_linestrings):
                # check for the start and end point of the trip matches the linestring start and end
                if self._geod.geometry_length(LineString(nearest_points(Point(line_string.coords[0]), start_point))) > 50:
                    continue

                if self._geod.geometry_length(LineString(nearest_points(Point(line_string.coords[-1]), end_point))) > 50:
                    continue

                # check whether any point in trip pattern is not in this linestring
                line_string_matched = True
                for tpc in trip_pattern_coordinates:
                    if self._geod.geometry_length(LineString(nearest_points(line_string, tpc))) > 50:
                        line_string_matched = False
                        break

                # if everything seems okay, use this as candidate
                if line_string_matched:
                    line_string_candidates[index] = self._geod.geometry_length(line_string)
            
            if len(line_string_candidates) > 0:
                # determine linestring index with the shortest possible length, this must be our linestring!
                line_string_index = min(line_string_candidates, key = line_string_candidates.get)

                print(f"Index {line_string_index} is a possible candidate")
                #print(f"{trip_pattern_id}")
            else:
                pass #print("No matching linestring found")

        

    def _read_geojson_file(self, geojson_file):
        geojson = json.load(geojson_file)

        for feature in geojson['features']:
            if feature['type'] == 'Feature' and feature['geometry']['type'] == 'LineString':
                
                coordinates = list()
                for coordinate in feature['geometry']['coordinates']:
                    coordinates.append(Point(coordinate[0], coordinate[1]))

                self._geojson_linestrings.append(LineString(coordinates))        

    def _read_gtfs_index(self, gtfs_input):
        
        # read internal GTFS data index
        if gtfs_input.lower().endswith('.zip'):
            with zipfile.ZipFile(gtfs_input) as geojson_zip_file:
                
                # read stop location data into index
                stop_coordinate_index = dict()
                with io.TextIOWrapper(geojson_zip_file.open('stops.txt'), encoding='utf-8') as txt_stops_file:
                    txt_stops_reader = csv.DictReader(txt_stops_file)
                    for txt_stops_row in txt_stops_reader:
                        stop_coordinate_index[txt_stops_row['stop_id']] = Point(
                            float(txt_stops_row['stop_lon']),
                            float(txt_stops_row['stop_lat'])
                        )

                # read trip stop IDs into temporary index
                trip_stop_id_lists = dict()
                with io.TextIOWrapper(geojson_zip_file.open('stop_times.txt'), encoding='utf-8') as txt_stop_times_file:
                    txt_stop_times_reader = csv.DictReader(txt_stop_times_file)
                    for txt_stop_times_row in txt_stop_times_reader:
                        trip_id = txt_stop_times_row['trip_id']

                        if not trip_id in trip_stop_id_lists:
                            trip_stop_id_lists[trip_id] = list()

                        trip_stop_id_lists[trip_id].append(txt_stop_times_row['stop_id'])

                # transform stop IDs to trip_patterns and coordinates
                for trip_id, stop_ids in trip_stop_id_lists.items():
                    trip_pattern_id = '#'.join(stop_ids)

                    if not trip_pattern_id in self._gtfs_trip_patterns:
                        self._gtfs_trip_patterns[trip_pattern_id] = list()
                        for stop_id in stop_ids:
                            self._gtfs_trip_patterns[trip_pattern_id].append(stop_coordinate_index[stop_id])

                    if not trip_pattern_id in self._gtfs_trip_patterns_trip_ids:
                        self._gtfs_trip_patterns_trip_ids[trip_pattern_id] = list()

                    self._gtfs_trip_patterns_trip_ids[trip_pattern_id].append(trip_id)

                # free up some memory ...
                del stop_coordinate_index
                del trip_stop_id_lists

                print(f"Found {len(self._gtfs_trip_patterns.keys())} TPs")

        else:
            # read stop location data into index
            stop_coordinate_index = dict()
            with open(os.path.join(gtfs_input, 'stops.txt'), 'r') as txt_stops_file:
                txt_stops_reader = csv.DictReader(txt_stops_file)
                for txt_stops_row in txt_stops_reader:
                    stop_coordinate_index[txt_stops_row['stop_id']] = Point(
                        float(txt_stops_row['stop_lon']),
                        float(txt_stops_row['stop_lat'])
                    )

            # read trip stop IDs into temporary index
            trip_stop_id_lists = dict()
            with open(os.path.join(gtfs_input, 'stop_times.txt'), 'r') as txt_stop_times_file:
                txt_stop_times_reader = csv.DictReader(txt_stop_times_file)
                for txt_stop_times_row in txt_stop_times_reader:
                    trip_id = txt_stop_times_row['trip_id']

                    if not trip_id in trip_stop_id_lists:
                        trip_stop_id_lists[trip_id] = list()

                    trip_stop_id_lists[trip_id].append(txt_stop_times_row['stop_id'])

            # transform stop IDs to trip_patterns and coordinates
            for trip_id, stop_ids in trip_stop_id_lists.items():
                trip_pattern_id = '#'.join(stop_ids)

                if not trip_pattern_id in self._gtfs_trip_patterns:
                    self._gtfs_trip_patterns[trip_pattern_id] = list()
                    for stop_id in stop_ids:
                        self._gtfs_trip_patterns[trip_pattern_id].append(stop_coordinate_index[stop_id])

                if not trip_pattern_id in self._gtfs_trip_patterns_trip_ids:
                    self._gtfs_trip_patterns_trip_ids[trip_pattern_id] = list()

                self._gtfs_trip_patterns_trip_ids[trip_pattern_id].append(trip_id)

            # free up some memory ...
            del stop_coordinate_index
            del trip_stop_id_lists

            print(f"Found {len(self._gtfs_trip_patterns.keys())} TPs")

                    