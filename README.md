# Earth Engine Imagery Downloader

The code in this repository takes an object-oriented approach to retrieving, filtering,
exploring, and exporting imagery from Google Earth Engine. Since the workflow to do this
in a one-off sense (e.g. for a specific region, date range, collection, and set of filters)
is fairly quick and simple to implement in the [Earth Engine Code Editor](https://code.earthengine.google.com/),
this codebase is designed to handle slightly more involved imagery acquisition needs. 

Key use cases include:

1. Configure (and save) multiple regions of interest, each with different image
collections and filters
2. Fetch imagery for multiple discrete date ranges at once (e.g. get imagery for same
months over different seasons)
3. Access various groups of filtered imagery simultaneously - e.g. retrieve HH/HV and VV
SAR imagery at the same time, but give each a handle to interact with individually.

Nearly all functionality is defined in the `eeImageryInterface` class and associated `utils.py`.

## Workflow

### 1. Configure Regions of Interest, Image Collections, and Image Filtering

Start with `./config/roi_configs.py` and `./config/collection_filters.py`.

### 2. Explore Configured Imagery in a GEE-Interfacing Notebook 

See `./notebooks/browse_ee_imagery_example.ipynb`.

Keep in mind that while some `eeImageryInterface` methods accept date ranges to return
imagery for (e.g. for visualization), the <b>imagery that has been filtered, loaded and
made available to the client-side class instance is defined by the roi configuration</b>.

### 3. Export Loaded Imagery to Google Drive

Exporting via Google Drive is necessary for files larger than 32MB. If your imagery is 
smaller than that, see [Image.getDownloadURL](https://developers.google.com/earth-engine/apidocs/ee-image-getdownloadurl).

Navigate to and run `./scripts/export_imagery.py`. To see available arguments:

```
export_imagery.py --help
```

### 4. Download Exported Imagery Using the Drive API

Once imagery is exported to Google Drive, you could download it manually. However,
if you have a lot of images, this sucks. Instead, you can try setting up & using a
script that leverages the Google Drive API to do this automatically. It requires a few
steps of Google-y setup, but once it works, it's pretty magical.

See `./scripts/download_drive_files.md`.
