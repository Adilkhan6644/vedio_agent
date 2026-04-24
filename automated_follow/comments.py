from playwright.sync_api import sync_playwright
import os
import time
import csv
import re
import random
from dotenv import load_dotenv
try:
    from groq import Groq
except ImportError:
    Groq = None

load_dotenv()

USERNAME = os.getenv("INSTAGRAM_USERNAME")
PASSWORD = os.getenv("INSTAGRAM_PASSWORD")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
SEARCH_QUERY = "swimming coach"
MAX_FOLLOWS = 5

groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY and Groq else None

def human_delay(min_s=0.25, max_s=0.8):
    time.sleep(random.uniform(min_s, max_s))


def type_like_human(locator, text, min_key_delay=45, max_key_delay=120):
    locator.click()
    locator.fill("")
    for ch in text:
        locator.type(ch, delay=random.randint(min_key_delay, max_key_delay))


def fill_first_available(page, selectors, value, timeout=3500):
    for selector in selectors:
        locator = page.locator(selector).first
        try:
            locator.wait_for(state="visible", timeout=timeout)
            type_like_human(locator, value)
            return selector
        except Exception:
            continue
    raise RuntimeError(f"Could not find a visible field for selectors: {selectors}")


def click_first_available(page, selectors, timeout=3500):
    for selector in selectors:
        locator = page.locator(selector).first
        try:
            locator.wait_for(state="visible", timeout=timeout)
            locator.click()
            return selector
        except Exception:
            continue
    raise RuntimeError(f"Could not find a visible clickable element for selectors: {selectors}")


def open_first_profile_post(page):
    post_selectors = [
        'article a[href*="/reel/"]',
        'article a[href*="/p/"]',
        'a[href*="/reel/"]',
        'a[href*="/p/"]',
    ]
    click_first_available(page, post_selectors, timeout=5000)
    page.wait_for_timeout(1200)


def extract_post_caption_text(page):
    candidates = []
    try:
        article_text = page.locator("article").first.inner_text(timeout=2500)
        if article_text:
            candidates.append(article_text.strip())
    except Exception:
        pass

    for selector in ['meta[property="og:description"]', 'meta[name="description"]']:
        try:
            content = page.locator(selector).first.get_attribute("content")
            if content:
                candidates.append(content.strip())
        except Exception:
            continue

    for text in candidates:
        cleaned = re.sub(r"\s+", " ", text).strip()
        if cleaned:
            return cleaned

    return ""


def build_comment_from_caption(caption_text):
    if not caption_text:
        return "Strong post."

    if not groq_client:
        hashtags = re.findall(r"#\w+", caption_text)
        if hashtags:
            return f"Strong post and great use of {' '.join(hashtags[:2])}."
        return "Strong post."

    system_prompt = (
        "You write short Instagram comments. Given a caption and hashtags, return one natural comment "
        "in the same language as the post. Keep it positive, specific, and non-spammy. "
        "Use 8 to 18 words. Return only the comment text."
    )

    response = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        max_tokens=60,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"CAPTION AND HASHTAGS:\n{caption_text}"},
        ],
    )

    comment = response.choices[0].message.content.strip()
    comment = re.sub(r'^"|"$', "", comment).strip()
    return comment or "Strong post."


def comment_on_first_profile_post(page):
    open_first_profile_post(page)
    caption_text = extract_post_caption_text(page)
    comment_text = build_comment_from_caption(caption_text)

    comment_box_selectors = [
        'textarea[aria-label^="Add a comment"]',
        'textarea[placeholder^="Add a comment"]',
        'textarea[aria-label*="comment"]',
    ]
    comment_box = None
    for selector in comment_box_selectors:
        try:
            locator = page.locator(selector).first
            locator.wait_for(state="visible", timeout=5000)
            comment_box = locator
            break
        except Exception:
            continue

    if comment_box is None:
        raise RuntimeError("Could not find the comment field on the post.")

    type_like_human(comment_box, comment_text)
    page.wait_for_timeout(500)

    def wait_for_comment_submit(action, timeout=9000):
        with page.expect_response(
            lambda response: (
                response.request.method == "POST"
                and "/comments/" in response.url
                and response.status in [200, 201]
            ),
            timeout=timeout,
        ):
            action()

    submit_error = None

    # Strategy 1: many Instagram surfaces submit comments on Enter.
    try:
        wait_for_comment_submit(lambda: comment_box.press("Enter"), timeout=7000)
    except Exception as exc:
        submit_error = exc

        # Strategy 2: fallback to enabled Post buttons in different layouts.
        post_button_selectors = [
            'div[role="button"][aria-disabled="false"]:has-text("Post")',
            'button:not([disabled]):has-text("Post")',
            '[role="button"]:has(span:has-text("Post"))[aria-disabled="false"]',
        ]

        posted = False
        for selector in post_button_selectors:
            try:
                post_button = page.locator(selector).first
                post_button.wait_for(state="visible", timeout=2500)
                wait_for_comment_submit(lambda btn=post_button: btn.click(), timeout=7000)
                posted = True
                break
            except Exception as inner_exc:
                submit_error = inner_exc
                continue

        if not posted:
            raise RuntimeError(f"Failed to submit comment: {submit_error}")

    page.wait_for_timeout(1500)

    return comment_text, caption_text


def wait_for_login_success(page, timeout_ms=35000):
    start = time.time()
    while (time.time() - start) * 1000 < timeout_ms:
        # Common post-login UI signals
        if page.locator('input[placeholder="Search"]').count() > 0:
            return True
        if page.locator('svg[aria-label="Home"]').count() > 0:
            return True
        if page.locator('a[href="/"]').count() > 0:
            return True
        # Still on login page
        if page.locator('input[type="password"]').count() > 0:
            page.wait_for_timeout(400)
            continue
        page.wait_for_timeout(400)
    return False


def dismiss_post_login_popups(page):
    not_now_selectors = [
        'button._a9--._ap36._a9_1:has-text("Not Now")',
        'button._a9--._ap36._a9_1',
        'button:has-text("Not Now")',
        'div[role="button"]:has-text("Not Now")',
        'button:has-text("Not now")',
        'div[role="dialog"] button:has-text("Not Now")',
    ]
    for selector in not_now_selectors:
        try:
            page.locator(selector).first.click(timeout=1800)
            page.wait_for_timeout(300)
            return True
        except Exception:
            continue
    return False


def dismiss_all_not_now_popups(page, max_rounds=4):
    dismissed_any = False
    for _ in range(max_rounds):
        clicked = dismiss_post_login_popups(page)
        if not clicked:
            break
        dismissed_any = True
        page.wait_for_timeout(250)
    return dismissed_any


def open_search_from_nav(page):
    search_nav_selectors = [
        'a[role="link"]:has(svg[aria-label="Search"])',
        'a[role="link"]:has-text("Search")',
        'svg[aria-label="Search"]',
        'a[href="#"]:has(svg[aria-label="Search"])',
    ]
    for selector in search_nav_selectors:
        try:
            page.locator(selector).first.click(timeout=2500)
            page.wait_for_timeout(300)
            return True
        except Exception:
            continue
    return False


def open_accounts_tab(page):
    accounts_tab_selectors = [
        'a:has-text("Accounts")',
        'button:has-text("Accounts")',
        'div[role="tab"]:has-text("Accounts")',
        'span:has-text("Accounts")',
    ]
    for selector in accounts_tab_selectors:
        try:
            page.locator(selector).first.click(timeout=2500)
            page.wait_for_timeout(500)
            return True
        except Exception:
            continue
    return False


def is_profile_href(href):
    if not href or not href.startswith("/"):
        return False
    blocked_prefixes = (
        "/explore/",
        "/reels/",
        "/direct/",
        "/accounts/",
        "/p/",
        "/stories/",
        "/about/",
    )
    if href in ["/", "/home/"]:
        return False
    if any(href.startswith(prefix) for prefix in blocked_prefixes):
        return False
    # Accept URLs like /username/ only.
    return href.count("/") == 2


def collect_search_profile_links(page, max_links=20, scroll_rounds=3):
    collected = []
    seen = set()

    for _ in range(scroll_rounds):
        candidate_locators = [
            page.locator('div[role="dialog"] a[href^="/"]'),
            page.locator('a[href^="/"]'),
        ]
        for links in candidate_locators:
            count = min(links.count(), 120)
            for i in range(count):
                href = links.nth(i).get_attribute("href")
                if is_profile_href(href):
                    full_url = "https://www.instagram.com" + href
                    if full_url not in seen:
                        seen.add(full_url)
                        collected.append(full_url)
                        if len(collected) >= max_links:
                            return collected

        page.mouse.wheel(0, 1800)
        page.wait_for_timeout(450)

    return collected


def follow_profiles(page, profile_urls, max_to_follow=5):
    followed = []
    comments_made = []
    for profile_url in profile_urls:
        if len(followed) >= max_to_follow:
            break

        page.goto(profile_url, wait_until="domcontentloaded")
        page.wait_for_timeout(700)
        dismiss_all_not_now_popups(page)

        follow_button = page.locator("button").filter(
            has_text=re.compile(r"^(Follow|Follow Back)$", re.IGNORECASE)
        ).first
        followed_this_profile = False
        try:
            follow_button.wait_for(state="visible", timeout=2200)
            follow_button.click()
            followed.append(profile_url)
            followed_this_profile = True
            print(f"Followed: {profile_url}")
            human_delay(0.35, 0.9)
        except Exception:
            print(f"Skipped (not followable now): {profile_url}")

        if followed_this_profile:
            try:
                comment_text, caption_text = comment_on_first_profile_post(page)
                comments_made.append({
                    "profile_url": profile_url,
                    "comment": comment_text,
                    "caption_excerpt": caption_text[:200],
                })
                print(f"Commented on first post for: {profile_url}")
                print(f"Caption: {caption_text[:200]}")
                print(f"Comment: {comment_text}")
            except Exception as exc:
                print(f"Skipped commenting on first post for {profile_url}: {exc}")

    return followed, comments_made

def run_instagram_comment_bot(
    search_query=SEARCH_QUERY,
    max_follows=MAX_FOLLOWS,
    username=None,
    password=None,
    headless=True,
    save_csv=True,
    csv_path="profiles.csv",
):
    username = username or USERNAME
    password = password or PASSWORD

    if not username or not password:
        raise RuntimeError(
            "Set INSTAGRAM_USERNAME and INSTAGRAM_PASSWORD environment variables or pass username/password before running the script."
        )

    collected = []
    followed_profiles = []
    comments_made = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context()
        page = context.new_page()
        page.set_default_timeout(6000)

        # 1. Go to Instagram
        page.goto("https://www.instagram.com/", wait_until="domcontentloaded")
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(1200)

        # Optional cookie banner handling
        for cookie_selector in [
            'button:has-text("Allow all cookies")',
            'button:has-text("Only allow essential cookies")',
            'button:has-text("Accept all")',
        ]:
            try:
                page.locator(cookie_selector).first.click(timeout=2000)
                break
            except Exception:
                pass

        # 2. Login
        username_selectors = [
            'input[name="email"]',
            'input[autocomplete="username webauthn"]',
            'input[name="email"][type="text"]',
            'input[name="username"]',
            'input[autocomplete="username"]',
            'input[type="text"]',
            'input[type="email"]',
            'input[type="tel"]',
            'input[aria-label="Phone number, username, or email"]',
            'input[aria-label="Mobile Number, Email or Username"]',
            'input[placeholder="Phone number, username, or email"]',
            'input[placeholder="Mobile number, username or email"]',
        ]
        password_selectors = [
            'input[name="password"]',
            'input[type="password"]',
            'input[autocomplete="current-password"]',
            'input[aria-label="Password"]',
            'input[placeholder="Password"]',
        ]
        submit_selectors = [
            'button[type="submit"]',
            'button:has-text("Log in")',
            'button:has-text("Log In")',
            'div[role="button"]:has-text("Log in")',
        ]

        auto_login_done = False
        try:
            fill_first_available(page, username_selectors, username, timeout=15000)
            fill_first_available(page, password_selectors, password, timeout=15000)
            click_first_available(page, submit_selectors, timeout=10000)
            auto_login_done = True
        except RuntimeError:
            print("Auto-login fields were not detected.")

        if not auto_login_done:
            if headless:
                raise RuntimeError(
                    "Auto-login fields were not detected in headless mode. Provide valid credentials or run the bot interactively."
                )
            print("Please complete login manually in the opened browser window.")
            input("After login is complete, press Enter to continue...")

        try:
            page.wait_for_load_state("networkidle", timeout=8000)
        except Exception:
            pass

        if not wait_for_login_success(page, timeout_ms=90000):
            raise RuntimeError("Login did not complete in time. Check credentials, 2FA, or checkpoint prompts.")

        page.wait_for_timeout(1000)

        # Handle post-login popups if they appear (can show multiple times)
        dismiss_all_not_now_popups(page)

        human_delay()

        # 3. Search for niche
        open_search_from_nav(page)
        dismiss_all_not_now_popups(page)

        search_candidates = [
            'input[placeholder="Search"]',
            'input[aria-label="Search input"]',
            'input[aria-label="Search"]',
            'input[type="search"]',
            'input[placeholder*="Search"]',
        ]
        used_search_selector = None
        for sel in search_candidates:
            locator = page.locator(sel).first
            try:
                locator.wait_for(state="visible", timeout=2500)
                type_like_human(locator, search_query)
                used_search_selector = sel
                break
            except Exception:
                continue

        if not used_search_selector:
            raise RuntimeError("Could not find search input after login.")

        # One more pass in case another notification prompt appears after focus/input.
        dismiss_all_not_now_popups(page)

        page.wait_for_timeout(1000)

        # 4. Open profile/account results and gather candidate profiles.
        open_accounts_tab(page)
        page.wait_for_timeout(700)
        dismiss_all_not_now_popups(page)

        collected = collect_search_profile_links(page, max_links=20, scroll_rounds=3)
        print(f"Collected {len(collected)} profile candidates")

        # 5. Visit and follow top profiles, then comment on latest post.
        followed_profiles, comments_made = follow_profiles(page, collected, max_to_follow=max_follows)
        print(f"Followed {len(followed_profiles)} profiles")
        print(f"Posted {len(comments_made)} comments")

        # 6. Save candidates and followed profiles to CSV.
        if save_csv:
            with open(csv_path, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["profile_url", "followed", "commented"])
                commented_profiles = {item["profile_url"] for item in comments_made}
                for url in collected:
                    writer.writerow([
                        url,
                        "yes" if url in followed_profiles else "no",
                        "yes" if url in commented_profiles else "no",
                    ])
            print(f"Saved to {csv_path}")

        browser.close()

    return {
        "collected_profiles": collected,
        "followed_profiles": followed_profiles,
        "comments": comments_made,
        "csv_path": csv_path if save_csv else None,
    }


if __name__ == "__main__":
    run_instagram_comment_bot(
        search_query=SEARCH_QUERY,
        max_follows=MAX_FOLLOWS,
        username=USERNAME,
        password=PASSWORD,
        headless=False,
        save_csv=True,
        csv_path="profiles.csv",
    )