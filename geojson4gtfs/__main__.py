import click

from geojson4gtfs.matcher import GeojsonMatcher

@click.group()
def cli():
    pass

@cli.command()
@click.option('--input', '-i', help='Directory or ZIP file containing GTFS data')
@click.option('--output', '-o', help='Directory or ZIP file containing GTFS data')
@click.option('--geojson', '-g', help='Directory or ZIP file containing GTFS data')
def match(input, output, geojson):
    matcher = GeojsonMatcher(geojson)
    matcher.run(input, output)

if __name__ == '__main__':
    cli()