# law-shorts — 노동 판례 이야기 숏폼 자동 생성기

노동 판례를 **옛날이야기·일상 비유**로 풀어낸 세로 숏폼(1080×1920, 9:16)을 GitHub Actions에서 매일 만들어
인스타그램 릴스·유튜브 쇼츠에 올립니다.

```
data/cases.json 에서 판례 1건 선택 (state.json으로 중복 발행 방지)
 → Gemini: 이야기 대본(JSON) 생성
 → 코드 안전필터: 연도·날짜·사건번호·조문번호가 있으면 탈락 → 재생성(최대 3회)
 → Gemini 2차 검증: 판결요지 vs 대본 결론 대조 — FAIL이면 그날 건너뜀
 → edge-tts 음성 → Pillow 프레임 + FFmpeg 합성(9:16)
 → 인스타 릴스 + (ENABLE_YOUTUBE=true면) 유튜브 업로드
 → data/state.json 커밋
```

## 안전장치

| 장치 | 동작 | 위치 |
|---|---|---|
| 번호·연도 차단 | 대본 전 필드(내레이션·자막·제목·해시태그)를 정규식으로 검사. 전각 숫자 우회도 정규화 후 검사. 걸리면 재생성, 3회 연속이면 건너뜀 | `shorts/safety.py` |
| 판례 정보는 원문만 | 법원·선고일·사건번호·판결요지는 **LLM을 거치지 않고** `cases.json` 값을 마지막 장면에 그대로 표시 | `media.render_case_card` |
| 2차 검증 | 판결요지와 결론 대조. 응답이 정확히 `PASS`일 때만 통과(형식 오류·애매함 = FAIL). 같은 판례 3회 FAIL이면 자동 선택 제외 | `shorts/llm.py` |
| 고지 자동 삽입 | 모든 장면 하단 “AI 각색 교육용 콘텐츠 · 법률자문 아님” + 마지막 장면 음성 고지 + 캡션/설명란 고지. 유튜브는 `containsSyntheticMedia=true` | `media.py`, `main.py`, `publish.py` |
| 미확인 판례 차단 | `verified: true`인 판례만 실제 발행(테스트 모드는 예외) | `cases.select_case` |
| 비밀값 | 전부 GitHub Secrets → 환경변수. 알림·로그에서 비밀값 마스킹. 텔레그램은 `parse_mode` 미사용 | `config.py`, `notify.py` |
| 인젝션 방지 | 워크플로 입력은 env로만 전달, 외부 명령은 `shell=False` 리스트 인자, 판례 id는 `[a-z0-9-]`만 허용(파일명 경로 조작 방지) | 워크플로, `media._run`, `cases.py` |

알림은 **실패할 때만** 텔레그램으로 갑니다(오류, 업로드 실패, 검증 FAIL로 건너뜀 포함). 성공 시엔 조용합니다.

---

## 세팅 순서

### 1단계 — 테스트 모드 (Gemini 키만 있으면 됨)

1. **Gemini API 키 발급**: Google AI Studio에서 API 키 생성.
2. GitHub 저장소 → **Settings → Secrets and variables → Actions → New repository secret**
   - `GEMINI_API_KEY`
3. (권장) 텔레그램 실패 알림
   - @BotFather에서 봇 생성 → 토큰을 `TELEGRAM_BOT_TOKEN`
   - 봇에게 아무 메시지 보낸 뒤 `https://api.telegram.org/bot<토큰>/getUpdates`에서 `chat.id` 확인 → `TELEGRAM_CHAT_ID`
4. **Actions 탭 → daily-short → Run workflow** → `테스트 모드` 체크(기본값) → 실행
5. 완료 후 실행 페이지 하단 **Artifacts**에서 `short-<번호>` 다운로드 → `short.mp4`, `script.json`(대본), `verify.json`(검증 결과), `post.txt`(캡션) 확인

> `GEMINI_API_KEY`가 없어도 테스트 모드는 동작합니다(고정 샘플 대본 + 실제 음성으로 영상 생성, 검증 생략).
> 테스트 모드는 발행도, `state.json` 변경도 하지 않으므로 몇 번이든 반복 실행해도 됩니다.

### 2단계 — 인스타그램 릴스

1. 인스타그램 계정을 **비즈니스/크리에이터 계정**으로 전환하고 페이스북 페이지에 연결
2. Meta for Developers에서 앱 생성 → Instagram Graph API 추가 → 권한 `instagram_basic`, `instagram_content_publish` (페이스북 로그인 방식이면 `pages_show_list`, `pages_read_engagement`도)
3. **장기 액세스 토큰**(약 60일) 발급 → Secret `IG_ACCESS_TOKEN`
4. 인스타 비즈니스 계정 ID → Secret `IG_USER_ID`
5. 토큰 만료 전 갱신 필요(만료되면 업로드 실패 → 텔레그램 알림으로 알 수 있음)

### 3단계 — 유튜브 (선택)

1. Google Cloud Console → 프로젝트 생성 → **YouTube Data API v3** 사용 설정
2. OAuth 동의 화면 구성 → OAuth 클라이언트 ID(**데스크톱 앱**) 생성 → `client_secret.json` 다운로드
3. 로컬 PC에서:
   ```bash
   pip install google-auth-oauthlib
   python scripts/get_youtube_token.py client_secret.json
   ```
4. 출력값을 Secrets `YT_CLIENT_ID`, `YT_CLIENT_SECRET`, `YT_REFRESH_TOKEN`에 저장
5. (자동) 토큰이 등록되면 유튜브 업로드가 자동으로 켜집니다. 처음엔 Variables에 `YT_PRIVACY=private` 권장

> OAuth 동의 화면이 “테스트” 상태면 refresh token이 7일 후 만료됩니다. 운영 시 “프로덕션”으로 게시하세요.
> 미인증 API 프로젝트로 올린 영상은 비공개로 잠길 수 있습니다(유튜브 정책). 처음엔 `YT_PRIVACY=private`로 확인 권장.

### 4단계 — 실제 발행 확인 후 매일 자동 실행

- 수동 실행에서 `테스트 모드` 체크를 **해제**하고 한 번 돌려 실제 업로드를 확인
- **Secrets만 넣으면 끝입니다.** `GEMINI_API_KEY` + (인스타 또는 유튜브 토큰)이 들어오는 순간부터 매일 **18:17 KST**에 자동 생성·업로드됩니다. 그 전에는 매일 조용히 대기만 합니다(알림 없음)(`.github/workflows/daily-short.yml`의 `cron`으로 변경)
- 발행된 판례는 `data/state.json`에 기록·커밋되어 다시 선택되지 않습니다

## 설정값 요약

**Secrets** (필수 표시는 해당 기능 사용 시)

| 이름 | 용도 |
|---|---|
| `GEMINI_API_KEY` | 대본 생성·검증 (필수) |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | 실패 알림 |
| `IG_USER_ID`, `IG_ACCESS_TOKEN` | 인스타 릴스 |
| `YT_CLIENT_ID`, `YT_CLIENT_SECRET`, `YT_REFRESH_TOKEN` | 유튜브 |

**Variables** (비밀 아님, 비워두면 기본값)

| 이름 | 기본값 | 설명 |
|---|---|---|
| `ENABLE_SCHEDULE` | (켜짐) | `false`로 두면 매일 자동 실행을 완전히 끔 |
| `ENABLE_YOUTUBE` | 토큰 있으면 켜짐 | 유튜브 업로드 강제 on/off |
| `ENABLE_INSTAGRAM` | 토큰 있으면 켜짐 | 인스타 업로드 강제 on/off |
| `GEMINI_MODEL` | `gemini-2.5-flash` | 모델명이 바뀌거나 폐기되면 여기서 교체 |
| `TTS_VOICE` | `ko-KR-SunHiNeural` | edge-tts 음성 (`ko-KR-InJoonNeural` 등) |
| `YT_PRIVACY` | `public` | `public` / `unlisted` / `private` |

## 판례 추가하기

`data/cases.json`의 `cases` 배열에 추가합니다. **파일 순서대로** 아직 발행 안 된 판례가 선택됩니다.

```json
{
  "id": "영문소문자-숫자-하이픈",
  "title": "화면에 보일 쟁점 한 줄",
  "court": "대법원",
  "decision_type": "판결",
  "date": "YYYY. M. D.",
  "case_no": "원문 그대로",
  "issue": "무엇이 쟁점이었는지",
  "holding": "판결요지 (영상 마지막 장면에 원문 표시, 대본 결론의 기준)",
  "verified": true,
  "verified_note": "어디서 확인했는지"
}
```

- `case_no`, `date`, `holding`은 **대법원 종합법률정보(glaw.scourt.go.kr) 또는 국가법령정보센터에서 원문 확인 후** 입력하세요. 코드는 이 값을 검증하지 못하고 그대로 표시합니다.
- 확인이 덜 됐으면 `"verified": false`로 두면 테스트 모드에서만 쓰이고 발행되지 않습니다.
- 판결요지가 너무 길면 마지막 장면에 들어가지 않아 오류가 납니다(글자 크기 자동 축소 후에도 안 들어갈 때).

### 수록된 샘플 판례

| id | 판례 | 확인 상태 |
|---|---|---|
| `severance-installment-2010` | 대법원 2010. 5. 20. 선고 2007다90760 전원합의체 판결 (퇴직금 분할 약정) | 2차 자료(법률신문, 법무법인 지평 뉴스레터)로 교차확인 |
| `ordinary-wage-fixedness-2024` | 대법원 2024. 12. 19. 선고 2020다247190 전원합의체 판결 (통상임금 고정성 폐기) | 2차 자료(법무법인 세종 해설, 법률신문)로 교차확인. 새 법리의 적용 범위 세부는 원문 확인 필요 |

> 2013년 통상임금 전원합의체 판결(2012다89399)은 2024년 판결로 ‘고정성’ 부분이 변경되어 샘플에서 제외했습니다.

## 로컬 개발

```bash
sudo apt-get install ffmpeg fonts-noto-cjk
pip install -r requirements.txt
python -m pytest -q                                  # 안전 필터·선택 로직 테스트
python -m shorts.main --test --offline               # Gemini·TTS 없이 고정 대본+무음으로 렌더링만 확인
GEMINI_API_KEY=... python -m shorts.main --test      # 실제 대본·음성으로 영상 생성(발행 안 함)
```

결과물: `output/<날짜>_<판례id>/short.mp4`

## 구조

```
shorts/
  config.py   설정(환경변수), 고지 문구, 비밀값 마스킹
  cases.py    판례 로드·검증·선택, state.json 관리
  safety.py   연도·사건번호·조문번호 차단 정규식
  llm.py      Gemini 대본 생성 + 2차 검증
  media.py    edge-tts, Pillow 프레임, FFmpeg 합성
  publish.py  인스타 릴스(resumable 업로드), 유튜브(Data API v3)
  notify.py   텔레그램 실패 알림
  main.py     파이프라인
data/cases.json   판례 원문 데이터
data/state.json   발행 이력·검증 실패 횟수
```

## 알려진 한계

- **인스타·유튜브 업로드 코드는 실제 계정으로 테스트되지 않았습니다.** 이 저장소에서 검증된 것은 테스트 모드(영상 생성)까지입니다. 첫 실발행은 `YT_PRIVACY=private`처럼 안전한 설정으로 확인하세요.
- 인스타 업로드는 Graph API의 resumable 업로드(`upload_type=resumable`, `rupload.facebook.com`)를 씁니다. Meta가 API 버전을 바꾸면 `IG_GRAPH_VERSION` 환경변수로 버전을 올려야 할 수 있습니다.
- 안전 필터는 보수적으로 설계되어 “3조 원” 외의 `N조`, `N항` 같은 일상 표현도 탈락시킵니다(재생성으로 해결).
- 2차 검증도 LLM이므로 100% 보장은 아닙니다. 초기엔 테스트 모드 결과(`script.json`)를 사람이 함께 검토하는 것을 권장합니다.
- 생성물은 교육용 각색이며 법률자문이 아닙니다.
