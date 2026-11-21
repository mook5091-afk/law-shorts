"""인스타그램 릴스 / 유튜브 업로드. 테스트 모드에서는 호출되지 않는다."""
from __future__ import annotations

import time
from pathlib import Path

import requests

from .config import Settings


class PublishError(RuntimeError):
    pass


# ---------- Instagram (Graph API, resumable upload) ----------
def upload_instagram_reel(settings: Settings, video: Path, caption: str) -> str:
    """Instagram Graph API의 resumable 업로드로 릴스를 게시하고 permalink(또는 media id)를 반환.

    흐름: 컨테이너 생성(upload_type=resumable) → rupload 서버로 파일 전송 → 처리 완료 대기 → media_publish
    """
    if not (settings.ig_user_id and settings.ig_access_token):
        raise PublishError("IG_USER_ID / IG_ACCESS_TOKEN 미설정")
    base = f"https://graph.facebook.com/{settings.ig_graph_version}"
    auth = {"Authorization": f"Bearer {settings.ig_access_token}"}

    r = requests.post(f"{base}/{settings.ig_user_id}/media", headers=auth, timeout=60, data={
        "media_type": "REELS", "upload_type": "resumable", "caption": caption, "share_to_feed": "true",
    })
    if r.status_code != 200:
        raise PublishError(f"IG 컨테이너 생성 실패 HTTP {r.status_code}: {r.text[:300]}")
    j = r.json()
    container_id = j["id"]
    upload_uri = j.get("uri") or (
        f"https://rupload.facebook.com/ig-api-upload/{settings.ig_graph_version}/{container_id}")

    size = video.stat().st_size
    with video.open("rb") as fh:
        r = requests.post(upload_uri, data=fh, timeout=600, headers={
            "Authorization": f"OAuth {settings.ig_access_token}",
            "offset": "0", "file_size": str(size), "Content-Type": "application/octet-stream",
        })
    if r.status_code != 200:
        raise PublishError(f"IG 업로드 실패 HTTP {r.status_code}: {r.text[:300]}")

    for _ in range(60):  # 최대 약 10분 대기
        s = requests.get(f"{base}/{container_id}", headers=auth, timeout=30,
                         params={"fields": "status_code,status"}).json()
        code = s.get("status_code")
        if code == "FINISHED":
            break
        if code in ("ERROR", "EXPIRED"):
            raise PublishError(f"IG 처리 실패: {s}")
        time.sleep(10)
    else:
        raise PublishError("IG 처리 시간 초과")

    r = requests.post(f"{base}/{settings.ig_user_id}/media_publish", headers=auth, timeout=60,
                      data={"creation_id": container_id})
    if r.status_code != 200:
        raise PublishError(f"IG 게시 실패 HTTP {r.status_code}: {r.text[:300]}")
    media_id = r.json()["id"]
    try:
        p = requests.get(f"{base}/{media_id}", headers=auth, timeout=30,
                         params={"fields": "permalink"}).json()
        return p.get("permalink") or media_id
    except requests.RequestException:
        return media_id


# ---------- YouTube (Data API v3) ----------
def upload_youtube(settings: Settings, video: Path, title: str, description: str,
                   tags: list[str]) -> str:
    if not (settings.yt_client_id and settings.yt_client_secret and settings.yt_refresh_token):
        raise PublishError("YT_CLIENT_ID / YT_CLIENT_SECRET / YT_REFRESH_TOKEN 미설정")
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    creds = Credentials(
        token=None, refresh_token=settings.yt_refresh_token, client_id=settings.yt_client_id,
        client_secret=settings.yt_client_secret, token_uri="https://oauth2.googleapis.com/token",
        scopes=["https://www.googleapis.com/auth/youtube.upload"],
    )
    yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
    body = {
        "snippet": {"title": title[:95], "description": description[:4900],
                    "tags": [t.lstrip("#") for t in tags][:15], "categoryId": "27"},  # 27 = Education
        "status": {"privacyStatus": settings.yt_privacy, "selfDeclaredMadeForKids": False,
                   "containsSyntheticMedia": True},  # AI 생성 콘텐츠 고지
    }
    req = yt.videos().insert(part="snippet,status", body=body,
                             media_body=MediaFileUpload(str(video), mimetype="video/mp4", resumable=True))
    resp = None
    while resp is None:
        _, resp = req.next_chunk()
    return f"https://youtube.com/shorts/{resp['id']}"
