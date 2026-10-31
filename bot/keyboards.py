from typing import Optional
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
import config

def get_channel_post_keyboard(channel: dict = None, include_custom_emoji: bool = True, include_style: bool = True) -> Optional[InlineKeyboardMarkup]:
    """
    Builds inline keyboard for channel posts ONLY from buttons explicitly configured by the admin.
    If no buttons are configured for the channel, returns None (no buttons attached).
    Supports Telegram Bot API native colored button styles: 'success' (green), 'danger' (red), 'primary' (blue).
    """
    if not channel:
        return None

    buttons_cfg = channel.get("buttons", [])
    if not buttons_cfg:
        return None

    keyboard = []
    for btn in buttons_cfg:
        text = btn.get("text", "").strip()
        url = btn.get("url", "").strip()
        if not text or not url:
            continue

        style = btn.get("style") if include_style else None
        if style not in ("success", "danger", "primary"):
            style = None

        emoji_id = btn.get("icon_custom_emoji_id") if include_custom_emoji else None

        try:
            button_kwargs = {"text": text, "url": url}
            if style:
                button_kwargs["style"] = style
            if emoji_id:
                button_kwargs["icon_custom_emoji_id"] = str(emoji_id)
            keyboard.append([InlineKeyboardButton(**button_kwargs)])
        except TypeError:
            keyboard.append([InlineKeyboardButton(text=text, url=url)])

    if not keyboard:
        return None

    return InlineKeyboardMarkup(keyboard)

def get_admin_main_keyboard(
    operating_mode: str = "24_7",
    browser_ready: bool = False,
    base_bet: int = 10,
    martingale_mult: int = 2,
    max_loss_cards: int = 3,
    auto_clean_loss: bool = True,
    strategy: str = "standard"
) -> InlineKeyboardMarkup:
    """Admin Dashboard Main Menu with Mode, Bet Amount, Loss Protection, Sessions & Templates"""
    mode_text = "⚡ Mode: 24/7" if operating_mode == "24_7" else "🕒 Mode: Sessions"
    browser_badge = "🟢 Browser Live" if browser_ready else "⚪ Browser Idle"
    clean_badge = "🧹 Clean Loss: ON" if auto_clean_loss else "🧹 Clean Loss: OFF"

    strat_text = "🔥 Strategy: SureShot Hack" if strategy == "sure_shot_hack" else "🎯 Strategy: Standard AI"

    keyboard = [
        [
            InlineKeyboardButton("⚡ Signal, APK & Stickers Setup", callback_data="admin_hack_menu")
        ],
        [
            InlineKeyboardButton(f"💰 Dual Bet: ₹{base_bet} (Big & Small)", callback_data="admin_set_bet"),
            InlineKeyboardButton(f"🎮 Game Login ({browser_badge})", callback_data="admin_browser_status")
        ],
        [
            InlineKeyboardButton(mode_text, callback_data="admin_toggle_mode"),
            InlineKeyboardButton("🕒 VIP Sessions", callback_data="admin_sessions")
        ],
        [
            InlineKeyboardButton("📝 Edit ALL Message Templates", callback_data="admin_templates")
        ],
        [
            InlineKeyboardButton("📱 VIP APK & HTML Overlay", callback_data="admin_apk_overlay"),
            InlineKeyboardButton("🔐 Telegram Userbot", callback_data="admin_userbot")
        ],
        [
            InlineKeyboardButton("📢 Manage Channels", callback_data="admin_channels"),
            InlineKeyboardButton("➕ Add Channel", callback_data="admin_add_channel")
        ],
        [
            InlineKeyboardButton("📊 System Stats", callback_data="admin_stats"),
            InlineKeyboardButton("📣 Broadcast", callback_data="admin_broadcast")
        ],
        [
            InlineKeyboardButton("🔄 Refresh Panel", callback_data="admin_refresh")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_bet_amount_keyboard(current_amount: int) -> InlineKeyboardMarkup:
    """Quick select buttons for base bet amount"""
    keyboard = [
        [
            InlineKeyboardButton("₹1", callback_data="set_base_amt:1"),
            InlineKeyboardButton("₹5", callback_data="set_base_amt:5"),
            InlineKeyboardButton("₹10", callback_data="set_base_amt:10")
        ],
        [
            InlineKeyboardButton("₹20", callback_data="set_base_amt:20"),
            InlineKeyboardButton("₹50", callback_data="set_base_amt:50"),
            InlineKeyboardButton("₹100", callback_data="set_base_amt:100")
        ],
        [
            InlineKeyboardButton("✏️ Enter Custom Amount", callback_data="input_custom_bet")
        ],
        [
            InlineKeyboardButton("⬅️ Back to Admin", callback_data="admin_main")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_apk_overlay_keyboard(
    overlay_enabled: bool = True,
    auto_send_apk: bool = False,
    has_apk: bool = False,
    apk_name: str = "ZayroVipHack.apk",
    has_custom_html: bool = False
) -> InlineKeyboardMarkup:
    """Settings menu for Floating HTML Overlay & Automatic APK Delivery on Win"""
    overlay_badge = "🖼️ HTML Overlay: ON ✅" if overlay_enabled else "🖼️ HTML Overlay: OFF ❌"
    apk_send_badge = "📱 Send APK on Win: ON ✅" if auto_send_apk else "📱 Send APK on Win: OFF ❌"
    apk_btn_label = f"📦 Change APK ({apk_name})" if has_apk else "📦 Upload VIP APK"
    html_btn_label = "📄 Change Custom HTML" if has_custom_html else "📄 Upload Custom HTML"

    keyboard = [
        [
            InlineKeyboardButton(overlay_badge, callback_data="toggle_overlay"),
            InlineKeyboardButton(apk_send_badge, callback_data="toggle_apk_send")
        ],
        [
            InlineKeyboardButton(apk_btn_label, callback_data="upload_apk_prompt"),
            InlineKeyboardButton("✏️ Edit APK Caption", callback_data="edit_apk_caption_prompt")
        ],
        [
            InlineKeyboardButton(html_btn_label, callback_data="upload_html_prompt"),
            InlineKeyboardButton("🔄 Reset Default HTML", callback_data="reset_html_overlay")
        ],
        [
            InlineKeyboardButton("🏷️ Change Hack Card Brand Title", callback_data="input_overlay_brand")
        ],
        [
            InlineKeyboardButton("◀️ Back to Admin Panel", callback_data="admin_refresh")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_templates_menu_keyboard() -> InlineKeyboardMarkup:
    """Menu to customize ALL message templates (matching maxie1min format)"""
    keyboard = [
        [
            InlineKeyboardButton("🎯 Prediction Card", callback_data="edit_tpl:prediction"),
            InlineKeyboardButton("🏆 Win Card", callback_data="edit_tpl:win")
        ],
        [
            InlineKeyboardButton("⚠️ Loss Card", callback_data="edit_tpl:loss"),
            InlineKeyboardButton("🚨 15m Pre-Alert", callback_data="edit_tpl:pre_session")
        ],
        [
            InlineKeyboardButton("🟢 Session Start", callback_data="edit_tpl:session_start"),
            InlineKeyboardButton("📊 Session Completed", callback_data="edit_tpl:session_summary")
        ],
        [
            InlineKeyboardButton("⏸️ Break Time", callback_data="edit_tpl:break"),
            InlineKeyboardButton("🌅 Good Morning", callback_data="edit_tpl:good_morning")
        ],
        [
            InlineKeyboardButton("🌙 Good Night", callback_data="edit_tpl:good_night")
        ],
        [
            InlineKeyboardButton("🔄 Reset All Templates to Default", callback_data="reset_tpl:all")
        ],
        [
            InlineKeyboardButton("⬅️ Back to Admin", callback_data="admin_main")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_sessions_manage_keyboard(sessions: list) -> InlineKeyboardMarkup:
    """Menu to view, edit timings, and add scheduled VIP sessions"""
    keyboard = []
    for s in sessions:
        s_id = s.get("id")
        s_name = s.get("name", f"Session {s_id}")
        start_t = s.get("start")
        end_t = s.get("end")
        rnds = s.get("max_rounds", 15)
        keyboard.append([
            InlineKeyboardButton(f"🕒 {s_name} [{start_t} - {end_t}] ({rnds} R)", callback_data=f"manage_sess:{s_id}")
        ])

    keyboard.append([
        InlineKeyboardButton("➕ Add New VIP Session", callback_data="admin_add_session"),
        InlineKeyboardButton("🔄 Reset Default Sessions", callback_data="admin_reset_sessions")
    ])
    keyboard.append([
        InlineKeyboardButton("⚙️ Switch to 24/7 Mode", callback_data="set_mode:24_7"),
        InlineKeyboardButton("⚙️ Switch to Session Mode", callback_data="set_mode:scheduled")
    ])
    keyboard.append([
        InlineKeyboardButton("⬅️ Back to Admin", callback_data="admin_main")
    ])
    return InlineKeyboardMarkup(keyboard)

def get_single_session_keyboard(session_id: int) -> InlineKeyboardMarkup:
    """Controls for a single session"""
    keyboard = [
        [
            InlineKeyboardButton("✏️ Edit Timing (Start - End)", callback_data=f"edit_sess_time:{session_id}")
        ],
        [
            InlineKeyboardButton("🏷️ Edit Session Name", callback_data=f"edit_sess_name:{session_id}"),
            InlineKeyboardButton("🎯 Edit Max Rounds", callback_data=f"edit_sess_rnds:{session_id}")
        ],
        [
            InlineKeyboardButton("🗑️ Delete This Session", callback_data=f"del_sess:{session_id}")
        ],
        [
            InlineKeyboardButton("⬅️ Back to Sessions", callback_data="admin_sessions")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_browser_status_keyboard() -> InlineKeyboardMarkup:
    """Menu to configure Game Link, ID/Phone, Password, Hack Brand Title, and test live browser"""
    keyboard = [
        [
            InlineKeyboardButton("⚡ Quick Setup (Link + ID + Pass)", callback_data="input_game_quick_setup")
        ],
        [
            InlineKeyboardButton("🔗 Change Game Link", callback_data="input_game_url"),
            InlineKeyboardButton("📱 Change Phone / ID", callback_data="input_game_user")
        ],
        [
            InlineKeyboardButton("🔑 Change Password", callback_data="input_game_pass"),
            InlineKeyboardButton("🏷️ Hack Card Title", callback_data="input_overlay_brand")
        ],
        [
            InlineKeyboardButton("📸 Live Board Preview (With Hack Card)", callback_data="browser_test_action"),
            InlineKeyboardButton("🔄 Reconnect Game", callback_data="browser_reconnect")
        ],
        [
            InlineKeyboardButton("⬅️ Back to Admin", callback_data="admin_main")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_game_select_keyboard(channel_id: str) -> InlineKeyboardMarkup:
    """Keyboard for selecting WinGo duration when adding/editing channel"""
    keyboard = [
        [
            InlineKeyboardButton("⏱️ WinGo 30s", callback_data=f"setgame:{channel_id}:wingo_30s"),
            InlineKeyboardButton("⏱️ WinGo 1 Min", callback_data=f"setgame:{channel_id}:wingo_1m")
        ],
        [
            InlineKeyboardButton("⏱️ WinGo 3 Min", callback_data=f"setgame:{channel_id}:wingo_3m"),
            InlineKeyboardButton("⏱️ WinGo 5 Min", callback_data=f"setgame:{channel_id}:wingo_5m")
        ],
        [
            InlineKeyboardButton("⬅️ Cancel", callback_data="admin_channels")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_channel_manage_keyboard(channel_id: str, is_active: bool, game_id: str, buttons_count: int = 0) -> InlineKeyboardMarkup:
    """Individual Channel Settings Menu"""
    toggle_text = "⏸️ Pause Predictions" if is_active else "▶️ Start Predictions"
    toggle_data = f"toggle_ch:{channel_id}"
    
    game_name = config.WINGO_GAMES.get(game_id, {}).get("name", game_id)
    btn_label = f"🔘 Manage Buttons ({buttons_count} Active)" if buttons_count > 0 else "🔘 Add / Set Channel Buttons (None)"
    
    keyboard = [
        [
            InlineKeyboardButton(toggle_text, callback_data=toggle_data)
        ],
        [
            InlineKeyboardButton(f"⏱️ Game: {game_name} (Change)", callback_data=f"change_game:{channel_id}")
        ],
        [
            InlineKeyboardButton(btn_label, callback_data=f"manage_btns:{channel_id}")
        ],
        [
            InlineKeyboardButton("🔄 Reset Level to 1", callback_data=f"reset_level:{channel_id}"),
            InlineKeyboardButton("🗑️ Remove Channel", callback_data=f"delete_ch:{channel_id}")
        ],
        [
            InlineKeyboardButton("⬅️ Back to Channels", callback_data="admin_channels")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_channel_buttons_keyboard(channel_id: str, buttons: list) -> InlineKeyboardMarkup:
    """Menu to view, add, or delete custom styled buttons for a channel"""
    keyboard = []
    style_badges = {
        "success": "🟢 Green",
        "danger": "🔴 Red",
        "primary": "🔵 Blue",
        None: "⚪ Default"
    }

    for idx, btn in enumerate(buttons):
        b_text = btn.get("text", "Button")
        b_style = style_badges.get(btn.get("style"), "⚪ Default")
        keyboard.append([
            InlineKeyboardButton(f"{idx+1}. {b_text} [{b_style}]", url=btn.get("url", "https://t.me")),
            InlineKeyboardButton("🗑️ Delete", callback_data=f"del_btn:{channel_id}:{idx}")
        ])

    keyboard.append([
        InlineKeyboardButton("➕ Add New Button", callback_data=f"add_btn:{channel_id}")
    ])
    if buttons:
        keyboard.append([
            InlineKeyboardButton("🗑️ Remove All Buttons (No Buttons)", callback_data=f"clear_btns:{channel_id}")
        ])
    keyboard.append([
        InlineKeyboardButton("⬅️ Back to Channel Settings", callback_data=f"view_ch:{channel_id}")
    ])
    return InlineKeyboardMarkup(keyboard)

def get_button_style_select_keyboard(channel_id: str) -> InlineKeyboardMarkup:
    """Menu to choose Telegram's native colored button style + premium emoji icon"""
    keyboard = [
        [
            InlineKeyboardButton("🟢 Green (Success Style)", callback_data=f"btnstyle:{channel_id}:success:5420315771991497307")
        ],
        [
            InlineKeyboardButton("🔴 Red (Danger Style)", callback_data=f"btnstyle:{channel_id}:danger:5188481279963715781")
        ],
        [
            InlineKeyboardButton("🔵 Blue (Primary Style)", callback_data=f"btnstyle:{channel_id}:primary:6266995104687330978")
        ],
        [
            InlineKeyboardButton("⚪ Default (Standard Style)", callback_data=f"btnstyle:{channel_id}:default:none")
        ],
        [
            InlineKeyboardButton("⬅️ Cancel", callback_data=f"manage_btns:{channel_id}")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_userbot_keyboard(is_active: bool) -> InlineKeyboardMarkup:
    """Menu for Telegram Userbot Management"""
    if is_active:
        keyboard = [
            [
                InlineKeyboardButton("🚪 Logout Userbot", callback_data="userbot_logout"),
                InlineKeyboardButton("🔄 Change / Re-login", callback_data="userbot_start_login")
            ],
            [
                InlineKeyboardButton("⬅️ Back to Admin Panel", callback_data="admin_main")
            ]
        ]
    else:
        keyboard = [
            [
                InlineKeyboardButton("📱 Connect Account (/login)", callback_data="userbot_start_login")
            ],
            [
                InlineKeyboardButton("⬅️ Back to Admin Panel", callback_data="admin_main")
            ]
        ]
    return InlineKeyboardMarkup(keyboard)



def get_hack_menu_keyboard(
    strategy: str,
    send_apk: bool,
    has_win_caption: bool,
    stickers_count: int,
    base_bet: int
) -> InlineKeyboardMarkup:
    strat_toggle = "Switch to Standard AI 🎯" if strategy == "sure_shot_hack" else "Activate SureShot Hack 🔥"
    apk_badge = "✅ Send APK with Signal: ON" if send_apk else "❌ Send APK with Signal: OFF"
    caption_badge = "📝 Win Caption: Custom" if has_win_caption else "⚪ Win Caption: Clean Shot Only"

    keyboard = [
        [
            InlineKeyboardButton(strat_toggle, callback_data="admin_toggle_strategy")
        ],
        [
            InlineKeyboardButton("📝 Edit Signal Template", callback_data="input_hack_signal_tpl"),
            InlineKeyboardButton(apk_badge, callback_data="toggle_hack_apk")
        ],
        [
            InlineKeyboardButton(caption_badge, callback_data="menu_hack_caption"),
            InlineKeyboardButton(f"🎉 Win Stickers ({stickers_count})", callback_data="admin_manage_stickers")
        ],
        [
            InlineKeyboardButton(f"💰 Dual Bet per Side: ₹{base_bet}", callback_data="admin_set_bet")
        ],
        [
            InlineKeyboardButton("⬅️ Back to Admin Panel", callback_data="admin_main")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_stickers_manage_keyboard(stickers_count: int) -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton("➕ Add Win Sticker (Send Sticker)", callback_data="add_win_sticker")
        ]
    ]
    if stickers_count > 0:
        keyboard.append([
            InlineKeyboardButton("🗑️ Clear All Win Stickers", callback_data="clear_win_stickers")
        ])
    keyboard.append([
        InlineKeyboardButton("⬅️ Back to Hack Settings", callback_data="admin_hack_menu")
    ])
    return InlineKeyboardMarkup(keyboard)

def get_win_caption_keyboard(has_caption: bool) -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton("✏️ Set Win Caption", callback_data="input_hack_win_caption")
        ]
    ]
    if has_caption:
        keyboard.append([
            InlineKeyboardButton("🗑️ Clear Caption (Clean Screenshot Only)", callback_data="clear_hack_win_caption")
        ])
    keyboard.append([
        InlineKeyboardButton("⬅️ Back to Hack Settings", callback_data="admin_hack_menu")
    ])
    return InlineKeyboardMarkup(keyboard)
