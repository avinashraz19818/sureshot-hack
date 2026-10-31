import os
import io
import re
import time
import shutil
import asyncio
import logging
from typing import Optional, Dict, Any
from playwright.async_api import async_playwright, BrowserContext, Page

import config

logger = logging.getLogger(__name__)

# Real WinGo DOM Selectors from smex engine
MOBILE_CONTEXT = {
    "user_agent": "Mozilla/5.0 (Linux; Android 13; SM-G981B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
    "viewport": {"width": 412, "height": 860},
    "device_scale_factor": 2.625,
    "is_mobile": True,
    "has_touch": True,
}

PERIOD_SELECTOR = ".TimeLeft__C-id"
TIME_SELECTOR = ".TimeLeft__C-time"
BALANCE_SELECTOR = ".Wallet__C-balance-l1, .Wallet__C-balance"
GAME_ITEM_SELECTOR = ".GameList__C-item"
BET_POPUP_SELECTOR = ".Betting__Popup-body, .lottery-container"
BET_CONFIRM_SELECTOR = ".Betting__Popup-foot-s, .footer button.bet-amount, button.bet-amount"
BET_CANCEL_SELECTOR = ".Betting__Popup-foot-c, .footer button.cancel, button.cancel"
BET_AGREE_SELECTOR = ".Betting__Popup-agree, .agreement div[role='checkbox'], .agreement .van-checkbox"
TOAST_FAIL_SELECTOR = ".van-toast--fail, .van-toast:has-text('insufficient'), .van-toast:has-text('fail'), .van-toast:has-text('parameter'), .van-toast:has-text('balance')"
WIN_DIALOG_SELECTOR = ".winning:not([style*='display: none']), .winning-body.isWin, .winning-wrap-l1.isWin, .WinningTip__C"

LOGIN_PHONE_SELECTOR = "input[name='userNumber'], input[placeholder*='phone'], input[placeholder*='Phone'], input[type='tel']"
LOGIN_PASS_SELECTOR = "input[type='password']"
LOGIN_SUBMIT_SELECTOR = "button:has-text('Log in'), button:has-text('Login'), .signIn__container-button button, .login-btn, button[type='submit']"

CLOSE_SELECTORS = [
    ".first-recharge-queue-dialog__close",
    ".closeBtn",
    ".close-btn",
    ".van-icon-cross",
    ".van-icon-close",
    ".van-popup__close-icon",
    ".van-popup__close-icon--bottom",
    ".dialog__close",
    "img[src*='close']",
    "[class*='close-icon']",
    "[class*='CloseBtn']",
    ".activity-close",
]

DETECT_WIN_POPUP_JS = """() => {
    const candidates = document.querySelectorAll(
        '.WinningTip__C, .winning, .winning-body.isWin, .winning-wrap-l1.isWin, .van-dialog, .van-popup, .win-popup, .Winning-Popup'
    );
    for (const el of candidates) {
        if (!el || el.id === 'zayro-vip-overlay' || el.closest('#zayro-vip-overlay')) continue;
        const style = window.getComputedStyle(el);
        if (style.display === 'none' || style.visibility === 'hidden' || parseFloat(style.opacity || '1') < 0.1) continue;
        const rect = el.getBoundingClientRect();
        if (rect.width < 120 || rect.height < 120) continue;

        const rawText = (el.innerText || el.textContent || '');
        const txt = rawText.toLowerCase();

        // Never match loss popup ("Sorry") or the open betting sheet ("Total amount")
        if (txt.includes('sorry') || txt.includes('total amount')) continue;

        const isWinClass = (
            el.classList.contains('isWin') ||
            !!el.querySelector('.isWin')
        );
        const hasCongrats = (
            txt.includes('congratulations') ||
            (txt.includes('bonus') && txt.includes('lottery results')) ||
            (isWinClass && (txt.includes('bonus') || txt.includes('congratul')))
        );

        if (hasCongrats) {
            let choice = null;
            let num = null;
            const m = rawText.match(/Lottery\\s*results[\\s\\S]{0,60}?([0-9])[\\s\\S]{0,30}?(Big|Small)/i);
            if (m) {
                num = parseInt(m[1], 10);
                choice = m[2].toUpperCase();
            } else {
                const mNum = rawText.match(/Lottery\\s*results[\\s\\S]{0,40}?\\b([0-9])\\b/i);
                if (mNum) {
                    num = parseInt(mNum[1], 10);
                    choice = num >= 5 ? 'BIG' : 'SMALL';
                } else if (/\\bSmall\\b/i.test(rawText)) {
                    choice = 'SMALL';
                } else if (/\\bBig\\b/i.test(rawText)) {
                    choice = 'BIG';
                }
            }
            return {
                detected: true,
                choice: choice,
                number: num
            };
        }
    }
    return { detected: false, choice: null, number: null };
}"""


class PlaywrightWinGoWorker:
    """
    Playwright-based real human-like game player with instant 0-second popup capture (smex pattern).
    Flow: Real Login -> Place Dual Bet (Big + Small) -> Continuous Draw Watcher -> Instant Win Popup Capture -> Telegram Delivery.
    """

    def __init__(self):
        self.enabled = True
        self.login_url = (getattr(config, "DEMO_LOGIN_URL", "") or "").strip() or "https://bdgwina.biz/#/login"
        self.username = (getattr(config, "DEMO_USERNAME", "") or "").strip() or "6556745550"
        self.password = (getattr(config, "DEMO_PASSWORD", "") or "").strip() or "win1222"
        self.headless = config.HEADLESS
        self.profile_dir = config.BROWSER_PROFILE_DIR

        self.playwright = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.is_ready = False
        self._lock = asyncio.Lock()
        self._watcher_task: Optional[asyncio.Task] = None
        self._popup_capture_in_progress = False

        # In-memory screenshot caches keyed by period string
        self.cached_win_screenshots: Dict[str, io.BytesIO] = {}
        self.cached_board_screenshots: Dict[str, io.BytesIO] = {}
        self.known_results: Dict[str, Dict[str, Any]] = {}

    def _get_chromium_path(self) -> Optional[str]:
        if config.CHROMIUM_PATH and os.path.exists(config.CHROMIUM_PATH):
            return config.CHROMIUM_PATH

        for candidate in [
            shutil.which("google-chrome"),
            shutil.which("google-chrome-stable"),
            shutil.which("chromium"),
            shutil.which("chromium-browser"),
            shutil.which("chrome"),
            "/usr/bin/google-chrome",
            "/usr/bin/google-chrome-stable",
            "/opt/google/chrome/chrome",
            "/usr/bin/chromium-browser",
            "/usr/bin/chromium",
            "/snap/bin/chromium",
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        ]:
            if candidate and os.path.exists(candidate):
                return candidate
        return None

    def _home_url(self) -> str:
        base = self.login_url.split("#", 1)[0].rstrip("/")
        return f"{base}/#/"

    def _get_game_url(self, game_id: str) -> str:
        base_origin = self.login_url.split("/#/")[0] if "/#/" in self.login_url else "https://bdgwina.biz"
        code_map = {
            "wingo_30s": "WinGo_30S",
            "wingo_1m": "WinGo_1M",
            "wingo_3m": "WinGo_3M",
            "wingo_5m": "WinGo_5M",
        }
        game_code = code_map.get(game_id, "WinGo_1M")
        return f"{base_origin}/#/saasLottery/WinGo?gameCode={game_code}&lottery=WinGo"

    async def initialize(self) -> bool:
        """Launches Playwright persistent browser context and signs in like a real user"""
        if not self.enabled or not self.username or not self.password:
            logger.info("ℹ️ Real game automation is disabled in config.")
            return False

        async with self._lock:
            if self.is_ready and self.page and not self.page.is_closed():
                return True

            try:
                os.makedirs(self.profile_dir, exist_ok=True)
                for lock_name in ["SingletonLock", "SingletonCookie", "SingletonSocket"]:
                    lock_path = os.path.join(self.profile_dir, lock_name)
                    if os.path.exists(lock_path) or os.path.islink(lock_path):
                        try:
                            os.remove(lock_path)
                        except Exception:
                            pass

                self.playwright = await async_playwright().start()

                chromium_path = self._get_chromium_path()
                launch_opts = {
                    "headless": self.headless,
                    "args": [
                        "--no-sandbox",
                        "--disable-setuid-sandbox",
                        "--disable-dev-shm-usage",
                        "--disable-gpu",
                        "--disable-software-rasterizer",
                        "--disable-extensions",
                        "--disable-blink-features=AutomationControlled",
                        "--no-first-run",
                        "--mute-audio",
                        "--js-flags=--max-old-space-size=256",
                    ],
                    **MOBILE_CONTEXT,
                }
                if chromium_path:
                    logger.info(f"🌐 Using detected Chromium/Chrome binary: {chromium_path}")
                    launch_opts["executable_path"] = chromium_path

                logger.info(f"🚀 Launching Playwright browser context (Profile: {self.profile_dir})...")
                self.context = await self.playwright.chromium.launch_persistent_context(
                    self.profile_dir,
                    **launch_opts
                )

                self.page = self.context.pages[0] if self.context.pages else await self.context.new_page()
                self.page.set_default_timeout(15000)

                ok = await self.open_room_step_by_step("wingo_1m")
                if ok:
                    self.is_ready = True
                    logger.info("🎯 Real Browser is logged in and ready on WinGo game board!")
                    return True
                else:
                    logger.warning("⚠️ Room not open yet; will retry on next round.")
                    return False

            except Exception as e:
                logger.error(f"❌ Playwright initialization error: {e}", exc_info=True)
                await self.close()
                return False

    # ------------------------------------------------------------------ #
    #  Real human-like login & popups (smex logic)
    # ------------------------------------------------------------------ #

    async def is_logged_out(self) -> bool:
        """Checks if session expired or user is logged out (smex logic)"""
        if not self.page:
            return True
        try:
            expired_toast = self.page.locator(".van-toast:has-text('expired'), .van-toast:has-text('login')").first
            if await expired_toast.is_visible(timeout=500):
                return True

            curr = self.page.url or ""
            if "#/login" in curr:
                return True

            phone_inp = self.page.locator(LOGIN_PHONE_SELECTOR).first
            if await phone_inp.is_visible(timeout=500):
                return True

            board = self.page.locator(PERIOD_SELECTOR).first
            if await board.is_visible(timeout=500):
                return False

            guest_btn = self.page.locator(".p8-home__guest-btn--login, button:has-text('Log in')").first
            if await guest_btn.is_visible(timeout=500):
                return True
        except Exception:
            pass
        return False

    async def dismiss_announcements(self):
        """Auto-close password change popups & floating banners (smex logic)"""
        if not self.page:
            return
        try:
            await self.page.evaluate(r"""() => {
                const dialogs = [...document.querySelectorAll('div[role="dialog"]')];
                for (const dialog of dialogs) {
                    if (!dialog.querySelector('input[autocomplete="new-password"]')) {
                        continue;
                    }
                    const buttons = [...dialog.querySelectorAll('button, [role="button"], .van-button')];
                    const closeButton = buttons.find((button) =>
                        /cancel|close|later|skip|not now|remind me later/i.test(
                            (button.innerText || button.textContent || '').trim()
                        )
                    );
                    if (closeButton) closeButton.click();
                    dialog.style.setProperty('display', 'none', 'important');
                    dialog.style.setProperty('visibility', 'hidden', 'important');
                    dialog.setAttribute('aria-hidden', 'true');
                }
                document.body.classList.remove('van-overflow-hidden');
            }""")
        except Exception:
            pass

        for _ in range(4):
            clicked_any = False
            try:
                no_rem = self.page.locator("text='No more reminders today'").first
                if await no_rem.is_visible(timeout=200):
                    await no_rem.click(timeout=600)
                    await asyncio.sleep(0.25)
                    clicked_any = True
            except Exception:
                pass

            for sel in CLOSE_SELECTORS:
                try:
                    locator = self.page.locator(sel).first
                    if await locator.is_visible(timeout=200):
                        await locator.click(force=True, timeout=600)
                        await asyncio.sleep(0.25)
                        clicked_any = True
                        break
                except Exception:
                    continue

            if not clicked_any:
                try:
                    confirm_el = self.page.locator(
                        'div[role="dialog"]:not(:has(input[autocomplete="new-password"])) button'
                    ).filter(has_text=re.compile(r"^\s*Confirm\s*$", re.I)).first
                    if await confirm_el.is_visible(timeout=200):
                        await confirm_el.click(timeout=800)
                        await asyncio.sleep(0.3)
                        clicked_any = True
                except Exception:
                    pass

            if not clicked_any:
                break

    async def setup_lottery_token(self):
        """Sets internal localStorage keys so lottery room authenticates instantly (smex logic)"""
        if not self.page:
            return
        try:
            await self.page.evaluate("""() => {
                let urlStr = localStorage.getItem('lotteryLoginUrl');
                if (urlStr) {
                    try {
                        let u = new URL(urlStr);
                        let token = u.searchParams.get("Token");
                        let skin = u.searchParams.get("Skin") || "";
                        let lang = u.searchParams.get("Lang") || "en";

                        localStorage.setItem("ar_token", JSON.stringify({ value: token, expires: -1 }));
                        localStorage.setItem("ar_api", JSON.stringify({ value: "https://h5.ar-lottery06.com", expires: -1 }));
                        localStorage.setItem("ar_api_json", JSON.stringify({ value: "https://draw.ar-lottery06.com", expires: -1 }));
                        localStorage.setItem("ar_lang", JSON.stringify({ value: lang, expires: -1 }));
                        localStorage.setItem("ar_skin", JSON.stringify({ value: skin, expires: -1 }));
                    } catch(e) {}
                }
            }""")
        except Exception:
            pass

    async def ensure_logged_in(self) -> bool:
        """Enters phone and password like a real user and logs in"""
        if not self.page:
            return False

        logger.info(f"🔑 Authenticating account: Navigating to {self.login_url}...")
        try:
            await self.page.goto(self.login_url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(3.0)
            await self.dismiss_announcements()

            curr = self.page.url or ""
            if "#/main" in curr or "#/home" in curr or "#/saasLottery" in curr:
                guest = self.page.locator(".p8-home__guest-btn--login, button:has-text('Log in')").first
                if not await guest.is_visible():
                    logger.info("✅ Already logged in with active user session!")
                    return True

            phone_field = self.page.locator(LOGIN_PHONE_SELECTOR).first
            try:
                await phone_field.wait_for(state="visible", timeout=8000)
            except Exception:
                phone_field = None

            if phone_field:
                logger.info(f"👉 Entering Mobile Number: {self.username}...")
                await phone_field.click()
                await phone_field.fill("")
                await phone_field.type(self.username, delay=35)
                await asyncio.sleep(0.3)

                pwd_field = self.page.locator(LOGIN_PASS_SELECTOR).first
                if await pwd_field.is_visible():
                    logger.info("👉 Entering Password...")
                    await pwd_field.click()
                    await pwd_field.fill("")
                    await pwd_field.type(self.password, delay=35)
                    await asyncio.sleep(0.4)

                try:
                    rem_cb = self.page.locator(".signIn__container-rememberRow .van-checkbox, input[type='checkbox']").first
                    if await rem_cb.is_visible():
                        await rem_cb.click()
                except Exception:
                    pass

                submit = self.page.locator(LOGIN_SUBMIT_SELECTOR).first
                if await submit.is_visible():
                    logger.info("👉 Clicking Login button...")
                    await submit.click()
                    await asyncio.sleep(4.5)

                await self.dismiss_announcements()
                logger.info("✅ Login form submitted successfully!")
                return True
            else:
                logger.info("ℹ️ Login input fields not present; proceeding with existing session...")
                return True
        except Exception as e:
            logger.error(f"❌ Real login error: {e}", exc_info=True)
            return False

    async def open_room_step_by_step(self, game_id: str = "wingo_1m") -> bool:
        if not self.page:
            return False

        logger.info("🧭 [1/5] Ensuring account is authenticated on game platform...")
        await self.ensure_logged_in()

        logger.info("🧭 [2/5] Opening Home page...")
        try:
            home = self._home_url()
            await self.page.goto(home, wait_until="domcontentloaded", timeout=25000)
            await asyncio.sleep(2.0)
            await self.dismiss_announcements()
            await self.setup_lottery_token()
        except Exception as e:
            logger.warning(f"Home page warning: {e}")

        room_url = self._get_game_url(game_id)
        logger.info(f"🧭 [3/5] Opening WinGo Room: {room_url}...")
        try:
            await self.page.goto(room_url, wait_until="domcontentloaded", timeout=25000)
            await asyncio.sleep(3.0)
            await self.dismiss_announcements()

            board_loc = self.page.locator(PERIOD_SELECTOR).first
            if not await board_loc.is_visible(timeout=3000):
                logger.info("👉 Clicking 'Lottery' icon from home screen...")
                lottery_btn = self.page.locator("text='Lottery', [class*='Lottery']").first
                if await lottery_btn.is_visible(timeout=2000):
                    await lottery_btn.click(force=True)
                    await asyncio.sleep(2.0)
                    await self.page.goto(room_url, wait_until="domcontentloaded", timeout=20000)
                    await asyncio.sleep(2.5)
        except Exception as e:
            logger.warning(f"Room open warning: {e}")

        logger.info("🧭 [4/5] Selecting WinGo 1Min tab...")
        try:
            tab = self.page.locator(GAME_ITEM_SELECTOR).filter(has_text=re.compile(r"1\s*Min", re.I)).first
            if await tab.is_visible(timeout=1500):
                await tab.click(force=True)
                await asyncio.sleep(1.0)
        except Exception:
            pass

        logger.info("🧭 [5/5] Checking WinGo board...")
        try:
            board_loc = self.page.locator(PERIOD_SELECTOR).first
            if await board_loc.is_visible(timeout=4000):
                period_text = (await board_loc.inner_text()).strip()
                logger.info(f"✅ [5/5] WinGo Board Live & Ready! Current Period: {period_text}")
                return True
        except Exception:
            pass

        logger.info("ℹ️ WinGo board ready.")
        return True

    # ------------------------------------------------------------------ #
    #  Timing, Live Countdown, Balance, and Continuous Draw Watcher
    # ------------------------------------------------------------------ #

    async def current_period(self) -> Optional[str]:
        if not self.page:
            return None
        try:
            loc = self.page.locator(PERIOD_SELECTOR).first
            if await loc.is_visible(timeout=400):
                txt = (await loc.inner_text(timeout=400)).strip()
                digits = ''.join(filter(str.isdigit, txt))
                return digits if digits else txt
        except Exception:
            pass
        return None

    async def read_balance(self) -> Optional[float]:
        if not self.page:
            return None
        try:
            loc = self.page.locator(BALANCE_SELECTOR).first
            if await loc.is_visible(timeout=600):
                txt = (await loc.inner_text(timeout=600)).strip()
                nums = re.findall(r"\d[\d,]*(?:\.\d+)?", txt)
                for n in nums:
                    try:
                        return float(n.replace(",", ""))
                    except ValueError:
                        continue
        except Exception:
            pass
        return None

    @staticmethod
    def _parse_countdown(text: str) -> Optional[int]:
        """Parse '0 0 : 1 3' / '0\n0\n:\n1\n3' / '00:13' style countdown into seconds (smex logic)."""
        if not text:
            return None
        digits = ''.join(filter(str.isdigit, text))
        if not digits:
            return None
        if len(digits) >= 4:
            mm = digits[-4:-2]
            ss = digits[-2:]
            try:
                val = int(mm) * 60 + int(ss)
                return val if val <= 300 else None
            except ValueError:
                return None
        try:
            val = int(digits)
            return val if val <= 300 else None
        except ValueError:
            return None

    async def seconds_left(self) -> Optional[int]:
        """Reads the exact remaining seconds on the live board"""
        if not self.page:
            return None
        try:
            time_loc = self.page.locator(TIME_SELECTOR).first
            if await time_loc.is_visible(timeout=400):
                text = (await time_loc.inner_text(timeout=400)).strip()
                parsed = self._parse_countdown(text)
                if parsed is not None:
                    return parsed

            fallback_loc = self.page.locator(".van-count-down, .countDown, .time").first
            if await fallback_loc.is_visible(timeout=400):
                text = (await fallback_loc.inner_text(timeout=400)).strip()
                return self._parse_countdown(text)
        except Exception:
            pass
        return None

    async def remove_prediction_overlay(self):
        if not self.page:
            return
        try:
            await self.page.evaluate("""() => {
                const el = document.getElementById('zayro-vip-overlay');
                if (el) el.remove();
            }""")
        except Exception:
            pass

    async def inject_prediction_overlay(
        self,
        issue: str,
        choice: str,
        confidence: float = 98.7,
        level: int = 1,
        number: Optional[int] = None
    ) -> bool:
        """
        Injects the Zayro VIP Hack card directly into the live game page DOM at top: 14px!
        Stays fixed at z-index 2147483647 right above the Congratulations popup (matching predction bot).
        """
        if not self.page:
            return False
        try:
            from database import db_manager
            if not db_manager.get_html_overlay_enabled():
                await self.remove_prediction_overlay()
                return False

            from services.overlay_manager import overlay_manager, ZAYRO_CSS
            card_html = overlay_manager.generate_html(
                issue=issue,
                choice=choice,
                confidence=confidence,
                level=level,
                number=number
            )

            await self.page.evaluate("""({html, css}) => {
                let style = document.getElementById('zayro-vip-overlay-style');
                if (!style) {
                    style = document.createElement('style');
                    style.id = 'zayro-vip-overlay-style';
                    document.head.appendChild(style);
                }
                style.textContent = css;

                let container = document.getElementById('zayro-vip-overlay');
                if (!container) {
                    container = document.createElement('div');
                    container.id = 'zayro-vip-overlay';
                    document.body.appendChild(container);
                }
                container.innerHTML = html;
                container.style.display = 'block';
                container.style.visibility = 'visible';
                container.style.opacity = '1';
            }""", {"html": card_html, "css": ZAYRO_CSS})

            logger.info(f"✨ VIP Hack Overlay injected onto live game board for period {issue} ({choice.upper()})!")
            return True
        except Exception as e:
            logger.warning(f"Could not inject VIP overlay: {e}")
            return False

    async def watch_and_capture_win_popup(
        self,
        target_issue: str,
        choice: str = "BIG",
        level: int = 1,
        confidence: float = 98.7,
        number: Optional[int] = None,
        game_id: str = "wingo_1m"
    ):
        """
        Continuous Period-Aware Win Popup Watcher:
        - Never does a blind sleep that could oversleep the draw!
        - Watches the live countdown & period flip continuously and polls DETECT_WIN_POPUP_JS at 50ms
          to catch the real 'Congratulations' Winning Popup the instant it appears on screen!
        - Extracts the actual winning outcome (BIG/SMALL & number) directly from the popup DOM
          so the injected Zayro VIP Hack card matches the Congratulations popup 100%!
        """
        max_sec = 60
        if "30s" in str(game_id):
            max_sec = 30
        elif "3m" in str(game_id):
            max_sec = 180
        elif "5m" in str(game_id):
            max_sec = 300

        secs = await self.seconds_left()
        logger.info(
            f"⏱️ Live Round Watcher started for period {target_issue} "
            f"(Countdown: {secs if secs is not None else '?'}s remaining)..."
        )

        overall_deadline = time.time() + max_sec + 16.0
        post_flip_deadline: Optional[float] = None
        entered_fast_mode = False
        popup_info: Optional[Dict[str, Any]] = None

        try:
            while time.time() < overall_deadline:
                # 1. Check if the Congratulations popup is currently visible on the DOM
                try:
                    res = await self.page.evaluate(DETECT_WIN_POPUP_JS)
                    if res and res.get("detected"):
                        popup_info = res
                        break
                except Exception:
                    pass

                # 2. Check board period & countdown to know when draw is imminent or happening
                try:
                    on_page_period = await self.current_period()
                    curr_secs = await self.seconds_left()

                    # If period on board has flipped past target_issue, draw is happening RIGHT NOW!
                    if on_page_period and str(target_issue) and on_page_period != str(target_issue):
                        if post_flip_deadline is None:
                            post_flip_deadline = time.time() + 11.0
                            self._popup_capture_in_progress = True
                            if not entered_fast_mode:
                                entered_fast_mode = True
                                logger.info(f"👀 Period flipped ({target_issue} -> {on_page_period})! Fast 50ms Win Popup detector active...")

                    elif curr_secs is not None and curr_secs <= 4:
                        self._popup_capture_in_progress = True
                        if not entered_fast_mode:
                            entered_fast_mode = True
                            logger.info(f"👀 Draw imminent ({curr_secs}s left for {target_issue})! Fast 50ms Win Popup detector active...")
                except Exception:
                    pass

                if post_flip_deadline is not None and time.time() > post_flip_deadline:
                    break

                # Poll every 50ms during draw window, or every 250ms while waiting for countdown
                await asyncio.sleep(0.05 if entered_fast_mode else 0.25)

            if popup_info and popup_info.get("detected"):
                # Resolve actual winning choice (BIG/SMALL) and number (0-9) for the VIP Hack card
                known = self.known_results.get(str(target_issue), {})
                detected_choice = popup_info.get("choice") or known.get("choice") or choice
                detected_num = popup_info.get("number")
                if detected_num is None:
                    detected_num = known.get("number", number)

                if str(detected_choice).upper() not in ("BIG", "SMALL"):
                    if detected_num is not None:
                        detected_choice = "BIG" if int(detected_num) >= 5 else "SMALL"
                    else:
                        detected_choice = "BIG"

                logger.info(
                    f"🎉 REAL IN-GAME CONGRATULATIONS WIN POPUP DETECTED for {target_issue} "
                    f"({detected_choice} / {detected_num})! Capturing at once..."
                )

                await self.inject_prediction_overlay(
                    issue=target_issue,
                    choice=str(detected_choice).upper(),
                    confidence=confidence,
                    level=level,
                    number=detected_num
                )
                await asyncio.sleep(0.18)  # Let bonus amount animation settle

                shot_bytes = await self.page.screenshot(type="png", full_page=False)
                buf = io.BytesIO(shot_bytes)
                buf.seek(0)
                self.cached_win_screenshots[str(target_issue)] = buf
                logger.info(f"📸 100% Real In-Game Win Popup Screenshot with VIP Overlay cached for period {target_issue}!")

                await self.dismiss_announcements()
                await self.remove_prediction_overlay()
                return
            else:
                logger.warning(
                    f"⚠️ Native Congratulations popup did not appear for {target_issue}. "
                    f"Check that the account has sufficient balance and bets were accepted."
                )
                await self.remove_prediction_overlay()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Error in watch_and_capture_win_popup for {target_issue}: {e}")
        finally:
            self._popup_capture_in_progress = False

    # ------------------------------------------------------------------ #
    #  Bet Modal Lifecycle Helpers (smex battle-tested logic)
    # ------------------------------------------------------------------ #

    async def _is_bet_popup_open(self) -> bool:
        if not self.page:
            return False
        try:
            return await self.page.evaluate("""() => {
                const els = document.querySelectorAll('.Betting__Popup-body, .lottery-container');
                for (const el of els) {
                    const st = window.getComputedStyle(el);
                    if (st.display !== 'none' && st.visibility !== 'hidden' && el.offsetWidth > 0 && el.offsetHeight > 0) {
                        return true;
                    }
                }
                return false;
            }""")
        except Exception:
            return False

    async def _wait_bet_popup_open(self, timeout_ms: int = 2000) -> bool:
        deadline = time.time() + (timeout_ms / 1000.0)
        while time.time() < deadline:
            if await self._is_bet_popup_open():
                return True
            await asyncio.sleep(0.06)
        return False

    async def _wait_bet_popup_closed(self, timeout_ms: int = 2500) -> bool:
        deadline = time.time() + (timeout_ms / 1000.0)
        while time.time() < deadline:
            if not await self._is_bet_popup_open():
                return True
            await asyncio.sleep(0.06)
        return False

    async def _force_close_bet_modal(self):
        """Cleanly closes any open betting sheet via Cancel button or overlay click."""
        if not self.page:
            return
        try:
            cancel = self.page.locator(BET_CANCEL_SELECTOR).first
            if await cancel.is_visible(timeout=250):
                await cancel.click(timeout=500)
                await asyncio.sleep(0.2)
                return
        except Exception:
            pass
        try:
            await self.page.evaluate("""() => {
                const cancelBtn = document.querySelector('.Betting__Popup-foot-c, .footer button.cancel, button.cancel');
                if (cancelBtn) { cancelBtn.click(); return; }
                const ov = document.querySelector('.van-overlay');
                if (ov) ov.click();
            }""")
            await asyncio.sleep(0.2)
        except Exception:
            pass

    async def _ensure_bet_agreed(self):
        """Ensures the 'I agree' checkbox on the betting popup is checked (never unchecks if already active)."""
        if not self.page:
            return
        try:
            await self.page.evaluate("""() => {
                const agree = document.querySelector(".Betting__Popup-agree, .agreement div[role='checkbox'], .agreement .van-checkbox");
                if (!agree) return;
                if (agree.getAttribute('aria-checked') === 'true') return;
                const cls = agree.getAttribute('class') || '';
                if (cls.includes('active') || cls.includes('--checked')) return;
                const icon = agree.querySelector('.van-checkbox__icon');
                if (icon && (icon.getAttribute('class') || '').includes('--checked')) return;
                agree.click();
            }""")
        except Exception:
            pass

    async def _read_toast_text(self) -> Optional[str]:
        if not self.page:
            return None
        try:
            txt = await self.page.evaluate("""() => {
                const t = document.querySelector('.van-toast, .van-toast__text');
                if (t && t.offsetWidth > 0) {
                    return (t.innerText || t.textContent || '').trim();
                }
                return null;
            }""")
            return txt if txt else None
        except Exception:
            return None

    async def set_bet_amount(self, target_total: int):
        """Sets the exact bet chip and multiplier on the open WinGo betting sheet (smex logic)"""
        if not self.page or target_total <= 0:
            return

        unit = 1
        qty = target_total
        if target_total >= 1000 and target_total % 1000 == 0:
            unit = 1000
            qty = target_total // 1000
        elif target_total >= 100 and target_total % 100 == 0:
            unit = 100
            qty = target_total // 100
        elif target_total >= 10 and target_total % 10 == 0:
            unit = 10
            qty = target_total // 10

        logger.info(f"💰 Setting In-Game Bet: Unit ₹{unit} x Multiplier {qty} = Total ₹{target_total}")

        # 1. Click Unit Chip (1, 10, 100, 1000)
        try:
            await self.page.evaluate("""(u) => {
                const chips = Array.from(document.querySelectorAll('.amount-buttons > div, .amount-section .amount-buttons > div, .Betting__Popup-body-line-item'));
                const target = chips.find(c => c.textContent.trim() === String(u));
                if (target) target.click();
            }""", unit)
        except Exception:
            pass

        # 2. If multiplier button matches (X1, X5, X10, X20, X50, X100)
        mult_clicked = False
        if qty in [1, 5, 10, 20, 50, 100]:
            try:
                mult_clicked = await self.page.evaluate("""(q) => {
                    const btns = Array.from(document.querySelectorAll('.multiplier-buttons > div, [class*="multiplier"] > div, .Betting__Popup-body-line-item, .Betting__Popup-btn'));
                    const target = btns.find(b => b.textContent.trim().toUpperCase() === 'X' + q);
                    if (target) {
                        target.click();
                        return true;
                    }
                    return false;
                }""", qty)
            except Exception:
                mult_clicked = False

        # 3. If custom quantity, set reactive input value
        if not mult_clicked and qty != 1:
            try:
                await self.page.evaluate("""(val) => {
                    const el = document.querySelector('.multiplier-section input, .m input, input[type="number"], .Betting__Popup-input input');
                    if (el) {
                        const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set;
                        if (nativeSetter) {
                            nativeSetter.call(el, String(val));
                        } else {
                            el.value = String(val);
                        }
                        el.dispatchEvent(new Event('input', { bubbles: true }));
                        el.dispatchEvent(new Event('change', { bubbles: true }));
                    }
                }""", str(qty))
            except Exception:
                pass

    async def _place_single_side_bet(self, side: str, bet_amount: int, issue_number: str) -> bool:
        """
        Cleanly places a single bet on 'BIG' or 'SMALL':
        1. Ensures any previous bet popup is closed.
        2. Clicks the Big/Small button on the board and waits for the bet popup to open (with retry).
        3. Ensures 'I agree' is checked and sets the bet amount.
        4. Clicks Confirm and waits for the bet popup to close naturally so the next bet never collides!
        """
        side_up = side.upper()
        is_big = (side_up == "BIG")
        btn_selector = ".Betting__C-foot-b, .bet-btn-big" if is_big else ".Betting__C-foot-s, .bet-btn-small"
        target_label = "Big" if is_big else "Small"

        # 1. Clean up any leftover open modal from previous bet
        if await self._is_bet_popup_open():
            await self._force_close_bet_modal()
            await self._wait_bet_popup_closed(timeout_ms=1000)

        # 2. Click Big / Small button and verify the popup opens (up to 3 attempts)
        popup_opened = False
        for attempt in range(3):
            try:
                loc = self.page.locator(btn_selector).first
                if await loc.is_visible(timeout=1000):
                    await loc.click(force=True, timeout=1200)
                else:
                    await self.page.evaluate("""({sel, label}) => {
                        const el = document.querySelector(sel);
                        if (el) { el.click(); return; }
                        const all = Array.from(document.querySelectorAll("div, button, span"));
                        const found = all.find(n => (n.innerText || '').trim() === label && n.children.length === 0);
                        if (found) found.click();
                    }""", {"sel": btn_selector, "label": target_label})
            except Exception:
                try:
                    await self.page.evaluate("""(sel) => {
                        const el = document.querySelector(sel);
                        if (el) el.click();
                    }""", btn_selector)
                except Exception:
                    pass

            if await self._wait_bet_popup_open(timeout_ms=1600):
                popup_opened = True
                break

            await asyncio.sleep(0.25)

        if not popup_opened:
            toast_msg = await self._read_toast_text()
            logger.warning(
                f"⚠️ Bet popup did not open for {side_up} on period {issue_number} "
                f"(Toast: {toast_msg!r})"
            )
            return False

        # 3. Ensure agreement checkbox & set bet amount
        await self._ensure_bet_agreed()
        await self.set_bet_amount(bet_amount)
        await asyncio.sleep(0.2)

        # 4. Click Confirm button inside the popup
        confirmed = False
        try:
            conf_loc = self.page.locator(BET_CONFIRM_SELECTOR).first
            if await conf_loc.is_visible(timeout=1000):
                await conf_loc.click(force=True, timeout=1000)
                confirmed = True
        except Exception:
            confirmed = False

        if not confirmed:
            try:
                confirmed = await self.page.evaluate("""() => {
                    const btn = document.querySelector(".Betting__Popup-foot-s, .footer button.bet-amount, button.bet-amount");
                    if (btn) { btn.click(); return true; }
                    return false;
                }""")
            except Exception:
                confirmed = False

        if not confirmed:
            logger.warning(f"⚠️ Could not click Confirm button for {side_up} on period {issue_number}!")
            await self._force_close_bet_modal()
            return False

        # 5. Wait for the popup to close naturally after server response
        closed = await self._wait_bet_popup_closed(timeout_ms=3000)
        toast_msg = await self._read_toast_text()

        if toast_msg and any(w in toast_msg.lower() for w in ("insufficient", "fail", "balance", "error")):
            logger.error(f"💸 Game rejected {side_up} bet for {issue_number} — Toast: {toast_msg!r}")
            if not closed:
                await self._force_close_bet_modal()
            return False

        if not closed:
            await self._force_close_bet_modal()
            await self._wait_bet_popup_closed(timeout_ms=1000)

        logger.info(
            f"✅ Bet placed on {side_up} (₹{bet_amount}) for period {issue_number}"
            + (f" [Toast: {toast_msg}]" if toast_msg else "")
        )
        return True

    # ------------------------------------------------------------------ #
    #  Single & Dual Bet Placement
    # ------------------------------------------------------------------ #

    async def place_bet(
        self,
        game_id: str,
        choice: str,
        issue_number: str = "",
        level: int = 1,
        confidence: float = 98.7,
        number: Optional[int] = None
    ) -> dict:
        """Places a single real bet on Big or Small and starts the draw watcher."""
        for _ in range(40):
            if not self._popup_capture_in_progress:
                break
            await asyncio.sleep(0.2)

        async with self._lock:
            if not self.is_ready or not self.page:
                logger.warning("Browser not ready for bet.")
                return {"ok": False, "reason": "browser_not_ready"}

            try:
                await self.dismiss_announcements()

                from database import db_manager
                base_bet = db_manager.get_base_bet_amount()
                martingale_mult = db_manager.get_martingale_multiplier()
                target_amount = base_bet * (martingale_mult ** max(0, level - 1))

                ok = await self._place_single_side_bet(choice.upper(), target_amount, issue_number)
                if ok:
                    await self.inject_prediction_overlay(
                        issue=issue_number,
                        choice=choice,
                        confidence=confidence,
                        level=level,
                        number=number
                    )
                    if self._watcher_task and not self._watcher_task.done():
                        self._watcher_task.cancel()
                    self._watcher_task = asyncio.create_task(self.watch_and_capture_win_popup(
                        target_issue=str(issue_number),
                        choice=choice,
                        level=level,
                        confidence=confidence,
                        number=number,
                        game_id=game_id
                    ))
                    return {"ok": True, "choice": choice.upper(), "issue": issue_number, "amount": target_amount}
                return {"ok": False, "reason": "bet_failed"}
            except Exception as e:
                logger.error(f"Error placing bet for {game_id}: {e}")
                return {"ok": False, "reason": str(e)}

    async def place_dual_bet(
        self,
        game_id: str,
        issue_number: str = "",
        amount: Optional[int] = None,
        confidence: float = 99.8
    ) -> dict:
        """
        Sure-Shot Hack Mode:
        Places real in-game flat bets on BOTH Big AND Small sequentially, waiting for the
        first bet popup to close completely before opening the second bet popup.
        Guarantees one outcome wins and triggers the real Congratulations Win popup!
        """
        # Never interrupt an active 00:00 Congratulations popup capture from the just-finished round!
        for _ in range(40):
            if not self._popup_capture_in_progress:
                break
            await asyncio.sleep(0.2)

        async with self._lock:
            if not self.is_ready or not self.page:
                logger.warning("Browser not ready for dual bet.")
                return {"ok": False, "reason": "browser_not_ready"}

            try:
                # Auto-recover if logged out or off the WinGo board
                if await self.is_logged_out():
                    logger.info("🔑 Session logged out — re-authenticating...")
                    await self.open_room_step_by_step(game_id)

                await self.dismiss_announcements()
                await self.remove_prediction_overlay()

                from database import db_manager
                bet_amount = amount if amount is not None else db_manager.get_base_bet_amount()
                if bet_amount <= 0:
                    bet_amount = 1

                balance = await self.read_balance()
                secs = await self.seconds_left()
                on_page_period = await self.current_period()
                logger.info(
                    f"⚡ Dual Bet Prep | Target Period: {issue_number} (Board: {on_page_period or '?'}) | "
                    f"Time Left: {secs if secs is not None else '?'}s | "
                    f"Wallet Balance: {f'₹{balance:,.2f}' if balance is not None else 'Unknown'} | "
                    f"Bet: ₹{bet_amount} on BIG + ₹{bet_amount} on SMALL"
                )

                if balance is not None and balance < (bet_amount * 2):
                    logger.error(
                        f"💸 Wallet balance (₹{balance:.2f}) is less than required dual bet (₹{bet_amount * 2})! "
                        f"Please top up the game account so bets succeed and Congratulations popup appears."
                    )

                if secs is not None and secs <= 6:
                    logger.warning(f"⏰ Only {secs}s left in period {issue_number} (draw lock active). Skipping bet click.")
                    return {"ok": False, "reason": "period_locked"}

                # 1. Place Bet on BIG and wait for modal to close completely
                logger.info(f"⚡ [1/2] Placing BIG ₹{bet_amount} for period {issue_number}...")
                big_ok = await self._place_single_side_bet("BIG", bet_amount, issue_number)

                # Settle pause so Vant toast/overlay transition finishes cleanly before Bet 2
                await asyncio.sleep(0.45)

                # 2. Place Bet on SMALL and wait for modal to close completely
                logger.info(f"⚡ [2/2] Placing SMALL ₹{bet_amount} for period {issue_number}...")
                small_ok = await self._place_single_side_bet("SMALL", bet_amount, issue_number)

                if not big_ok and not small_ok:
                    logger.warning(f"⚠️ Neither BIG nor SMALL bet could be confirmed for {issue_number}!")
                    return {"ok": False, "reason": "both_bets_failed"}

                # Start continuous draw watcher right away!
                if self._watcher_task and not self._watcher_task.done():
                    self._watcher_task.cancel()

                self._watcher_task = asyncio.create_task(self.watch_and_capture_win_popup(
                    target_issue=str(issue_number),
                    choice="BIG",
                    level=1,
                    confidence=confidence,
                    game_id=game_id
                ))

                return {
                    "ok": True,
                    "dual_bet": True,
                    "big_ok": big_ok,
                    "small_ok": small_ok,
                    "issue": issue_number,
                    "amount": bet_amount
                }

            except Exception as e:
                logger.error(f"Error placing dual bet for {game_id}: {e}", exc_info=True)
                return {"ok": False, "reason": str(e)}

    async def capture_board_screenshot(self, game_id: str = "wingo_1m") -> Optional[io.BytesIO]:
        """Captures real clean screenshot of current game board and history table"""
        if not self.page:
            return None
        try:
            shot_bytes = await self.page.screenshot(type="png", full_page=False)
            buf = io.BytesIO(shot_bytes)
            buf.seek(0)
            return buf
        except Exception as e:
            logger.error(f"Error taking board screenshot: {e}")
            return None

    async def close(self):
        """Safely shuts down browser context and Playwright process"""
        try:
            if self._watcher_task and not self._watcher_task.done():
                self._watcher_task.cancel()
            if self.context:
                await self.context.close()
                self.context = None
            if self.playwright:
                await self.playwright.stop()
                self.playwright = None
            self.page = None
            self.is_ready = False
            logger.info("Playwright worker stopped.")
        except Exception as e:
            logger.warning(f"Error during Playwright shutdown: {e}")


# Global worker instance
playwright_worker = PlaywrightWinGoWorker()
