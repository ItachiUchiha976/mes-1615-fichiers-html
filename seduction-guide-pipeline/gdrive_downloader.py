"""
Module 1 – Téléchargement des vidéos depuis Google Drive.

Utilise l'API Google Drive v3 avec OAuth2.
Il liste récursivement tous les fichiers vidéo d'un dossier (ou de tout le Drive)
et les télécharge dans DOWNLOAD_DIR.
"""

import os
import io
import pickle
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from tqdm import tqdm

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

VIDEO_MIME_TYPES = {
    "video/mp4",
    "video/x-msvideo",
    "video/quicktime",
    "video/x-matroska",
    "video/webm",
    "video/mpeg",
    "video/3gpp",
}


def _authenticate(credentials_file: str, token_file: str):
    """Authentifie l'utilisateur et retourne les credentials OAuth2."""
    creds = None
    if os.path.exists(token_file):
        with open(token_file, "rb") as f:
            creds = pickle.load(f)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(credentials_file, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_file, "wb") as f:
            pickle.dump(creds, f)
    return creds


def list_video_files(service, folder_id: str | None = None) -> list[dict]:
    """
    Liste tous les fichiers vidéo accessibles.
    Si folder_id est fourni, se limite à ce dossier (récursivement).
    """
    video_files = []
    page_token = None

    if folder_id:
        query = f"'{folder_id}' in parents and trashed=false"
    else:
        # Cherche parmi tous les fichiers partagés/possédés
        mime_conditions = " or ".join(
            f"mimeType='{m}'" for m in VIDEO_MIME_TYPES
        )
        query = f"({mime_conditions}) and trashed=false"

    while True:
        response = (
            service.files()
            .list(
                q=query,
                spaces="drive",
                fields="nextPageToken, files(id, name, mimeType, size)",
                pageToken=page_token,
                pageSize=1000,
            )
            .execute()
        )
        for f in response.get("files", []):
            if f.get("mimeType") in VIDEO_MIME_TYPES:
                video_files.append(f)
            elif f.get("mimeType") == "application/vnd.google-apps.folder":
                # Récursion dans les sous-dossiers
                video_files.extend(list_video_files(service, folder_id=f["id"]))
        page_token = response.get("nextPageToken")
        if not page_token:
            break
    return video_files


def download_file(service, file_info: dict, dest_dir: Path) -> Path:
    """Télécharge un fichier Drive vers dest_dir, retourne le chemin local."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / file_info["name"]

    if dest_path.exists():
        print(f"  [SKIP] {file_info['name']} déjà téléchargé.")
        return dest_path

    request = service.files().get_media(fileId=file_info["id"])
    total = int(file_info.get("size", 0))

    with open(dest_path, "wb") as fh:
        downloader = MediaIoBaseDownload(fh, request, chunksize=10 * 1024 * 1024)
        with tqdm(
            total=total,
            unit="B",
            unit_scale=True,
            desc=file_info["name"][:50],
            leave=False,
        ) as pbar:
            done = False
            while not done:
                status, done = downloader.next_chunk()
                if status:
                    pbar.update(int(status.resumable_progress) - pbar.n)
    return dest_path


def run(
    credentials_file: str,
    token_file: str,
    download_dir: str,
    folder_id: str | None = None,
) -> list[Path]:
    """
    Point d'entrée principal du module.
    Retourne la liste des chemins locaux des vidéos téléchargées.
    """
    creds = _authenticate(credentials_file, token_file)
    service = build("drive", "v3", credentials=creds)

    print("Listage des vidéos sur Google Drive…")
    videos = list_video_files(service, folder_id=folder_id)
    print(f"  → {len(videos)} vidéo(s) trouvée(s).")

    dest = Path(download_dir)
    local_paths = []
    for v in tqdm(videos, desc="Téléchargement"):
        path = download_file(service, v, dest)
        local_paths.append(path)

    return local_paths
