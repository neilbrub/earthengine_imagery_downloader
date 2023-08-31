## download_drive_files.md

This document walks through the use of Google Drive API via a python script to facilitate downloading a large number of files (e.g. imagery exported from Google Earth Engine to Google Drive) to relieve the time and frustration of doing so manually.

There are three steps to programmatically downloading imagery from Google Drive:

1. Set up a Google Cloud Project that has the Drive API enabled (this is needed for authentication)

2. Set up a python environment that can use the Drive API

3. Configure a python script to download the desired imagery from your Google Drive

Consult the diagram at https://developers.google.com/drive/api/guides/about-sdk depicting the interaction between the python script (the ‘Google Drive App' in our case), Google’s authentication system, and your Google Drive files.

Subsequent steps are derived from https://developers.google.com/drive/api/quickstart/python. Feel free to follow along with those instructions instead, then skip to step 3.

### 1. Set up Google Drive API on a Google Cloud Project

From the console of a new or existing Google Cloud Project, do the following:

`APIs & Services` → `+ Enable APIs and Services` → search "Drive" → `Google Drive API` → `Enable`

`APIs & Services` → `OAuth Consent Screen` → Select ‘External’ User Type → `Create`

Fill out required fields in the app registration form that appears (i.e. app name & contact info) - what you choose here is not critically important, as this ‘app’ will just be used by you to access the Drive API. You could name the app something like ‘Drive Interface’. Save and Continue.

Skip ‘Scopes’ by scrolling down and clicking Save and Continue

In ‘Test Users’ click `+ Add Users` and enter the google email address for the google account you'd like to access the Google Drive of. This should be the account you exported imagery to, i.e. the account that earthengine is authenticated to. Evidently, you should have the password for this account, as it will be needed later. Feel free to add multiple accounts (you can add more later if needed). `Save and Continue`.

Verify everything looks good, then click Back to Dashboard.

Under `APIs & Services` → `Credentials`, click `+ Create Credentials` and select ‘OAuth client ID’.

Under `Application type` select ‘Desktop app’, then `Create`. From the popup window, `Download JSON`. This .json file has the credentials you will use to authenticate the python script, allowing it to access Drive. Keep track of where this downloaded file ends up! You should rename it `credentials.json`, or modify the python script to look for something else.

### 2. Configure python environment to use Drive API

A conda environment is recommended for managing python packages in a more contained way. A pip environment could instead be used, in which case you can replace ‘conda’ with ‘pip’ in the following lines. The conda environment being used for the rest of this repo is fine - you'll just have to add a couple packages.

Within your conda environment, run:

```
conda install google-api-python-client google-auth-httplib2 google-auth-oauthlib
```

You will now have access to the google and googleapiclient python libraries, which handle authentication and programmatic access to Google Drive within your python script.

### 3. Download files with a python script

TL;DR: You should now be able to run `download_drive_files.py`. 

```
python download_drive_files.py --help
```

#### Authentication & Authorization

To link a python script to your Google Drive account, the script needs to follow Google’s authentication and authorization requirements. As we are accessing user data, this must be done with an OAuth client ID. Credentials for this kind of authentication were generated in step 1, and are contained in the .json file you downloaded. You will need to provide the filepath of this .json file to the python script.

In addition to the downloaded credentials, the authentication workflow requires specifying a set of scopes that define the level of access the authenticated script will have. This is referred to as ‘authorization’. The scope(s) you choose depend on what you want to do with the files (view-only, download, edit, etc.). The various scopes can be explored here.

This reference code demonstrates the authentication workflow in python, assuming you’ve named your credentials file credentials.json and placed it beside the python script. After authenticating the first time, it saves a token.json file to be used on subsequent API requests, effectively keeping you logged in.

Your google credentials or token files should not be tracked by version control (e.g. git). gitignore can be a useful tool to automatically ignore files that match certain patterns.The uw-polynya-detection codebase uses an ignored auth/ folder to store credentials and tokens.

#### Retrieving files

Once authenticated, the python script can retrieve information and perform actions on files in a similar way one does through their browser when logged into their google account, with limitations governed by the scopes used during authentication. Actions are performed via a client object;

```
from googleapiclient.discovery import build
client = build('drive', 'v3', credentials=creds)
```

File-oriented actions are performed by the client.files() interface. The API documentation can be consulted for the various actions available. Here, we are interested in identifying all files within a target Drive folder and downloading those files to somewhere on our computer. This is done in four steps:

1. Determine the file ID of the target folder

2. Retrieve all file objects that are contained by this target folder (using the query folder_ID in parents)

3. Download each file to a BytesIO object using Drive’s MediaIoBaseDownload interface

4. Writing each downloaded BytesIO file to disk at the specified location.

This functionality is all packaged into the `download_drive_files.py` script.

