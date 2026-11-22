"""(로컬 PC에서 1회 실행) 유튜브 업로드용 refresh token 발급.

  pip install google-auth-oauthlib
  python scripts/get_youtube_token.py client_secret.json

출력된 값 3개를 GitHub Secrets(YT_CLIENT_ID / YT_CLIENT_SECRET / YT_REFRESH_TOKEN)에 넣는다.
client_secret.json과 출력값은 절대 커밋하지 말 것(.gitignore 처리됨).
"""
import json
import sys

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/spreadsheets",  # 숏폼로그 시트 읽기/기록(백업 자동화용)
]

if len(sys.argv) != 2:
    sys.exit("사용법: python scripts/get_youtube_token.py client_secret.json")
flow = InstalledAppFlow.from_client_secrets_file(sys.argv[1], SCOPES)
creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")
info = json.load(open(sys.argv[1]))
cfg = info.get("installed") or info.get("web")
print("YT_CLIENT_ID     =", cfg["client_id"])
print("YT_CLIENT_SECRET =", cfg["client_secret"])
print("YT_REFRESH_TOKEN =", creds.refresh_token)
