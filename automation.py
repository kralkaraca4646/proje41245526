import json
import os
import subprocess
import sys

import gspread
from google.oauth2.service_account import Credentials as SACredentials
from google.oauth2.credentials import Credentials as UserCredentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

READY_STATUSES = {"hazır", "hazir", "bekliyor", ""}

# Sabit açıklama metni - istediğin gibi düzenle
FIXED_DESCRIPTION = """#shorts #keşfet #viral #trend #eğlence"""


def get_sheet():
    creds_dict = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"])
    creds = SACredentials.from_service_account_info(
        creds_dict, scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
    gc = gspread.authorize(creds)
    return gc.open_by_key(os.environ["SHEET_ID"]).sheet1


def find_ready_row(sheet):
    rows = sheet.get_all_values()
    for i, row in enumerate(rows[1:], start=2):
        url = row[1].strip() if len(row) > 1 else ""              # B: link
        sheet_title = row[2].strip() if len(row) > 2 else ""      # C: başlık
        status = row[3].strip().lower() if len(row) > 3 else ""   # D: Durum
        if url and status in READY_STATUSES:
            return i, url, sheet_title
    return None, None, None


def download_video(url):
    result = subprocess.run(
        [
            "yt-dlp",
            "-f", "bestvideo+bestaudio/best",
            "--merge-output-format", "mp4",
            "-o", "video.mp4",
            url,
        ],
        capture_output=True,
        text=True,
    )
    print(result.stdout)
    print(result.stderr)
    if result.returncode != 0:
        raise RuntimeError("Video indirilemedi")


def upload_to_youtube(title, description):
    oauth_data = json.loads(os.environ["YOUTUBE_OAUTH_JSON"])
    client = oauth_data["installed"]

    creds = UserCredentials(
        token=None,
        refresh_token=os.environ["YOUTUBE_REFRESH_TOKEN"],
        token_uri=client["token_uri"],
        client_id=client["client_id"],
        client_secret=client["client_secret"],
        scopes=["https://www.googleapis.com/auth/youtube.upload"],
    )

    youtube = build("youtube", "v3", credentials=creds)

    body = {
        "snippet": {"title": title, "description": description, "categoryId": "22"},
        "status": {"privacyStatus": "private"},
    }

    media = MediaFileUpload("video.mp4", chunksize=-1, resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"Upload %{int(status.progress() * 100)}")

    return response["id"]


def main():
    sheet = get_sheet()

    row, url, sheet_title = find_ready_row(sheet)
    if not url:
        print("İşlenecek video yok (Hazır/Bekliyor durumunda satır bulunamadı).")
        return

    print(f"Seçilen video: {url} (satır {row})")
    sheet.update_cell(row, 4, "İşleniyor")

    try:
        download_video(url)

        title = sheet_title if sheet_title else "Otomatik Video"
        video_id = upload_to_youtube(title, FIXED_DESCRIPTION)

        sheet.update_cell(row, 4, "Yüklendi")
        sheet.update_cell(row, 5, video_id)
        print(f"Tamamlandı! YouTube ID: {video_id}")

    except Exception as e:
        print(f"Hata oluştu: {e}")
        sheet.update_cell(row, 4, "Hata")
        sys.exit(1)


if __name__ == "__main__":
    main()
