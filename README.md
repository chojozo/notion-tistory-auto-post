# Notion → Tistory 자동 게시 에이전트

노션 데이터베이스에서 24시간 이내 생성된 페이지를 매일 오전 11시(KST)에 티스토리 블로그에 자동으로 게시하는 GitHub Actions 에이전트입니다.

---

## 파일 구조

```
notion_tistory_auto_post/
├── .github/
│   └── workflows/
│       └── auto_post.yml      # GitHub Actions 워크플로우
├── notion_tistory_agent.py    # 메인 에이전트
├── requirements.txt
├── .env.example               # 환경 변수 템플릿
├── .gitignore
└── README.md
```

---

## 사전 준비

### 1. Notion API 키 발급

1. [https://www.notion.so/my-integrations](https://www.notion.so/my-integrations) 접속
2. **New integration** 클릭 → 이름 입력 → Submit
3. **Internal Integration Token** 복사 → `NOTION_API_KEY`
4. 노션에서 대상 데이터베이스 열기 → 우측 상단 `...` → **Connections** → 방금 만든 integration 추가
5. 데이터베이스 URL에서 ID 추출
   예: `https://www.notion.so/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx?v=...`
   → `xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx` 부분이 `NOTION_DATABASE_ID`

### 2. Tistory Access Token 발급

티스토리 API는 OAuth 2.0을 사용합니다. 아래 순서로 토큰을 발급하세요.

1. [https://www.tistory.com/guide/api/register](https://www.tistory.com/guide/api/register) 에서 앱 등록
   - Callback URL: `https://www.tistory.com` (임시로 사용)
2. 아래 URL을 브라우저에서 열어 로그인 후 code 파라미터 획득
   ```
   https://www.tistory.com/oauth/authorize?client_id={CLIENT_ID}&redirect_uri=https://www.tistory.com&response_type=code
   ```
3. 리다이렉트된 URL에서 `code=xxxxx` 부분 복사
4. 아래 URL로 GET 요청하여 `access_token` 획득
   ```
   https://www.tistory.com/oauth/access_token?client_id={CLIENT_ID}&client_secret={CLIENT_SECRET}&redirect_uri=https://www.tistory.com&code={CODE}&grant_type=authorization_code
   ```
5. 응답에서 `access_token` 값 복사 → `TISTORY_ACCESS_TOKEN`
6. 블로그 주소 `https://{블로그이름}.tistory.com` → `{블로그이름}` → `TISTORY_BLOG_NAME`

---

## 로컬 실행

```bash
# 1. 의존성 설치
pip install -r requirements.txt

# 2. 환경 변수 파일 생성
cp .env.example .env
# .env 파일을 열고 실제 값 입력

# 3. 실행
python notion_tistory_agent.py
```

---

## GitHub Actions 배포 (GitHub Secrets 설정)

### GitHub Secrets 등록 방법

1. GitHub에서 이 저장소 열기
2. **Settings** 탭 클릭
3. 좌측 메뉴에서 **Secrets and variables** → **Actions** 클릭
4. **New repository secret** 버튼 클릭
5. 아래 4개 Secret을 하나씩 등록

| Secret 이름 | 값 |
|---|---|
| `NOTION_API_KEY` | 노션 Integration Token |
| `NOTION_DATABASE_ID` | 노션 데이터베이스 ID |
| `TISTORY_ACCESS_TOKEN` | 티스토리 OAuth 액세스 토큰 |
| `TISTORY_BLOG_NAME` | 티스토리 블로그 이름 |

### 저장소에 Push

```bash
git init
git add .
git commit -m "feat: notion to tistory auto post agent"
git remote add origin https://github.com/{username}/{repo-name}.git
git push -u origin main
```

### 실행 스케줄

- **자동 실행**: 매일 오전 11:00 KST (UTC 02:00)
- **수동 실행**: GitHub → Actions 탭 → `Notion to Tistory Auto Post` → **Run workflow**

---

## 노션 데이터베이스 속성 요구사항

에이전트는 아래 속성을 자동으로 인식합니다.

| 속성 타입 | 용도 |
|---|---|
| `title` | 글 제목 (필수) |
| `multi_select` | 태그 (선택) |
| `select` | 태그 (선택, multi_select 없을 때) |

본문은 페이지 블록 내용을 자동으로 HTML로 변환합니다.

---

## 지원하는 노션 블록 타입

- 문단 (paragraph)
- 제목 1/2/3 (heading_1/2/3)
- 글머리 기호 목록 (bulleted_list_item)
- 번호 목록 (numbered_list_item)
- 인용 (quote)
- 코드 블록 (code)
- 구분선 (divider)
- 이미지 (image)
- 임베드/동영상 링크 (embed, video)
