import os
import json
import logging
import google.auth
import google.auth.transport.requests
import google.oauth2.credentials
import google_auth_oauthlib.flow
import googleapiclient.discovery
import googleapiclient.errors
import googleapiclient.http
import moviepy.editor as mp
from datetime import datetime, timedelta, timezone
import subprocess
from PIL import Image  # Import Pillow for image processing

# Constants
DOWNLOAD_PATH = os.getenv('DOWNLOAD_PATH', "/tmp/downloads")
LOGO_PATH = os.getenv('LOGO_PATH', "logo.png")
END_VIDEO_PATH = os.getenv('END_VIDEO_PATH', "end_video.mp4")
CLIENT_SECRETS_FILE = "client_secrets.json"
CREDENTIALS_FILE = "youtube_credentials.json"
COMMON_DESCRIPTION = "Your common description here"
YOUTUBE_API_SERVICE_NAME = "youtube"
YOUTUBE_API_VERSION = "v3"
CHANNEL_ID = "UC1NF71EwP41VdjAU1iXdLkw"  # Replace with your actual channel ID

# Ensure the download path exists
os.makedirs(DOWNLOAD_PATH, exist_ok=True)

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s:%(levelname)s:%(message)s')

def get_authenticated_service():
    credentials = None
    if os.path.exists(CREDENTIALS_FILE):
        with open(CREDENTIALS_FILE, 'r') as f:
            credentials_info = json.load(f)
            credentials = google.oauth2.credentials.Credentials.from_authorized_user_info(credentials_info)

    if not credentials or not credentials.valid:
        if credentials and credentials.expired and credentials.refresh_token:
            request = google.auth.transport.requests.Request()
            credentials.refresh(request)
        else:
            flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file(
                CLIENT_SECRETS_FILE, scopes=["https://www.googleapis.com/auth/youtube.force-ssl"]
            )
            credentials = flow.run_local_server(port=0)

        with open(CREDENTIALS_FILE, 'w') as f:
            f.write(credentials.to_json())

    return googleapiclient.discovery.build(
        YOUTUBE_API_SERVICE_NAME, YOUTUBE_API_VERSION, credentials=credentials
    )

def get_recent_videos(youtube, channel_id):
    request = youtube.search().list(
        part="snippet",
        channelId=channel_id,
        order="date",
        publishedAfter=(datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
        maxResults=50
    )
    response = request.execute()
    videos = []
    for item in response.get("items", []):
        if item["id"]["kind"] == "youtube#video":
            videos.append({
                "video_id": item["id"]["videoId"],
                "title": item["snippet"]["title"],
                "description": item["snippet"]["description"],
                "tags": item["snippet"].get("tags", []),
                "thumbnail_url": item["snippet"]["thumbnails"]["high"]["url"]
            })
    return videos

def download_video(video_id):
    try:
        video_url = f"https://www.youtube.com/watch?v={video_id}"
        output_path = os.path.join(DOWNLOAD_PATH, f"{video_id}.mp4")
        subprocess.run(["yt-dlp", "--verbose", "-o", output_path, video_url], check=True)
        return output_path
    except subprocess.CalledProcessError as e:
        logging.error(f"Failed to download video {video_id}: {e}")
        return None

def add_logo_and_append_video(video_file, output_file):
    try:
        video = mp.VideoFileClip(video_file)
        # Resize logo using Pillow
        with Image.open(LOGO_PATH) as logo_img:
            logo_img = logo_img.resize((int(logo_img.width / 2), int(logo_img.height / 2)), Image.Resampling.LANCZOS)
            logo_img.save(LOGO_PATH)  # Save the resized logo back to disk if needed
        
        logo = mp.ImageClip(LOGO_PATH).set_duration(video.duration).resize(height=50).margin(right=8, top=8, opacity=0).set_pos(("right", "top"))
        video_with_logo = mp.CompositeVideoClip([video, logo])
        end_video = mp.VideoFileClip(END_VIDEO_PATH)
        final_video = mp.concatenate_videoclips([video_with_logo, end_video])
        final_video.write_videofile(output_file, codec="libx264")
        logging.info(f"Processed video file {output_file}.")
    except Exception as e:
        logging.error(f"Failed to process video {video_file}: {e}")

def upload_video(youtube, video_file, title, description, tags, thumbnail_url):
    try:
        body = {
            "snippet": {
                "title": title,
                "description": description,
                "tags": tags,
                "categoryId": "22",  # Change this to the appropriate category ID
                "thumbnails": {
                    "default": {
                        "url": thumbnail_url
                    }
                }
            },
            "status": {
                "privacyStatus": "public"  # Options: "public", "private", "unlisted"
            }
        }
        
        request = youtube.videos().insert(
            part="snippet,status",
            body=body,
            media_body=googleapiclient.http.MediaFileUpload(video_file)
        )
        
        response = request.execute()
        logging.info(f"Video uploaded successfully: {response['id']}")
    except Exception as e:
        logging.error(f"Failed to upload video {video_file}: {e}")

def main():
    logging.info(f"Checking for new videos on channel: https://www.youtube.com/channel/{CHANNEL_ID}")
    youtube = get_authenticated_service()
    videos = get_recent_videos(youtube, CHANNEL_ID)
    
    if not videos:
        logging.info("No new videos found.")
        return

    for video in videos:
        video_file = download_video(video["video_id"])
        if not video_file:
            logging.error(f"Failed to download video {video['video_id']}")
            continue
        output_file = os.path.join(DOWNLOAD_PATH, f"processed_{os.path.basename(video_file)}")
        add_logo_and_append_video(video_file, output_file)
        upload_video(youtube, output_file, video["title"], video["description"], video["tags"], video["thumbnail_url"])

    logging.info("Script completed successfully.")
    return "Success"

if __name__ == "__main__":
    main()
