import os
import logging
from datetime import datetime, timedelta
from pytube import Channel
import google_auth_oauthlib.flow
import googleapiclient.discovery
import googleapiclient.errors
import googleapiclient.http
import moviepy.editor as mp
from urllib.error import HTTPError

# Constants
DOWNLOAD_PATH = "/tmp"
LOGO_PATH = "/tmp/logo.png"
END_VIDEO_PATH = "/tmp/end_video.mp4"
LAST_CHECK_FILE = "/tmp/last_check.txt"
CLIENT_SECRETS_FILE = "/tmp/client_secrets.json"

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s:%(levelname)s:%(message)s')

def read_last_check():
    if os.path.exists(LAST_CHECK_FILE):
        with open(LAST_CHECK_FILE, "r") as file:
            return datetime.fromisoformat(file.read().strip())
    return datetime.utcnow() - timedelta(hours=1)

def write_last_check():
    with open(LAST_CHECK_FILE, "w") as file:
        file.write(datetime.utcnow().isoformat())

def download_new_videos(channel_url):
    try:
        last_check = read_last_check()
        channel = Channel(channel_url)
        new_videos = [video for video in channel.videos if video.publish_date > last_check]
        video_files = []
        for video in new_videos:
            logging.info(f"Downloading {video.watch_url}")
            video_file = video.streams.get_highest_resolution().download(output_path=DOWNLOAD_PATH)
            video_files.append(video_file)
        write_last_check()
        return video_files
    except HTTPError as e:
        logging.error(f"HTTP error occurred: {e}")
        logging.error(f"Failed to download videos from {channel_url}")
        return []
    except Exception as e:
        logging.error(f"An error occurred: {e}")
        return []

def add_logo_and_append_video(video_file, output_file):
    video = mp.VideoFileClip(video_file)
    logo = mp.ImageClip(LOGO_PATH).set_duration(video.duration).resize(height=50).margin(right=8, top=8, opacity=0).set_pos(("right", "top"))
    video_with_logo = mp.CompositeVideoClip([video, logo])
    end_video = mp.VideoFileClip(END_VIDEO_PATH)
    final_video = mp.concatenate_videoclips([video_with_logo, end_video])
    final_video.write_videofile(output_file, codec="libx264")

def upload_video(video_file, title, description, tags, category, privacy_status):
    scopes = ["https://www.googleapis.com/auth/youtube.upload"]
    flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS_FILE, scopes)
    credentials = flow.run_console()
    youtube = googleapiclient.discovery.build("youtube", "v3", credentials=credentials)
    
    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": category
        },
        "status": {
            "privacyStatus": privacy_status
        }
    }
    
    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=googleapiclient.http.MediaFileUpload(video_file)
    )
    
    response = request.execute()
    logging.info(f"Video uploaded successfully: {response['id']}")

def main():
    channel_url = "https://studio.youtube.com/channel/UCTD4XeJX1meLq4DokXuzYZg"  # Replace with a valid channel URL
    logging.info(f"Checking for new videos on channel: {channel_url}")
    video_files = download_new_videos(channel_url)
    for video_file in video_files:
        output_file = os.path.join(DOWNLOAD_PATH, f"processed_{os.path.basename(video_file)}")
        add_logo_and_append_video(video_file, output_file)
        upload_video(output_file, "Video Title", "Video Description", ["tag1", "tag2"], "22", "public")
    return "Success"

if __name__ == "__main__":
    main()
