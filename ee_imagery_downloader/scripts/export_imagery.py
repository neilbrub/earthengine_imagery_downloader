import argparse
import datetime as dt

from ee_imagery_downloader.eeImageryInterface import eeImageryInterface


def parse_args():
    accepted_date_fmt = '%Y%m%d'
    date_fmt_readable = 'yyyymmdd'

    parser = argparse.ArgumentParser()
    parser.add_argument('--roi', required=True,
                        help='Entry in config.roi_configs')
    
    parser.add_argument('--collection', '-i', required=True,
                        help='Image collection identifier (e.g. S1 or S2)')

    parser.add_argument('--resolution', '-r', required=True,
                    help='Spatial resolution (m) in which to export imagery')
    
    parser.add_argument('--keys', '-k', required=False, default=None,
                        help='Nested keys separated by _, e.g. EW_HH-HV '
                            '(see image_filtering_configs)')
   
    parser.add_argument('--bands', '-b', required=False, default=None,
                        help='Bands to include in export, separated by _, '\
                            'e.g. B2_B3_B4')
    
    parser.add_argument('--season', '-y', default=None,
                        help='Export all imagery for this season (year)')
   
    parser.add_argument('--start-date', '-s', default=None,
                        help=f'Start of date range ({date_fmt_readable}) for which to export imagery')
   
    parser.add_argument('--end-date', '-e', default=None,
                        help=f'End of date range ({date_fmt_readable}) for which to export imagery')

    # parser.add_argument('--no-mosaic', action='store_true',
    #                     help='Export imagery tiles rather than mosaicked images (faster '
    #                     'and may avoid Drive chunking - '
    #                     'https://developers.google.com/earth-engine/guides/exporting_images#large_file_exports)')

    args = parser.parse_args()
    roi = args.roi
    collection = args.collection
    res = int(args.resolution)
    
    nested_keys = []
    if args.keys: nested_keys = args.keys.split('_')

    bands = []
    if args.bands: bands = args.bands.split('_')

    season = args.season

    start_date = args.start_date
    end_date = args.end_date
    date_query = {}
    if start_date and end_date:
        try:
            start_date = dt.datetime.strptime(start_date, accepted_date_fmt)
            end_date = dt.datetime.strptime(end_date, accepted_date_fmt)
        except ValueError:
            raise ValueError(f"Please specify datestrings in format {accepted_date_fmt}")
        
        date_query = {
            'start': start_date,
            'end': end_date,
            'format': accepted_date_fmt
        }

    # mosaic = not args.no_mosaic
    mosaic=True
    
    return {
        'roi': roi,
        'collection': collection,
        'bands': bands,
        'nested_keys': nested_keys,
        'season': season,
        'date_query': date_query,
        'res': res,
        'mosaic': mosaic
    }


if __name__ == "__main__":
    args = parse_args()

    interface = eeImageryInterface(args['roi'])
    interface.exportImagery(
        args['collection'],
        bands=args['bands'],
        nested_keys=args['nested_keys'],
        season=args['season'],
        date_query=args['date_query'],
        mosaic=args['mosaic'],
        export_params={
            'scale': args['res']
        }
    )
