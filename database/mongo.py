import os
import logging
from typing import Optional
from datetime import datetime
from pymongo import MongoClient
import config

logger = logging.getLogger(__name__)

class DatabaseManager:
    def __init__(self):
        self.client = None
        self.db = None
        self.connected = False
        self._memory_channels = {}
        self._memory_settings = {
            "mode": getattr(config, "DEFAULT_OPERATING_MODE", "24_7"),
            "pre_alert_minutes": getattr(config, "PRE_ALERT_MINUTES", 15),
            "sessions": getattr(config, "DEFAULT_SESSIONS", []),
            "timezone": getattr(config, "TIMEZONE", "Asia/Kolkata"),
            "active_session": None,
            "base_bet_amount": getattr(config, "DEMO_BET_AMOUNT", 10),
            "martingale_multiplier": 2,
            "max_loss_display_level": 3,
            "auto_clean_loss": True,
            "tpl_prediction": None,
            "tpl_win": None,
            "tpl_loss": None,
            "tpl_pre_session": None,
            "tpl_session_start": None,
            "tpl_session_summary": None,
            "tpl_break": None,
            "tpl_good_morning": None,
            "tpl_good_night": None,
        }
        self._channel_loss_messages = {}
        self._last_settings_fetch = 0
        self.connect()

    def connect(self):
        try:
            self.client = MongoClient(
                config.MONGO_URI,
                serverSelectionTimeoutMS=8000,
                connectTimeoutMS=8000,
                socketTimeoutMS=10000,
                tlsAllowInvalidCertificates=True
            )
            self.db = self.client[config.MONGO_DB_NAME]
            # Test connection
            self.client.admin.command('ping')
            self.connected = True
            logger.info("✅ MongoDB connected successfully!")
            self._ensure_indexes()
            self._ensure_settings()
        except Exception as e:
            self.connected = False
            logger.warning(f"⚠️ MongoDB connection failed: {e}. Using in-memory fallback storage.")

    def _ensure_indexes(self):
        if not self.connected:
            return
        try:
            self.db.channels.create_index("channel_id", unique=True)
            self.db.predictions.create_index([("game_id", 1), ("issue_number", 1)])
            self.db.settings.create_index("key", unique=True)
        except Exception as e:
            logger.error(f"Error creating indexes: {e}")

    def _ensure_settings(self):
        if not self.connected:
            return
        try:
            doc = self.db.settings.find_one({"key": "system_config"})
            if not doc:
                initial = {
                    "key": "system_config",
                    "mode": getattr(config, "DEFAULT_OPERATING_MODE", "24_7"),
                    "pre_alert_minutes": getattr(config, "PRE_ALERT_MINUTES", 15),
                    "sessions": getattr(config, "DEFAULT_SESSIONS", []),
                    "timezone": getattr(config, "TIMEZONE", "Asia/Kolkata"),
                    "active_session": None,
                    "base_bet_amount": getattr(config, "DEMO_BET_AMOUNT", 10),
                    "martingale_multiplier": 2,
                    "max_loss_display_level": 3,
                    "auto_clean_loss": True,
                    "tpl_prediction": None,
                    "tpl_win": None,
                    "tpl_loss": None,
                    "tpl_pre_session": None,
                    "tpl_session_start": None,
                    "tpl_session_summary": None,
                    "tpl_break": None,
                    "tpl_good_morning": None,
                    "tpl_good_night": None,
                    "html_overlay_enabled": True,
                    "custom_html_template": None,
                    "auto_send_apk": False,
                    "apk_file_id": None,
                    "apk_file_name": "ZayroVipHack.apk",
                    "apk_caption": None,
                    "userbot_session": getattr(config, "USERBOT_SESSION", None) or None,
                    "bot_strategy": getattr(config, "BOT_STRATEGY", "sure_shot_hack"),
                    "tpl_hack_signal": None,
                    "hack_send_apk": True,
                    "hack_win_caption": None,
                    "win_stickers": [],
                    "hack_dual_bet_amount": getattr(config, "DEMO_BET_AMOUNT", 10),
                    "updated_at": datetime.utcnow()
                }
                self.db.settings.insert_one(initial)
                self._memory_settings = initial
            else:
                doc.pop("_id", None)
                # Ensure defaults for newly added keys
                if "base_bet_amount" not in doc:
                    doc["base_bet_amount"] = 10
                if "martingale_multiplier" not in doc:
                    doc["martingale_multiplier"] = 2
                if "max_loss_display_level" not in doc:
                    doc["max_loss_display_level"] = 3
                if "auto_clean_loss" not in doc:
                    doc["auto_clean_loss"] = True
                if "html_overlay_enabled" not in doc:
                    doc["html_overlay_enabled"] = True
                if "custom_html_template" not in doc:
                    doc["custom_html_template"] = None
                if "auto_send_apk" not in doc:
                    doc["auto_send_apk"] = False
                if "apk_file_id" not in doc:
                    doc["apk_file_id"] = None
                if "apk_file_name" not in doc:
                    doc["apk_file_name"] = "ZayroVipHack.apk"
                if "apk_caption" not in doc:
                    doc["apk_caption"] = "📥 <b>VIP Mod APK</b> — Download & Win Every Round!"
                if "bot_strategy" not in doc:
                    doc["bot_strategy"] = getattr(config, "BOT_STRATEGY", "sure_shot_hack")
                if "tpl_hack_signal" not in doc:
                    doc["tpl_hack_signal"] = None
                if "hack_send_apk" not in doc:
                    doc["hack_send_apk"] = True
                if "hack_win_caption" not in doc:
                    doc["hack_win_caption"] = None
                if "win_stickers" not in doc:
                    doc["win_stickers"] = []
                if "hack_dual_bet_amount" not in doc:
                    doc["hack_dual_bet_amount"] = doc.get("base_bet_amount", 10)
                if isinstance(doc.get("custom_html_template"), str) and len(doc["custom_html_template"]) > 500:
                    doc["custom_html_template"] = "uploads/custom_overlay.html"
                self._memory_settings = doc
                import time
                self._last_settings_fetch = time.time()
        except Exception as e:
            logger.error(f"Error initializing system settings: {e}")

    # ================= SYSTEM SETTINGS & SESSION SCHEDULE =================

    def get_system_settings(self, force_refresh: bool = False) -> dict:
        import time
        now = time.time()
        if self.connected and (force_refresh or not self._memory_settings or (now - getattr(self, "_last_settings_fetch", 0) > 60)):
            try:
                doc = self.db.settings.find_one({"key": "system_config"})
                if doc:
                    doc.pop("_id", None)
                    if isinstance(doc.get("custom_html_template"), str) and len(doc["custom_html_template"]) > 500:
                        doc["custom_html_template"] = "uploads/custom_overlay.html"
                    self._memory_settings = doc
                    self._last_settings_fetch = now
                    return doc
            except Exception as e:
                logger.error(f"Error getting settings from Mongo: {e}")
        return self._memory_settings

    def update_system_settings(self, updates: dict) -> dict:
        import time
        self._memory_settings.update(updates)
        self._last_settings_fetch = time.time()
        updates["updated_at"] = datetime.utcnow()
        if self.connected:
            try:
                self.db.settings.update_one(
                    {"key": "system_config"},
                    {"$set": updates},
                    upsert=True
                )
                logger.info(f"✅ System settings updated: {list(updates.keys())}")
            except Exception as e:
                logger.error(f"Error updating settings in Mongo: {e}")
        return self._memory_settings

    def set_operating_mode(self, mode: str) -> str:
        """Sets operating mode: '24_7' or 'scheduled'"""
        mode = "24_7" if mode == "24_7" else "scheduled"
        self.update_system_settings({"mode": mode})
        return mode

    def get_base_bet_amount(self) -> int:
        cfg = self.get_system_settings()
        return int(cfg.get("base_bet_amount", 10))

    def set_base_bet_amount(self, amount: int) -> int:
        amount = max(1, int(amount))
        self.update_system_settings({"base_bet_amount": amount})
        return amount

    def get_martingale_multiplier(self) -> int:
        cfg = self.get_system_settings()
        return int(cfg.get("martingale_multiplier", 2))

    def set_martingale_multiplier(self, mult: int) -> int:
        mult = 3 if mult == 3 else 2
        self.update_system_settings({"martingale_multiplier": mult})
        return mult

    def get_message_template(self, tpl_type: str) -> str:
        cfg = self.get_system_settings()
        key = f"tpl_{tpl_type}"
        return cfg.get(key) or ""

    def set_message_template(self, tpl_type: str, content: str):
        key = f"tpl_{tpl_type}"
        self.update_system_settings({key: content.strip() if content else None})

    def get_max_loss_display_level(self) -> int:
        cfg = self.get_system_settings()
        return int(cfg.get("max_loss_display_level", 3))

    def set_max_loss_display_level(self, lvl: int) -> int:
        lvl = max(1, min(10, int(lvl)))
        self.update_system_settings({"max_loss_display_level": lvl})
        return lvl

    def get_auto_clean_loss(self) -> bool:
        cfg = self.get_system_settings()
        return bool(cfg.get("auto_clean_loss", True))

    def set_auto_clean_loss(self, enabled: bool) -> bool:
        self.update_system_settings({"auto_clean_loss": bool(enabled)})
        return bool(enabled)

    def record_channel_loss_message(self, channel_id: str, message_id: int):
        """Stores sent loss message_id to allow auto-deletion on next WIN"""
        channel_id = str(channel_id).strip()
        self._channel_loss_messages.setdefault(channel_id, []).append(int(message_id))

    def pop_channel_loss_messages(self, channel_id: str) -> list:
        """Retrieves and clears all pending loss message_ids for a channel"""
        channel_id = str(channel_id).strip()
        return self._channel_loss_messages.pop(channel_id, [])

    # ================= HTML OVERLAY & VIP APK SETTINGS =================

    def get_html_overlay_enabled(self) -> bool:
        cfg = self.get_system_settings()
        return bool(cfg.get("html_overlay_enabled", True))

    def set_html_overlay_enabled(self, enabled: bool) -> bool:
        self.update_system_settings({"html_overlay_enabled": bool(enabled)})
        return bool(enabled)

    def get_custom_html_template(self) -> Optional[str]:
        cfg = self.get_system_settings()
        val = cfg.get("custom_html_template")
        if not val:
            return None
        # If val points to a file or file exists on disk
        local_path = os.path.join("uploads", "custom_overlay.html")
        if val == "uploads/custom_overlay.html" or os.path.exists(local_path):
            try:
                with open(local_path, "r", encoding="utf-8") as f:
                    return f.read()
            except Exception:
                return None
        # If huge string is in mongo, migrate to disk to keep database tiny and fast
        if isinstance(val, str) and len(val) > 2000:
            try:
                os.makedirs("uploads", exist_ok=True)
                with open(local_path, "w", encoding="utf-8") as f:
                    f.write(val)
                self.update_system_settings({"custom_html_template": "uploads/custom_overlay.html"})
                return val
            except Exception:
                pass
        return val

    def set_custom_html_template(self, content: Optional[str]):
        local_path = os.path.join("uploads", "custom_overlay.html")
        if not content:
            self.update_system_settings({"custom_html_template": None})
            try:
                if os.path.exists(local_path):
                    os.remove(local_path)
            except Exception:
                pass
            return

        # Always save content to local disk so Mongo document stays super small and fast
        try:
            os.makedirs("uploads", exist_ok=True)
            with open(local_path, "w", encoding="utf-8") as f:
                f.write(content)
            self.update_system_settings({"custom_html_template": "uploads/custom_overlay.html"})
        except Exception as e:
            logger.error(f"Error saving custom html template: {e}")
            self.update_system_settings({"custom_html_template": "active"})

    def get_auto_send_apk(self) -> bool:
        cfg = self.get_system_settings()
        val = cfg.get("auto_send_apk")
        if val is None:
            return bool(cfg.get("apk_file_id"))
        return bool(val)

    def set_auto_send_apk(self, enabled: bool) -> bool:
        self.update_system_settings({"auto_send_apk": bool(enabled)})
        return bool(enabled)

    def get_apk_file_id(self) -> Optional[str]:
        cfg = self.get_system_settings()
        return cfg.get("apk_file_id")

    def set_apk_file(self, file_id: str, file_name: str = "ZayroVipHack.apk", caption: Optional[str] = None):
        updates = {
            "apk_file_id": str(file_id).strip(),
            "apk_file_name": str(file_name).strip(),
            "auto_send_apk": True
        }
        if caption is not None and str(caption).strip():
            updates["apk_caption"] = str(caption).strip()
        self.update_system_settings(updates)

    def get_apk_file_name(self) -> str:
        cfg = self.get_system_settings()
        return cfg.get("apk_file_name", "ZayroVipHack.apk")

    def get_apk_caption(self) -> Optional[str]:
        cfg = self.get_system_settings()
        cap = cfg.get("apk_caption")
        if cap is not None and str(cap).strip():
            return str(cap).strip()
        return None

    def set_apk_caption(self, caption: Optional[str]) -> Optional[str]:
        if caption is not None:
            caption = str(caption).strip()
        self.update_system_settings({"apk_caption": caption})
        return caption

    def get_userbot_session(self) -> Optional[str]:
        cfg = self.get_system_settings()
        sess = cfg.get("userbot_session")
        if sess and str(sess).strip():
            return str(sess).strip()
        from_cfg = getattr(config, "USERBOT_SESSION", "")
        return from_cfg.strip() if from_cfg else None

    def set_userbot_session(self, session_str: Optional[str]):
        val = str(session_str).strip() if session_str else None
        self.update_system_settings({"userbot_session": val})

    # ================= STRATEGY & SURE-SHOT HACK MODE =================

    def get_bot_strategy(self) -> str:
        cfg = self.get_system_settings()
        return str(cfg.get("bot_strategy", getattr(config, "BOT_STRATEGY", "sure_shot_hack"))).lower()

    def set_bot_strategy(self, strategy: str) -> str:
        s = "sure_shot_hack" if "hack" in str(strategy).lower() or "sure" in str(strategy).lower() else "standard"
        self.update_system_settings({"bot_strategy": s})
        return s

    def is_hack_strategy(self) -> bool:
        return self.get_bot_strategy() == "sure_shot_hack"

    def get_hack_signal_template(self) -> Optional[str]:
        cfg = self.get_system_settings()
        tpl = cfg.get("tpl_hack_signal")
        return str(tpl).strip() if tpl and str(tpl).strip() else None

    def set_hack_signal_template(self, tpl: Optional[str]) -> Optional[str]:
        val = str(tpl).strip() if tpl and str(tpl).strip() else None
        self.update_system_settings({"tpl_hack_signal": val})
        return val

    def get_hack_send_apk(self) -> bool:
        cfg = self.get_system_settings()
        return bool(cfg.get("hack_send_apk", True))

    def set_hack_send_apk(self, enabled: bool) -> bool:
        self.update_system_settings({"hack_send_apk": bool(enabled)})
        return bool(enabled)

    def get_hack_win_caption(self) -> Optional[str]:
        cfg = self.get_system_settings()
        cap = cfg.get("hack_win_caption")
        return str(cap).strip() if cap and str(cap).strip() else None

    def set_hack_win_caption(self, caption: Optional[str]) -> Optional[str]:
        val = str(caption).strip() if caption and str(caption).strip() else None
        self.update_system_settings({"hack_win_caption": val})
        return val

    def get_win_stickers(self) -> list:
        cfg = self.get_system_settings()
        return list(cfg.get("win_stickers", []))

    def add_win_sticker(self, sticker_id: str) -> list:
        stickers = self.get_win_stickers()
        s_id = str(sticker_id).strip()
        if s_id and s_id not in stickers:
            stickers.append(s_id)
            self.update_system_settings({"win_stickers": stickers})
        return stickers

    def clear_win_stickers(self) -> list:
        self.update_system_settings({"win_stickers": []})
        return []

    def get_sessions(self) -> list:
        cfg = self.get_system_settings()
        return cfg.get("sessions", getattr(config, "DEFAULT_SESSIONS", []))

    def update_sessions(self, sessions: list) -> list:
        self.update_system_settings({"sessions": sessions})
        return sessions

    def add_session(self, name: str, start: str, end: str, max_rounds: int = 15) -> dict:
        sessions = self.get_sessions()
        next_id = max([s.get("id", 0) for s in sessions], default=0) + 1
        new_sess = {
            "id": next_id,
            "name": name.strip(),
            "start": start.strip(),
            "end": end.strip(),
            "max_rounds": int(max_rounds)
        }
        sessions.append(new_sess)
        self.update_sessions(sessions)
        return new_sess

    def delete_session(self, session_id: int) -> bool:
        sessions = self.get_sessions()
        filtered = [s for s in sessions if s.get("id") != session_id]
        if len(filtered) != len(sessions):
            self.update_sessions(filtered)
            return True
        return False

    def update_session(self, session_id: int, updates: dict) -> bool:
        sessions = self.get_sessions()
        updated = False
        for s in sessions:
            if s.get("id") == session_id:
                s.update(updates)
                updated = True
                break
        if updated:
            self.update_sessions(sessions)
        return updated

    def reset_sessions_to_default(self) -> list:
        default_s = getattr(config, "DEFAULT_SESSIONS", [])
        self.update_sessions(default_s)
        return default_s

    # ================= CHANNEL MANAGEMENT =================

    def add_channel(self, channel_id, title="", game_id="wingo_1m", register_link=None, promo_text=None):
        channel_id = str(channel_id).strip()
        existing = self.get_channel(channel_id)
        existing_buttons = existing.get("buttons", []) if existing else []

        data = {
            "channel_id": channel_id,
            "title": title or (existing.get("title") if existing else f"Channel {channel_id}"),
            "game_id": game_id,
            "is_active": True,
            "register_link": register_link or (existing.get("register_link") if existing else config.DEFAULT_REGISTER_LINK),
            "promo_text": promo_text or (existing.get("promo_text") if existing else config.DEFAULT_PROMO_TEXT),
            "buttons": existing_buttons,
            "loss_message_ids": existing.get("loss_message_ids", []) if existing else [],
            "current_level": existing.get("current_level", 1) if existing else 1,
            "max_level": 5,
            "stats": existing.get("stats", {
                "total_predictions": 0,
                "wins": 0,
                "losses": 0,
                "current_streak": 0,
                "best_streak": 0
            }) if existing else {
                "total_predictions": 0,
                "wins": 0,
                "losses": 0,
                "current_streak": 0,
                "best_streak": 0
            },
            "created_at": existing.get("created_at", datetime.utcnow()) if existing else datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }

        self._memory_channels[channel_id] = data

        if self.connected:
            try:
                self.db.channels.update_one(
                    {"channel_id": channel_id},
                    {"$set": data},
                    upsert=True
                )
                logger.info(f"✅ Channel {channel_id} saved to MongoDB (Game: {game_id})")
            except Exception as e:
                logger.error(f"Error saving channel to Mongo: {e}")
        return data

    def get_channel(self, channel_id):
        channel_id = str(channel_id).strip()
        if self.connected:
            try:
                doc = self.db.channels.find_one({"channel_id": channel_id})
                if doc:
                    doc.pop("_id", None)
                    if "buttons" not in doc:
                        doc["buttons"] = []
                    return doc
            except Exception as e:
                logger.error(f"Error getting channel from Mongo: {e}")
        return self._memory_channels.get(channel_id)

    def get_all_channels(self):
        if self.connected:
            try:
                cursor = self.db.channels.find()
                channels = []
                for c in cursor:
                    c.pop("_id", None)
                    if "buttons" not in c:
                        c["buttons"] = []
                    channels.append(c)
                for c in channels:
                    self._memory_channels[c["channel_id"]] = c
                return channels
            except Exception as e:
                logger.error(f"Error fetching all channels: {e}")
        return list(self._memory_channels.values())

    def get_channels_by_game(self, game_id, only_active=True):
        channels = self.get_all_channels()
        filtered = [c for c in channels if c.get("game_id") == game_id]
        if only_active:
            filtered = [c for c in filtered if c.get("is_active", True)]
        return filtered

    def update_channel(self, channel_id, updates: dict):
        channel_id = str(channel_id).strip()
        updates["updated_at"] = datetime.utcnow()

        if channel_id in self._memory_channels:
            self._memory_channels[channel_id].update(updates)

        if self.connected:
            try:
                self.db.channels.update_one(
                    {"channel_id": channel_id},
                    {"$set": updates}
                )
                logger.info(f"✅ Channel {channel_id} updated: {list(updates.keys())}")
            except Exception as e:
                logger.error(f"Error updating channel: {e}")

    # ================= CHANNEL BUTTON MANAGEMENT =================

    def add_channel_button(self, channel_id: str, text: str, url: str, style: str = None, icon_custom_emoji_id: str = None):
        ch = self.get_channel(channel_id)
        if not ch:
            return []
        buttons = ch.get("buttons", [])
        btn_obj = {
            "text": text.strip(),
            "url": url.strip(),
            "style": style if style in ("success", "danger", "primary") else None,
            "icon_custom_emoji_id": icon_custom_emoji_id
        }
        buttons.append(btn_obj)
        self.update_channel(channel_id, {"buttons": buttons})
        return buttons

    def remove_channel_button(self, channel_id: str, index: int):
        ch = self.get_channel(channel_id)
        if not ch:
            return []
        buttons = ch.get("buttons", [])
        if 0 <= index < len(buttons):
            buttons.pop(index)
            self.update_channel(channel_id, {"buttons": buttons})
        return buttons

    def clear_channel_buttons(self, channel_id: str):
        self.update_channel(channel_id, {"buttons": []})
        return []

    def remove_channel(self, channel_id):
        channel_id = str(channel_id).strip()
        self._memory_channels.pop(channel_id, None)
        if self.connected:
            try:
                self.db.channels.delete_one({"channel_id": channel_id})
                logger.info(f"✅ Channel {channel_id} deleted from DB")
                return True
            except Exception as e:
                logger.error(f"Error removing channel: {e}")
        return True

    def toggle_channel_active(self, channel_id):
        ch = self.get_channel(channel_id)
        if not ch:
            return False
        new_status = not ch.get("is_active", True)
        self.update_channel(channel_id, {"is_active": new_status})
        return new_status

    def record_channel_result(self, channel_id, is_win: bool):
        ch = self.get_channel(channel_id)
        if not ch:
            return {}, 1

        stats = ch.get("stats", {
            "total_predictions": 0,
            "wins": 0,
            "losses": 0,
            "current_streak": 0,
            "best_streak": 0
        })

        curr_level = ch.get("current_level", 1)
        max_level = ch.get("max_level", 5)

        stats["total_predictions"] += 1
        if is_win:
            stats["wins"] += 1
            stats["current_streak"] = stats.get("current_streak", 0) + 1
            if stats["current_streak"] > stats.get("best_streak", 0):
                stats["best_streak"] = stats["current_streak"]
            next_level = 1  # Reset to Level 1 on WIN
        else:
            stats["losses"] += 1
            stats["current_streak"] = 0
            next_level = curr_level + 1 if curr_level < max_level else 1

        self.update_channel(channel_id, {
            "stats": stats,
            "current_level": next_level
        })
        return stats, next_level

    # ================= PREDICTION HISTORY =================

    def save_prediction(self, game_id, issue_number, prediction_data):
        doc = {
            "game_id": game_id,
            "issue_number": str(issue_number),
            "data": prediction_data,
            "created_at": datetime.utcnow()
        }
        if self.connected:
            try:
                self.db.predictions.update_one(
                    {"game_id": game_id, "issue_number": str(issue_number)},
                    {"$set": doc},
                    upsert=True
                )
            except Exception as e:
                logger.error(f"Error saving prediction doc: {e}")

db_manager = DatabaseManager()
db = db_manager

