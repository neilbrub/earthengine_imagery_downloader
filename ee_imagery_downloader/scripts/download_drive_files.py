import os
import io
import argparse
from tqdm import tqdm

from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.auth.exceptions import RefreshError
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload

"""
This is a command-line script to download all files in a specified
Google Drive folder to a specified directory on your computer.

This script uses the google drive API, which can be reviewed here:
https://developers.google.com/drive/api/guides/about-sdk.

An authentication token is needed to connect to Google Drive via a
Google Cloud project that specifies which google user's account to
connect to for Drive access.
"""

# OAuth2 token downloaded from Google Cloud project
AUTH_DIR = './auth/'
SCOPES = ['https://www.googleapis.com/auth/drive.readonly']


def parse_args():
    """
    Parse command-line arguments that configure this script.
    Run `python download_imagery_from_drive.py --help` to see options.
    """
    parser = argparse.ArgumentParser(
        prog='Drive Downloader',
        description='Download files from a specified Google Drive folder'
    )
    parser.add_argument('--drive-folder', '-i', required=True,
        help="Drive folder name from which to download all files")
    parser.add_argument('--output-dir', '-o', default=None, required=False,
        help="Path to local directory where you want the Drive files downloaded to")
    parser.add_argument('--test', action='store_true',
        help="Test run - print filenames that would be downloaded, but don't download anything.")

    args = parser.parse_args()
    return {
        'drive_folder': args.drive_folder,
        'output_dir': args.output_dir,
        'test': args.test
    }


def authenticate_gcp_oauth2(auth_dir, scopes):
    creds = None

    # Check for existing token
    if os.path.exists(os.path.join(auth_dir, 'token.json')):
        creds = Credentials.from_authorized_user_file(auth_dir + 'token.json', scopes)
    
    if creds and creds.valid: return creds

    # If no or expired token, log user in with credentials
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            return creds
        except RefreshError:
            # Expired token; remove it and go from scratch
            print("Removing expired token...")
            os.remove(os.path.join(auth_dir, 'token.json'))

    # Authenticate from scratch using downloaded credentials
    if not os.path.exists(os.path.join(auth_dir, 'credentials.json')):
        raise FileNotFoundError(f"Must have a credentials.json file in {auth_dir}")
    flow = InstalledAppFlow.from_client_secrets_file(
        os.path.join(auth_dir, 'credentials.json'), scopes)
    creds = flow.run_local_server(port=0)
    
    # Save the credentials for the next run
    with open(os.path.join(auth_dir, 'token.json'), 'w') as token:
        token.write(creds.to_json())

    return creds


def download(drive_folder, output_dir=None, test_run=False):
    if not output_dir and not test_run:
        raise ValueError("output_dir must be specified if not test run") 
    
    if output_dir and not os.path.exists(output_dir): os.makedirs(output_dir)

    creds = authenticate_gcp_oauth2(AUTH_DIR, SCOPES)

    files = []

    try:
        client = build('drive', 'v3', credentials=creds)

        # Get ID of target folder
        response = client.files().list(
            q=f"name = '{drive_folder}' and mimeType = 'application/vnd.google-apps.folder'",
            fields="files(id)"
        ).execute()
        items = response.get('files', [])
        if not items:
            raise FileNotFoundError(f"{drive_folder} folder not found in Google Drive")
        elif len(items) > 1:
            raise ValueError(f"Multiple folders named {drive_folder} found in Google Drive; "
                             "Please remove duplicates before trying again (may need to empty trash!)")
        folder_id = items[0]['id']

        page_token = None

        # Get ID of all files in folder (accumulate over all pages)
        print(f"Retrieving all files in {drive_folder}...")
        while True:
            response = client.files().list(
                q=f"'{folder_id}' in parents",
                pageSize=10,
                fields="nextPageToken, files(id,name)",
                pageToken=page_token
            ).execute()

            # Accumulate files
            items = response.get('files', [])
            files.extend(items)

            # Go to next page or end if last
            page_token = response.get('nextPageToken', None)
            if page_token is None:
                break

    except HttpError as error:
        print(f'HTTP error encountered: {error}')
        return

    print(f"> Found {len(files)} files.")

    # If test run, just print file names & exit
    if test_run:
        for file in files:
            print(f"> {file['name']}")
        return
    
    # Else, download files one by one (track duplicates)
    fn_counts = {}
    print(f"Downloading to {output_dir}...")
    for file in tqdm(files):
    # for file in files:
        file_id = file['id']

        try:
            file_request = client.files().get_media(fileId=file_id)

            bytes_file = io.BytesIO()
            downloader = MediaIoBaseDownload(bytes_file, file_request)
            done = False
            while done is False:
                status, done = downloader.next_chunk()
            
            # Save the BytesIO file to disk
            out_fp = os.path.join(output_dir, file['name'])
            if out_fp not in fn_counts: fn_counts[out_fp] = 1
            else:
                fn_counts[out_fp] += 1
                out_fp = f"{'.'.join(out_fp.split('.')[:-1])}_{fn_counts[out_fp]}.{out_fp.split('.')[-1]}" 

            with open(out_fp, 'wb') as f:
                f.write(bytes_file.getbuffer())
        
        except HttpError as error:
            print(f"HTTP error while downloading {file['name']}; skipping")

    for fn, counts in fn_counts.items():
        if counts > 1: print(f"Duplicate file: {fn} ({counts} instances)")


if __name__ == "__main__":
    args = parse_args()
    download(args['drive_folder'], args['output_dir'], test_run=args['test'])

