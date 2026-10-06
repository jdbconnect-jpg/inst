# Instagram Reels Studio

대본 JSON과 이미지·음성으로 세로 영상을 만들고, Meta 공식 Instagram API로 릴스를 게시하는 독립 프로젝트입니다. 기존 `agent`, `shot` 저장소를 참조하지 않습니다.

## 가능한 작업

- 장면별 한글 제목·본문, 배경색 또는 이미지, 페이드 효과를 포함한 **1080×1920 / 30fps MP4** 제작
- 선택한 음성·음악 파일 결합, 영상보다 짧은 오디오는 무음으로 채우기
- 커버 이미지, 캡션 파일, 코덱·길이·SHA256 기록 생성
- Instagram 계정 조회 → 영상 처리 요청 → 처리 상태 확인 → 게시
- 업로드 영수증과 잠금 파일을 통한 같은 작업의 중복 게시 방지

별도 웹 UI, AI 이미지·음성 생성, 예약 실행 및 스토리지 업로드는 포함하지 않습니다. 기본 예제는 **무음**입니다. 실제 음성이 필요하면 `audio`에 준비한 파일을 지정하세요.

## 설치와 첫 영상

Python 3.11 이상, FFmpeg/FFprobe, 한글 폰트가 필요합니다. 클라우드에서는 모두 준비되어 있습니다. Ubuntu에서는 `python3-venv ffmpeg fonts-noto-cjk` 패키지를 설치하세요.

```bash
cd /workspace/instagram-reels-studio
bash scripts/setup.sh
make test
make demo
make check
```

`out/demo/`에 `reel.mp4`, `cover.png`, `caption.txt`, `manifest.json`이 생성됩니다. 출력 폴더가 이미 차 있으면 덮어쓰지 않습니다. 다시 렌더링할 때는 새 경로를 사용하세요.

```bash
.venv/bin/python -m reels render examples/reel.json --out out/my-next-reel
```

## 내 콘텐츠로 제작

`examples/reel.json`을 새 파일로 복사해 제목·본문·캡션을 수정하세요. 각 장면은 1~60초이며 전체 영상은 이 템플릿 기준 3~180초입니다. 이미지·오디오 경로는 JSON 파일 위치를 기준으로 해석합니다.

```json
{
  "title": "내 첫 릴스",
  "brand": "MY STUDIO",
  "caption": "오늘의 이야기 #릴스",
  "audio": "assets/narration.mp3",
  "scenes": [
    {
      "title": "오늘의 순간",
      "text": "기억하고 싶은 이야기를\n영상으로 남겨보세요",
      "duration": 6,
      "image": "assets/photo.jpg",
      "color": "#102C34"
    }
  ]
}
```

`image`, `audio`는 선택 항목입니다. `REELS_FONT`로 한글 폰트 파일을 지정할 수 있습니다. 화면 텍스트는 영상에 직접 들어갑니다. 커버 PNG는 검수용이며 게시 API의 별도 커버 지정 기능은 아직 구현하지 않았습니다.

## Instagram 연결

이 프로젝트는 **Instagram API with Instagram Login**의 `graph.instagram.com` 경로를 사용합니다. Facebook Login 토큰과 혼용하지 마세요.

1. 비즈니스 또는 크리에이터 **프로페셔널 계정**과 Instagram Login을 설정한 Meta 앱을 준비합니다.
2. 앱에서 `instagram_business_basic`, `instagram_business_content_publish` 권한이 있는 토큰을 발급합니다. 외부 사용자에게 서비스할 경우 Meta의 앱 검수·라이브 모드 요건을 확인하세요.
3. 계정 ID와 토큰을 클라우드 환경 설정에 등록합니다. **비밀번호나 토큰을 저장소·채팅에 넣지 마세요.**
4. 사용 중인 Meta 앱에서 지원하는 API 버전을 확인하세요. 기본값은 명시적으로 `v24.0`에 고정되어 있으며 `INSTAGRAM_API_VERSION`으로 변경합니다.

| 변수 | 용도 |
| --- | --- |
| `INSTAGRAM_USER_ID` | 연결할 프로페셔널 계정의 숫자 ID |
| `INSTAGRAM_ACCESS_TOKEN` | Instagram Login 액세스 토큰; 요청 헤더로만 전송 |
| `INSTAGRAM_API_VERSION` | 기본값 `v24.0` |
| `REELS_FONT` | 선택: 한글 폰트 파일의 절대 경로 |

`.env.example`은 항목 설명용입니다. 프로그램은 `.env`를 자동으로 읽지 않습니다. 클라우드에서는 환경 설정을 사용하고, 로컬에서는 쉘에 환경변수를 등록하세요. 토큰 만료·갱신과 OAuth 로그인 UI는 Meta 앱에서 별도로 관리합니다.

```bash
.venv/bin/python -m reels account
```

공식 참고: [Instagram Login](https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login/), [Content Publishing](https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login/content-publishing/).

## 업로드와 게시

현재 업로드 방식은 **Meta가 공개 HTTPS MP4 URL에서 영상을 다운로드하는 방식**입니다. 이 도구가 로컬 파일을 스토리지에 올려주지는 않습니다. 먼저 생성한 `reel.mp4`를 본인 스토리지/CDN에 올려야 합니다. localhost, 로그인 페이지, 파일 미리보기 페이지는 사용할 수 없습니다. 서명된 URL이라면 처리 완료까지 만료되지 않아야 합니다. Meta가 해당 영상을 직접 받을 수 있어야 합니다.

```bash
# 1. 로컬 영상 검사
.venv/bin/python -m reels check out/demo/reel.mp4

# 2. 스토리지에 올린 동일 MP4의 주소로 컨테이너 생성 (아직 게시하지 않음)
.venv/bin/python -m reels upload \
  --video-url 'https://YOUR-CDN.example/reel.mp4' \
  --caption-file out/demo/caption.txt \
  --receipt .state/my-reel.json

# 3. 최대 5분간 처리를 확인. 타임아웃이면 같은 영수증으로 다시 확인
.venv/bin/python -m reels status --receipt .state/my-reel.json --wait

# 4. 실제 Instagram 계정에 게시
.venv/bin/python -m reels publish --receipt .state/my-reel.json
```

`upload`의 URL과 검사한 로컬 파일이 동일한지는 사용자가 확인해야 합니다. 토큰·서명 URL·캡션은 영수증에 저장하지 않습니다. 영수증에는 계정, API 버전, 컨테이너 ID, 게시 ID와 진행 상태만 기록됩니다. 완료된 같은 영수증으로 다시 `publish`해도 게시 요청을 반복하지 않습니다. 서로 다른 영수증은 별개 작업이므로 동일 영상에 여러 영수증을 만들지 마세요.

### 중단된 작업 복구

- `status`가 `ERROR` 또는 `EXPIRED`: URL 접근성, 영상 규격, 계정 권한을 점검합니다. 만료된 컨테이너는 재사용할 수 없습니다.
- 영수증이 `creating`이고 컨테이너 ID가 없음: 생성 요청이 전송되었는지 불명확합니다. 게시된 것은 아니지만 자동 생성 재시도는 하지 않습니다. Meta 앱의 요청 기록을 확인한 뒤 새 작업을 생성하세요.
- 영수증이 `publishing`: 게시 요청은 완료되었을 수 있습니다. `status`와 실제 계정을 먼저 확인하세요. `PUBLISHED`이면 이미 게시되었으므로 다시 게시하지 마세요. `FINISHED`인 경우에도 요청이 아직 진행 중인지 확인하고 충분히 기다린 후, 게시되지 않았음이 확인된 경우에만 영수증 상태를 `created`로 수정해 재시도합니다.
- `.lock` 파일이 남음: 해당 영수증을 사용하는 프로세스가 종료된 것을 확인한 뒤 잠금 파일만 제거합니다. 영수증을 지워서 재시도하지 마세요.

이 프로젝트는 상시 실행되는 스케줄러가 아닙니다. 클라우드 스냅샷은 파일을 보존하지만 실행 중인 프로세스를 보존하지 않습니다.

## 검증 범위

`make test`는 실제 FFmpeg 인코딩/디코딩과 이미지·오디오 결합을 검사하고, 모의 API로 인증 헤더·컨테이너 처리·오류·타임아웃·중복 게시 방지를 검증합니다. 테스트는 실제 Instagram API를 호출하거나 게시하지 않습니다.

실제 계정 조회·컨테이너 생성·게시까지는 계정 ID, 토큰, 네트워크 허용, 공개 MP4가 필요합니다. 모의 테스트 통과는 라이브 API 검증을 의미하지 않습니다. 플랫폼의 제한·권한·버전 변경은 Meta 공식 문서에서 확인하세요.
