import click
import logging

from geojson4gtfs.matcher import GeojsonMatcher

logging.basicConfig(
    level=logging.INFO, 
    format= '[%(asctime)s] %(levelname)s: %(message)s',
    datefmt='%H:%M:%S'
)

@click.command()
@click.option('--input', '-i', help='directory or ZIP file containing GTFS data')
@click.option('--output', '-o', help='directory or ZIP file containing GTFS data')
@click.option('--geojson', '-g', help='directory or ZIP file containing GTFS data')
@click.option('--config', '-c', default=None, help='additional config file')
def match(input, output, geojson, config):
    matcher = GeojsonMatcher(geojson, config)
    matcher.run(input, output)

if __name__ == '__main__':
    match()