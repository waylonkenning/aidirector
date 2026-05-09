import os
import pickle
import google_auth_oauthlib.flow
import googleapiclient.discovery
import googleapiclient.errors
from google.auth.transport.requests import Request
from googleapiclient.http import MediaFileUpload

# The SCOPES for YouTube Data API v3
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

class YouTubeUploader:
    def __init__(self, client_secrets_file="client_secrets.json", token_file="token.pickle"):
        self.client_secrets_file = client_secrets_file
        self.token_file = token_file
        self.youtube = self._get_authenticated_service()

    def _get_authenticated_service(self):
        credentials = None
        # The file token.pickle stores the user's access and refresh tokens
        if os.path.exists(self.token_file):
            with open(self.token_file, "rb") as token:
                credentials = pickle.load(token)
                
        # If there are no (valid) credentials available, let the user log in.
        if not credentials or not credentials.valid:
            if credentials and credentials.expired and credentials.refresh_token:
                credentials.refresh(Request())
            else:
                if not os.path.exists(self.client_secrets_file):
                    raise FileNotFoundError(
                        f"Missing {self.client_secrets_file}. Please follow instructions "
                        "to create a Google Cloud Project and download OAuth2 credentials."
                    )
                flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file(
                    self.client_secrets_file, SCOPES
                )
                credentials = flow.run_local_server(port=0)
            
            # Save the credentials for the next run
            with open(self.token_file, "wb") as token:
                pickle.dump(credentials, token)

        return googleapiclient.discovery.build("youtube", "v3", credentials=credentials)

    def upload_video(self, file_path, title, description, category_id="22", tags=None, privacy_status="private", thumbnail_path=None):
        """
        Uploads a video to YouTube.
        - file_path: Path to the video file.
        - title: Video title.
        - description: Video description.
        - category_id: YouTube category ID (22 is People & Blogs).
        - tags: List of tags.
        - privacy_status: 'public', 'private', or 'unlisted'.
        - thumbnail_path: Path to the thumbnail image (optional).
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Video file not found: {file_path}")

        body = {
            "snippet": {
                "title": title,
                "description": description,
                "tags": tags or [],
                "categoryId": category_id
            },
            "status": {
                "privacyStatus": privacy_status
            }
        }

        # Call the API's videos.insert method to create and upload the video.
        media = MediaFileUpload(file_path, chunksize=-1, resumable=True, mimetype="video/mp4")
        
        request = self.youtube.videos().insert(
            part="snippet,status",
            body=body,
            media_body=media
        )

        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                print(f"Uploaded {int(status.progress() * 100)}%")

        video_id = response.get("id")
        print(f"Video id '{video_id}' was successfully uploaded.")

        # Set custom thumbnail if provided
        if thumbnail_path and os.path.exists(thumbnail_path):
            try:
                self.youtube.thumbnails().set(
                    videoId=video_id,
                    media_body=MediaFileUpload(thumbnail_path)
                ).execute()
                print("Thumbnail set successfully.")
            except Exception as e:
                print(f"Error setting thumbnail: {e}")

        return video_id

if __name__ == "__main__":
    # Example usage for manual testing
    # uploader = YouTubeUploader()
    # uploader.upload_video("path/to/video.mp4", "Test Title", "Test Description")
    pass
