import os
import requests
from tqdm import tqdm

from config import settings


def download_file(url, output_path, chunk_size=1024*1024):
    """
    Download a file from a URL in chunks and save it to the output path.
    
    Args:
    - url (str): URL of the file to download.
    - output_path (str): Local path to save the downloaded file.
    - chunk_size (int): Size of each chunk to download. Default is 1MB.
    """
    # Ensure the output directory exists
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # Get the size of the file to be downloaded
    response = requests.get(url, stream=True)
    file_size = int(response.headers.get('content-length', 0))
    print(f"File size: {file_size / (1024 * 1024):.2f} MB")

    # Check if the file already exists and get its size
    if os.path.exists(output_path):
        downloaded_size = os.path.getsize(output_path)
        if downloaded_size >= file_size:
            print("File already downloaded.")
            return
    else:
        downloaded_size = 0

    # Download the file in chunks
    headers = {"Range": f"bytes={downloaded_size}-"}
    response = requests.get(url, headers=headers, stream=True)

    progress = tqdm(total=file_size, initial=downloaded_size, unit='B', unit_scale=True, desc=output_path)

    with open(output_path, "ab") as file:
        for chunk in response.iter_content(chunk_size=chunk_size):
            if chunk:
                file.write(chunk)
                progress.update(len(chunk))

    progress.close()
    print("Download completed.")
