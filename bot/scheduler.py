import io
import asyncio
import logging
from datetime import datetime, timedelta
import pytz
from telegram import Bot
from telegram.constants import ParseMode
from telegram.error import TelegramError

import config
from database import db_manager
from services.lottery_api import lottery_api
from services.bet_automation import bet_automation
from engine.predictor import predictor
from bot.templates import (
    render_hack_signal_card,
    render_prediction_card,
    render_win_card,
    render_loss_card,
    render_pre_session_alert_card,
    render_session_start_card,
    render_session_summary_card,
    render_break_card,
    render_good_morning_card,
    render_good_night_card,
    strip_tg_emoji_tags
)
from bot.keyboards import get_channel_post_keyboard
from services.userbot_manager import userbot_manager

logger = logging.getLogger(__name__)


class WinGoScheduler:
    def __init__(self, bot: Bot):
        self.bot = bot
        self.running = False
        self.tasks = []
        self.tz = pytz.timezone(getattr(config, "TIMEZONE", "Asia/Kolkata"))

        # Session tracking state
        self.active_session = None  # None or dict of active session details
        self.pre_alerts_sent_today = set()  # set of session_ids
        self.completed_sessions_today = set()  # set of session_ids
        self.morning_sent_today = False
        self.night_sent_today = False
        self.last_day_checked = None

        # State per game_id
        self.game_states = {
            game_id: {
                "last_processed_issue": None,
                "active_prediction": None,
                "waiting_result": False
            }
            for game_id in config.WINGO_GAMES.keys()
        }

    async def start(self):
        self.running = True
        logger.info("🚀 Starting WinGo Multi-Game Schedulers with Session Controller...")

        # Initialize Playwright real game automation in background after Telegram polling is active
        if config.DEMO_AUTO_BET or db_manager.is_hack_strategy():
            async def _bg_playwright_init():
                await asyncio.sleep(4.0)
                await bet_automation.initialize()
            asyncio.create_task(_bg_playwright_init())

        # Start game prediction loops
        for game_id in config.WINGO_GAMES.keys():
            task = asyncio.create_task(self._game_loop(game_id))
            self.tasks.append(task)

        # Start Session Controller loop
        session_task = asyncio.create_task(self._session_controller_loop())
        self.tasks.append(session_task)

    async def stop(self):
        self.running = False
        for task in self.tasks:
            task.cancel()
        await lottery_api.close()
        await bet_automation.close()
        logger.info("🛑 WinGo Schedulers stopped.")

    # ================= MESSAGE SENDING HELPERS =================

    async def _safe_send_message(self, channel: dict, text: str):
        """Sends message with custom colored buttons & premium emojis, with userbot & standard fallback"""
        channel_id = channel["channel_id"]

        # 1. Try sending via Telegram Userbot for 100% animated custom emojis
        if userbot_manager.is_active():
            try:
                sent = await userbot_manager.send_channel_message(channel_id, text, channel)
                if sent:
                    return sent
            except Exception as ue:
                logger.warning(f"⚠️ Userbot send message failed ({ue}), falling back to Bot API...")

        reply_markup = get_channel_post_keyboard(channel, include_custom_emoji=True, include_style=True)

        try:
            msg = await self.bot.send_message(
                chat_id=channel_id,
                text=text,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup,
                disable_web_page_preview=True
            )
            return msg
        except TelegramError as te:
            err_str = str(te).lower()
            if "custom_emoji" in err_str or "button" in err_str or "style" in err_str or "entity" in err_str or "parse" in err_str:
                try:
                    fallback_markup = get_channel_post_keyboard(channel, include_custom_emoji=False, include_style=True)
                    msg = await self.bot.send_message(
                        chat_id=channel_id,
                        text=strip_tg_emoji_tags(text),
                        parse_mode=ParseMode.HTML,
                        reply_markup=fallback_markup,
                        disable_web_page_preview=True
                    )
                    return msg
                except TelegramError:
                    try:
                        fallback_markup2 = get_channel_post_keyboard(channel, include_custom_emoji=False, include_style=False)
                        msg = await self.bot.send_message(
                            chat_id=channel_id,
                            text=strip_tg_emoji_tags(text),
                            parse_mode=ParseMode.HTML,
                            reply_markup=fallback_markup2,
                            disable_web_page_preview=True
                        )
                        return msg
                    except TelegramError as te2:
                        # Final plain-text fallback
                        try:
                            clean_plain = re.sub(r"<[^>]+>", "", text)
                            return await self.bot.send_message(
                                chat_id=channel_id,
                                text=clean_plain,
                                disable_web_page_preview=True
                            )
                        except Exception:
                            pass
            logger.error(f"❌ Failed to send message to {channel_id}: {te}")
            return None

    async def _safe_send_photo(self, channel: dict, photo_bytes: bytes, caption: str):
        """Sends photo with custom colored buttons & premium emojis, with userbot & standard fallback"""
        channel_id = channel["channel_id"]

        # 1. Try sending via Telegram Userbot for 100% animated custom emojis in caption
        if userbot_manager.is_active():
            try:
                sent = await userbot_manager.send_channel_photo(channel_id, photo_bytes, caption, channel)
                if sent:
                    return sent
            except Exception as ue:
                logger.warning(f"⚠️ Userbot send photo failed ({ue}), falling back to Bot API...")

        reply_markup = get_channel_post_keyboard(channel, include_custom_emoji=True, include_style=True)

        try:
            msg = await self.bot.send_photo(
                chat_id=channel_id,
                photo=io.BytesIO(photo_bytes),
                caption=caption,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup
            )
            return msg
        except TelegramError as te:
            err_str = str(te).lower()
            if "custom_emoji" in err_str or "button" in err_str or "style" in err_str or "entity" in err_str or "parse" in err_str:
                try:
                    fallback_markup = get_channel_post_keyboard(channel, include_custom_emoji=False, include_style=True)
                    msg = await self.bot.send_photo(
                        chat_id=channel_id,
                        photo=io.BytesIO(photo_bytes),
                        caption=strip_tg_emoji_tags(caption),
                        parse_mode=ParseMode.HTML,
                        reply_markup=fallback_markup
                    )
                    return msg
                except TelegramError:
                    try:
                        fallback_markup2 = get_channel_post_keyboard(channel, include_custom_emoji=False, include_style=False)
                        msg = await self.bot.send_photo(
                            chat_id=channel_id,
                            photo=io.BytesIO(photo_bytes),
                            caption=strip_tg_emoji_tags(caption),
                            parse_mode=ParseMode.HTML,
                            reply_markup=fallback_markup2
                        )
                        return msg
                    except TelegramError:
                        clean_plain = re.sub(r"<[^>]+>", "", caption)
                        return await self.bot.send_photo(
                            chat_id=channel_id,
                            photo=io.BytesIO(photo_bytes),
                            caption=clean_plain
                        )
            logger.error(f"❌ Failed to send photo to {channel_id}: {te}")
            return None

    async def _safe_send_sticker(self, channel_id: int | str, sticker_id: str):
        try:
            if userbot_manager.is_active():
                try:
                    return await userbot_manager.send_channel_sticker(channel_id, sticker_id)
                except Exception as ue:
                    logger.debug(f"Userbot send sticker fallback: {ue}")
            return await self.bot.send_sticker(chat_id=channel_id, sticker=sticker_id)
        except Exception as e:
            logger.warning(f"Failed to send sticker to {channel_id}: {e}")
            return None

    async def _safe_send_document(self, channel_id: int | str, document: str, caption: str = None):
        try:
            if userbot_manager.is_active():
                try:
                    return await userbot_manager.send_channel_document(channel_id, document, caption)
                except Exception as ue:
                    logger.debug(f"Userbot send document fallback: {ue}")
            return await self.bot.send_document(
                chat_id=channel_id,
                document=document,
                caption=caption,
                parse_mode=ParseMode.HTML if caption else None
            )
        except Exception as e:
            logger.warning(f"Failed to send document to {channel_id}: {e}")
            return None

    # ================= SESSION SCHEDULER CONTROLLER ================

    def _now_ist(self) -> datetime:
        return datetime.now(self.tz)

    def is_signal_allowed(self) -> bool:
        """Determines if signals should be posted right now based on mode"""
        cfg = db_manager.get_system_settings()
        mode = cfg.get("mode", "24_7")
        if mode == "24_7":
            return True
        # In Scheduled mode, only allowed if a session is actively running
        return self.active_session is not None

    async def _session_controller_loop(self):
        """Monitors IST clock and manages pre-alerts, session starts, and wrap-up cards"""
        logger.info("🕒 Session Controller Loop active (Timezone: IST)...")

        while self.running:
            try:
                now = self._now_ist()
                today_str = now.strftime("%Y-%m-%d")

                # Daily reset of session tracking
                if self.last_day_checked != today_str:
                    self.pre_alerts_sent_today.clear()
                    self.completed_sessions_today.clear()
                    self.morning_sent_today = False
                    self.night_sent_today = False
                    self.last_day_checked = today_str

                cfg = db_manager.get_system_settings()
                mode = cfg.get("mode", "24_7")

                if mode == "scheduled":
                    sessions = cfg.get("sessions", getattr(config, "DEFAULT_SESSIONS", []))
                    current_hm = now.strftime("%H:%M")
                    pre_alert_mins = int(cfg.get("pre_alert_minutes", 15))

                    # Morning Greetings Check (08:00 AM IST)
                    if now.hour >= 8 and not self.morning_sent_today:
                        await self._broadcast_good_morning()
                        self.morning_sent_today = True

                    # Night Message Check (All sessions finished or after 22:30 IST)
                    all_done = (len(self.completed_sessions_today) >= len(sessions) > 0)
                    late_night = (now.hour >= 23 or (now.hour == 22 and now.minute >= 30))
                    if (all_done or late_night) and not self.night_sent_today and not self.active_session:
                        await self._broadcast_good_night()
                        self.night_sent_today = True

                    for s in sessions:
                        s_id = s["id"]
                        s_name = s.get("name", f"Session {s_id}")
                        start_str = s["start"]
                        end_str = s["end"]
                        max_rounds = s.get("max_rounds", 15)

                        # Parse times
                        s_start_dt = now.replace(
                            hour=int(start_str.split(":")[0]),
                            minute=int(start_str.split(":")[1]),
                            second=0,
                            microsecond=0
                        )
                        s_end_dt = now.replace(
                            hour=int(end_str.split(":")[0]),
                            minute=int(end_str.split(":")[1]),
                            second=0,
                            microsecond=0
                        )
                        pre_alert_dt = s_start_dt - timedelta(minutes=pre_alert_mins)

                        # 1. Check Pre-Session Alert (T - 15 mins)
                        if pre_alert_dt <= now < s_start_dt:
                            if s_id not in self.pre_alerts_sent_today:
                                await self._broadcast_pre_session_alert(s_name, start_str)
                                self.pre_alerts_sent_today.add(s_id)

                        # 2. Check Session Start
                        if s_start_dt <= now < s_end_dt and s_id not in self.completed_sessions_today:
                            if not self.active_session or self.active_session.get("id") != s_id:
                                self.active_session = {
                                    "id": s_id,
                                    "name": s_name,
                                    "start": start_str,
                                    "end": end_str,
                                    "max_rounds": max_rounds,
                                    "rounds": 0,
                                    "wins": 0,
                                    "losses": 0,
                                    "current_streak": 0,
                                    "max_streak": 0,
                                    "max_level_used": 1,
                                    "profit": 0.0
                                }
                                await self._broadcast_session_start(s_name, end_str, max_rounds)

                        # 3. Check Session End Condition
                        if self.active_session and self.active_session.get("id") == s_id:
                            time_up = (now >= s_end_dt)
                            rounds_done = (self.active_session["rounds"] >= max_rounds)

                            if time_up or rounds_done:
                                await self._conclude_session(self.active_session, sessions)
                                self.completed_sessions_today.add(s_id)
                                self.active_session = None

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in session controller: {e}", exc_info=True)

            await asyncio.sleep(10)

    async def _broadcast_pre_session_alert(self, session_name: str, start_time: str):
        """Sends 15-minute advance notice to all active channels"""
        channels = db_manager.get_all_channels()
        active_channels = [c for c in channels if c.get("is_active", True)]
        if not active_channels:
            return

        logger.info(f"🚨 Broadcasting Pre-Session Alert for {session_name} starting at {start_time} IST...")
        custom_tpl = db_manager.get_message_template("pre_session")
        for ch in active_channels:
            promo = ch.get("promo_text", config.DEFAULT_PROMO_TEXT)
            text = render_pre_session_alert_card(
                session_name=session_name,
                start_time=start_time,
                game_name="WinGo 1 Minute VIP",
                promo_text=promo,
                custom_template=custom_tpl
            )
            await self._safe_send_message(ch, text)

    async def _broadcast_session_start(self, session_name: str, end_time: str, max_rounds: int):
        """Sends live kickoff announcement to all channels"""
        channels = db_manager.get_all_channels()
        active_channels = [c for c in channels if c.get("is_active", True)]
        if not active_channels:
            return

        logger.info(f"🟢 Broadcasting VIP Session Live Alert: {session_name}!")
        custom_tpl = db_manager.get_message_template("session_start")
        for ch in active_channels:
            text = render_session_start_card(
                session_name=session_name,
                end_time=end_time,
                max_rounds=max_rounds,
                game_name="WinGo 1 Minute",
                custom_template=custom_tpl
            )
            await self._safe_send_message(ch, text)

    async def _conclude_session(self, session_data: dict, all_sessions: list):
        """Sends end-of-session summary card with accuracy and profit metrics"""
        channels = db_manager.get_all_channels()
        active_channels = [c for c in channels if c.get("is_active", True)]
        if not active_channels:
            return

        # Find next session
        next_text = "Tomorrow at 11:00 AM IST"
        curr_id = session_data["id"]
        for s in all_sessions:
            if s["id"] > curr_id:
                next_text = f"Today at {s['start']} IST ({s.get('name', 'Next Session')})"
                break

        total_rounds = session_data["rounds"]
        wins = session_data["wins"]
        losses = session_data["losses"]
        max_streak = session_data["max_streak"]
        max_lvl = session_data["max_level_used"]
        profit = session_data["profit"]

        logger.info(f"🏆 Concluding {session_data['name']}: {wins}/{total_rounds} Wins | Profit: ₹{profit}")

        custom_tpl = db_manager.get_message_template("session_summary")
        text = render_session_summary_card(
            session_name=session_data["name"],
            total_rounds=total_rounds,
            wins=wins,
            losses=losses,
            max_streak=max_streak,
            max_level_used=max_lvl,
            profit_inr=profit,
            next_session_text=next_text,
            custom_template=custom_tpl
        )

        for ch in active_channels:
            await self._safe_send_message(ch, text)

        # Broadcast Break Time Card (matching maxie1min format)
        await asyncio.sleep(2)
        await self._broadcast_break(next_text, duration_mins=15)

    async def _broadcast_break(self, next_session_text: str, duration_mins: int = 15):
        """Sends Break Time notice between sessions to all active channels"""
        channels = db_manager.get_all_channels()
        active_channels = [c for c in channels if c.get("is_active", True)]
        if not active_channels:
            return

        logger.info(f"⏸️ Broadcasting Break Time Card (Next: {next_session_text})...")
        custom_tpl = db_manager.get_message_template("break")
        break_text = render_break_card(
            next_session_text=next_session_text,
            duration_mins=duration_mins,
            custom_template=custom_tpl
        )
        for ch in active_channels:
            await self._safe_send_message(ch, break_text)

    async def _broadcast_good_morning(self):
        """Sends daily morning greeting kickoff to all active channels"""
        channels = db_manager.get_all_channels()
        active_channels = [c for c in channels if c.get("is_active", True)]
        if not active_channels:
            return

        logger.info("🌅 Broadcasting Good Morning Card to all channels...")
        custom_tpl = db_manager.get_message_template("good_morning")
        text = render_good_morning_card(custom_template=custom_tpl)
        for ch in active_channels:
            await self._safe_send_message(ch, text)

    async def _broadcast_good_night(self):
        """Sends evening signoff completion report to all active channels"""
        channels = db_manager.get_all_channels()
        active_channels = [c for c in channels if c.get("is_active", True)]
        if not active_channels:
            return

        tot_wins = sum(c.get("stats", {}).get("wins", 0) for c in channels)
        tot_losses = sum(c.get("stats", {}).get("losses", 0) for c in channels)

        logger.info(f"🌙 Broadcasting Good Night Card ({tot_wins}W / {tot_losses}L)...")
        custom_tpl = db_manager.get_message_template("good_night")
        text = render_good_night_card(
            wins=tot_wins,
            losses=tot_losses,
            custom_template=custom_tpl
        )
        for ch in active_channels:
            await self._safe_send_message(ch, text)

    # ================= MAIN GAME LOOP =================

    async def _game_loop(self, game_id: str):
        game_cfg = config.WINGO_GAMES[game_id]
        game_name = game_cfg["name"]
        poll_interval = 4 if game_id == "wingo_30s" else (8 if game_id == "wingo_1m" else 15)

        logger.info(f"[{game_name}] Loop active (Polling every {poll_interval}s)")

        while self.running:
            try:
                state = self.game_states[game_id]
                active_pred = state["active_prediction"]

                # Optimization Guard: Only poll if at least one active channel is listening to this game!
                active_channels = db_manager.get_channels_by_game(game_id, only_active=True)
                if not active_channels and not state["waiting_result"]:
                    await asyncio.sleep(15)
                    continue

                # 1. Fetch live history
                history = await lottery_api.fetch_history(game_id)
                if not history or len(history) < 2:
                    await asyncio.sleep(poll_interval)
                    continue

                latest_item = history[0]
                latest_issue = str(latest_item["issueNumber"])

                # 2. Check Result of Active Prediction
                if state["waiting_result"] and active_pred:
                    target_issue = str(active_pred["issue"])

                    matched_item = None
                    for item in history[:10]:
                        if str(item["issueNumber"]) == target_issue:
                            matched_item = item
                            break

                    if matched_item:
                        actual_num = matched_item["number"]
                        actual_choice = matched_item["big_small"]
                        is_hack_mode = db_manager.is_hack_strategy()
                        if is_hack_mode:
                            is_win = True
                        else:
                            is_win = (active_pred["choice"] == actual_choice)
                        hit_lucky = (actual_num in active_pred.get("numbers", []))

                        logger.info(f"[{game_name}] Result for {target_issue}: {actual_choice} ({actual_num}) | Pred: {active_pred['choice']} -> {'WIN ✅' if is_win else 'LOSS ❌'}")

                        # Update session stats if session is active
                        if self.active_session:
                            self.active_session["rounds"] += 1
                            if is_win:
                                self.active_session["wins"] += 1
                                self.active_session["current_streak"] += 1
                                if self.active_session["current_streak"] > self.active_session["max_streak"]:
                                    self.active_session["max_streak"] = self.active_session["current_streak"]
                                self.active_session["profit"] += 350.0  # Normalized estimated VIP win profit
                            else:
                                self.active_session["losses"] += 1
                                self.active_session["current_streak"] = 0

                        # Broadcast result to channels with guaranteed state cleanup
                        try:
                            await self._broadcast_result(
                                game_id=game_id,
                                issue_number=target_issue,
                                pred_choice=active_pred["choice"],
                                actual_choice=actual_choice,
                                actual_number=actual_num,
                                is_win=is_win,
                                hit_lucky_number=hit_lucky
                            )
                        except Exception as br_err:
                            logger.error(f"[{game_name}] Error broadcasting result for {target_issue}: {br_err}", exc_info=True)
                        finally:
                            state["waiting_result"] = False
                            state["active_prediction"] = None

                    else:
                        # Safety Catch: If latest drawn issue is >= target_issue, this round has already finished!
                        # Never get stuck waiting indefinitely for a past issue.
                        try:
                            if int(latest_issue) >= int(target_issue):
                                logger.warning(
                                    f"[{game_name}] Round {target_issue} has concluded in the past (Latest drawn: {latest_issue}). "
                                    f"Clearing waiting state to resume new predictions immediately!"
                                )
                                state["waiting_result"] = False
                                state["active_prediction"] = None
                        except Exception:
                            pass

                # 3. Generate and Send Next Prediction
                if not state["waiting_result"]:
                    # Guard: Check if signals are allowed by Operating Mode (24/7 or Session)
                    if not self.is_signal_allowed():
                        await asyncio.sleep(poll_interval)
                        continue

                    next_issue = lottery_api.get_next_issue(latest_issue)

                    if state["last_processed_issue"] != next_issue:
                        active_channels = db_manager.get_channels_by_game(game_id, only_active=True)
                        if not active_channels:
                            await asyncio.sleep(poll_interval)
                            continue

                        pred_result = predictor.analyze(history)
                        pred_data = {
                            "issue": next_issue,
                            "choice": pred_result["choice"],
                            "numbers": pred_result["numbers"],
                            "confidence": pred_result["confidence"],
                            "pattern_name": pred_result["pattern_name"],
                            "created_at": datetime.utcnow().isoformat()
                        }

                        is_hack_mode = db_manager.is_hack_strategy()

                        if is_hack_mode:
                            if not bet_automation.is_logged_in:
                                logger.info("Playwright browser not ready yet, initializing before starting round...")
                                await bet_automation.initialize()
                                fresh_hist = await lottery_api.fetch_history(game_id)
                                if fresh_hist and len(fresh_hist) >= 2:
                                    latest_issue = str(fresh_hist[0]["issueNumber"])
                                    next_issue = lottery_api.get_next_issue(latest_issue)

                            logger.info(f"[{game_name}] 🔥 SureShot Hack Active for {next_issue}! Placing Dual Bet on Big & Small...")
                            async def _do_dual_bet(gid, iss):
                                try:
                                    if not bet_automation.is_logged_in:
                                        await bet_automation.initialize()
                                    if bet_automation.is_logged_in:
                                        await bet_automation.place_dual_bet(game_id=gid, issue_number=iss)
                                    else:
                                        logger.warning("Playwright browser could not be initialized.")
                                except Exception as be:
                                    logger.error(f"Error in dual bet runner: {be}")
                            asyncio.create_task(_do_dual_bet(game_id, next_issue))
                            await self._broadcast_hack_signal(game_id, next_issue, active_channels)
                            pred_data = {
                                "issue": next_issue,
                                "choice": "CONFIRMED",
                                "numbers": [],
                                "confidence": 100,
                                "pattern_name": "SureShot Hack",
                                "created_at": datetime.utcnow().isoformat()
                            }
                        else:
                            logger.info(f"[{game_name}] New Signal for {next_issue}: {pred_data['choice']} Numbers: {pred_data['numbers']} ({pred_data['confidence']}%)")
                            current_martingale_level = max([ch.get("current_level", 1) for ch in active_channels], default=1)

                            if bet_automation.enabled and bet_automation.is_logged_in:
                                first_num = pred_data["numbers"][0] if pred_data.get("numbers") else None
                                asyncio.create_task(
                                    bet_automation.place_bet(
                                        game_id=game_id,
                                        choice=pred_data["choice"],
                                        issue_number=next_issue,
                                        level=current_martingale_level,
                                        confidence=pred_data.get("confidence", 98.7),
                                        number=first_num
                                    )
                                )
                            await self._broadcast_prediction(game_id, pred_data, active_channels)

                        state["active_prediction"] = pred_data
                        state["waiting_result"] = True
                        state["last_processed_issue"] = next_issue

                        db_manager.save_prediction(game_id, next_issue, pred_data)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[{game_name}] Loop error: {e}", exc_info=True)

            await asyncio.sleep(poll_interval)

    async def _broadcast_hack_signal(self, game_id: str, issue_number: str, channels: list):
        game_cfg = config.WINGO_GAMES[game_id]
        game_name = game_cfg["name"]
        custom_tpl = db_manager.get_hack_signal_template()
        text = render_hack_signal_card(game_name, issue_number, custom_tpl)

        send_apk = db_manager.get_hack_send_apk()
        apk_file_id = db_manager.get_apk_file_id()
        apk_caption = db_manager.get_apk_caption()

        for ch in channels:
            channel_id = ch["channel_id"]
            try:
                ok = await self._safe_send_message(ch, text)
                if ok:
                    logger.info(f"✅ SureShot Hack signal posted to channel {channel_id}")
                if send_apk and apk_file_id:
                    await asyncio.sleep(0.5)
                    await self._safe_send_document(channel_id, apk_file_id, apk_caption)
                    logger.info(f"📱 Sent VIP APK with signal to channel {channel_id}")
            except Exception as e:
                logger.error(f"❌ Error broadcasting hack signal to {channel_id}: {e}", exc_info=True)

    async def _broadcast_prediction(self, game_id: str, pred_data: dict, channels: list):
        """Sends a brand new individual prediction message to all subscribed channels"""
        game_cfg = config.WINGO_GAMES[game_id]
        game_name = game_cfg["name"]
        custom_tpl = db_manager.get_message_template("prediction")

        for ch in channels:
            channel_id = ch["channel_id"]
            curr_level = ch.get("current_level", 1)
            promo = ch.get("promo_text", config.DEFAULT_PROMO_TEXT)

            text = render_prediction_card(
                game_name=game_name,
                issue_number=pred_data["issue"],
                choice=pred_data["choice"],
                numbers=pred_data["numbers"],
                confidence=pred_data["confidence"],
                level=curr_level,
                pattern_name=pred_data["pattern_name"],
                promo_text=promo,
                custom_template=custom_tpl
            )

            try:
                ok = await self._safe_send_message(ch, text)
                if ok:
                    logger.info(f"✅ Signal posted to channel {channel_id}")
                else:
                    logger.warning(f"⚠️ Failed to deliver signal to channel {channel_id} (verify bot is Admin in channel)")
            except Exception as e:
                logger.error(f"❌ Unexpected error sending to {channel_id}: {e}", exc_info=True)

    async def _broadcast_result(
        self,
        game_id: str,
        issue_number: str,
        pred_choice: str,
        actual_choice: str,
        actual_number: int,
        is_win: bool,
        hit_lucky_number: bool
    ):
        """
        Sends separate WIN celebration (with real Playwright winning screenshot) or LOSS notification
        """
        channels = db_manager.get_channels_by_game(game_id, only_active=True)
        game_cfg = config.WINGO_GAMES[game_id]
        game_name = game_cfg["name"]
        custom_win_tpl = db_manager.get_message_template("win")
        custom_loss_tpl = db_manager.get_message_template("loss")
        max_loss_cards = db_manager.get_max_loss_display_level()
        auto_clean_loss = db_manager.get_auto_clean_loss()

        is_hack_mode = db_manager.is_hack_strategy()
        if is_hack_mode:
            is_win = True  # Dual bet guarantees a win every single round!

        screenshot_bytes = None
        if is_win:
            try:
                screenshot_stream = await asyncio.wait_for(
                    bet_automation.capture_win_screenshot(
                        game_id=game_id,
                        target_issue=issue_number,
                        choice=actual_choice,
                        actual_number=actual_number,
                        level=1,
                        streak=1
                    ),
                    timeout=10.5
                )
                if screenshot_stream:
                    screenshot_bytes = screenshot_stream.getvalue()
            except (asyncio.TimeoutError, Exception) as s_err:
                logger.warning(f"Screenshot delivery fallback: {s_err}")
                screenshot_bytes = None

        for ch in channels:
            channel_id = ch["channel_id"]
            curr_level = ch.get("current_level", 1)

            # Update stats & level in database (records 100% WIN in hack mode)
            stats, next_level = db_manager.record_channel_result(channel_id, is_win)
            streak = stats.get("current_streak", 1)

            if self.active_session:
                if curr_level > self.active_session["max_level_used"]:
                    self.active_session["max_level_used"] = curr_level

            try:
                if is_win:
                    # 1. Auto-Clean previous loss notifications if enabled
                    if auto_clean_loss:
                        loss_msg_ids = db_manager.pop_channel_loss_messages(channel_id)
                        for m_id in loss_msg_ids:
                            try:
                                await self.bot.delete_message(chat_id=channel_id, message_id=m_id)
                            except Exception:
                                pass

                    if is_hack_mode:
                        # SureShot Hack Mode:
                        # Caption: if set, send with caption; if blank/None, send ONLY raw photo!
                        hack_caption = db_manager.get_hack_win_caption() or ""
                        if screenshot_bytes:
                            await self._safe_send_photo(ch, screenshot_bytes, hack_caption)
                        elif hack_caption:
                            await self._safe_send_message(ch, hack_caption)

                        # Send configured win celebratory stickers
                        win_stks = db_manager.get_win_stickers()
                        if win_stks:
                            await asyncio.sleep(0.5)
                            for s_id in win_stks:
                                await self._safe_send_sticker(channel_id, s_id)
                                await asyncio.sleep(0.4)
                    else:
                        # Standard Mode
                        win_text = render_win_card(
                            game_name=game_name,
                            issue_number=issue_number,
                            actual_choice=actual_choice,
                            actual_number=actual_number,
                            level=curr_level,
                            streak=streak,
                            hit_lucky_number=hit_lucky_number,
                            custom_template=custom_win_tpl
                        )
                        if screenshot_bytes:
                            await self._safe_send_photo(ch, screenshot_bytes, win_text)
                        else:
                            await self._safe_send_message(ch, win_text)

                        # Auto-send VIP APK on WIN if enabled
                        auto_send = db_manager.get_auto_send_apk()
                        apk_file_id = db_manager.get_apk_file_id()
                        if auto_send and apk_file_id:
                            apk_caption = db_manager.get_apk_caption()
                            try:
                                await asyncio.sleep(1.0)
                                await self.bot.send_document(
                                    chat_id=channel_id,
                                    document=apk_file_id,
                                    caption=apk_caption,
                                    parse_mode=ParseMode.HTML if apk_caption else None
                                )
                                logger.info(f"📱 Sent VIP APK to channel {channel_id} after WIN!")
                            except Exception as apk_err:
                                logger.warning(f"Failed to auto-send APK: {apk_err}")
                else:
                    # Anti-Loss Clutter: Only broadcast loss card up to configured max level (e.g. 2 or 3)
                    if curr_level <= max_loss_cards:
                        loss_text = render_loss_card(
                            game_name=game_name,
                            issue_number=issue_number,
                            actual_choice=actual_choice,
                            actual_number=actual_number,
                            curr_level=curr_level,
                            next_level=next_level,
                            custom_template=custom_loss_tpl
                        )
                        sent_msg = await self._safe_send_message(ch, loss_text)
                        if sent_msg and hasattr(sent_msg, "message_id"):
                            db_manager.record_channel_loss_message(channel_id, sent_msg.message_id)
                    else:
                        logger.info(
                            f"🛡️ [Anti-Loss Clutter] Suppressed public loss alert for {channel_id} at Level {curr_level} "
                            f"(Max allowed: {max_loss_cards}). Keeping channel clean!"
                        )

            except Exception as e:
                logger.error(f"❌ Error broadcasting result to {channel_id}: {e}")
