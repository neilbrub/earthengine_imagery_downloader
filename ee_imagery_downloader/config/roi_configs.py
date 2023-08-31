from ee_imagery_downloader.config.collection_filters import example_S1_filters, example_S2_filters

"""
This file configures regions of interest (RoI). RoIs are registered by an entry
(key: dict) in 'roi_configs' below. Each RoI describes the following:

    1. Geographical extent (list of lat/lon coords drawing a polygon)

    2. A coordinate reference system to use for exported imagery
    
    3. A set of Earth Engine image collections to support (give them nicknames!)
    
    4. One or multiple keyed sets of imagery filters, representing seasons. This system
        is implemented to:
        a. Be able to filter imagery to multiple non-continuous date ranges (e.g. same
            range of months for different seasons)
        b. Force natural chunking of export data (only supports one season at a time) to
            avoid accidentally overrunning Google Drive storage space.
"""

# Shorthand to use S1 & S2 as configured in collection_filters.py
S1_S2_filters = {
    'S1': example_S1_filters,
    'S2': example_S2_filters
}

roi_configs = {
    # Add your RoI as a new dict item: 'roi_name': { ... }

    'example_sanikiluaq': {
        "roi_coords": [
            [-80.399, 55.433],
            [-78.306, 55.433],
            [-78.306, 57.077],
            [-80.399, 57.077],
            [-80.399, 55.433]
        ],
        "crs": "EPSG:32617",  # UTM Zone 17N

        "image_collections": {
            'S1': 'COPERNICUS/S1_GRD',
            'S2': 'COPERNICUS/S2'
        },

        "imagery_filters": {
            # E.g.: Select imagery for 2022 (Dec. - Apr.) and 2020 (Jan. - Jul.)
            "2022": {
                "date_start": "2021-12-01",
                "date_end": "2022-05-31",
                **S1_S2_filters
            },
            "2020": {
                "date_start": "2020-01-01",
                "date_end": "2020-06-30",
                **S1_S2_filters
            }
        }
    }
}