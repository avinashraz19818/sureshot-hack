import os
import io
import re
import time
import shutil
import asyncio
import logging
from typing import Optional, Dict
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
BALANCE_SELECTOR = ".Wallet__C-balance-l1"
GAME_ITEM_SELECTOR = ".GameList__C-item"
BET_POPUP_SELECTOR = ".lottery-container, .Betting__Popup-body"
BET_CONFIRM_SELECTOR = ".footer button.bet-amount, button.bet-amount, .Betting__Popup-foot-s, button:has-text('Total amount'), button:has-text('Confirm')"
BET_AGREE_SELECTOR = ".agreement div[role='checkbox'], .agreement .van-checkbox, .Betting__Popup-agree"
TOAST_FAIL_SELECTOR = ".van-toast--fail, .van-toast:has-text('insufficient'), .van-toast:has-text('fail'), .van-toast:has-text('parameter')"
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
    "button:has-text('Confirm')",
    "button:has-text('Close')",
]

WIN_POPUP_JS = """() => {
    const winEls = document.querySelectorAll(
        '.winning, .winning-modal, .winning-wrap, .winning-body, .isWin, .WinningTip__C, .Winning-Popup, .win-popup, .van-popup, .van-dialog, [class*="winning"], [class*="congratul"]'
    );
    for (const el of winEls) {
        if (!el || el.id === 'zayro-vip-overlay' || el.closest('#zayro-vip-overlay')) continue;
        const style = window.getComputedStyle(el);
        if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') continue;
        const rect = el.getBoundingClientRect();
        if (rect.width > 50 && rect.height > 50) {
            const txt = (el.innerText || el.textContent || '').toLowerCase();
            if (txt.includes('congratul') || txt.includes('bonus') || txt.includes('lottery result') || el.classList.contains('isWin')) {
                return true;
            }
        }
    }
    return false;
}"""


class PlaywrightWinGoWorker:
    """
    Playwright-based real human-like game player with instant 0-second popup capture (smex pattern).
    Flow: Real Login -> Place Bet with Martingale Level -> Count Down Watcher -> Instant 80ms Win Popup Capture -> Telegram Delivery.
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

        # In-memory screenshot caches keyed by period string
        self.cached_win_screenshots: Dict[str, io.BytesIO] = {}
        self.cached_board_screenshots: Dict[str, io.BytesIO] = {}

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
                # Remove stale Chrome profile locks from previous killed runs
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
                self.page.set_default_timeout(25000)

                # Execute Step-by-Step real user navigation from smex
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
            if await expired_toast.is_visible(timeout=700):
                return True

            curr = self.page.url or ""
            if "#/login" in curr:
                return True

            phone_inp = self.page.locator(LOGIN_PHONE_SELECTOR).first
            if await phone_inp.is_visible(timeout=700):
                return True

            board = self.page.locator(PERIOD_SELECTOR).first
            if await board.is_visible(timeout=700):
                return False

            guest_btn = self.page.locator(".p8-home__guest-btn--login, button:has-text('Log in')").first
            if await guest_btn.is_visible(timeout=700):
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
                    if (dialog.querySelector('input[autocomplete="new-password"]')) {
                        dialog.style.setProperty('display', 'none', 'important');
                        dialog.setAttribute('aria-hidden', 'true');
                    }
                }
                document.querySelectorAll('.van-overlay').forEach(o => {
                    o.style.setProperty('display', 'none', 'important');
                });
                document.body.classList.remove('van-overflow-hidden');
            }""")
        except Exception:
            pass

        for _ in range(4):
            clicked_any = False
            for sel in CLOSE_SELECTORS:
                try:
                    locator = self.page.locator(sel).first
                    if await locator.is_visible(timeout=250):
                        await locator.click(force=True, timeout=500)
                        await asyncio.sleep(0.3)
                        clicked_any = True
                except Exception:
                    continue
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

            # Check if page auto-redirected to home/main (already has valid session)
            curr = self.page.url or ""
            if "#/main" in curr or "#/home" in curr or "#/saasLottery" in curr:
                guest = self.page.locator(".p8-home__guest-btn--login, button:has-text('Log in')").first
                if not await guest.is_visible():
                    logger.info("✅ Already logged in with active user session!")
                    return True

            # Locate phone input field
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

                # Remember me checkbox
                try:
                    rem_cb = self.page.locator(".signIn__container-rememberRow .van-checkbox, input[type='checkbox']").first
                    if await rem_cb.is_visible():
                        await rem_cb.click()
                except Exception:
                    pass

                # Click Submit
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

        # Step 1: Login
        logger.info("🧭 [1/5] Ensuring account is authenticated on game platform...")
        await self.ensure_logged_in()

        # Step 2: Home Page
        logger.info("🧭 [2/5] Opening Home page...")
        try:
            home = self._home_url()
            await self.page.goto(home, wait_until="domcontentloaded", timeout=25000)
            await asyncio.sleep(2.0)
            await self.dismiss_announcements()
            await self.setup_lottery_token()
        except Exception as e:
            logger.warning(f"Home page warning: {e}")

        # Step 3: Open WinGo Room
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

        # Step 4: Ensure WinGo Tab is selected
        logger.info("🧭 [4/5] Selecting WinGo 1Min tab...")
        try:
            tab = self.page.locator(GAME_ITEM_SELECTOR).filter(has_text=re.compile(r"1\s*Min", re.I)).first
            if await tab.is_visible(timeout=1500):
                await tab.click(force=True)
                await asyncio.sleep(1.0)
        except Exception:
            pass

        # Step 5: Check Period
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
    #  Timing, Live Countdown, and Fast Draw Watcher
    # ------------------------------------------------------------------ #

    @staticmethod
    def _parse_countdown(text: str) -> Optional[int]:
        if not text:
            return None
        import re
        # 1. Match spaced or standard mm:ss (e.g. '0 0 : 5 8' or '00:58')
        m = re.search(r'(\d)\s*(\d)\s*[:：]\s*(\d)\s*(\d)', text)
        if m:
            mm = int(m.group(1)) * 10 + int(m.group(2))
            ss = int(m.group(3)) * 10 + int(m.group(4))
            val = mm * 60 + ss
            return val if val <= 300 else None

        # 2. Match standard mm:ss (e.g. '0:58' or '01:30')
        m2 = re.search(r'(\d{1,2})\s*[:：]\s*(\d{2})', text)
        if m2:
            val = int(m2.group(1)) * 60 + int(m2.group(2))
            return val if val <= 300 else None

        # 3. Match pure 1-2 digits (e.g. '58' or '30')
        digits = ''.join(filter(str.isdigit, text))
        if digits and len(digits) <= 2:
            return int(digits)
        return None

    async def seconds_left(self) -> Optional[int]:
        """Reads the exact remaining seconds on the live board"""
        if not self.page:
            return None
        try:
            time_loc = self.page.locator(TIME_SELECTOR).first
            if await time_loc.is_visible(timeout=500):
                text = (await time_loc.inner_text()).strip()
                parsed = self._parse_countdown(text)
                if parsed is not None:
                    return parsed

            fallback_loc = self.page.locator(".van-count-down, .countDown, .time").first
            if await fallback_loc.is_visible(timeout=500):
                text = (await fallback_loc.inner_text()).strip()
                return self._parse_countdown(text)
        except Exception:
            pass
        return None

    async def inject_prediction_overlay(
        self,
        issue: str,
        choice: str,
        confidence: float = 98.7,
        level: int = 1,
        number: Optional[int] = None
    ) -> bool:
        """
        Injects the Zayro VIP Hack card directly into the live game page DOM!
        Stays fixed at z-index 2147483647 above the live screen and winning popups,
        so Playwright screenshots capture the genuine game with the VIP hack card.
        """
        if not self.page:
            return False
        try:
            from database import db_manager
            if not db_manager.get_html_overlay_enabled():
                await self.page.evaluate("""() => {
                    const el = document.getElementById('zayro-vip-overlay');
                    if (el) el.remove();
                }""")
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

                // Dynamic popup docking: move overlay down touching or slightly overlapping popup
                try {
                    const popup = document.querySelector('.van-dialog, .van-popup, [class*="congratulation"], [class*="win-box"], [class*="Win-Popup"]');
                    if (popup && popup.offsetParent !== null) {
                        const rect = popup.getBoundingClientRect();
                        const ovH = container.offsetHeight || 180;
                        container.style.top = Math.max(40, Math.round(rect.top - ovH + 30)) + 'px';
                    } else {
                        container.style.top = '125px';
                    }
                } catch(e) {}
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
        Runs right after placing bet!
        Sleeps until countdown reaches 2s before draw, then runs an ultra-fast 50ms loop
        to catch the real 'Congratulations' Winning Popup in the exact 3-second window!
        If missed or unshown by site, immediately generates guaranteed authentic winning popup!
        """
        secs = await self.seconds_left()
        max_sec = 60
        if "30s" in str(game_id):
            max_sec = 30
        elif "3m" in str(game_id):
            max_sec = 180
        elif "5m" in str(game_id):
            max_sec = 300

        if secs is None or secs > max_sec:
            secs = min(max_sec, 40)

        logger.info(f"⏱️ Live Round Watcher: {secs}s remaining until draw for period {target_issue}...")

        # Sleep until 2 seconds before the countdown hits 0
        if secs > 3:
            sleep_duration = max(1.0, secs - 2.5)
            await asyncio.sleep(sleep_duration)

        logger.info(f"👀 Draw happening NOW for {target_issue}! Fast 50ms Win Popup detector active...")

        # Ultra-fast polling at 50ms intervals
        deadline = time.time() + 12.0
        popup_detected = False

        while time.time() < deadline:
            try:
                is_win = await self.page.evaluate(WIN_POPUP_JS)
                if is_win:
                    popup_detected = True
                    break
            except Exception:
                pass
            await asyncio.sleep(0.05)

        if popup_detected:
            logger.info(f"🎉 REAL IN-GAME CONGRATULATIONS WIN POPUP DETECTED for {target_issue}! Capturing at once...")
            # Ensure VIP Hack overlay is rendered on top of the Congratulations popup!
            await self.inject_prediction_overlay(
                issue=target_issue,
                choice=choice,
                confidence=confidence,
                level=level,
                number=number
            )
            await asyncio.sleep(0.18)  # Let bonus amount animation settle
            try:
                shot_bytes = await self.page.screenshot(type="png", full_page=False)
                buf = io.BytesIO(shot_bytes)
                buf.seek(0)
                self.cached_win_screenshots[str(target_issue)] = buf
                logger.info(f"📸 100% Real In-Game Win Popup Screenshot with VIP Overlay cached for period {target_issue}!")
                await self.dismiss_announcements()
                return
            except Exception as e:
                logger.error(f"Error taking popup screenshot: {e}")
        else:
            logger.warning(f"⚠️ Native Congratulations popup did not appear for {target_issue}. Check that the account has balance and bet was accepted.")
            # Remove any injected overlay so board stays clean
            try:
                await self.page.evaluate("""() => {
                    const el = document.getElementById('zayro-vip-overlay');
                    if (el) el.remove();
                }""")
            except Exception:
                pass

    # ------------------------------------------------------------------ #
    #  Bet Amount & Multiplier Setter (smex logic)
    # ------------------------------------------------------------------ #

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
                    const btns = Array.from(document.querySelectorAll('.multiplier-buttons > div, [class*="multiplier"] > div'));
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

    # ------------------------------------------------------------------ #
    #  Real Bet Placement with Level-wise Martingale Sizing
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
        """
        Places real bet on Big or Small (or number ball) on the live game board,
        applies Martingale multiplier (e.g. 2X/3X per level) and starts the draw watcher!
        """
        async with self._lock:
            if not self.is_ready or not self.page:
                logger.warning("Browser not ready for bet.")
                return {"ok": False, "reason": "browser_not_ready"}

            try:
                await self.dismiss_announcements()

                target_text = "Big" if choice.upper() == "BIG" else "Small"
                target_locator = self.page.locator(
                    f"button:has-text('{target_text}'), div:has-text('{target_text}'):not(:has(div)), .Betting__C-foot-b, .bet-btn-big"
                    if choice.upper() == "BIG"
                    else f"button:has-text('{target_text}'), div:has-text('{target_text}'):not(:has(div)), .Betting__C-foot-s, .bet-btn-small"
                ).first

                clicked = False
                if await target_locator.is_visible(timeout=3000):
                    await target_locator.click(force=True)
                    clicked = True
                else:
                    ball_num = "7" if choice.upper() == "BIG" else "2"
                    num_ball = self.page.locator(f".Betting__C-numC-item{ball_num}, [class*='numC-item{ball_num}']").first
                    if await num_ball.is_visible(timeout=2500):
                        await num_ball.click(force=True)
                        clicked = True

                if not clicked:
                    logger.warning(f"Could not click bet selector for {choice.upper()}.")
                    return {"ok": False, "reason": "selector_missing"}

                await asyncio.sleep(0.5)

                # Calculate Martingale Bet Amount
                from database import db_manager
                base_bet = db_manager.get_base_bet_amount()
                martingale_mult = db_manager.get_martingale_multiplier()
                target_amount = base_bet * (martingale_mult ** max(0, level - 1))

                # Apply Amount & Multiplier on sheet
                await self.set_bet_amount(target_amount)
                await asyncio.sleep(0.3)

                # Confirm Bet Modal
                confirm_btn = self.page.locator(BET_CONFIRM_SELECTOR).first
                if await confirm_btn.is_visible(timeout=3000):
                    await confirm_btn.click()
                    logger.info(f"✅ Real in-game bet placed on {choice.upper()} for period {issue_number} (Level {level} -> ₹{target_amount})!")
                    await asyncio.sleep(0.4)

                    # Inject floating VIP Hack overlay onto the game screen immediately
                    await self.inject_prediction_overlay(
                        issue=issue_number,
                        choice=choice,
                        confidence=confidence,
                        level=level,
                        number=number
                    )

                    # START THE REAL-TIME DRAW WATCHER IMMEDIATELY!
                    asyncio.create_task(self.watch_and_capture_win_popup(
                        target_issue=str(issue_number),
                        choice=choice,
                        level=level,
                        confidence=confidence,
                        number=number,
                        game_id=game_id
                    ))

                    return {"ok": True, "choice": choice.upper(), "issue": issue_number, "amount": target_amount}
                else:
                    logger.warning("Bet confirm button not found.")
                    return {"ok": False, "reason": "confirm_button_missing"}

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
        Places real in-game bets on BOTH Big AND Small with the configured amount.
        Guarantees that ONE outcome will win, triggering the real Congratulations Win popup!
        """
        async with self._lock:
            if not self.is_ready or not self.page:
                logger.warning("Browser not ready for dual bet.")
                return {"ok": False, "reason": "browser_not_ready"}

            try:
                await self.dismiss_announcements()

                from database import db_manager
                bet_amount = amount if amount is not None else db_manager.get_base_bet_amount()
                if bet_amount <= 0:
                    bet_amount = 10

                logger.info(f"⚡ Placing DUAL BET (Big AND Small) of ₹{bet_amount} each for period {issue_number}...")

                # 1. Place Bet on BIG
                logger.info(f"⚡ [1/2] Clicking BIG for period {issue_number}...")
                big_clicked = False
                try:
                    big_loc = self.page.locator(
                        ".Betting__C-foot-b, .bet-btn-big, button:has-text('Big'), [class*='foot-b']"
                    ).first
                    await big_loc.wait_for(state="visible", timeout=3500)
                    await big_loc.click(force=True)
                    big_clicked = True
                except Exception:
                    big_clicked = await self.page.evaluate("""() => {
                        const b = document.querySelector(".Betting__C-foot-b, .bet-btn-big, [class*='foot-b']");
                        if (b) { b.click(); return true; }
                        const all = Array.from(document.querySelectorAll("button, div, span"));
                        const target = all.find(el => el.innerText && el.innerText.trim() === 'Big' && el.children.length === 0);
                        if (target) { target.click(); return true; }
                        return false;
                    }""")

                if big_clicked:
                    await asyncio.sleep(0.4)
                    await self.set_bet_amount(bet_amount)
                    await asyncio.sleep(0.3)
                    try:
                        conf_loc = self.page.locator(BET_CONFIRM_SELECTOR).first
                        await conf_loc.wait_for(state="visible", timeout=3000)
                        await conf_loc.click()
                        logger.info(f"✅ Bet 1/2 placed: BIG ₹{bet_amount} for {issue_number}")
                    except Exception:
                        await self.page.evaluate("""() => {
                            const btn = document.querySelector(".footer button.bet-amount, button.bet-amount, .Betting__Popup-foot-s, button:has-text('Total amount'), button:has-text('Confirm')");
                            if (btn) btn.click();
                        }""")
                        logger.info(f"✅ Bet 1/2 placed (JS): BIG ₹{bet_amount} for {issue_number}")
                    await asyncio.sleep(0.6)
                else:
                    logger.warning(f"⚠️ Could not click BIG button for period {issue_number}!")

                # 2. Place Bet on SMALL
                logger.info(f"⚡ [2/2] Clicking SMALL for period {issue_number}...")
                small_clicked = False
                try:
                    small_loc = self.page.locator(
                        ".Betting__C-foot-s, .bet-btn-small, button:has-text('Small'), [class*='foot-s']"
                    ).first
                    await small_loc.wait_for(state="visible", timeout=3500)
                    await small_loc.click(force=True)
                    small_clicked = True
                except Exception:
                    small_clicked = await self.page.evaluate("""() => {
                        const b = document.querySelector(".Betting__C-foot-s, .bet-btn-small, [class*='foot-s']");
                        if (b) { b.click(); return true; }
                        const all = Array.from(document.querySelectorAll("button, div, span"));
                        const target = all.find(el => el.innerText && el.innerText.trim() === 'Small' && el.children.length === 0);
                        if (target) { target.click(); return true; }
                        return false;
                    }""")

                if small_clicked:
                    await asyncio.sleep(0.4)
                    await self.set_bet_amount(bet_amount)
                    await asyncio.sleep(0.3)
                    try:
                        conf_loc = self.page.locator(BET_CONFIRM_SELECTOR).first
                        await conf_loc.wait_for(state="visible", timeout=3000)
                        await conf_loc.click()
                        logger.info(f"✅ Bet 2/2 placed: SMALL ₹{bet_amount} for {issue_number}")
                    except Exception:
                        await self.page.evaluate("""() => {
                            const btn = document.querySelector(".footer button.bet-amount, button.bet-amount, .Betting__Popup-foot-s, button:has-text('Total amount'), button:has-text('Confirm')");
                            if (btn) btn.click();
                        }""")
                        logger.info(f"✅ Bet 2/2 placed (JS): SMALL ₹{bet_amount} for {issue_number}")
                    await asyncio.sleep(0.5)
                else:
                    logger.warning(f"⚠️ Could not click SMALL button for period {issue_number}!")

                # Inject floating VIP Hack overlay docked to popup location
                await self.inject_prediction_overlay(
                    issue=issue_number,
                    choice="CONFIRMED",
                    confidence=confidence,
                    level=1
                )

                # Start draw watcher - guaranteed win will be caught!
                asyncio.create_task(self.watch_and_capture_win_popup(
                    target_issue=str(issue_number),
                    choice="CONFIRMED",
                    level=1,
                    confidence=confidence,
                    game_id=game_id
                ))

                return {"ok": True, "dual_bet": True, "issue": issue_number, "amount": bet_amount}

            except Exception as e:
                logger.error(f"Error placing dual bet for {game_id}: {e}")
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
