"""YouTube Data API v3 client — upload videos using OAuth2 refresh token."""
import logging
import os
import json

logger = logging.getLogger(__name__)

_TOKEN_URL = "https://oauth2.googleapis.com/token"
_UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos"
_YT_SCOPE = "https://www.googleapis.com/auth/youtube.upload"


def _get_access_token(client_id, client_secret, refresh_token):
    import requests
    resp = requests.post(_TOKEN_URL, data={
        "grant_type": "refresh_token",
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
    }, timeout=15)
    if not resp.ok:
        raise RuntimeError(f"YouTube token refresh failed {resp.status_code}: {resp.text}")
    return resp.json()["access_token"]


def get_auth_url(client_id, redirect_uri):
    from urllib.parse import urlencode
    return "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode({
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": _YT_SCOPE,
        "access_type": "offline",
        "prompt": "consent",
    })


def exchange_code(client_id, client_secret, code, redirect_uri):
    import requests
    resp = requests.post(_TOKEN_URL, data={
        "grant_type": "authorization_code",
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "redirect_uri": redirect_uri,
    }, timeout=15)
    if not resp.ok:
        raise RuntimeError(f"YouTube code exchange failed {resp.status_code}: {resp.text}")
    data = resp.json()
    refresh_token = data.get("refresh_token", "")
    if not refresh_token:
        raise RuntimeError("No refresh_token returned. Ensure offline access + consent prompt.")
    return refresh_token


def upload_video(client_id, client_secret, refresh_token, video_path, title, description, privacy="public"):
    """Upload a video file to YouTube. Returns the YouTube video URL."""
    import requests
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video file not found: {video_path}")
    access_token = _get_access_token(client_id, client_secret, refresh_token)
    metadata = {
        "snippet": {"title": title[:100], "description": description[:5000], "categoryId": "22"},
        "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": False},
    }
    file_size = os.path.getsize(video_path)
    init_resp = requests.post(
        _UPLOAD_URL + "?uploadType=resumable&part=snippet,status",
        headers={
            "Authorization": f"Bearer {access_token}",
            "X-Upload-Content-Type": "video/mp4",
            "X-Upload-Content-Length": str(file_size),
            "Content-Type": "application/json",
        },
        data=json.dumps(metadata),
        timeout=30,
    )
    if not init_resp.ok:
        raise RuntimeError(f"YouTube upload init failed {init_resp.status_code}: {init_resp.text}")
    upload_url = init_resp.headers.get("Location")
    if not upload_url:
        raise RuntimeError("YouTube did not return upload Location header")
    with open(video_path, "rb") as f:
        upload_resp = requests.put(
            upload_url,
            headers={"Authorization": f"Bearer {access_token}", "Content-Type": "video/mp4", "Content-Length": str(file_size)},
            data=f,
            timeout=600,
        )
    if upload_resp.status_code not in (200, 201):
        raise RuntimeError(f"YouTube upload failed {upload_resp.status_code}: {upload_resp.text}")
    video_id = upload_resp.json().get("id", "")
    if not video_id:
        raise RuntimeError(f"YouTube upload succeeded but no video id: {upload_resp.text}")
    url = f"https://www.youtube.com/watch?v={video_id}"
    logger.info(f"YouTube video uploaded: {url}")
    return url
