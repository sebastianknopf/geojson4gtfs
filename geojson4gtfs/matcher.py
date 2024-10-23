import csv
import io
import json
import logging
import os
import zipfile

from shapely.geometry import Point, LineString
from shapely.ops import nearest_points

from pyproj import Geod

class GeojsonMatcher:

    def __init__(self, geojson_input):
        self._geojson_linestrings = list()

        self._gtfs_trip_patterns = dict()
        self._gtfs_trip_patterns_trip_ids = dict()
        self._gtfs_trips_shape_ids = dict()

        self._gtfs_shapes = dict()

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
        
        # determine working directory and copy input data or exract input archive
        working_directory = gtfs_output
        if gtfs_output.lower().endswith('.zip'):
            working_directory = os.path.dirname(gtfs_output)

        if gtfs_input.lower().endswith('.zip'):
            with zipfile.ZipFile(gtfs_input, 'r') as gtfs_input_archive:
                gtfs_input_archive.extractall(working_directory)
        else:
            pass
        
        # read trip patterns of input GTFS feed into working index
        self._read_gtfs_index(working_directory)

        # iterate over each trip pattern and find best matching shape
        for trip_pattern_id, trip_pattern_coordinates in self._gtfs_trip_patterns.items():
            start_point = trip_pattern_coordinates[0]
            end_point = trip_pattern_coordinates[-1]

            line_string_candidates = dict()
            for index, line_string in enumerate(self._geojson_linestrings):
                # check for the start and end point of the trip matches the linestring start and end
                if self._geod.geometry_length(LineString(nearest_points(Point(line_string.coords[0]), start_point))) > 20:
                    continue

                if self._geod.geometry_length(LineString(nearest_points(Point(line_string.coords[-1]), end_point))) > 20:
                    continue

                # check whether any point in trip pattern is not in this linestring
                line_string_matched = True
                
                trip_pattern_projections = list()
                for tpc in trip_pattern_coordinates:
                    if self._geod.geometry_length(LineString(nearest_points(line_string, tpc))) > 20:
                        line_string_matched = False
                        break

                    trip_pattern_projections.append(line_string.project(tpc))

                # check whether projections are increasing, this ensures the stops order matches the shape
                line_projection_matched = True #trip_pattern_projections == sorted(trip_pattern_projections)

                # if everything seems okay, use this as candidate
                if line_string_matched and line_projection_matched:
                    line_string_candidates[index] = self._geod.geometry_length(line_string)
            
            if len(line_string_candidates) > 0:
                # determine linestring index with the shortest possible length, this must be our linestring!
                line_string_index = min(line_string_candidates, key = line_string_candidates.get)

                # render shape data and store shape ID for trip pattern
                shape_id = self._create_shape(trip_pattern_id, self._geojson_linestrings[line_string_index])

                for trip_id in self._gtfs_trip_patterns_trip_ids[trip_pattern_id]:
                    self._gtfs_trips_shape_ids[trip_id] = shape_id
            else:
                logging.warning(f"no matching line string found for trip pattern {trip_pattern_id}")

        # generate shape data output
        self._write_gtfs_data(working_directory, gtfs_output)

    def _read_geojson_file(self, geojson_file):
        geojson = json.load(geojson_file)

        for feature in geojson['features']:
            if feature['type'] == 'Feature' and feature['geometry']['type'] == 'LineString':
                
                coordinates = list()
                for coordinate in feature['geometry']['coordinates']:
                    coordinates.append(Point(coordinate[0], coordinate[1]))

                self._geojson_linestrings.append(LineString(coordinates))        

    def _read_gtfs_index(self, working_directory):
        # read internal GTFS data index
        # read stop location data into index
        stop_coordinate_index = dict()
        with open(os.path.join(working_directory, 'stops.txt'), 'r') as txt_stops_file:
            txt_stops_reader = csv.DictReader(txt_stops_file)
            for txt_stops_row in txt_stops_reader:
                stop_coordinate_index[txt_stops_row['stop_id']] = Point(
                    float(txt_stops_row['stop_lon']),
                    float(txt_stops_row['stop_lat'])
                )

        # read trip stop IDs into temporary index
        trip_stop_id_lists = dict()
        with open(os.path.join(working_directory, 'stop_times.txt'), 'r') as txt_stop_times_file:
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

    def _write_gtfs_data(self, working_directory, gtfs_output):
        # remove old shapes.txt and write new shape data
        if os.path.exists(os.path.join(working_directory, 'shapes.txt')):
            os.remove(os.path.join(working_directory, 'shapes.txt'))
        
        with open(os.path.join(working_directory, 'shapes.txt'), 'w', newline='', encoding='utf-8') as txt_shapes:
            txt_shapes_writer = csv.DictWriter(txt_shapes, fieldnames=['shape_id', 'shape_pt_lat', 'shape_pt_lon', 'shape_pt_sequence', 'shape_dist_traveled'])
            txt_shapes_writer.writeheader()

            for _, shape_data in self._gtfs_shapes.items():
                txt_shapes_writer.writerows(shape_data)

        # load existing trips.txt into memory ...
        trips_data = list()

        with open(os.path.join(working_directory, 'trips.txt'), 'r', encoding='utf-8') as txt_trips:
            txt_trips_reader = csv.DictReader(txt_trips)
            trips_data = list(txt_trips_reader)

        # remove old trips.txt and write adapted trip data
        os.remove(os.path.join(working_directory, 'trips.txt'))
        with open(os.path.join(working_directory, 'trips.txt'), 'w', newline='', encoding='utf-8') as txt_trips:
            txt_trips_headers = list(trips_data[0].keys())
            if 'shape_id' not in txt_trips_headers:
                txt_trips_headers.append('shape_id')
            
            txt_trips_writer = csv.DictWriter(txt_trips, fieldnames=txt_trips_headers)
            txt_trips_writer.writeheader()

            for trip_record in trips_data:
                if trip_record['trip_id'] in self._gtfs_trips_shape_ids:
                    trip_record['shape_id'] = self._gtfs_trips_shape_ids[trip_record['trip_id']]
                else:
                    trip_record['shape_id'] = ''

                txt_trips_writer.writerow(trip_record)

        # if output should be a ZIP archive, compress everything
        if gtfs_output.lower().endswith('.zip'):
            with zipfile.ZipFile(gtfs_output, 'w', zipfile.ZIP_DEFLATED) as gtfs_output_archive:
                for txt_file in os.listdir(working_directory):
                    if txt_file.endswith('.txt'):
                        gtfs_output_archive.write(
                            os.path.join(working_directory, txt_file),
                            txt_file
                        )

                        os.remove(os.path.join(working_directory, txt_file))
    
    def _create_shape(self, trip_pattern_id, line_string):
        
        shape_data = list()

        shape_id = f"de:vpe:shape:{len(self._gtfs_shapes.keys())}"
        shape_dist_traveled = 0.0
        for i in range(len(line_string.coords) - 1):
            shape_pt = line_string.coords[i]
            next_shape_pt = line_string.coords[i + 1]

            shape_data.append({
                'shape_id': shape_id,
                'shape_pt_lat': shape_pt[1],
                'shape_pt_lon': shape_pt[0],
                'shape_pt_sequence': i + 1,
                'shape_dist_traveled': shape_dist_traveled
            })

            shape_dist_traveled = shape_dist_traveled + (self._geod.geometry_length(LineString([shape_pt, next_shape_pt])) / 1000.0)
        
        # finally add last shape point
        last_shape_pt = line_string.coords[-1]

        shape_data.append({
            'shape_id': shape_id,
            'shape_pt_lat': last_shape_pt[1],
            'shape_pt_lon': last_shape_pt[0],
            'shape_pt_sequence': len(shape_data) + 1,
            'shape_dist_traveled': shape_dist_traveled
        })

        # add shape data to GTFS shape index and return 
        self._gtfs_shapes[shape_id] = shape_data

        return shape_id



                    