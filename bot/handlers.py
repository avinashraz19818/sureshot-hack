import os
import io
import re
import html
import time
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

import config
from database import db_manager
from services.bet_automation import bet_automation
from services.userbot_manager import userbot_manager
from bot.keyboards import (
    get_admin_main_keyboard,
    get_game_select_keyboard,
    get_channel_manage_keyboard,
    get_channel_buttons_keyboard,
    get_button_style_select_keyboard,
    get_sessions_manage_keyboard,
    get_single_session_keyboard,
    get_browser_status_keyboard,
    get_bet_amount_keyboard,
    get_templates_menu_keyboard,
    get_apk_overlay_keyboard,
    get_userbot_keyboard,
    get_hack_menu_keyboard,
    get_stickers_manage_keyboard,
    get_win_caption_keyboard
)
from bot.templates import (
    DEFAULT_HACK_SIGNAL_TEMPLATE,
    render_hack_signal_card,
    DEFAULT_PREDICTION_TEMPLATE,
    DEFAULT_WIN_TEMPLATE,
    DEFAULT_LOSS_TEMPLATE,
    DEFAULT_PRE_SESSION_TEMPLATE,
    DEFAULT_SESSION_START_TEMPLATE,
    DEFAULT_SESSION_SUMMARY_TEMPLATE,
    DEFAULT_BREAK_TEMPLATE,
    DEFAULT_GOOD_MORNING_TEMPLATE,
    DEFAULT_GOOD_NIGHT_TEMPLATE
)

logger = logging.getLogger(__name__)

# In-memory admin state: { user_id: { "state": ..., "data": ... } }
admin_states = {}

def is_admin(user_id: int) -> bool:
    if not config.ADMIN_IDS:
        return True
    return user_id in config.ADMIN_IDS

def _get_admin_panel_text(user_first_name: str) -> str:
    cfg = db_manager.get_system_settings()
    mode = cfg.get("mode", "24_7")
    mode_str = "⚡ 24/7 Continuous (Non-Stop)" if mode == "24_7" else "🕒 Scheduled VIP Sessions (IST)"
    browser_ready = bet_automation.is_logged_in
    browser_status = "🟢 Logged In & Ready (Playwright)" if browser_ready else "⚪ Idle / Connecting..."
    base_bet = db_manager.get_base_bet_amount()
    martingale_mult = db_manager.get_martingale_multiplier()
    max_loss = db_manager.get_max_loss_display_level()
    clean_loss = "ENABLED" if db_manager.get_auto_clean_loss() else "DISABLED"
    safe_name = html.escape(user_first_name or "Admin")

    ub_status = userbot_manager.get_status()
    if ub_status["active"] and ub_status["me"]:
        ub_badge = "🟢 Connected (Animated Emojis Active)"
    else:
        ub_badge = "⚪ Inactive (/login to connect)"

    strat = db_manager.get_bot_strategy()
    strat_str = "🔥 SureShot Hack (Dual Bet 100% Win)" if strat == "sure_shot_hack" else "🎯 Standard AI (Big/Small)"

    return f"""👑 <b>WIN-GO VIP SURESHOT HACK PANEL</b> 👑
━━━━━━━━━━━━━━━━━━━━━━━━━
👋 Welcome, <b>{safe_name}</b>!
⚡ <b>Mode:</b> <code>100% SureShot Dual Bet (Big & Small Both Bet)</code>
🕒 <b>Operating Mode:</b> <code>{mode_str}</code>
💰 <b>Dual Bet Amount:</b> <code>₹{base_bet} on Big & ₹{base_bet} on Small</code>
🎮 <b>Automation Status:</b> <code>{browser_status}</code>
🔐 <b>Telegram Userbot:</b> <code>{ub_badge}</code>
🤖 <b>Engine:</b> WinGo 30s, 1M, 3M, 5M (SureShot Win)
━━━━━━━━━━━━━━━━━━━━━━━━━
Select an option from the menu below:"""

def _get_userbot_panel_text() -> str:
    status = userbot_manager.get_status()
    if status["active"] and status["me"]:
        me = status["me"]
        prem_badge = "✅ Active (100% Animated Custom Emojis Enabled)" if me.get("is_premium") else "⚠️ Regular (No Telegram Premium detected)"
        user_handle = f"@{me.get('username')}" if me.get('username') else "No username"
        return f"""👑 <b>𝗧𝗘𝗟𝗘𝗚𝗥𝗔𝗠 𝗨𝗦𝗘𝗥𝗕𝗢𝗧 𝗦𝗧𝗔𝗧𝗨𝗦: 𝗔𝗖𝗧𝗜𝗩𝗘 🟢</b>
━━━━━━━━━━━━━━━━━━━━━━━━━
👤 <b>Account Name:</b> <code>{html.escape(me.get('first_name', '') + ' ' + me.get('last_name', ''))}</code>
🔖 <b>Username:</b> {user_handle}
🆔 <b>User ID:</b> <code>{me.get('id', '')}</code>
⭐ <b>Telegram Premium:</b> {prem_badge}
━━━━━━━━━━━━━━━━━━━━━━━━━
🚀 <b>Live Channel Delivery:</b>
Active channels par sabhi predictions, win alerts, aur screenshots aapke is Telegram Premium session se dispatch honge taaki <b>saare animated emojis 100% smoothly animate</b> karein!

<b>Commands:</b>
• <code>/login</code> — Dusra account connect / switch karne ke liye
• <code>/logout_userbot</code> — Userbot disconnect karne ke liye"""
    else:
        return """👑 <b>𝗧𝗘𝗟𝗘𝗚𝗥𝗔𝗠 𝗨𝗦𝗘𝗥𝗕𝗢𝗧 𝗦𝗧𝗔𝗧𝗨𝗦: 𝗜𝗡𝗔𝗖𝗧𝗜𝗩𝗘 ⚪</b>
━━━━━━━━━━━━━━━━━━━━━━━━━
Telegram channel me animated emojis post karne ke liye apna Telegram account connect karein.

<b>✨ Key Benefits:</b>
• Sabhi WinGo Signals & Win Alerts me <b>100% Animated Premium Emojis</b> display honge!
• Fast & direct delivery via Telegram MTProto.
• Session encrypted & securely saved in MongoDB and local .env.

👉 <b>Connect karne ke liye niche button dabayein ya <code>/login</code> likhein:</b>"""


def _get_main_keyboard():
    cfg = db_manager.get_system_settings()
    return get_admin_main_keyboard(
        operating_mode=cfg.get("mode", "24_7"),
        browser_ready=bet_automation.is_logged_in,
        base_bet=db_manager.get_base_bet_amount(),
        martingale_mult=db_manager.get_martingale_multiplier(),
        max_loss_cards=db_manager.get_max_loss_display_level(),
        auto_clean_loss=db_manager.get_auto_clean_loss(),
        strategy=db_manager.get_bot_strategy()
    )

def _get_hack_menu_text() -> str:
    cfg = db_manager.get_system_settings()
    strat = db_manager.get_bot_strategy()
    strat_badge = "🔥 SureShot Hack (ACTIVE)" if strat == "sure_shot_hack" else "🎯 Standard AI (Inactive)"
    sig_tpl = db_manager.get_hack_signal_template() or DEFAULT_HACK_SIGNAL_TEMPLATE
    send_apk = "✅ YES (Auto-sends APK with Signal)" if db_manager.get_hack_send_apk() else "❌ NO (Signal only)"
    cap = db_manager.get_hack_win_caption()
    cap_text = f"\n<code>{html.escape(cap)}</code>" if cap else " <i>(Clean screenshot only, no text caption)</i>"
    stickers = db_manager.get_win_stickers()
    base_bet = db_manager.get_base_bet_amount()

    return f"""⚡ <b>𝗦𝗨𝗥𝗘-𝗦𝗛𝗢𝗧 𝗛𝗔𝗖𝗞 & 𝗗𝗨𝗔𝗟-𝗕𝗘𝗧 𝗦𝗘𝗧𝗧𝗜𝗡𝗚𝗦</b> ⚡
━━━━━━━━━━━━━━━━━━━━━━━━━
🎯 <b>Current Strategy:</b> <code>{strat_badge}</code>
💰 <b>Dual Bet Amount:</b> <code>₹{base_bet}</code> (Placed on BOTH Big & Small = 100% Guaranteed Win!)
📱 <b>Auto-Send APK with Signal:</b> <code>{send_apk}</code>
🖼️ <b>Win Screenshot Caption:</b>{cap_text}
🎉 <b>Configured Win Stickers:</b> <code>{len(stickers)} Sticker(s)</code>
━━━━━━━━━━━━━━━━━━━━━━━━━
📝 <b>Current Signal Message Template:</b>
<pre>{html.escape(sig_tpl)}</pre>
━━━━━━━━━━━━━━━━━━━━━━━━━
<i>When SureShot Hack is active, signals send this message without Big/Small, place bets on BOTH sides, and deliver genuine win screenshots with stickers every round!</i>"""

async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user:
        return

    logger.info(f"📩 Incoming /start from user_id={user.id} (@{user.username}, name='{user.first_name}')")

    if not is_admin(user.id):
        logger.warning(f"⛔ Unauthorized access attempt from user_id={user.id} (@{user.username})")
        if update.message:
            await update.message.reply_text(
                f"⛔ <b>Access Denied</b>\n\nYour User ID: <code>{user.id}</code>\n"
                f"Please add this ID to <code>ADMIN_IDS</code> in <code>.env</code> file to gain admin access.",
                parse_mode=ParseMode.HTML
            )
        return

    try:
        text = _get_admin_panel_text(user.first_name)
        reply_markup = _get_main_keyboard()
        if update.message:
            try:
                await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
            except Exception as tg_err:
                logger.warning(f"HTML reply failed ({tg_err}), falling back to plain text...")
                clean_plain = re.sub(r"<[^>]+>", "", text)
                await update.message.reply_text(clean_plain, reply_markup=reply_markup)
            logger.info(f"✅ Admin panel menu delivered to user {user.id}")
    except Exception as e:
        logger.error(f"Error rendering admin panel: {e}", exc_info=True)
        if update.message:
            await update.message.reply_text(f"⚠️ Error loading admin panel: {e}")

async def _render_channel_view(query, ch_id: str):
    ch = db_manager.get_channel(ch_id)
    if not ch:
        await query.edit_message_text(
            "❌ Channel not found.",
            reply_markup=_get_main_keyboard()
        )
        return

    game_id = ch.get("game_id", "wingo_1m")
    game_label = config.WINGO_GAMES.get(game_id, {}).get("display_name", game_id)
    is_active = ch.get("is_active", True)
    status_text = "🟢 Active" if is_active else "⏸️ Paused"
    stats = ch.get("stats", {})
    wins = stats.get("wins", 0)
    losses = stats.get("losses", 0)
    total = wins + losses
    win_rate = (wins / total * 100) if total > 0 else 0.0
    buttons = ch.get("buttons", [])
    btn_summary = f"<code>{len(buttons)} Button(s) Set</code>" if buttons else "<code>None (No Buttons Shown)</code>"

    text = f"""📢 <b>𝗖𝗵𝗮𝗻𝗻𝗲𝗹 𝗦𝗲𝘁𝘁𝗶𝗻𝗴𝘀: {ch.get('title', ch_id)}</b>
━━━━━━━━━━━━━━━━━━━━━━━━━
🆔 <b>ID:</b> <code>{ch_id}</code>
⚡ <b>Status:</b> {status_text}
⏱️ <b>Game Mode:</b> <b>{game_label}</b>
🛡️ <b>Current Level:</b> <b>Level {ch.get('current_level', 1)}</b>
📊 <b>Win Rate:</b> <b>{win_rate:.1f}%</b> ({wins}W / {losses}L)
🔥 <b>Current Streak:</b> <b>{stats.get('current_streak', 0)}W</b>
🔘 <b>Channel Buttons:</b> {btn_summary}
━━━━━━━━━━━━━━━━━━━━━━━━━"""

    reply_markup = get_channel_manage_keyboard(ch_id, is_active, game_id, len(buttons))
    await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user = update.effective_user
    if not is_admin(user.id):
        await query.edit_message_text("⛔ Unauthorized.")
        return

    data = query.data
    cfg = db_manager.get_system_settings()

    # 1. Main Menu Refresh / Home
    if data in ["admin_main", "admin_refresh"]:
        admin_states.pop(user.id, None)
        text = _get_admin_panel_text(user.first_name)
        await query.edit_message_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=_get_main_keyboard()
        )

    # 2. Toggle Operating Mode (24/7 vs Scheduled)
    elif data == "admin_toggle_mode":
        curr_mode = cfg.get("mode", "24_7")
        new_mode = "scheduled" if curr_mode == "24_7" else "24_7"
        db_manager.set_operating_mode(new_mode)
        mode_str = "Scheduled VIP Sessions" if new_mode == "scheduled" else "24/7 Continuous Mode"
        await query.answer(f"Switched to {mode_str}!", show_alert=True)
        text = _get_admin_panel_text(user.first_name)
        await query.edit_message_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=_get_main_keyboard()
        )

    elif data.startswith("set_mode:"):
        target_mode = data.split(":")[1]
        db_manager.set_operating_mode(target_mode)
        mode_str = "Scheduled VIP Sessions" if target_mode == "scheduled" else "24/7 Continuous Mode"
        await query.answer(f"Operating Mode set to: {mode_str}!", show_alert=True)
        text = _get_admin_panel_text(user.first_name)
        await query.edit_message_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=_get_main_keyboard()
        )

    # Bet Amount Configuration
    elif data == "admin_set_bet":
        current_amt = db_manager.get_base_bet_amount()
        mult = db_manager.get_martingale_multiplier()
        text = f"""💰 <b>𝗖𝗢𝗡𝗙𝗜𝗚𝗨𝗥𝗘 𝗕𝗔𝗦𝗘 𝗕𝗘𝗧 𝗔𝗠𝗢𝗨𝗡𝗧</b>
━━━━━━━━━━━━━━━━━━━━━━━━━
Current Base Bet: <b>₹{current_amt}</b>
Martingale Multiplier: <b>{mult}X</b>

<b>Level Progression Preview:</b>
• Level 1: ₹{current_amt}
• Level 2: ₹{current_amt * mult}
• Level 3: ₹{current_amt * (mult**2)}
• Level 4: ₹{current_amt * (mult**3)}
• Level 5: ₹{current_amt * (mult**4)}

Select a quick amount or enter a custom amount:"""
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=get_bet_amount_keyboard(current_amt))

    elif data.startswith("set_base_amt:"):
        amt = int(data.split(":")[1])
        db_manager.set_base_bet_amount(amt)
        await query.answer(f"Base bet set to ₹{amt}!", show_alert=True)
        text = _get_admin_panel_text(user.first_name)
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=_get_main_keyboard())

    elif data == "input_custom_bet":
        admin_states[user.id] = {"state": "waiting_custom_bet"}
        text = """✏️ <b>Enter Custom Base Bet Amount</b>
━━━━━━━━━━━━━━━━━━━━━━━━━
Please send an integer amount in INR (e.g. <code>10</code>, <code>25</code>, <code>50</code>, <code>100</code>):"""
        keyboard = [[InlineKeyboardButton("⬅️ Cancel", callback_data="admin_set_bet")]]
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))

    # Martingale Multiplier Toggle (2X <-> 3X)
    elif data == "admin_toggle_martingale":
        curr_mult = db_manager.get_martingale_multiplier()
        new_mult = 3 if curr_mult == 2 else 2
        db_manager.set_martingale_multiplier(new_mult)
        await query.answer(f"Martingale multiplier set to {new_mult}X!", show_alert=True)
        text = _get_admin_panel_text(user.first_name)
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=_get_main_keyboard())

    # Anti-Loss Clutter: Toggle Max Loss Alerts (2 -> 3 -> 4)
    elif data == "admin_toggle_max_loss":
        curr = db_manager.get_max_loss_display_level()
        new_val = 2 if curr >= 4 else (curr + 1)
        db_manager.set_max_loss_display_level(new_val)
        await query.answer(f"Max Loss Alerts set to Level {new_val}!", show_alert=True)
        text = _get_admin_panel_text(user.first_name)
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=_get_main_keyboard())

    # Anti-Loss Clutter: Toggle Auto-Clean Loss on Win
    elif data == "admin_toggle_clean_loss":
        curr = db_manager.get_auto_clean_loss()
        new_val = not curr
        db_manager.set_auto_clean_loss(new_val)
        status_str = "ENABLED (Auto-deletes earlier losses on Win)" if new_val else "DISABLED"
        await query.answer(f"Auto-Clean Loss: {status_str}!", show_alert=True)
        text = _get_admin_panel_text(user.first_name)
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=_get_main_keyboard())

    # Message Templates Menu (All 6 Templates)
    elif data == "admin_templates":
        text = """📝 <b>𝗖𝗨𝗦𝗧𝗢𝗠𝗜𝗭𝗘 𝗔𝗟𝗟 𝗠𝗘𝗦𝗦𝗔𝗚𝗘 𝗧𝗘𝗠𝗣𝗟𝗔𝗧𝗘𝗦</b>
━━━━━━━━━━━━━━━━━━━━━━━━━
You can fully customize how every single message appears in your channels:

<b>1. Signals & Results:</b>
• <b>Prediction Card:</b> Period, Choice, Confidence, Safe Level
• <b>Win Card:</b> Winning celebration, streak, level passed
• <b>Loss Card:</b> Missed level, next recovery step

<b>2. VIP Session Cards:</b>
• <b>Pre-Session Alert:</b> 15-minute advance notice & fund rule
• <b>Session Live Start:</b> Kickoff announcement & target rounds
• <b>Session Summary:</b> Win rate, accuracy, and total profit

Select a message template below to preview and edit:"""
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=get_templates_menu_keyboard())

    elif data.startswith("edit_tpl:"):
        tpl_type = data.split(":")[1]
        current_tpl = db_manager.get_message_template(tpl_type)
        if not current_tpl:
            if tpl_type == "prediction":
                current_tpl = DEFAULT_PREDICTION_TEMPLATE
            elif tpl_type == "win":
                current_tpl = DEFAULT_WIN_TEMPLATE
            elif tpl_type == "loss":
                current_tpl = DEFAULT_LOSS_TEMPLATE
            elif tpl_type == "pre_session":
                current_tpl = DEFAULT_PRE_SESSION_TEMPLATE
            elif tpl_type == "session_start":
                current_tpl = DEFAULT_SESSION_START_TEMPLATE
            elif tpl_type == "session_summary":
                current_tpl = DEFAULT_SESSION_SUMMARY_TEMPLATE
            elif tpl_type == "break":
                current_tpl = DEFAULT_BREAK_TEMPLATE
            elif tpl_type == "good_morning":
                current_tpl = DEFAULT_GOOD_MORNING_TEMPLATE
            elif tpl_type == "good_night":
                current_tpl = DEFAULT_GOOD_NIGHT_TEMPLATE
            else:
                current_tpl = "Default template"

        admin_states[user.id] = {"state": f"waiting_tpl_{tpl_type}"}
        prompt = f"""✏️ <b>Edit {tpl_type.upper()} Template</b>
━━━━━━━━━━━━━━━━━━━━━━━━━
<b>Current Template:</b>
<pre>{current_tpl}</pre>

━━━━━━━━━━━━━━━━━━━━━━━━━
Send your new template message text below. (HTML tags & placeholders supported)."""
        keyboard = [[InlineKeyboardButton("⬅️ Cancel", callback_data="admin_templates")]]
        await query.edit_message_text(prompt, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "reset_tpl:all":
        for t in ["prediction", "win", "loss", "pre_session", "session_start", "session_summary", "break", "good_morning", "good_night"]:
            db_manager.set_message_template(t, None)
        await query.answer("All message templates reset to default!", show_alert=True)
        text = _get_admin_panel_text(user.first_name)
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=_get_main_keyboard())

    # VIP APK & Floating HTML Overlay Settings Menu
    elif data == "admin_apk_overlay":
        overlay_on = db_manager.get_html_overlay_enabled()
        auto_apk = db_manager.get_auto_send_apk()
        apk_id = db_manager.get_apk_file_id()
        apk_name = db_manager.get_apk_file_name()
        apk_caption = db_manager.get_apk_caption()
        has_custom_html = bool(db_manager.get_custom_html_template())

        overlay_txt = "✅ ENABLED (Zayro VIP Hack Card floating on live screen)" if overlay_on else "❌ DISABLED"
        apk_status_txt = f"📦 Configured: <code>{apk_name}</code>" if apk_id else "⚪ No APK File Uploaded"
        auto_send_txt = "✅ ACTIVE (Auto-sends to channels on WIN)" if auto_apk else "❌ OFF (Manual only)"
        html_status_txt = "🎨 Custom Uploaded HTML Active" if has_custom_html else "⚡ Built-in Zayro VIP Cyber Card Active"
        caption_preview = f"\n{apk_caption}" if apk_caption else " <i>(None - clean file delivery)</i>"

        text = f"""📱 <b>𝗩𝗜𝗣 𝗔𝗣𝗞 & 𝗙𝗟𝗢𝗔𝗧𝗜𝗡𝗚 𝗛𝗧𝗠𝗟 𝗢𝗩𝗘𝗥𝗟𝗔𝗬 𝗦𝗘𝗧𝗧𝗜𝗡𝗚𝗦</b>
━━━━━━━━━━━━━━━━━━━━━━━━━
🖼️ <b>Live Screen HTML Overlay:</b> {overlay_txt}
📄 <b>Overlay Design:</b> {html_status_txt}

📱 <b>Auto-Send APK on Win:</b> {auto_send_txt}
📦 <b>Current APK File:</b> {apk_status_txt}
📝 <b>APK Caption:</b>{caption_preview}
━━━━━━━━━━━━━━━━━━━━━━━━━
• When <b>HTML Overlay</b> is ON, Playwright injects the open VIP hack prediction card on top of the live game and winning popup before taking screenshots!
• When <b>Auto-Send APK</b> is ON, the APK document is instantly sent into the channels right after each WIN!"""

        await query.edit_message_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=get_apk_overlay_keyboard(
                overlay_enabled=overlay_on,
                auto_send_apk=auto_apk,
                has_apk=bool(apk_id),
                apk_name=apk_name,
                has_custom_html=has_custom_html
            )
        )

    elif data == "toggle_overlay":
        curr = db_manager.get_html_overlay_enabled()
        new_val = not curr
        db_manager.set_html_overlay_enabled(new_val)
        status_txt = "HTML Overlay ENABLED! It will float on live screenshots." if new_val else "HTML Overlay DISABLED."
        await query.answer(status_txt, show_alert=True)

        overlay_on = new_val
        auto_apk = db_manager.get_auto_send_apk()
        apk_id = db_manager.get_apk_file_id()
        apk_name = db_manager.get_apk_file_name()
        apk_caption = db_manager.get_apk_caption()
        has_custom_html = bool(db_manager.get_custom_html_template())
        text = f"""📱 <b>𝗩𝗜𝗣 𝗔𝗣𝗞 & 𝗙𝗟𝗢𝗔𝗧𝗜𝗡𝗚 𝗛𝗧𝗠𝗟 𝗢𝗩𝗘𝗥𝗟𝗔𝗬 𝗦𝗘𝗧𝗧𝗜𝗡𝗚𝗦</b>
━━━━━━━━━━━━━━━━━━━━━━━━━
🖼️ <b>Live Screen HTML Overlay:</b> {"✅ ENABLED" if overlay_on else "❌ DISABLED"}
📄 <b>Overlay Design:</b> {"🎨 Custom Uploaded HTML Active" if has_custom_html else "⚡ Built-in Zayro VIP Cyber Card Active"}

📱 <b>Auto-Send APK on Win:</b> {"✅ ACTIVE" if auto_apk else "❌ OFF"}
📦 <b>Current APK File:</b> {f"<code>{apk_name}</code>" if apk_id else "⚪ No APK File Uploaded"}
📝 <b>APK Caption:</b> {apk_caption}"""
        await query.edit_message_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=get_apk_overlay_keyboard(
                overlay_enabled=overlay_on,
                auto_send_apk=auto_apk,
                has_apk=bool(apk_id),
                apk_name=apk_name,
                has_custom_html=has_custom_html
            )
        )

    elif data == "toggle_apk_send":
        curr = db_manager.get_auto_send_apk()
        new_val = not curr
        if new_val and not db_manager.get_apk_file_id():
            await query.answer("⚠️ Please upload an APK file first before enabling auto-send!", show_alert=True)
        else:
            db_manager.set_auto_send_apk(new_val)
            await query.answer(f"Auto-Send APK: {'ON' if new_val else 'OFF'}!", show_alert=True)

        overlay_on = db_manager.get_html_overlay_enabled()
        auto_apk = db_manager.get_auto_send_apk()
        apk_id = db_manager.get_apk_file_id()
        apk_name = db_manager.get_apk_file_name()
        apk_caption = db_manager.get_apk_caption()
        has_custom_html = bool(db_manager.get_custom_html_template())
        text = f"""📱 <b>𝗩𝗜𝗣 𝗔𝗣𝗞 & 𝗙𝗟𝗢𝗔𝗧𝗜𝗡𝗚 𝗛𝗧𝗠𝗟 𝗢𝗩𝗘𝗥𝗟𝗔𝗬 𝗦𝗘𝗧𝗧𝗜𝗡𝗚𝗦</b>
━━━━━━━━━━━━━━━━━━━━━━━━━
🖼️ <b>Live Screen HTML Overlay:</b> {"✅ ENABLED" if overlay_on else "❌ DISABLED"}
📄 <b>Overlay Design:</b> {"🎨 Custom Uploaded HTML Active" if has_custom_html else "⚡ Built-in Zayro VIP Cyber Card Active"}

📱 <b>Auto-Send APK on Win:</b> {"✅ ACTIVE" if auto_apk else "❌ OFF"}
📦 <b>Current APK File:</b> {f"<code>{apk_name}</code>" if apk_id else "⚪ No APK File Uploaded"}
📝 <b>APK Caption:</b> {apk_caption}"""
        await query.edit_message_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=get_apk_overlay_keyboard(
                overlay_enabled=overlay_on,
                auto_send_apk=auto_apk,
                has_apk=bool(apk_id),
                apk_name=apk_name,
                has_custom_html=has_custom_html
            )
        )

    elif data == "upload_apk_prompt":
        admin_states[user.id] = {"state": "waiting_apk_file"}
        prompt = """📦 <b>Upload Official VIP Mod APK File</b>
━━━━━━━━━━━━━━━━━━━━━━━━━
Please send the <b>.apk file</b> as a Telegram Document right now.
The bot will cache it instantly and use it for automatic channel distribution on every WIN round!"""
        keyboard = [[InlineKeyboardButton("⬅️ Cancel", callback_data="admin_apk_overlay")]]
        await query.edit_message_text(prompt, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "edit_apk_caption_prompt":
        curr_caption = db_manager.get_apk_caption()
        admin_states[user.id] = {"state": "waiting_apk_caption"}
        prompt = f"""✏️ <b>Edit APK Delivery Caption</b>
━━━━━━━━━━━━━━━━━━━━━━━━━
<b>Current Caption:</b>
{curr_caption}

━━━━━━━━━━━━━━━━━━━━━━━━━
Send your new caption text below (Telegram HTML formatting supported):"""
        keyboard = [[InlineKeyboardButton("⬅️ Cancel", callback_data="admin_apk_overlay")]]
        await query.edit_message_text(prompt, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "upload_html_prompt":
        admin_states[user.id] = {"state": "waiting_html_file"}
        prompt = """📄 <b>Upload Custom HTML Overlay File</b>
━━━━━━━━━━━━━━━━━━━━━━━━━
Send your custom <b>.html file</b> as a Telegram Document (or paste raw HTML code directly in chat).
The template can use placeholders:
• <code>{choice}</code> (BIG / SMALL)
• <code>{issue}</code> (Period number)
• <code>{confidence}</code> (Confidence %)
• <code>{level}</code> (Martingale level)
• <code>{number}</code> (Lucky ball number)"""
        keyboard = [[InlineKeyboardButton("⬅️ Cancel", callback_data="admin_apk_overlay")]]
        await query.edit_message_text(prompt, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "reset_html_overlay":
        db_manager.set_custom_html_template(None)
        await query.answer("Reset to default Zayro VIP Hack Overlay!", show_alert=True)
        overlay_on = db_manager.get_html_overlay_enabled()
        auto_apk = db_manager.get_auto_send_apk()
        apk_id = db_manager.get_apk_file_id()
        apk_name = db_manager.get_apk_file_name()
        apk_caption = db_manager.get_apk_caption()
        text = f"""📱 <b>𝗩𝗜𝗣 𝗔𝗣𝗞 & 𝗙𝗟𝗢𝗔𝗧𝗜𝗡𝗚 𝗛𝗧𝗠𝗟 𝗢𝗩𝗘𝗥𝗟𝗔𝗬 𝗦𝗘𝗧𝗧𝗜𝗡𝗚𝗦</b>
━━━━━━━━━━━━━━━━━━━━━━━━━
🖼️ <b>Live Screen HTML Overlay:</b> {"✅ ENABLED" if overlay_on else "❌ DISABLED"}
📄 <b>Overlay Design:</b> ⚡ Built-in Zayro VIP Cyber Card Active

📱 <b>Auto-Send APK on Win:</b> {"✅ ACTIVE" if auto_apk else "❌ OFF"}
📦 <b>Current APK File:</b> {f"<code>{apk_name}</code>" if apk_id else "⚪ No APK File Uploaded"}
📝 <b>APK Caption:</b> {apk_caption}"""
        await query.edit_message_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=get_apk_overlay_keyboard(
                overlay_enabled=overlay_on,
                auto_send_apk=auto_apk,
                has_apk=bool(apk_id),
                apk_name=apk_name,
                has_custom_html=False
            )
        )

    # 3. View & Manage Scheduled Sessions
    elif data == "admin_sessions":
        sessions = db_manager.get_sessions()
        curr_mode = cfg.get("mode", "24_7")
        mode_label = "⚡ 24/7 Continuous" if curr_mode == "24_7" else "🕒 Scheduled VIP Sessions Active"

        lines = [
            "🕒 <b>𝗗𝗔𝗜𝗟𝗬 𝗩𝗜𝗣 𝗦𝗘𝗦𝗦𝗜𝗢𝗡 𝗧𝗜𝗠𝗜𝗡𝗚𝗦 (𝗜𝗦𝗧)</b> 🕒",
            "━━━━━━━━━━━━━━━━━━━━━━━━━",
            f"⚡ <b>Current Mode:</b> <code>{mode_label}</code>",
            f"🔔 <b>Pre-Session Alert:</b> <code>15 Minutes Before Start</code>",
            "━━━━━━━━━━━━━━━━━━━━━━━━━"
        ]
        if not sessions:
            lines.append("<i>No sessions configured! Click below to add or reset.</i>")
        for s in sessions:
            lines.append(f"• <b>{s.get('name', 'Session')}:</b> <code>{s.get('start')} – {s.get('end')} IST</code> (Target: {s.get('max_rounds', 15)} rounds)")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━")
        lines.append("<i>Click any session below to edit its timing, name, or rounds:</i>")

        text = "\n".join(lines)
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=get_sessions_manage_keyboard(sessions))

    elif data.startswith("manage_sess:"):
        s_id = int(data.split(":")[1])
        sessions = db_manager.get_sessions()
        matched = next((s for s in sessions if s.get("id") == s_id), None)
        if not matched:
            await query.answer("Session not found!", show_alert=True)
            text = _get_admin_panel_text(user.first_name)
            await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=_get_main_keyboard())
            return

        text = f"""🕒 <b>𝗦𝗘𝗦𝗦𝗜𝗢𝗡 𝗦𝗘𝗧𝗧𝗜𝗡𝗚𝗦: {matched.get('name')}</b>
━━━━━━━━━━━━━━━━━━━━━━━━━
🆔 <b>ID:</b> <code>{s_id}</code>
🏷️ <b>Name:</b> <b>{matched.get('name')}</b>
⏰ <b>Timing:</b> <code>{matched.get('start')} – {matched.get('end')} IST</code>
🎯 <b>Target Rounds:</b> <code>{matched.get('max_rounds', 15)} Signals</code>
━━━━━━━━━━━━━━━━━━━━━━━━━
Select what you want to change:"""
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=get_single_session_keyboard(s_id))

    elif data.startswith("edit_sess_time:"):
        s_id = int(data.split(":")[1])
        admin_states[user.id] = {"state": "waiting_sess_time", "session_id": s_id}
        prompt = f"""✏️ <b>Edit Timing for Session #{s_id}</b>
━━━━━━━━━━━━━━━━━━━━━━━━━
Send the new Start and End time in 24-hour IST format:
<b>Example:</b> <code>11:00 - 11:30</code> or <code>15:30 - 16:00</code>

Send new timing now:"""
        keyboard = [[InlineKeyboardButton("⬅️ Cancel", callback_data=f"manage_sess:{s_id}")]]
        await query.edit_message_text(prompt, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("edit_sess_name:"):
        s_id = int(data.split(":")[1])
        admin_states[user.id] = {"state": "waiting_sess_name", "session_id": s_id}
        prompt = f"""🏷️ <b>Edit Name for Session #{s_id}</b>
━━━━━━━━━━━━━━━━━━━━━━━━━
Send the new name for this session (e.g. <code>Morning Super VIP</code>):"""
        keyboard = [[InlineKeyboardButton("⬅️ Cancel", callback_data=f"manage_sess:{s_id}")]]
        await query.edit_message_text(prompt, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("edit_sess_rnds:"):
        s_id = int(data.split(":")[1])
        admin_states[user.id] = {"state": "waiting_sess_rnds", "session_id": s_id}
        prompt = f"""🎯 <b>Edit Target Rounds for Session #{s_id}</b>
━━━━━━━━━━━━━━━━━━━━━━━━━
Send the target number of signals (e.g. <code>10</code>, <code>15</code>, <code>20</code>):"""
        keyboard = [[InlineKeyboardButton("⬅️ Cancel", callback_data=f"manage_sess:{s_id}")]]
        await query.edit_message_text(prompt, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("del_sess:"):
        s_id = int(data.split(":")[1])
        db_manager.delete_session(s_id)
        await query.answer(f"Session #{s_id} deleted!", show_alert=True)
        sessions = db_manager.get_sessions()
        await query.edit_message_text(
            f"🗑️ <b>Session #{s_id} removed.</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=get_sessions_manage_keyboard(sessions)
        )

    elif data == "admin_add_session":
        admin_states[user.id] = {"state": "waiting_add_sess"}
        prompt = """➕ <b>Add New VIP Session</b>
━━━━━━━━━━━━━━━━━━━━━━━━━
Send session details in format:
<code>Name, Start Time, End Time, Max Rounds</code>

<b>Example:</b>
<code>Night Super VIP, 22:00, 22:30, 15</code>

Send new session details now:"""
        keyboard = [[InlineKeyboardButton("⬅️ Cancel", callback_data="admin_sessions")]]
        await query.edit_message_text(prompt, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "admin_reset_sessions":
        db_manager.reset_sessions_to_default()
        await query.answer("Reset to default 4 VIP daily sessions!", show_alert=True)
        sessions = db_manager.get_sessions()
        await query.edit_message_text(
            "🔄 <b>Sessions reset to default daily schedule.</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=get_sessions_manage_keyboard(sessions)
        )

    # 4. Browser Automation Status & Test
    elif data == "admin_browser_status":
        ready = bet_automation.is_logged_in
        status_label = "🟢 Logged In & Ready (Playwright)" if ready else "⚪ Disconnected / Initializing"
        demo_user = config.DEMO_USERNAME or "N/A"
        demo_url = config.DEMO_LOGIN_URL or "N/A"

        text = f"""🎮 <b>𝗣𝗟𝗔𝗬𝗪𝗥𝗜𝗚𝗛𝗧 𝗔𝗨𝗧𝗢𝗠𝗔𝗧𝗜𝗢𝗡 𝗦𝗧𝗔𝗧𝗨𝗦</b> 🎮
━━━━━━━━━━━━━━━━━━━━━━━━━
⚡ <b>Status:</b> <code>{status_label}</code>
👤 <b>Account:</b> <code>{demo_user}</code>
🌐 <b>Game Platform:</b> <code>{demo_url}</code>
🎯 <b>Auto-Bet Mode:</b> <code>{'ENABLED' if config.DEMO_AUTO_BET else 'DISABLED'}</code>
📸 <b>Real Win Popup:</b> <code>Active Fast Detector (80ms)</code>
━━━━━━━━━━━━━━━━━━━━━━━━━
Click below to test live bet placement and capture a screenshot:"""
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=get_browser_status_keyboard())

    # 5. Browser Test Bet & Screenshot
    elif data == "browser_test_action":
        await query.answer("Capturing live game board screenshot...", show_alert=False)
        loading_msg = await query.message.reply_text("⏳ Communicating with Playwright browser on live game screen...")

        try:
            shot_stream = await bet_automation.capture_win_screenshot(
                game_id="wingo_1m",
                target_issue="TEST-PERIOD",
                choice="BIG",
                actual_number=7,
                level=1,
                streak=5
            )
            if shot_stream:
                raw = shot_stream.getvalue()
                await context.bot.send_photo(
                    chat_id=user.id,
                    photo=io.BytesIO(raw),
                    caption="📸 <b>Verified Live Screen Capture!</b>\nReal winning popup & board capture is functioning 100% properly.",
                    parse_mode=ParseMode.HTML
                )
                await loading_msg.delete()
            else:
                await loading_msg.edit_text("⚠️ Could not capture screenshot. Check browser logs.")
        except Exception as e:
            await loading_msg.edit_text(f"❌ Error during test: {e}")

    # 6. Reconnect Browser
    elif data == "browser_reconnect":
        await query.answer("Reconnecting Playwright browser...", show_alert=True)
        try:
            await bet_automation.initialize()
            await query.answer("Browser reconnected successfully!", show_alert=True)
        except Exception as e:
            await query.answer(f"Reconnect failed: {e}", show_alert=True)
        text = _get_admin_panel_text(user.first_name)
        await query.edit_message_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=_get_main_keyboard()
        )

    # 7. Channel List
    elif data == "admin_channels":
        admin_states.pop(user.id, None)
        channels = db_manager.get_all_channels()
        if not channels:
            keyboard = [
                [InlineKeyboardButton("➕ Add New Channel", callback_data="admin_add_channel")],
                [InlineKeyboardButton("⬅️ Back", callback_data="admin_main")]
            ]
            await query.edit_message_text(
                "📢 <b>No channels added yet!</b>\n\nClick below to add your first channel.",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return

        buttons = []
        for ch in channels:
            ch_id = ch["channel_id"]
            title = ch.get("title", ch_id)
            game_id = ch.get("game_id", "wingo_1m")
            game_info = config.WINGO_GAMES.get(game_id, {})
            game_label = game_info.get("name", game_id)
            status_icon = "🟢" if ch.get("is_active", True) else "🔴"
            btn_cnt = len(ch.get("buttons", []))

            buttons.append([
                InlineKeyboardButton(f"{status_icon} {title} ({game_label} | {btn_cnt} Btns)", callback_data=f"view_ch:{ch_id}")
            ])

        buttons.append([InlineKeyboardButton("➕ Add Channel", callback_data="admin_add_channel")])
        buttons.append([InlineKeyboardButton("⬅️ Back", callback_data="admin_main")])

        await query.edit_message_text(
            f"📢 <b>Active Channels ({len(channels)})</b>\n\nClick any channel to manage its WinGo game, colored buttons, and status:",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(buttons)
        )

    # 8. View / Manage Specific Channel
    elif data.startswith("view_ch:"):
        admin_states.pop(user.id, None)
        ch_id = data.split(":", 1)[1]
        await _render_channel_view(query, ch_id)

    # 9. Toggle Channel
    elif data.startswith("toggle_ch:"):
        ch_id = data.split(":", 1)[1]
        new_status = db_manager.toggle_channel_active(ch_id)
        status_msg = "STARTED ✅" if new_status else "PAUSED ⏸️"
        await query.answer(f"Predictions {status_msg} for channel!", show_alert=True)
        await _render_channel_view(query, ch_id)

    # 10. Change Game Duration
    elif data.startswith("change_game:"):
        ch_id = data.split(":", 1)[1]
        text = f"⏱️ <b>Select New WinGo Duration for channel {ch_id}:</b>"
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=get_game_select_keyboard(ch_id))

    # 11. Set Game Duration Callback
    elif data.startswith("setgame:"):
        parts = data.split(":")
        ch_id = parts[1]
        selected_game = parts[2]

        ch = db_manager.get_channel(ch_id)
        if ch:
            db_manager.update_channel(ch_id, {"game_id": selected_game})
            game_name = config.WINGO_GAMES.get(selected_game, {}).get("name", selected_game)
            await query.answer(f"Game updated to {game_name}!", show_alert=True)
        else:
            db_manager.add_channel(channel_id=ch_id, game_id=selected_game)
            await query.answer(f"Channel added with {selected_game}!", show_alert=True)

        await _render_channel_view(query, ch_id)

    # 12. Manage Channel Buttons Menu
    elif data.startswith("manage_btns:"):
        admin_states.pop(user.id, None)
        ch_id = data.split(":", 1)[1]
        ch = db_manager.get_channel(ch_id)
        if not ch:
            await query.answer("Channel not found", show_alert=True)
            return

        buttons = ch.get("buttons", [])
        text = f"""🔘 <b>𝗠𝗮𝗻𝗮𝗴𝗲 𝗜𝗻𝗹𝗶𝗻𝗲 𝗕𝘂𝘁𝘁𝗼𝗻𝘀 𝗳𝗼𝗿 {ch.get('title', ch_id)}</b>
━━━━━━━━━━━━━━━━━━━━━━━━━
Active Buttons: <b>{len(buttons)}</b>
<i>These buttons appear below every signal & win notification posted in this channel.</i>
━━━━━━━━━━━━━━━━━━━━━━━━━"""
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=get_channel_buttons_keyboard(ch_id, buttons))

    # 13. Add Button (Initiate Step 1: Text)
    elif data.startswith("add_btn:"):
        ch_id = data.split(":", 1)[1]
        admin_states[user.id] = {"state": "waiting_btn_text", "channel_id": ch_id}
        keyboard = [[InlineKeyboardButton("⬅️ Cancel", callback_data=f"manage_btns:{ch_id}")]]
        await query.edit_message_text(
            f"➕ <b>Add Button for {ch_id} (Step 1/3)</b>\n\nPlease send the <b>Button Text</b> (e.g., <code>🔥 Register VIP Account</code>):",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    # 14. Select Button Style & Save
    elif data.startswith("btnstyle:"):
        parts = data.split(":")
        ch_id = parts[1]
        chosen_style = parts[2]
        emoji_id = parts[3] if len(parts) > 3 and parts[3] != "none" else None

        state_info = admin_states.pop(user.id, None)
        if not state_info or state_info.get("channel_id") != ch_id:
            await query.answer("Session expired. Please try again.", show_alert=True)
            await _render_channel_view(query, ch_id)
            return

        btn_text = state_info.get("btn_text")
        btn_url = state_info.get("btn_url")
        style_val = chosen_style if chosen_style in ("success", "danger", "primary") else None

        db_manager.add_channel_button(
            channel_id=ch_id,
            text=btn_text,
            url=btn_url,
            style=style_val,
            icon_custom_emoji_id=emoji_id
        )

        await query.answer("✅ Button added successfully!", show_alert=True)
        ch = db_manager.get_channel(ch_id)
        buttons = ch.get("buttons", [])
        await query.edit_message_text(
            f"✅ <b>Button added! Total: {len(buttons)} button(s).</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=get_channel_buttons_keyboard(ch_id, buttons)
        )

    # 15. Delete Single Button
    elif data.startswith("del_btn:"):
        parts = data.split(":")
        ch_id = parts[1]
        btn_idx = int(parts[2])
        db_manager.remove_channel_button(ch_id, btn_idx)
        await query.answer("Button removed!", show_alert=True)
        ch = db_manager.get_channel(ch_id)
        buttons = ch.get("buttons", [])
        await query.edit_message_text(
            f"🗑️ <b>Button removed. Total: {len(buttons)} remaining.</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=get_channel_buttons_keyboard(ch_id, buttons)
        )

    # 16. Clear All Buttons
    elif data.startswith("clear_btns:"):
        ch_id = data.split(":", 1)[1]
        db_manager.clear_channel_buttons(ch_id)
        await query.answer("All buttons cleared! Posts will have 0 buttons.", show_alert=True)
        await query.edit_message_text(
            "🗑️ <b>All buttons removed. Posts in this channel will now be sent with NO buttons.</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=get_channel_buttons_keyboard(ch_id, [])
        )

    # 17. Reset Level to 1
    elif data.startswith("reset_level:"):
        ch_id = data.split(":", 1)[1]
        db_manager.update_channel(ch_id, {"current_level": 1})
        await query.answer("Martingale level reset to Level 1!", show_alert=True)
        await _render_channel_view(query, ch_id)

    # 18. Delete Channel
    elif data.startswith("delete_ch:"):
        ch_id = data.split(":", 1)[1]
        db_manager.remove_channel(ch_id)
        await query.answer("Channel removed!", show_alert=True)
        keyboard = [
            [InlineKeyboardButton("📢 Channel List", callback_data="admin_channels")],
            [InlineKeyboardButton("⬅️ Main Menu", callback_data="admin_main")]
        ]
        await query.edit_message_text(
            f"🗑️ <b>Channel {ch_id} has been removed.</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    # 19. Add Channel Form
    elif data == "admin_add_channel":
        admin_states[user.id] = {"state": "waiting_channel_id"}
        text = """➕ <b>𝗔𝗱𝗱 𝗡𝗲𝘄 𝗧𝗲𝗹𝗲𝗴𝗿𝗮𝗺 𝗖𝗵𝗮𝗻𝗻𝗲𝗹</b>
━━━━━━━━━━━━━━━━━━━━━━━━━
1. Make sure this bot is added as an <b>Administrator</b> in your channel with <b>Post Messages</b> permission.
2. Send your Channel Username or ID below:
   • Example Username: <code>@MyWinGoVIP</code>
   • Example Channel ID: <code>-1001234567890</code>

Send your Channel ID or Username now:"""
        keyboard = [[InlineKeyboardButton("⬅️ Cancel", callback_data="admin_channels")]]
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))

    # 20. Overall System Stats
    elif data == "admin_stats":
        channels = db_manager.get_all_channels()
        total_ch = len(channels)
        active_ch = len([c for c in channels if c.get("is_active", True)])

        tot_preds = sum(c.get("stats", {}).get("total_predictions", 0) for c in channels)
        tot_wins = sum(c.get("stats", {}).get("wins", 0) for c in channels)
        tot_losses = sum(c.get("stats", {}).get("losses", 0) for c in channels)
        overall_wr = (tot_wins / tot_preds * 100) if tot_preds > 0 else 0.0

        text = f"""📊 <b>𝗪𝗜𝗡𝗚𝗢 𝗔𝗜 𝗦𝗬𝗦𝗧𝗘𝗠 𝗦𝗧𝗔𝗧𝗜𝗦𝗧𝗜𝗖𝗦</b> 📊
━━━━━━━━━━━━━━━━━━━━━━━━━
📢 <b>Channels:</b> <code>{active_ch} Active / {total_ch} Total</code>
🎯 <b>Total Predictions Sent:</b> <code>{tot_preds}</code>
✅ <b>Total Wins:</b> <code>{tot_wins}</code>
❌ <b>Total Losses:</b> <code>{tot_losses}</code>
🏆 <b>Overall Win Rate:</b> <b>{overall_wr:.1f}%</b>
━━━━━━━━━━━━━━━━━━━━━━━━━"""
        keyboard = [[InlineKeyboardButton("⬅️ Back to Admin", callback_data="admin_main")]]
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))

    # 21. Broadcast
    elif data == "admin_broadcast":
        admin_states[user.id] = {"state": "waiting_broadcast_text"}
        text = "📣 <b>Broadcast Message to All Channels</b>\n\nSend the message text you want to broadcast (HTML supported):"
        keyboard = [[InlineKeyboardButton("⬅️ Cancel", callback_data="admin_main")]]
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))

    # 22. Telegram Userbot Dashboard
    elif data == "admin_userbot":
        status = userbot_manager.get_status()
        panel_text = _get_userbot_panel_text()
        await query.edit_message_text(
            panel_text,
            parse_mode=ParseMode.HTML,
            reply_markup=get_userbot_keyboard(status["active"])
        )

    elif data == "userbot_start_login":
        admin_states[user.id] = {"state": "waiting_userbot_phone", "ts": time.time()}
        prompt = """📱 <b>Telegram Userbot Login</b>
━━━━━━━━━━━━━━━━━━━━━━━━━
👉 Kripya apna <b>Telegram Phone Number</b> country code ke sath bhejein:
<i>Example:</i> <code>+919876543210</code> ya <code>919876543210</code>

<i>(Radd karne ke liye <code>/cancel</code> likhein)</i>"""
        await query.message.reply_text(prompt, parse_mode=ParseMode.HTML)
        await query.answer()

    elif data == "userbot_logout":
        await userbot_manager.logout()
        status = userbot_manager.get_status()
        panel_text = _get_userbot_panel_text()
        await query.answer("🚪 Userbot disconnected!", show_alert=True)
        await query.edit_message_text(
            panel_text,
            parse_mode=ParseMode.HTML,
            reply_markup=get_userbot_keyboard(status["active"])
        )

    # 23. Strategy Mode Toggle
    elif data == "admin_toggle_strategy":
        curr_strat = db_manager.get_bot_strategy()
        new_strat = "standard" if curr_strat == "sure_shot_hack" else "sure_shot_hack"
        db_manager.set_bot_strategy(new_strat)
        alert_txt = "🔥 SureShot Hack Mode ACTIVATED! (Dual Bet 100% Win)" if new_strat == "sure_shot_hack" else "🎯 Standard AI Prediction Mode Activated!"
        await query.answer(alert_txt, show_alert=True)
        text = _get_admin_panel_text(user.first_name)
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=_get_main_keyboard())

    # 24. SureShot Hack Menu
    elif data == "admin_hack_menu":
        text = _get_hack_menu_text()
        strat = db_manager.get_bot_strategy()
        send_apk = db_manager.get_hack_send_apk()
        has_win_cap = bool(db_manager.get_hack_win_caption())
        stickers_count = len(db_manager.get_win_stickers())
        base_bet = db_manager.get_base_bet_amount()
        kb = get_hack_menu_keyboard(strat, send_apk, has_win_cap, stickers_count, base_bet)
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)

    elif data == "toggle_hack_apk":
        curr = db_manager.get_hack_send_apk()
        db_manager.set_hack_send_apk(not curr)
        await query.answer(f"Send APK with Signal: {'ON' if not curr else 'OFF'}!", show_alert=True)
        text = _get_hack_menu_text()
        strat = db_manager.get_bot_strategy()
        send_apk = db_manager.get_hack_send_apk()
        has_win_cap = bool(db_manager.get_hack_win_caption())
        stickers_count = len(db_manager.get_win_stickers())
        base_bet = db_manager.get_base_bet_amount()
        kb = get_hack_menu_keyboard(strat, send_apk, has_win_cap, stickers_count, base_bet)
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)

    elif data == "input_hack_signal_tpl":
        admin_states[user.id] = {"state": "waiting_hack_signal_tpl"}
        curr_tpl = db_manager.get_hack_signal_template() or DEFAULT_HACK_SIGNAL_TEMPLATE
        text = f"""📝 <b>Edit SureShot Signal Template</b>
━━━━━━━━━━━━━━━━━━━━━━━━━
Current Template:
<pre>{html.escape(curr_tpl)}</pre>

<b>Available Placeholders:</b>
• <code>{{issue_short}}</code> — Last 3 digits of period (e.g. 980)
• <code>{{issue}}</code> — Full period number (e.g. 20261028100010980)
• <code>{{game_name}}</code> — Game name (e.g. WinGo 30s)

Send your new template message text below:
<i>(Send <code>/cancel</code> to abort)</i>"""
        keyboard = [[InlineKeyboardButton("⬅️ Cancel", callback_data="admin_hack_menu")]]
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "menu_hack_caption":
        curr_cap = db_manager.get_hack_win_caption()
        cap_disp = f"\n<code>{html.escape(curr_cap)}</code>" if curr_cap else " <i>(Clean screenshot only, no text caption)</i>"
        text = f"""🖼️ <b>Win Screenshot Caption Setting</b>
━━━━━━━━━━━━━━━━━━━━━━━━━
Current Caption:{cap_disp}

• If a caption is set, winning screenshots will be sent with this caption.
• If no caption is set, the bot sends ONLY the raw screenshot image!"""
        kb = get_win_caption_keyboard(bool(curr_cap))
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)

    elif data == "input_hack_win_caption":
        admin_states[user.id] = {"state": "waiting_hack_win_caption"}
        text = """✏️ <b>Enter Winning Screenshot Caption</b>
━━━━━━━━━━━━━━━━━━━━━━━━━
Send the text you want attached as the caption for the winning screenshot.
HTML is supported.

<i>(Send <code>/cancel</code> to abort)</i>"""
        keyboard = [[InlineKeyboardButton("⬅️ Cancel", callback_data="menu_hack_caption")]]
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "clear_hack_win_caption":
        db_manager.set_hack_win_caption(None)
        await query.answer("Caption cleared! Bot will send clean screenshots only.", show_alert=True)
        text = """🖼️ <b>Win Screenshot Caption Setting</b>
━━━━━━━━━━━━━━━━━━━━━━━━━
Current Caption: <i>(Clean screenshot only, no text caption)</i>

The bot will now send ONLY the winning screenshot without any caption."""
        kb = get_win_caption_keyboard(False)
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)

    elif data == "admin_manage_stickers":
        stickers = db_manager.get_win_stickers()
        text = f"""🎉 <b>Manage Winning Stickers</b>
━━━━━━━━━━━━━━━━━━━━━━━━━
Total Configured: <b>{len(stickers)} Sticker(s)</b>

After the winning screenshot is posted to the channel, the bot sends these celebratory stickers right after it!"""
        kb = get_stickers_manage_keyboard(len(stickers))
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)

    elif data == "add_win_sticker":
        admin_states[user.id] = {"state": "waiting_win_sticker"}
        text = """🎉 <b>Add Winning Sticker</b>
━━━━━━━━━━━━━━━━━━━━━━━━━
👉 Forward or send any Telegram Sticker here right now that you want sent to the channel after each win!

<i>(Send <code>/cancel</code> to abort)</i>"""
        keyboard = [[InlineKeyboardButton("⬅️ Cancel", callback_data="admin_manage_stickers")]]
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "clear_win_stickers":
        db_manager.clear_win_stickers()
        await query.answer("All win stickers cleared!", show_alert=True)
        text = """🎉 <b>Manage Winning Stickers</b>
━━━━━━━━━━━━━━━━━━━━━━━━━
Total Configured: <b>0 Stickers</b> (None set)"""
        kb = get_stickers_manage_keyboard(0)
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        return

    text = (update.message.text or "").strip()
    doc = update.message.document
    sticker = update.message.sticker
    state_info = admin_states.get(user.id)
    current_state = state_info.get("state") if state_info else None
    cfg = db_manager.get_system_settings()

    # Sticker upload handler (Win Stickers)
    if sticker and current_state == "waiting_win_sticker":
        admin_states.pop(user.id, None)
        stk_id = sticker.file_id
        all_stks = db_manager.add_win_sticker(stk_id)
        await update.message.reply_text(
            f"✅ <b>Win Sticker Added Successfully!</b>\n\n"
            f"🎉 Total Configured: <b>{len(all_stks)} Sticker(s)</b>\n"
            f"🆔 Sticker ID: <code>{stk_id}</code>\n\n"
            f"This sticker will now be sent automatically after each winning screenshot!",
            parse_mode=ParseMode.HTML,
            reply_markup=_get_main_keyboard()
        )
        return

    # Document upload handlers (APK & HTML)
    if doc and doc.file_name and doc.file_name.lower().endswith(".apk"):
        admin_states.pop(user.id, None)
        file_name = doc.file_name or "ZayroVipHack.apk"
        # Capture custom caption if provided with document
        custom_caption = (update.message.caption_html or update.message.caption or "").strip()
        db_manager.set_apk_file(doc.file_id, file_name, caption=custom_caption or None)

        try:
            os.makedirs("uploads", exist_ok=True)
            tg_file = await doc.get_file()
            local_path = os.path.join("uploads", file_name)
            await tg_file.download_to_drive(local_path)
        except Exception as e:
            logger.warning(f"Could not download local copy of APK: {e}")

        caption_info = f"\n📝 <b>Attached Caption:</b>\n{custom_caption}" if custom_caption else "\n📝 <b>Caption:</b> <i>(No caption attached - will use saved caption or send clean document)</i>"
        await update.message.reply_text(
            f"✅ <b>Official VIP Mod APK Received & Configured!</b>\n"
            f"📦 <b>File Name:</b> <code>{file_name}</code>\n"
            f"🆔 <b>File ID:</b> <code>{doc.file_id}</code>\n"
            f"⚡ <b>Auto-Send on WIN:</b> Active ✅{caption_info}\n\n"
            f"Whenever a round is a <b>WIN</b>, this APK document with its exact caption will be automatically sent to all active channels right after the winning screenshot!",
            parse_mode=ParseMode.HTML,
            reply_markup=_get_main_keyboard()
        )
        return

    if not state_info:
        return

    # Document upload handlers for HTML
    if doc:
        if current_state == "waiting_apk_file":
            admin_states.pop(user.id, None)
            file_name = doc.file_name or "ZayroVipHack.apk"
            custom_caption = (update.message.caption_html or update.message.caption or "").strip()
            db_manager.set_apk_file(doc.file_id, file_name, caption=custom_caption or None)

            try:
                os.makedirs("uploads", exist_ok=True)
                tg_file = await doc.get_file()
                local_path = os.path.join("uploads", file_name)
                await tg_file.download_to_drive(local_path)
            except Exception as e:
                logger.warning(f"Could not download local copy of APK: {e}")

            caption_info = f"\n📝 <b>Attached Caption:</b>\n{custom_caption}" if custom_caption else ""
            await update.message.reply_text(
                f"✅ <b>Official VIP Mod APK Received & Configured!</b>\n"
                f"📦 <b>File Name:</b> <code>{file_name}</code>\n"
                f"🆔 <b>File ID:</b> <code>{doc.file_id}</code>\n"
                f"⚡ <b>Auto-Send on WIN:</b> Active ✅{caption_info}\n\n"
                f"Whenever a round is a <b>WIN</b>, this APK will be automatically sent to all active channels right after the winning screenshot!",
                parse_mode=ParseMode.HTML,
                reply_markup=_get_main_keyboard()
            )
            return

        elif current_state == "waiting_html_file":
            admin_states.pop(user.id, None)
            try:
                os.makedirs("uploads", exist_ok=True)
                tg_file = await doc.get_file()
                content_bytes = await tg_file.download_as_bytearray()
                html_code = content_bytes.decode("utf-8", errors="ignore")
                db_manager.set_custom_html_template(html_code)

                local_path = os.path.join("uploads", "custom_overlay.html")
                with open(local_path, "w", encoding="utf-8") as f:
                    f.write(html_code)

                await update.message.reply_text(
                    f"✅ <b>Custom HTML Overlay Template Uploaded Successfully!</b>\n"
                    f"📄 File: <code>{doc.file_name}</code> ({len(html_code)} chars)\n"
                    f"The live game screen will now render this custom card during Playwright automation!",
                    parse_mode=ParseMode.HTML,
                    reply_markup=_get_main_keyboard()
                )
            except Exception as e:
                logger.error(f"Error saving HTML file: {e}")
                await update.message.reply_text(f"❌ Failed to process HTML file: {e}")
            return

    if text.lower() == "/cancel":
        admin_states.pop(user.id, None)
        await userbot_manager.cancel_login(user.id)
        await update.message.reply_text("❌ Action cancel kar diya gaya.", reply_markup=_get_main_keyboard())
        return

    # Userbot Login Step 1: Phone number
    if current_state == "waiting_userbot_phone":
        wait_msg = await update.message.reply_text("⏳ Connecting to Telegram & sending OTP code...")
        res = await userbot_manager.send_login_code(user.id, text)
        if not res.get("ok"):
            admin_states.pop(user.id, None)
            await wait_msg.edit_text(
                f"❌ <b>Error:</b> {res.get('error')}\n\nDobara koshish karne ke liye <code>/login</code> likhein.",
                parse_mode=ParseMode.HTML
            )
            return

        admin_states[user.id] = {"state": "waiting_userbot_otp", "ts": time.time(), "phone": res.get("phone")}
        await wait_msg.edit_text(
            f"📩 <b>OTP Code Sent to {res.get('phone')}!</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Telegram app me aaya <b>Login Code</b> yahan bhejein.\n\n"
            f"💡 <i>Tip: Agar Telegram code direct na bhejne de to space dekar bhejein (jaise: <code>1 2 3 4 5</code>).</i>\n\n"
            f"<i>(Radd karne ke liye <code>/cancel</code> likhein)</i>",
            parse_mode=ParseMode.HTML
        )
        return

    # Userbot Login Step 2: OTP
    elif current_state == "waiting_userbot_otp":
        try:
            await update.message.delete()
        except Exception:
            pass

        wait_msg = await update.message.reply_text("⏳ Verifying OTP code...")
        res = await userbot_manager.sign_in_otp(user.id, text)
        if not res.get("ok"):
            await wait_msg.edit_text(
                f"❌ <b>Verification Error:</b> {res.get('error')}\n\nSahi OTP bhejein ya <code>/cancel</code> likhein.",
                parse_mode=ParseMode.HTML
            )
            return

        if res.get("needs_password"):
            admin_states[user.id] = {"state": "waiting_userbot_password", "ts": time.time()}
            await wait_msg.edit_text(
                "🔐 <b>Two-Step Verification (2FA Password) Required!</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "Is account par 2FA Cloud Password set hai.\n\n"
                "👉 Kripya apna <b>Two-Step Password</b> yahan bhejein:\n\n"
                "<i>(Radd karne ke liye <code>/cancel</code> likhein)</i>",
                parse_mode=ParseMode.HTML
            )
            return

        admin_states.pop(user.id, None)
        me = res.get("me", {})
        prem = "✅ Active (100% Animated Custom Emojis Enabled!)" if me.get("is_premium") else "⚠️ Inactive (Regular Account)"
        await wait_msg.edit_text(
            f"🎉 <b>Telegram Userbot Successfully Connected!</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 <b>Account:</b> {me.get('first_name', '')} {me.get('last_name', '')}\n"
            f"🔖 <b>Username:</b> @{me.get('username') or 'None'}\n"
            f"🆔 <b>User ID:</b> <code>{me.get('id', '')}</code>\n"
            f"⭐ <b>Telegram Premium:</b> {prem}\n━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🚀 Ab channel me sabhi predictions, win screenshots aur alerts aapke is Premium account ke through <b>100% Animated Custom Emojis</b> ke sath deliver honge!\n\n"
            f"<i>(Session logout karne ke liye <code>/logout_userbot</code> use karein)</i>",
            parse_mode=ParseMode.HTML,
            reply_markup=_get_main_keyboard()
        )
        return

    # Userbot Login Step 3: 2FA Password
    elif current_state == "waiting_userbot_password":
        try:
            await update.message.delete()
        except Exception:
            pass

        wait_msg = await update.message.reply_text("⏳ Verifying 2FA Password...")
        res = await userbot_manager.check_password(user.id, text)
        if not res.get("ok"):
            await wait_msg.edit_text(
                f"❌ <b>2FA Error:</b> {res.get('error')}\n\nSahi Password bhejein ya <code>/cancel</code> likhein.",
                parse_mode=ParseMode.HTML
            )
            return

        admin_states.pop(user.id, None)
        me = res.get("me", {})
        prem = "✅ Active (100% Animated Custom Emojis Enabled!)" if me.get("is_premium") else "⚠️ Inactive (Regular Account)"
        await wait_msg.edit_text(
            f"🎉 <b>Telegram Userbot Successfully Connected!</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 <b>Account:</b> {me.get('first_name', '')} {me.get('last_name', '')}\n"
            f"🔖 <b>Username:</b> @{me.get('username') or 'None'}\n"
            f"🆔 <b>User ID:</b> <code>{me.get('id', '')}</code>\n"
            f"⭐ <b>Telegram Premium:</b> {prem}\n━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🚀 Ab channel me sabhi predictions, win screenshots aur alerts aapke is Premium account ke through <b>100% Animated Custom Emojis</b> ke sath deliver honge!\n\n"
            f"<i>(Session logout karne ke liye <code>/logout_userbot</code> use karein)</i>",
            parse_mode=ParseMode.HTML,
            reply_markup=_get_main_keyboard()
        )
        return

    # Case: SureShot Signal Template Text
    if current_state == "waiting_hack_signal_tpl":
        admin_states.pop(user.id, None)
        raw_text = (update.message.text_html or update.message.text or "").strip()
        if raw_text:
            db_manager.set_hack_signal_template(raw_text)
            await update.message.reply_text(
                f"✅ <b>SureShot Signal Template Updated!</b>\n\n<pre>{html.escape(raw_text)}</pre>",
                parse_mode=ParseMode.HTML,
                reply_markup=_get_main_keyboard()
            )
        else:
            await update.message.reply_text("❌ Template cannot be empty.", reply_markup=_get_main_keyboard())
        return

    # Case: SureShot Win Caption Text
    elif current_state == "waiting_hack_win_caption":
        admin_states.pop(user.id, None)
        raw_caption = (update.message.text_html or update.message.text or "").strip()
        db_manager.set_hack_win_caption(raw_caption or None)
        if raw_caption:
            await update.message.reply_text(
                f"✅ <b>Winning Screenshot Caption Saved!</b>\n\n<b>Preview:</b>\n{raw_caption}",
                parse_mode=ParseMode.HTML,
                reply_markup=_get_main_keyboard()
            )
        else:
            await update.message.reply_text("✅ <b>Caption Cleared!</b> (Clean screenshot only will be sent)", reply_markup=_get_main_keyboard())
        return

    # Case 1: Channel ID received
    if current_state == "waiting_channel_id":
        admin_states.pop(user.id, None)
        ch_id = text
        prompt_text = f"""⏱️ <b>Select WinGo Duration for {ch_id}</b>
━━━━━━━━━━━━━━━━━━━━━━━━━
Choose which WinGo duration this channel should broadcast signals for:"""
        await update.message.reply_text(
            prompt_text,
            parse_mode=ParseMode.HTML,
            reply_markup=get_game_select_keyboard(ch_id)
        )

    # Case 2: Button Text received
    elif current_state == "waiting_btn_text":
        ch_id = state_info.get("channel_id")
        if not text:
            await update.message.reply_text("❌ Button text cannot be empty. Please send valid text:")
            return

        admin_states[user.id] = {
            "state": "waiting_btn_url",
            "channel_id": ch_id,
            "btn_text": text
        }
        prompt = f"""🔗 <b>Add Button for {ch_id} (Step 2/3)</b>
━━━━━━━━━━━━━━━━━━━━━━━━━
🏷️ <b>Button Text:</b> <code>{text}</code>

Now send the <b>Button URL / Link</b> (must start with <code>https://</code> or <code>http://</code> or <code>tg://</code>):"""
        keyboard = [[InlineKeyboardButton("⬅️ Cancel", callback_data=f"manage_btns:{ch_id}")]]
        await update.message.reply_text(
            prompt,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    # Case 3: Button URL received
    elif current_state == "waiting_btn_url":
        ch_id = state_info.get("channel_id")
        btn_text = state_info.get("btn_text")

        if not (text.startswith("http://") or text.startswith("https://") or text.startswith("tg://")):
            await update.message.reply_text(
                "❌ Invalid URL! Please send a valid link starting with <code>https://</code>:",
                parse_mode=ParseMode.HTML
            )
            return

        admin_states[user.id] = {
            "state": "waiting_btn_style",
            "channel_id": ch_id,
            "btn_text": btn_text,
            "btn_url": text
        }
        prompt = f"""🎨 <b>Select Button Color Style (Step 3/3)</b>
━━━━━━━━━━━━━━━━━━━━━━━━━
🏷️ <b>Text:</b> {btn_text}
🔗 <b>URL:</b> <code>{text}</code>

Choose the Telegram Native Colored Button Style below:"""
        await update.message.reply_text(
            prompt,
            parse_mode=ParseMode.HTML,
            reply_markup=get_button_style_select_keyboard(ch_id),
            disable_web_page_preview=True
        )

    # Case 4: Broadcast Text received
    elif current_state == "waiting_broadcast_text":
        admin_states.pop(user.id, None)
        channels = db_manager.get_all_channels()
        sent_count = 0

        for ch in channels:
            ch_id = ch["channel_id"]
            try:
                await context.bot.send_message(
                    chat_id=ch_id,
                    text=text,
                    parse_mode=ParseMode.HTML
                )
                sent_count += 1
            except Exception as e:
                logger.error(f"Error broadcasting to {ch_id}: {e}")

        await update.message.reply_text(
            f"📣 <b>Broadcast Complete!</b>\nSent successfully to <b>{sent_count}/{len(channels)}</b> channels.",
            parse_mode=ParseMode.HTML,
            reply_markup=_get_main_keyboard()
        )

    # Case 5: Custom Base Bet Amount
    elif current_state == "waiting_custom_bet":
        admin_states.pop(user.id, None)
        cleaned = text.replace("₹", "").replace(",", "").strip()
        try:
            amt = int(cleaned)
            if amt <= 0:
                raise ValueError
            db_manager.set_base_bet_amount(amt)
            mult = db_manager.get_martingale_multiplier()
            await update.message.reply_text(
                f"✅ <b>Base Bet Amount updated to ₹{amt}!</b>\nMartingale Scaling: ₹{amt} → ₹{amt*mult} → ₹{amt*(mult**2)}...",
                parse_mode=ParseMode.HTML,
                reply_markup=_get_main_keyboard()
            )
        except ValueError:
            await update.message.reply_text(
                "❌ Invalid amount. Please enter a positive integer like <code>10</code>, <code>50</code>, <code>100</code>:",
                parse_mode=ParseMode.HTML,
                reply_markup=_get_main_keyboard()
            )

    # Case 6: Custom Message Templates (prediction / win / loss / pre_session / session_start / session_summary)
    elif current_state.startswith("waiting_tpl_"):
        tpl_type = current_state.replace("waiting_tpl_", "")
        admin_states.pop(user.id, None)
        db_manager.set_message_template(tpl_type, text)
        await update.message.reply_text(
            f"✅ <b>{tpl_type.upper()} message template updated successfully!</b>\nAll subsequent signals will be rendered with your custom style.",
            parse_mode=ParseMode.HTML,
            reply_markup=_get_main_keyboard()
        )

    # Case 7: Session Timing
    elif current_state == "waiting_sess_time":
        s_id = state_info.get("session_id")
        admin_states.pop(user.id, None)
        parts = re.split(r'[-–,to]+', text)
        if len(parts) >= 2:
            st = parts[0].strip()
            et = parts[1].strip()
            db_manager.update_session(s_id, {"start": st, "end": et})
            await update.message.reply_text(
                f"✅ <b>Session #{s_id} Timing Updated to {st} – {et} IST!</b>",
                parse_mode=ParseMode.HTML,
                reply_markup=get_sessions_manage_keyboard(db_manager.get_sessions())
            )
        else:
            await update.message.reply_text(
                "❌ Invalid format! Please enter as <code>11:00 - 11:30</code>:",
                parse_mode=ParseMode.HTML,
                reply_markup=get_sessions_manage_keyboard(db_manager.get_sessions())
            )

    # Case 8: Session Name
    elif current_state == "waiting_sess_name":
        s_id = state_info.get("session_id")
        admin_states.pop(user.id, None)
        db_manager.update_session(s_id, {"name": text.strip()})
        await update.message.reply_text(
            f"✅ <b>Session #{s_id} Name updated to '{text.strip()}'!</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=get_sessions_manage_keyboard(db_manager.get_sessions())
        )

    # Case 9: Session Target Rounds
    elif current_state == "waiting_sess_rnds":
        s_id = state_info.get("session_id")
        admin_states.pop(user.id, None)
        try:
            rnds = int(text.strip())
            db_manager.update_session(s_id, {"max_rounds": rnds})
            await update.message.reply_text(
                f"✅ <b>Session #{s_id} Target Rounds updated to {rnds}!</b>",
                parse_mode=ParseMode.HTML,
                reply_markup=get_sessions_manage_keyboard(db_manager.get_sessions())
            )
        except ValueError:
            await update.message.reply_text(
                "❌ Please enter a valid number:",
                reply_markup=get_sessions_manage_keyboard(db_manager.get_sessions())
            )

    # Case 10: Add New Session
    elif current_state == "waiting_add_sess":
        admin_states.pop(user.id, None)
        parts = [p.strip() for p in text.split(",")]
        if len(parts) >= 3:
            s_name = parts[0]
            s_start = parts[1]
            s_end = parts[2]
            s_rnds = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 15
            new_sess = db_manager.add_session(s_name, s_start, s_end, s_rnds)
            await update.message.reply_text(
                f"✅ <b>New VIP Session '{s_name}' added [{s_start} – {s_end} IST | {s_rnds} Rounds]!</b>",
                parse_mode=ParseMode.HTML,
                reply_markup=get_sessions_manage_keyboard(db_manager.get_sessions())
            )
        else:
            await update.message.reply_text(
                "❌ Invalid format. Please provide: <code>Name, Start, End, Rounds</code> (e.g. <code>Night VIP, 21:00, 21:30, 15</code>):",
                parse_mode=ParseMode.HTML,
                reply_markup=get_sessions_manage_keyboard(db_manager.get_sessions())
            )

    # Case 11: APK Caption Text
    elif current_state == "waiting_apk_caption":
        admin_states.pop(user.id, None)
        caption_text = (update.message.text_html or update.message.text or "").strip()
        if caption_text:
            db_manager.set_apk_caption(caption_text)
            await update.message.reply_text(
                f"✅ <b>APK Delivery Caption Updated Successfully!</b>\n\n<b>Preview:</b>\n{caption_text}",
                parse_mode=ParseMode.HTML,
                reply_markup=_get_main_keyboard()
            )
        else:
            await update.message.reply_text("❌ Caption cannot be empty.", reply_markup=_get_main_keyboard())

    # Case 12: Custom HTML Text (Pasted code)
    elif current_state == "waiting_html_file":
        admin_states.pop(user.id, None)
        db_manager.set_custom_html_template(text)
        try:
            os.makedirs("uploads", exist_ok=True)
            with open(os.path.join("uploads", "custom_overlay.html"), "w", encoding="utf-8") as f:
                f.write(text)
        except Exception:
            pass
        await update.message.reply_text(
            "✅ <b>Custom HTML Overlay Code Saved!</b>\n"
            "The live game screen will now render this custom card during Playwright runs.",
            parse_mode=ParseMode.HTML,
            reply_markup=_get_main_keyboard()
        )

# ================= USERBOT COMMAND HANDLERS =================

async def login_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user or not is_admin(user.id):
        return

    admin_states[user.id] = {"state": "waiting_userbot_phone", "ts": time.time()}
    prompt = """📱 <b>Telegram Userbot Login (100% Animated Emojis)</b>
━━━━━━━━━━━━━━━━━━━━━━━━━
Apna Telegram account connect karein jisse channel me saari predictions <b>100% Animated Premium Emojis</b> ke sath post hon!

👉 Kripya apna <b>Telegram Phone Number</b> country code ke sath bhejein:
<i>Example:</i> <code>+919876543210</code> ya <code>919876543210</code>

<i>(Radd karne ke liye <code>/cancel</code> likhein)</i>"""
    await update.message.reply_text(prompt, parse_mode=ParseMode.HTML)

async def userbot_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user or not is_admin(user.id):
        return
    status = userbot_manager.get_status()
    panel_text = _get_userbot_panel_text()
    await update.message.reply_text(
        panel_text,
        parse_mode=ParseMode.HTML,
        reply_markup=get_userbot_keyboard(status["active"])
    )

async def logout_userbot_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user or not is_admin(user.id):
        return
    await userbot_manager.logout()
    await update.message.reply_text(
        "🚪 <b>Telegram Userbot successfully logged out!</b>\n\nAb messages standard Bot API ke through post honge.",
        parse_mode=ParseMode.HTML,
        reply_markup=_get_main_keyboard()
    )

async def cancel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user:
        return
    if user.id in admin_states:
        admin_states.pop(user.id, None)
        await userbot_manager.cancel_login(user.id)
        await update.message.reply_text("❌ Action cancel kar diya gaya.", reply_markup=_get_main_keyboard())

