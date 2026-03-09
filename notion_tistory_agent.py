import os
import time
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
import requests
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

load_dotenv()

NOTION_API_KEY = os.environ["NOTION_API_KEY"]
NOTION_DATABASE_ID = os.environ["NOTION_DATABASE_ID"]
TISTORY_EMAIL = os.environ["TISTORY_EMAIL"]
TISTORY_PASSWORD = os.environ["TISTORY_PASSWORD"]
TISTORY_BLOG_NAME = os.environ["TISTORY_BLOG_NAME"]

NOTION_HEADERS = {
    "Authorization": f"Bearer {NOTION_API_KEY}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}

KST = timezone(timedelta(hours=9))


# ──────────────────────────────────────────
# 노션
# ──────────────────────────────────────────

def get_recent_notion_pages() -> list[dict]:
    since = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    url = f"https://api.notion.com/v1/databases/{NOTION_DATABASE_ID}/query"
    payload = {
        "filter": {
            "timestamp": "created_time",
            "created_time": {"on_or_after": since},
        },
        "sorts": [{"timestamp": "created_time", "direction": "descending"}],
    }
    response = requests.post(url, headers=NOTION_HEADERS, json=payload)
    response.raise_for_status()
    return response.json().get("results", [])


def extract_page_title(page: dict) -> str:
    for prop in page.get("properties", {}).values():
        if prop.get("type") == "title":
            return "".join(t.get("plain_text", "") for t in prop.get("title", []))
    return "제목 없음"


def extract_tags(page: dict) -> list[str]:
    for prop in page.get("properties", {}).values():
        ptype = prop.get("type")
        if ptype == "multi_select":
            return [opt["name"] for opt in prop.get("multi_select", [])]
        if ptype == "select" and prop.get("select"):
            return [prop["select"]["name"]]
    return []


def get_page_blocks(page_id: str) -> list[dict]:
    url = f"https://api.notion.com/v1/blocks/{page_id}/children"
    blocks, cursor = [], None
    while True:
        params = {"page_size": 100}
        if cursor:
            params["start_cursor"] = cursor
        response = requests.get(url, headers=NOTION_HEADERS, params=params)
        response.raise_for_status()
        data = response.json()
        blocks.extend(data.get("results", []))
        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor")
    return blocks


def blocks_to_html(blocks: list[dict]) -> str:
    parts = []

    def rich(rich_texts: list[dict]) -> str:
        result = ""
        for rt in rich_texts:
            text = rt.get("plain_text", "")
            ann = rt.get("annotations", {})
            href = rt.get("href")
            if ann.get("bold"):
                text = f"<strong>{text}</strong>"
            if ann.get("italic"):
                text = f"<em>{text}</em>"
            if ann.get("strikethrough"):
                text = f"<s>{text}</s>"
            if ann.get("underline"):
                text = f"<u>{text}</u>"
            if ann.get("code"):
                text = f"<code>{text}</code>"
            if href:
                text = f'<a href="{href}">{text}</a>'
            result += text
        return result

    for block in blocks:
        btype = block.get("type", "")
        content = block.get(btype, {})
        rt = content.get("rich_text", [])

        if btype == "paragraph":
            inner = rich(rt)
            parts.append(f"<p>{inner}</p>" if inner else "<br>")
        elif btype in ("heading_1", "heading_2", "heading_3"):
            lvl = btype[-1]
            parts.append(f"<h{lvl}>{rich(rt)}</h{lvl}>")
        elif btype == "bulleted_list_item":
            parts.append(f"<ul><li>{rich(rt)}</li></ul>")
        elif btype == "numbered_list_item":
            parts.append(f"<ol><li>{rich(rt)}</li></ol>")
        elif btype == "quote":
            parts.append(f"<blockquote>{rich(rt)}</blockquote>")
        elif btype == "code":
            code_text = "".join(r.get("plain_text", "") for r in rt)
            lang = content.get("language", "")
            parts.append(f'<pre><code class="{lang}">{code_text}</code></pre>')
        elif btype == "divider":
            parts.append("<hr>")
        elif btype == "image":
            img = content.get("file", content.get("external", {}))
            img_url = img.get("url", "")
            caption = "".join(r.get("plain_text", "") for r in content.get("caption", []))
            if img_url:
                parts.append(f'<figure><img src="{img_url}" alt="{caption or "image"}"><figcaption>{caption}</figcaption></figure>')
        elif btype in ("embed", "video"):
            url = content.get("url", "")
            if url:
                parts.append(f'<p><a href="{url}">{url}</a></p>')

    return "\n".join(parts)


# ──────────────────────────────────────────
# 티스토리 (Playwright)
# ──────────────────────────────────────────

def login_tistory(context, page):
    """티스토리 로그인 — 쿠키 우선, 없으면 카카오 ID/PW 로그인"""
    # ── 방법 1: 저장된 쿠키 사용 (GitHub Actions 환경)
    cookies_json = os.environ.get("TISTORY_COOKIES", "")
    if cookies_json:
        import json
        cookies = json.loads(cookies_json)
        context.add_cookies(cookies)
        # 관리 페이지로 직접 접근해서 쿠키 유효성 검증
        page.goto(f"https://{TISTORY_BLOG_NAME}.tistory.com/manage/", wait_until="networkidle")
        if "/manage/" in page.url and "auth/login" not in page.url:
            print("  티스토리 로그인 완료 (쿠키)")
            return
        print("  쿠키 만료됨 — ID/PW 로그인으로 전환")

    # ── 방법 2: 카카오 ID/PW 로그인 (로컬 환경)
    page.goto("https://www.tistory.com/auth/login", wait_until="networkidle")
    page.click('a.btn_login.link_kakao_id')
    page.wait_for_load_state("networkidle")
    page.fill('#loginId--1', TISTORY_EMAIL)
    page.fill('#password--2', TISTORY_PASSWORD)
    page.click('.btn_g.highlight.submit')

    try:
        page.wait_for_url("*tistory.com*", timeout=30000)
    except Exception:
        pass
    page.wait_for_load_state("networkidle")

    if "tistory.com" not in page.url or "auth/login" in page.url:
        raise RuntimeError(f"로그인 실패. 현재 URL: {page.url}")

    print("  티스토리 로그인 완료 (ID/PW)")


def post_article(page, title: str, html_content: str, tags: list[str]) -> str:
    """티스토리 글 작성 및 발행, 게시된 URL 반환"""
    write_url = f"https://{TISTORY_BLOG_NAME}.tistory.com/manage/post/"
    page.goto(write_url, wait_until="networkidle")
    time.sleep(5)

    # ── "이전 글 이어쓰기" 팝업 처리: 취소 클릭으로 새 글 시작
    try:
        cancel_btn = page.locator('button:has-text("취소")')
        cancel_btn.wait_for(state="visible", timeout=8000)
        cancel_btn.click()
        print("    임시저장 팝업 닫음 (취소)")
        time.sleep(2)
    except Exception:
        pass  # 팝업 없으면 그냥 진행

    # ── 에디터 로드 대기 (#category-btn 기준)
    page.locator('#category-btn').wait_for(state="visible", timeout=30000)

    # ── 제목 입력 (메인 프레임의 title 전용 contenteditable)
    title_set = page.evaluate(f"""
        () => {{
            // 제목 placeholder로 타겟 정확히 지정
            const el = document.querySelector('[placeholder="제목을 입력하세요"]')
                    || document.querySelector('.title-input [contenteditable]')
                    || document.querySelector('[contenteditable="true"]');
            if (!el) return false;
            el.focus();
            el.textContent = {repr(title)};
            el.dispatchEvent(new Event('input', {{bubbles: true}}));
            el.dispatchEvent(new Event('change', {{bubbles: true}}));
            return true;
        }}
    """)
    print(f"    제목 입력: {title_set}")

    # ── 카테고리 선택 (AI트렌드)
    try:
        page.locator('#category-btn').click()
        time.sleep(1)
        category_item = page.get_by_text("AI트렌드", exact=True)
        if category_item.count() > 0:
            category_item.first.click()
            time.sleep(0.5)
    except Exception:
        pass

    # ── HTML 모드로 전환 (우측 상단 "기본모드" 드롭다운)
    try:
        mode_btn = page.locator('button:has-text("기본모드"), [class*="mode"]:has-text("기본모드")')
        if mode_btn.count() > 0:
            mode_btn.first.click()
            time.sleep(1)
            html_option = page.locator('li:has-text("HTML"), button:has-text("HTML"), a:has-text("HTML")')
            if html_option.count() > 0:
                html_option.first.click()
                time.sleep(1)
    except Exception:
        pass

    # ── 본문 내용 입력 (TinyMCE API 우선, 없으면 innerHTML)
    injected = False

    for frame in page.frames:
        try:
            result = frame.evaluate(f"""
                () => {{
                    // TinyMCE API로 먼저 시도 (에디터 내부 모델도 업데이트됨)
                    if (typeof tinymce !== 'undefined' && tinymce.activeEditor) {{
                        tinymce.activeEditor.setContent({repr(html_content)});
                        tinymce.activeEditor.save();  // 폼 textarea에 동기화
                        tinymce.activeEditor.fire('change');
                        return 'tinymce';
                    }}
                    // fallback: innerHTML 직접 주입
                    const els = document.querySelectorAll('[contenteditable="true"]');
                    const target = els.length >= 2 ? els[1] : els[0];
                    if (!target) return null;
                    target.focus();
                    target.innerHTML = {repr(html_content)};
                    target.dispatchEvent(new Event('input', {{bubbles: true}}));
                    target.dispatchEvent(new Event('change', {{bubbles: true}}));
                    return 'innerHTML';
                }}
            """)
            if result:
                print(f"    본문 입력 방법: {result}")
                injected = True
                break
        except Exception:
            continue

    # 방법 2: textarea
    if not injected:
        try:
            ta = page.locator('textarea')
            if ta.count() > 0:
                ta.first.fill(html_content)
                injected = True
        except Exception:
            pass

    if not injected:
        raise RuntimeError("에디터에 내용을 입력할 수 없습니다.")

    time.sleep(1)

    # ── 태그 입력
    if tags:
        try:
            tag_input = page.locator('[placeholder*="태그"], #tagText')
            if tag_input.count() > 0:
                tag_input.first.click()
                tag_input.first.fill(", ".join(tags))
                tag_input.first.press("Enter")
        except Exception:
            pass

    # ── "완료" 버튼 클릭 → 발행 패널 열기
    done_btn = page.locator('button:has-text("완료")').last
    done_btn.wait_for(state="visible", timeout=10000)
    done_btn.click()
    print("    '완료' 버튼 클릭")
    time.sleep(5)

    # ── 발행 패널 처리: 모든 frame 탐색
    pub_result = "not found"
    for frame in page.frames:
        try:
            result = frame.evaluate("""
                () => {
                    const open20 = document.querySelector('#open20');
                    if (open20) open20.click();
                    const publishBtn = document.querySelector('#publish-btn');
                    if (publishBtn) { publishBtn.click(); return 'publish-btn clicked'; }
                    const allBtns = Array.from(document.querySelectorAll('button'));
                    const target = allBtns.find(b =>
                        ['발행','공개발행','게시'].some(t => b.textContent.trim() === t)
                    );
                    if (target) { target.click(); return 'btn: ' + target.textContent.trim(); }
                    return null;
                }
            """)
            if result:
                pub_result = result
                break
        except Exception:
            continue
    print(f"    발행 결과: {pub_result}")

    if "not found" in pub_result:
        raise RuntimeError("발행 버튼을 찾지 못했습니다.")

    time.sleep(5)

    # ── 게시된 URL 확인
    current_url = page.url
    print(f"    현재 URL: {current_url}")
    if "/manage/" not in current_url:
        return current_url

    # 여전히 관리 페이지지만 발행은 됐을 수 있음 → 블로그 최신 글 URL 반환
    return f"https://{TISTORY_BLOG_NAME}.tistory.com"


# ──────────────────────────────────────────
# 메인
# ──────────────────────────────────────────

def main():
    print(f"[{datetime.now(KST).strftime('%Y-%m-%d %H:%M:%S KST')}] 에이전트 시작")

    pages = get_recent_notion_pages()
    print(f"  24시간 내 생성된 페이지: {len(pages)}개")

    if not pages:
        print("  게시할 페이지가 없습니다.")
        return

    success, fail = 0, 0

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            locale="ko-KR",
            extra_http_headers={"Accept-Language": "ko-KR,ko;q=0.9"},
            viewport={"width": 1280, "height": 900},
        )
        page = context.new_page()

        try:
            login_tistory(context, page)
        except Exception as e:
            print(f"  로그인 실패: {e}")
            browser.close()
            return

        for article in pages:
            page_id = article["id"]
            title = extract_page_title(article)
            tags = extract_tags(article)

            print(f"\n  처리 중: [{title}]")

            try:
                blocks = get_page_blocks(page_id)
                html_content = blocks_to_html(blocks)

                if not html_content.strip():
                    print("    -> 본문이 비어 있어 건너뜁니다.")
                    continue

                post_url = post_article(page, title, html_content, tags)
                print(f"    -> 게시 완료: {post_url}")
                success += 1

            except Exception as e:
                print(f"    -> 오류 발생: {e}")
                fail += 1

        browser.close()

    print(f"\n완료: 성공 {success}개 / 실패 {fail}개")


if __name__ == "__main__":
    main()
