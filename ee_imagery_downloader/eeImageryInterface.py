import ee
import copy
import time
import pprint
import warnings
import datetime as dt

import ee_imagery_downloader.utils as utils
from ee_imagery_downloader.config.roi_configs import roi_configs


class eeImageryInterface:
    """
    Retrieve, filter & process imagery from the Google Earth Engine catalog.

    This class provides a stateful interface to GEE client-side proxy objects, which are
    nothing more than pointers to actual server-side data. The implications of this are:
        
        1. None of the methods in this class will download data from the internet or
            store any data on your filesystem;
        
        2. Very little computational power is required from the computer running this
            script, since all processing is done via earthengine functions on Google's
            backend (https://developers.google.com/earth-engine/guides/client_server);
        
        3. The latter means that while you can easily run this script on a toaster, the
            code may appear a bit foreign to those not familiar with Earth Engine
            functions. Cross-referencing the earth engine API Reference may be helpful
            (https://developers.google.com/earth-engine/apidocs).
        
    For a more foundational description of using earth engine with python, see the docs:
    https://developers.google.com/earth-engine/guides.
    
    Attributes:
        - roi_name (str): Name of region of interest (roi_configs entry)
        - config (dict): Configuration dictionary for the given RoI
        - ee_roi (ee.Geometry.Polygon): Polygon describing the location of the RoI
        - ee_collections (dict): LUT mapping collection nicknames to GEE identifiers 
        - imagery_filters (dict): nested dictionaries describing per-collection filter
            (e.g. date ranges, polarisations, cloud cover %), keyed by season (year)
        - imagery (dict): ee proxy objects for imagery retrieved by applying imagery_
            filters to ee_collections. Follows same nested structure as imagery_filters.
            E.g.:
            {
                '2022': {
                    'S1': {
                        'EW': {
                            'HH_HV': ee.ImageCollection
                        }
                    }
                }
            }
    """
    def __init__(self, roi):
        """
        Inits eeImageryInterface for a given RoI.

        Args:
            - roi (str): key in config.image_filtering_configs.roi_configs
        """
        # --- Input checking --- #
        roi = roi.lower()
        if roi not in roi_configs:
            raise ValueError(f"'{roi}' is not registered in roi_configs")
        self.roi_name = roi
        self.config = roi_configs[roi]

        if 'roi_coords' not in self.config:
            raise ValueError(
                "roi_coords (list of [lat, ln]) should be specified in roi_configs")

        # --- Initialize ee client --- #
        ee.Initialize()

        # --- Configuration & Defaults --- #
        self.ee_roi = ee.Geometry.Polygon([self.config['roi_coords']])

        # Default collections: COPERNICUS/S1_GRD & COPERNICUS/S2
        try:
            self.ee_collections = self.config['image_collections']
        except KeyError:
            self.ee_collections = {
                'S1': 'COPERNICUS/S1_GRD',
                'S2': 'COPERNICUS/S2'
            }

        # Default imagery filters: all in last two weeks for each collection
        try:
            self.imagery_filters = self.config['imagery_filters']
        except KeyError:
            now = dt.datetime.now()
            default_end = ee.Date(dt.datetime.now())
            default_start = default_end.advance(-2, 'week')
            self.imagery_filters = {}
            self.imagery_filters[str(now.year)] = {
                "date_start": default_start,
                "date_end": default_end,
                # Add collection keys without any filters
                **{coll_key: {} for coll_key in self.ee_collections.keys()}
            }
        
        # For easier downstream implementation, store flattened version of nested imagery
        # filter configs; [ {'nested_keys': [], 'filters': []}, ...] for each szn, coll.
        # Note that date ranges are still stored in imagery_filters.
        self._flattened_filters = {
            szn: {
                coll_key: {} for coll_key in self.ee_collections.keys()
            } for szn in self.imagery_filters.keys()
        }

        # While flattening, do some verification
        for szn, coll_cfg in self.imagery_filters.items():  # By year
            for coll_key, filt_cfg in coll_cfg.items():  # By collection

                # Verify that imagery_filter keys are consistent with ee_collections keys
                daterange_keys = ['date_start', 'date_end']
                accepted_keys = list(self.ee_collections.keys()) + daterange_keys
                if coll_key not in accepted_keys:
                    raise ValueError(
                        f"imagery_filters key {coll_key} for {szn} not recognized.")

                # Don't try to flatten date range filters
                if coll_key in daterange_keys: continue

                # Do try to flatten collection - recursive function with depth limit
                flattened_filters = utils.flatten_nested_imagery_filters(filt_cfg)
                
                # Verify that all listed filter types are legimite ee.Filters 
                for nested_filter in flattened_filters:
                    filters = nested_filter['filters']
                    for f in filters:
                        assert hasattr(ee.Filter, f['type']), \
                            f"Invalid filter type provided for {coll_key}: {f['type']}"
                
                self._flattened_filters[szn][coll_key] = flattened_filters

        # --- Initialize state --- #
        self.imagery = {}
        self._loadImagery()


    def seasonsLoaded(self):
        return sorted(list(self.imagery.keys()))


    def __str__(self):
        print_string = ''
        print_string += f"eeImageryInterface for {self.roi_name};\n"
        
        szns = self.seasonsLoaded()
        print_string += f"> Imagery loaded for seasons: {', '.join(szns)}\n"
        print_string += "> Structure of self.imagery (keyed by season):\n"
        ex_szn = szns[-1]
        pp = pprint.PrettyPrinter(indent=1, depth=6)
        print_string += pp.pformat(self.imagery[str(ex_szn)])

        return print_string
    

    def getImagery(
            self,
            collection,
            nested_keys=[],
            bands=[],
            season=None,
            date_query={},  # {'start', 'end', ['format']}
            mosaic_window=None  # None, 'hour', 'day', 'week', or 'month'
        ):
        """
        Get imagery for a specified collection, nested group, and season or date range.

        Args:
            - collection (str) - key in self.ee_collections
            - nested_keys (list: default [])
            - bands (list: default [])
            - season (str: default None) - retrieve all imagery for the given season
            - date_query (obj: default {}) - finer-grained control on selected imagery;
                should contain keys 'start' and 'end', and optionally 'format' string
                ('%Y-%m-%d' will be attempted by default).
            - mosaic_window (str: default None) - If specified, imagery will be mosaicked
                by the time window specified. If None, images are not mosaicked.
                Mosaicking can add significantly higher computation time, and result in 
                larger exported files that may get chunked on Google Drive.
        """
        season, date_query = self._handle_season_and_date_query_args(season, date_query)

        if date_query:
            parsed_date_query = self._parse_date_query(date_query)
            season = parsed_date_query['season']
            query_start = parsed_date_query['start']
            query_end = parsed_date_query['end']

        try:
            imgry = copy.deepcopy(self.imagery[season][collection])
        except KeyError:
            warnings.warn(f"imagery not loaded for {season}, {collection}")
            return None
        
        # Pick out requested sub-groups of sorted imagery based on nested_keys
        for k in nested_keys:
            try:
                imgry = imgry[k]
            except KeyError:
                warnings.warn(f"Nested key {k} not found in {season}, {collection}")

        # If no additional processing required, return collection (possibly grouped)
        if not date_query and  mosaic_window is None and not bands: return imgry

        # It's possible that imgry still points to a tree of nested groups; any
        # processing requested (e.g. filtering or mosaicking) in this case must be
        # applied to each collection individually. We thus need to traverse the tree,
        # access each of the collections (leaves), apply the processing, then return the
        # whole tree now containing the processed collections.

        date_start = ee.Date(query_start) if date_query \
            else ee.Date(self.imagery_filters[season]['date_start'])
        date_end = ee.Date(query_end) if date_query \
            else ee.Date(self.imagery_filters[season]['date_end'])

        # Use a recursive function to traverse the grouped tree & apply processing
        # (filtering, band selection, mosaicking, etc.) within the local context 
        def apply_processing(ptr, sub_keys=[]):
            # Base case - made it to a leaf; apply processing
            if isinstance(ptr, ee.ImageCollection):
                if date_query:
                    ptr = ptr.filter(
                        ee.Filter.date(query_start, query_end))
                if bands:
                    ptr = ptr.select(bands)
                if mosaic_window is not None:
                    print(f"Mosaicking {collection}" \
                          f"{'/'+'/'.join(nested_keys) if nested_keys else ''}" \
                          f"{'/'+'/'.join(sub_keys) if sub_keys else ''} " \
                          f"by {mosaic_window}")
                    ptr = utils.doMosaic(
                        ptr,
                        date_start,
                        date_end,
                        self.ee_roi,
                        mosaic_window=mosaic_window
                    )
                return ptr

            # Recursion case: traverse children
            for child_key in ptr.keys():
                ptr[child_key] = apply_processing(ptr[child_key], sub_keys + [child_key])
            
            return ptr

        return apply_processing(imgry)


    def exportImagery(
            self,
            collection,
            nested_keys=[],
            bands=[],
            season=None,
            date_query={},
            mosaic_window=None,
            export_params={}
        ):
        """
        Export a single ImageCollection to Google Drive. Note that this is fine-grained;
        this method only exports imagery for a given year and collection, and if relevant
        given filtering configuration, a single nested level.
        E.g. exportCollection('S1', ['EW', 'HH_HV'], season='2022')
        
        Args:
            - collection (str) - key in self.ee_collections
            - nested_keys (list: default [])
            - bands (list: default [])
            - season (str: default None) - retrieve all imagery for the given season
            - date_query (obj: default {}) - finer-grained control on selected imagery;
                should contain keys 'start' and 'end', and optionally 'format' string
                ('%Y-%m-%d' will be attempted by default).
            - mosaic_window (str: default None)
            - export_params (dict: default {})
                -> (REQ) 'scale' OR 'crsTransform' OR 'dimensions':
                    o 'scale' (int): pixel spacing in meters of exported imagery
                    o 'crsTransform' (list): affine transformation consistent with 'crs'
                    o 'dimensions' (str: "{width}x{height}"): exact image dimensions
                        (warning: implicit reprojection, not recommended)
                
                -> 'crs' (str: "EPSG:{code}"): CRS for exported imagery
                    Default: crs listed in roi_configs if available or 'EPSG:4326' (WGS84)
                
                -> 'folder' (str): Drive folder in which to store exported imagery
                    Default: "{roi name}/{collection name}-{season}/{Nested-Keys}"
                    Note that this is all one folder name; '/' doesn't create subfolders :(
        """
        # Required export_params
        geom_args = ['scale', 'crsTransform', 'dimensions']
        geom_args_provided = [k in export_params for k in geom_args]
        if not any(geom_args_provided):
            raise ValueError(f"One of {', '.join(geom_args)} is required in export_params")
        if sum(geom_args_provided) > 1:
            # Prioritization if more than one provided: dimensions > crsTransform > scale
            msg = f"More than one of {','.join(geom_args)} provided; "
            if 'dimensions' in export_params:
                msg += 'Using dimensions.'
                if 'crsTransform' in export_params: del export_params['crsTransform']
                if 'scale' in export_params: del export_params['scale']
            elif 'crsTransform' in export_params:
                msg += 'Using crsTransform'
                if 'scale' in export_params: del export_params['scale']
            warnings.warn(msg)

        # Optional export_params
        if 'crs' not in export_params:
            try:
                export_params['crs'] = self.config['crs']
            except KeyError:
                export_params['crs'] = 'EPSG:4326'  # WGS84

        if 'folder' not in export_params:
            # Get season from date_query if provided
            szn_name = season
            if date_query:
                parsed_date_query = self._parse_date_query(date_query)
                szn_name = parsed_date_query['season']
            export_params['folder'] = f"{self.roi_name}/{collection}_{szn_name}/{'_'.join(nested_keys)}"

        # Get imagery
        export_collection = self.getImagery(
            collection,
            nested_keys=nested_keys,
            bands=bands,
            season=season,
            date_query=date_query,
            mosaic_window=mosaic_window
        )
        assert isinstance(export_collection, ee.ImageCollection), \
            "exportCollection only exports one ImageCollection at a time. It appears " \
            f"{collection}/{'/'.join(nested_keys)} is not an ImageCollection; you may " \
            f"need to specify more nested_keys; \n{self.__str__()}"

        # Get user's confirmation on exporting these images & bands
        n_bands = export_collection.first().bandNames().size().getInfo()
        n_images = export_collection.size().getInfo()
        
        print(f"About to export {n_images} {collection}"
              f"{'/'+'/'.join(nested_keys) if nested_keys else ''} images, "
              f"each with {n_bands} bands, with the following "
              f"export_params:\n{export_params}")
        if not utils.user_confirms('> Do you wish to continue?'): return
        print("Proceeding...")

        # Parse relevant info into standard filenames for each image 
        img_basename = utils.genImageBasename(
            collection,
            nested_keys,
            scale=export_params['scale'] if 'scale' in export_params else None)

        # Launch export task for each image in collection
        export_tasks = utils.exportImageCollection(
            export_collection, self.ee_roi, img_basename, export_params)
        
        print("Tasks submitted; check https://code.earthengine.google.com/tasks")

        # Keep monitoring alive (note that exiting script will NOT cancel ee tasks)
        print(f"\nWaiting for {len(export_tasks)} export tasks to finish...")
        exp_start = time.time()
        last_update = exp_start-300
        task_outstanding = True
        failed_taskids = []
        while task_outstanding:
            time.sleep(3)
            task_outstanding = False
            n_completed = 0
            n_failed = 0
            for i, t in enumerate(export_tasks):
                t_state = t.status()['state']
                if t_state not in ['COMPLETED', 'FAILED', 'CANCELLED']:
                    task_outstanding = True
                elif t_state in['FAILED', 'CANCELLED'] and i not in failed_taskids:
                    print(f"Task {i} failed.")
                    n_failed+=1
                    failed_taskids.append(i)
                else:
                    n_completed+=1
            
            if (time.time() - last_update) > 300:  # Give update every 5 min
                print(f"> {(time.time()-exp_start)/60:.1f} min elapsed; "
                      f"{n_completed}/{len(export_tasks)} tasks completed, "
                      f"{n_failed} failed.")
                last_update = time.time()
        
        exp_end = time.time()
        print(f"All tasks finished in {exp_end-exp_start:.1f} seconds.")


    def _reset_imagery(self):
        self.imagery = {
            szn: {
                coll_key: {} for coll_key in self.ee_collections.keys()
            } for szn in self.imagery_filters.keys()
        }


    def _loadImagery(self):
        """
        Retrieve & filter imagery based on configuration passed on init.
        Save ee proxy objects to instance state variable 'imagery'.
        """
        self._reset_imagery()

        # Fetch & store imagery by season (year)
        # Note that start & end dates for a season might not all belong to the same year
        # (e.g. date filter for '2022' may start in December 2021), which is ok since
        # date ranges are only pulled from the user-specified imagery_filters config.
        for szn in self.imagery_filters.keys():
            date_start = ee.Date(self.imagery_filters[szn]['date_start'])
            date_end = ee.Date(self.imagery_filters[szn]['date_end'])

            # Loop over all collections in filter config
            for coll_key in self._flattened_filters[szn].keys():
                ee_coll_name = self.ee_collections[coll_key]

                # Get 'baseline' collection (date + roi filters only)
                base_coll = (ee.ImageCollection(ee_coll_name)
                    .filter(ee.Filter.date(date_start, date_end))
                    .filter(ee.Filter.bounds(self.ee_roi))
                ).map(lambda img: img.clip(self.ee_roi))

                # Construct each nested (or not) path for differently-filtered imagery
                nested_filters = self._flattened_filters[szn][coll_key]
                for nested_filter in nested_filters:
                    nested_keys = nested_filter['nested_keys']
                    filters = nested_filter['filters']

                    # Construct the nested path
                    imgry_ptr = self.imagery
                    imgry_keys = [szn, coll_key] + nested_keys
                    for k in imgry_keys[:-1]:
                        imgry_ptr = imgry_ptr.setdefault(k, {})
                    
                    # Filter the collection & populate the nested level
                    filtered_coll = base_coll
                    for filter_components in filters:
                        filter_class = getattr(ee.Filter, filter_components['type'])
                        filt = filter_class(*filter_components['args'])
                        filtered_coll = filtered_coll.filter(filt)

                    imgry_ptr[imgry_keys[-1]] = filtered_coll

    
    def _handle_season_and_date_query_args(self, season, date_query):
        """
        For functions that accept a season (e.g. '2022') OR a specific date_query,
        validate the usage of these arguments.
        """
        if date_query and not all([r in date_query.keys() for r in ['start', 'end']]):
            warnings.warn("date_query must contain keys 'start' and 'end', which were "
                          "not found.")
            date_query = {}
        if season and date_query:
            warnings.warn("Specifying season as well as date_query is redundant; "
                          "season will be ignored in favour of date_query.")
            season = None
        if season and season not in self.imagery_filters:
            warnings.warn(f"season '{season}' not found in imagery_filters for "
                          f"{self.roi_name}")
            season = None
        if not season and not date_query:
            raise ValueError("Must specify valid season or date_query to getImagery")
        
        return season, date_query


    def _parse_date_query(self, date_query):
        """
        Attempt to match date_query (start & end dates) to a season specified 
        in roi_configs.

        E.g.:
        date_query = {
            'start': '2021-12-01',
            'end': '2022-02-28',
            'format' '%Y-%m-%d'
        }

        Case 1: date_query is contained in a season as specified by roi_config.

        Case 2: date_query overlaps, but is not fully contained by season in roi_config;
            E.g. f start date in roi_config for season '2022' is '2022-01-22', then:
            Return = {
                'season': '2022',
                'start': '2022-01-22',
                'end': '2022-02-28'
            }
        
        Case 3: date_query does not overlap any date ranges in seasons defined in roi_config
            (raise error)

        Case 4: date_query overlaps multiple seasonal date ranges. TODO.
            Current behaviour: matches first season with overlap.
        """
        start_date = date_query['start']
        end_date = date_query['end']
        date_fmt = date_query['format'] if 'format' in date_query else '%Y-%m-%d'

        if not isinstance(start_date, dt.datetime):
            start_date = dt.datetime.strptime(start_date, date_fmt)
        if not isinstance(end_date, dt.datetime):
            end_date = dt.datetime.strptime(end_date, date_fmt)

        # Check if requested dates overlap date range for a season or not.
        # Return only dates that overlap.
        matched_szn = None
        overlap_dates = None
        for szn, szn_filts in self.imagery_filters.items():
            szn_start = szn_filts['date_start']
            szn_end = szn_filts['date_end']

            if not isinstance(szn_start, dt.datetime):
                szn_start = dt.datetime.strptime(szn_start, '%Y-%m-%d')
            if not isinstance(szn_end, dt.datetime):
                szn_end = dt.datetime.strptime(szn_end, '%Y-%m-%d')

            overlap_dates = utils.get_date_range_overlap(
                start_date, end_date, szn_start, szn_end)
            
            if overlap_dates is None: continue
            
            matched_szn = szn
            break
        
        if matched_szn is None:
            raise ValueError(f"date_query {date_query} did not match date range for any "
                             f"seasons configured for {self.roi_name}.")

        return {
            'season': matched_szn,
            'start': overlap_dates['start'].strftime(date_fmt),
            'end': overlap_dates['end'].strftime(date_fmt)
        }


        # # Check if requested dates are within config for a season or not.
        # # end_year is used to attempt a match to a season in imagery_filters,
        # # since it is assumed seasons are indicated by end date (e.g. seasons
        # # ending in spring or summer, well distanced from year rollover).
        # # E.g. 2021-12-05 to 2022-03-31 would map to season '2022'.
        # end_year = end_date.year
        # cand_szn = str(end_year)

        # if cand_szn not in self.imagery_filters:
        #     raise ValueError(f"Could not find season in {self.roi_name} config "
        #                      f"for dates {start_date.strftime(date_fmt)} to "
        #                      f"{end_date.strftime(date_fmt)}")
    
        # cand_szn_start = dt.datetime.strptime(
        #     self.imagery_filters[cand_szn]['date_start'],
        #     '%Y-%m-%d')  # as in image_filtering_configs.py
        # cand_szn_end = dt.datetime.strptime(
        #     self.imagery_filters[cand_szn]['date_end'],
        #     '%Y-%m-%d')
        
        # # Check if requested start date is before config start date for season
        # # (if true, clip the start date to config)
        # if start_date < cand_szn_start:
        #     warnings.warn(f"Start date requested in getImagery ("
        #                   f"{start_date.strftime(date_fmt)}) is earlier than "
        #                   f"start date for season in {self.roi_name} config ("
        #                   f"{cand_szn_start}) - using config date instead.")
        #     start_date = cand_szn_start
        # # Check if requested end date is after config end date for season
        # # (if true, clip the end date to config)
        # if end_date > cand_szn_end:
        #     warnings.warn(f"End date requested in getImagery ("
        #                   f"{end_date.strftime(date_fmt)}) is later than "
        #                   f"end date for season in {self.roi_name} config ("
        #                   f"{cand_szn_end}) - using config date instead.")
        #     end_date = cand_szn_end
        # # Check if requested end date is before config start date for season
        # # (if true, no imagery matches the query; abort)
        # if end_date < cand_szn_start:
        #     raise ValueError(f"End date requested in getImagery ("
        #                      f"{end_date.strftime(date_fmt)}) is earlier than "
        #                      f"start date for season in {self.roi_name} config ("
        #                      f"{cand_szn_start}).")
        # # Check if requested start date is after config end date for season
        # # (if true, no imagery matches the query; abort)
        # if start_date > cand_szn_end:
        #     raise ValueError(f"Start date requested in getImagery ("
        #                      f"{start_date.strftime(date_fmt)}) is later than "
        #                      f"end date for season in {self.roi_name} config ("
        #                      f"{cand_szn_end}).")

        # season = cand_szn

        # return {
        #     'season': season,
        #     'start': start_date.strftime(date_fmt),
        #     'end': end_date.strftime(date_fmt)
        # }