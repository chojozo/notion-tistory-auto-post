"""
로컬에서 티스토리 로그인 후 쿠키를 저장하는 스크립트.
저장된 쿠키를 GitHub Secret 'TISTORY_COOKIES' 에 등록하면
GitHub Actions에서 해외 IP 로그인 차단 없이 동작합니다.

사용법:
    python3 save_cookies.py
    -> tistory_cookies.json 생성
    -> 파일 내용을 복사해서 GitHub Secret TISTORY_COOKIES 에 등록
"""
import os, json
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv()
EMAIL = os.environ["TISTORY_EMAIL"]
PASSWORD = os.environ["TISTORY_PASSWORD"]

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    page = context.new_page()

    print("티스토리 로그인 중...")
    page.goto("https://www.tistory.com/auth/login", wait_until="networkidle")
    page.click('a.btn_login.link_kakao_id')
    page.wait_for_load_state("networkidle")
    page.fill('#loginId--1', EMAIL)
    page.fill('#password--2', PASSWORD)
    page.click('.btn_g.highlight.submit')

    # 티스토리 메인으로 리다이렉트될 때까지 대기 (최대 30초)
    try:
        page.wait_for_url("*tistory.com*", timeout=30000)
    except Exception:
        pass
    page.wait_for_load_state("networkidle")

    if "tistory.com" in page.url and "accounts.kakao" not in page.url:
        cookies = context.cookies()
        with open("tistory_cookies.json", "w") as f:
            json.dump(cookies, f)
        print(f"\n로그인 성공! 쿠키 {len(cookies)}개 저장됨: tistory_cookies.json")
        print("\n--- GitHub Secret 등록 방법 ---")
        print("1. tistory_cookies.json 파일 내용을 전체 복사")
        print("2. GitHub 저장소 → Settings → Secrets → New secret")
        print("   Name: TISTORY_COOKIES")
        print("   Value: (복사한 JSON 전체 붙여넣기)")
        print("3. Add secret 클릭")
    else:
        print(f"로그인 실패. 현재 URL: {page.url}")
        print("추가 인증(2단계 인증 등)이 필요할 수 있습니다.")

    browser.close()
