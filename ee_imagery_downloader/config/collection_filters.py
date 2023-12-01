"""
To allow precise but generalizable selection of imagery from any collection, a nested
filtering system has been set up.

Filters for each image collection are defined in multi-level nested dictionaries, whose
keys describe a desired grouping configuration. E.g., it might be desired that data from
a SAR collection is grouped by instrument mode, and within that grouped by polarisation.
Group keys can be nested indefinitely, and can take any unique string value that is not
'filters'.

Eventually, a list under a key called 'filters' should be specified. This list should 
contain dictionaries each describing an Earth Engine filter that, when applied to the
collection, will yield data for the group. Specifically, each dict in the 'filters' list
should have the following {key: value} pairs:

    - 'type': str, an attribute of ee.Filter (assert hasattr(ee.Filter, filter['type']))

    - 'args': list, a list of positional arguments to the ee.Filter (order matters!)

Note that this pattern allows arbitrary grouping & filtering for any EE image collection.

See examples immediately below, then add your own; be sure to import and use them in
roi_configs for them to be applied by eeImageryInterface.
"""

example_S1_filters = {
    # Group by instrument mode and polarisation;
    # E.g. Get EW imagery with HH/HV polarisation, and IW imagery with VV polarisation.
    "EW": {
        "HH-HV": {
            'filters': [
                {
                    'type': 'listContains',
                    'args': ['transmitterReceiverPolarisation', 'HH']
                },
                {
                    'type': 'listContains',
                    'args': ['transmitterReceiverPolarisation', 'HV']
                },
                {
                    'type': 'eq',
                    'args': ['instrumentMode', 'EW']
                }
            ]
        }
    },
    "IW": {
        "VV": {
            'filters': [
                {
                    'type': 'listContains',
                    'args': ['transmitterReceiverPolarisation', 'VV']
                },
                {
                    'type': 'eq',
                    'args': ['instrumentMode', 'IW']
                }
            ]
        }
    }
}

example_S2_filters = {
    # No grouping
    'filters': [
        {
            'type': 'lt',
            'args': ['CLOUDY_PIXEL_PERCENTAGE', 80]
        }
    ]
}
