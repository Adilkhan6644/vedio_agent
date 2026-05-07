from playwright.sync_api import sync_playwright
import os
import csv
import re
from dotenv import load_dotenv

load_dotenv()

INSTAGRAM_USERNAME = os.getenv("INSTAGRAM_USERNAME")
INSTAGRAM_PASSWORD = os.getenv("INSTAGRAM_PASSWORD")

try:
    from .comments import (
        human_delay,
        type_like_human,
        fill_first_available,
        click_first_available,
        wait_for_login_success,
        dismiss_all_not_now_popups,
        extract_post_caption_text,
        build_comment_from_caption,
    )
except ImportError:
    from comments import (
        human_delay,
        type_like_human,
        fill_first_available,
        click_first_available,
        wait_for_login_success,
        dismiss_all_not_now_popups,
        extract_post_caption_text,
        build_comment_from_caption,
    )


def login_to_instagram(page, username, password, headless):
    page.goto("https://www.instagram.com/", wait_until="domcontentloaded")
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_timeout(1200)

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
                "Auto-login fields were not detected in headless mode. Provide valid credentials or run interactively."
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
    dismiss_all_not_now_popups(page)


def normalize_profile_username(target_username):
    return target_username.strip().lstrip("@").strip("/")


def collect_profile_post_links(page, max_posts=5, scroll_rounds=6):
    post_urls = []
    seen = set()

    for _ in range(scroll_rounds):
        post_locators = [
            page.locator('article a[href*="/p/"]'),
            page.locator('article a[href*="/reel/"]'),
            page.locator('a[href*="/p/"]'),
            page.locator('a[href*="/reel/"]'),
        ]

        for locator in post_locators:
            count = min(locator.count(), 180)
            for i in range(count):
                href = locator.nth(i).get_attribute("href")
                if not href:
                    continue
                if "/p/" not in href and "/reel/" not in href:
                    continue
                full_url = href if href.startswith("http") else f"https://www.instagram.com{href}"
                full_url = full_url.split("?")[0]
                if full_url in seen:
                    continue
                seen.add(full_url)
                post_urls.append(full_url)
                if len(post_urls) >= max_posts:
                    return post_urls

        page.mouse.wheel(0, 2800)
        page.wait_for_timeout(700)

    return post_urls


def like_current_post_if_needed(page):
    if page.locator('svg[aria-label="Unlike"]').count() > 0:
        return False

    like_button_selectors = [
        'svg[aria-label="Like"]',
        'button:has(svg[aria-label="Like"])',
        'section span button:has(svg[aria-label="Like"])',
    ]

    for selector in like_button_selectors:
        try:
            page.locator(selector).first.click(timeout=3500)
            page.wait_for_timeout(500)
            return True
        except Exception:
            continue

    return False


def comment_on_current_post(page):
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
    try:
        wait_for_comment_submit(lambda: comment_box.press("Enter"), timeout=7000)
    except Exception as exc:
        submit_error = exc

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

    page.wait_for_timeout(1200)
    return comment_text, caption_text


def engage_profile_posts(page, target_username, max_posts=5, comment_each_post=True, like_each_post=True):
    profile_url = f"https://www.instagram.com/{normalize_profile_username(target_username)}/"
    page.goto(profile_url, wait_until="domcontentloaded")
    page.wait_for_timeout(1200)
    dismiss_all_not_now_popups(page)

    post_urls = collect_profile_post_links(page, max_posts=max_posts, scroll_rounds=max(6, max_posts))
    if not post_urls:
        raise RuntimeError("No posts found on target profile.")

    print(f"Collected {len(post_urls)} posts from {profile_url}")
    actions = []

    for index, post_url in enumerate(post_urls, start=1):
        entry = {
            "post_url": post_url,
            "liked": False,
            "commented": False,
            "comment_text": "",
            "caption_excerpt": "",
            "error": "",
        }

        try:
            page.goto(post_url, wait_until="domcontentloaded")
            page.wait_for_timeout(1000)
            dismiss_all_not_now_popups(page)

            if like_each_post:
                entry["liked"] = like_current_post_if_needed(page)

            if comment_each_post:
                comment_text, caption_text = comment_on_current_post(page)
                entry["commented"] = True
                entry["comment_text"] = comment_text
                entry["caption_excerpt"] = caption_text[:200]

            print(
                f"[{index}/{len(post_urls)}] done: liked={entry['liked']} commented={entry['commented']} {post_url}"
            )
            human_delay(0.8, 1.6)

        except Exception as exc:
            entry["error"] = str(exc)
            print(f"[{index}/{len(post_urls)}] skipped {post_url}: {exc}")

        actions.append(entry)

    return profile_url, post_urls, actions


def run_instagram_profile_engagement_bot(
    target_username,
    max_posts=5,
    username=None,
    password=None,
    headless=True,
    comment_each_post=True,
    like_each_post=True,
    save_csv=True,
    csv_path="profile_engagement.csv",
):
    username = username or INSTAGRAM_USERNAME
    password = password or INSTAGRAM_PASSWORD

    if not target_username:
        raise RuntimeError("target_username is required.")

    if not username or not password:
        raise RuntimeError(
            "Set INSTAGRAM_USERNAME and INSTAGRAM_PASSWORD in environment or pass username/password."
        )

    profile_url = ""
    post_urls = []
    actions = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context()
        page = context.new_page()
        page.set_default_timeout(7000)

        try:
            login_to_instagram(page, username, password, headless=headless)
            profile_url, post_urls, actions = engage_profile_posts(
                page,
                target_username=target_username,
                max_posts=max_posts,
                comment_each_post=comment_each_post,
                like_each_post=like_each_post,
            )

            if save_csv:
                with open(csv_path, "w", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    writer.writerow(
                        [
                            "profile_url",
                            "post_url",
                            "liked",
                            "commented",
                            "comment_text",
                            "caption_excerpt",
                            "error",
                        ]
                    )
                    for entry in actions:
                        writer.writerow(
                            [
                                profile_url,
                                entry["post_url"],
                                "yes" if entry["liked"] else "no",
                                "yes" if entry["commented"] else "no",
                                entry["comment_text"],
                                entry["caption_excerpt"],
                                entry["error"],
                            ]
                        )
                print(f"Saved to {csv_path}")

        finally:
            browser.close()

    return {
        "profile_url": profile_url,
        "total_posts_collected": len(post_urls),
        "results": actions,
        "csv_path": csv_path if save_csv else None,
    }


if __name__ == "__main__":
    result = run_instagram_profile_engagement_bot(
        target_username="instagram",
        max_posts=5,
        username=INSTAGRAM_USERNAME,
        password=INSTAGRAM_PASSWORD,
        headless=False,
        comment_each_post=True,
        like_each_post=True,
        save_csv=True,
        csv_path="profile_engagement.csv",
    )

    print(f"Profile: {result['profile_url']}")
    print(f"Posts collected: {result['total_posts_collected']}")
    print(f"Actions completed: {len(result['results'])}")
