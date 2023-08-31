import ee
from tqdm import tqdm

"""
Collection of stateless functions performing miscellaneous tasks related to image
filtering, processing and download.
"""

def user_confirms(question, default=True):
    valid_responses = {"yes": True, "y": True, "ye": True, "no": False, "n": False}
    prompt = '[y/n]'
    if default is True: prompt = '[Y/n]'
    elif default is False: prompt = '[y/N]'
    print(f"{question} {prompt}")
    choice = input().lower()
    
    while True:
        if default is not None and choice == "":
            return default
        elif choice in valid_responses:
            return valid_responses[choice]
        else:
            print(f"valid responses are {', '.join(valid_responses.keys())}")


def flatten_nested_imagery_filters(filter_dict, nested_keys=[], max_depth=10):
    """
    Recursively flatten nested image filtering config dictionary.
    Depth First Search-inspired.

    Args:
        filter_dict (dict): Potentially nested dictionary describing imagery groups
            and filters for a given year and collection.
        max_depth (int): How deep into the nested dictionary to look for 'filters'
            before giving up.
    
    Return: flattened version of filter_dict;
        grouped_filters_list (list[dict{nested_keys, filters}]) 
    """
    # Base cases
    if 'filters' in filter_dict:  # Filters found
        return [{
            'nested_keys': nested_keys,
            'filters': filter_dict['filters']
        }]
    if max_depth < 1:  # recursion limit exceeded - return empty filter & append None
        return [{
            'nested_keys': nested_keys + [None],
            'filters': []
        }]

    # Recursion case - return filters for all children
    grouped_filters_list = []
    for sub_key, sub_dict in filter_dict.items():
        sub_grouped_filters_list = flatten_nested_imagery_filters(
            sub_dict,
            nested_keys=nested_keys + [sub_key],
            max_depth=max_depth-1)

        # Expect children to return a list of grouped filters
        for sub_grouped_filters in sub_grouped_filters_list:
            grouped_filters_list.append(sub_grouped_filters)
    
    return grouped_filters_list        


def genImageBasename(collection, nested_keys=[], scale=None):
    """
    Synthesize an identifier for all images belonging to a particular group defined
    by collection & nested_keys. Optionally include scale information.

    A per-image datetime string and file extension should be appended to this.
    """
    return (
        f"{collection}"
        f"{'_' + '_'.join(nested_keys) if nested_keys else ''}"
        f"{'_' + str(scale) + 'm' if scale else ''}"
    )


def get_date_range_overlap(range1_start, range1_end, range2_start, range2_end):
    overlap_start = max(range1_start, range2_start)
    overlap_end = min(range1_end, range2_end)

    if overlap_start > overlap_end: return None

    return {
        'start': overlap_start,
        'end': overlap_end
    }



# ------- EarthEngine functions ------- #

def latlnFromPolygon(ee_poly):
    return ee_poly.centroid().coordinates().getInfo()[::-1]


def dateToDatestring(ee_date):
    if not isinstance(ee_date, ee.Date): ee_date = ee.Date(ee_date)
    return ee.String(ee_date.format("YYYYMMdd'T'HHmm"))


def genMosaickingFunction(image_collection, roi, mosaic_window='hour'):
    """
    Often iterator-type functions operating over a collection reference the collection
    itself, which is bad news for generalizability. Here, we bind such a function to
    whatever collection (and roi) is passed.

    Args:
        - image_collection: ee.ImageCollection to mosaic
        - roi: ee.Geometry object
        - mosaic_window (default='hour'): one of 'hour', 'day' or 'week'.
    """
    supported_mosaic_windows = ['hour', 'day', 'week']
    if mosaic_window not in supported_mosaic_windows:
        raise ValueError(f"mosaic_window must be in {supported_mosaic_windows}; " \
                         f"received {mosaic_window}")
    
    # First sort image_collection by system:time_start in ascending order. This
    # guarantees that a windowing pass over a time range will capture all images well.
    sorted_collection = image_collection.sort('system:time_start')

    def mosaicCollection(datetime, image_list):
        """
        Mosaic all images in image_list within an hour of of the given datetime
        """
        datetime = ee.Date(datetime)
        image_list = ee.List(image_list)
        
        tiles_in_window = sorted_collection.filterDate(
            datetime, datetime.advance(1, mosaic_window))
        mosaicked = ee.Image(tiles_in_window.mosaic()).set({
            'system:time_start': tiles_in_window.first().get('system:time_start'),
            'resolution_meters': tiles_in_window.first().get('resolution_meters')
        })
        mosaicked = mosaicked.clip(roi)
        return ee.List(ee.Algorithms.If(
            tiles_in_window.size(),
            image_list.add(mosaicked),
            image_list
        ))
    
    return mosaicCollection


def doMosaic(collection, startDate, endDate, roi, mosaic_window='hour'):
    """
    For the specified collection in the specified date range, create a mosaic per window.
    

    """
    supported_mosaic_windows = ['hour', 'day', 'week']
    if mosaic_window not in supported_mosaic_windows:
        raise ValueError(f"mosaic_window must be in {supported_mosaic_windows}; " \
                         f"received {mosaic_window}")

    hourly_diff = endDate.difference(startDate, mosaic_window)
    hourly_datetime_list = ee.List.sequence(0, hourly_diff).map(
        lambda hour: startDate.advance(hour, mosaic_window)
    )

    if not isinstance(collection, ee.ImageCollection):
        print(f"Mosaic called on {type(collection)}, {collection}")

    mosaicking_func = genMosaickingFunction(collection, roi, mosaic_window=mosaic_window)
    mosaics = ee.List(hourly_datetime_list.iterate(mosaicking_func, ee.List([])))
    mosaics = ee.ImageCollection(mosaics)

    return mosaics


def exportImageCollection(collection, region, coll_basename, export_params):
    coll_list = collection.toList(collection.size())
    export_tasks = []
    
    coll_size = coll_list.size().getInfo()
    print(f"Launching {coll_size} export tasks...")
    for i in tqdm(range(coll_size)):
        img = ee.Image(coll_list.get(i)).double()

        img_dtstring = dateToDatestring(img.date()).getInfo()
        img_name = f"{coll_basename}_{img_dtstring}"

        scale = None
        dims = None
        crsTransform = None
        if 'dimensions' in export_params: dims = export_params['dimensions']
        elif 'scale' in export_params: scale = export_params['scale']
        elif 'crsTransform' in export_params: crsTransform = export_params['crsTransform']

        task = ee.batch.Export.image.toDrive(
            image=img,
            folder=export_params['folder'],
            description=img_name,
            region=region,
            crs=export_params['crs'],
            dimensions=dims,
            crsTransform=crsTransform,
            scale=scale,
            maxPixels=1e13
        )
        task.start()

        export_tasks.append(task)

    return export_tasks

