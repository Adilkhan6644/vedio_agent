from playwright.sync_api import sync_playwright
import os
import time
import csv
import re
import random
from dotenv import load_dotenv

load_dotenv()

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
    for profile_url in profile_urls:
        if len(followed) >= max_to_follow:
            break

        page.goto(profile_url, wait_until="domcontentloaded")
        page.wait_for_timeout(700)
        dismiss_all_not_now_popups(page)

        follow_button = page.locator("button").filter(
            has_text=re.compile(r"^(Follow|Follow Back)$", re.IGNORECASE)
        ).first
        try:
            follow_button.wait_for(state="visible", timeout=2200)
            follow_button.click()
            followed.append(profile_url)
            print(f"Followed: {profile_url}")
            human_delay(0.35, 0.9)
        except Exception:
            print(f"Skipped (not followable now): {profile_url}")
            continue

    return followed


def run_instagram_follow_bot(search_query, max_follows, username, password, headless, save_csv):
    username = username or os.getenv("INSTAGRAM_USERNAME")
    password = password or os.getenv("INSTAGRAM_PASSWORD")

    if not username or not password:
        raise RuntimeError(
            "Set INSTAGRAM_USERNAME and INSTAGRAM_PASSWORD environment variables or pass username/password before running the script."
        )

    collected = []
    followed_profiles = []
    csv_path = None

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context()
        page = context.new_page()
        page.set_default_timeout(6000)

        try:
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

            # 5. Visit and follow top profiles.
            followed_profiles = follow_profiles(page, collected, max_to_follow=max_follows)
            print(f"Followed {len(followed_profiles)} profiles")

            # 6. Save candidates and followed profiles to CSV.
            if save_csv:
                csv_path = "profiles.csv"
                with open(csv_path, "w", newline="") as f:
                    writer = csv.writer(f)
                    writer.writerow(["profile_url", "followed"])
                    for url in collected:
                        writer.writerow([url, "yes" if url in followed_profiles else "no"])

                print("Saved to profiles.csv")
        finally:
            browser.close()

    return {
        "collected_profiles": collected,
        "followed_profiles": followed_profiles,
        "csv_path": csv_path,
    }


if __name__ == "__main__":
    SEARCH_QUERY = "fitness coach"
    MAX_FOLLOWS = 5

    result = run_instagram_follow_bot(
        search_query=SEARCH_QUERY,
        max_follows=MAX_FOLLOWS,
        username=os.getenv("INSTAGRAM_USERNAME"),
        password=os.getenv("INSTAGRAM_PASSWORD"),
        headless=False,
        save_csv=True,
    )

    print(f"Collected {len(result['collected_profiles'])} profile candidates")
    print(f"Followed {len(result['followed_profiles'])} profiles")