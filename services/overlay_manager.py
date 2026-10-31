import os
import json
import logging
from typing import Optional, List

from database import db_manager

logger = logging.getLogger(__name__)

# Complete standalone CSS extracted from zayro.html with high-priority isolation
ZAYRO_CSS = """
:root {
  --z-red: #ff003c;
  --z-glow: rgba(255, 0, 60, 0.45);
  --z-gold: #ffd000;
  --z-green: #00ff88;
  --z-bg-card: #0d0208;
  --z-card-w: 236px;
}

#zayro-vip-overlay {
  position: fixed !important;
  top: 14px !important;
  left: 50% !important;
  transform: translateX(-50%) !important;
  z-index: 2147483647 !important;
  width: var(--z-card-w) !important;
  pointer-events: none !important;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif !important;
  user-select: none !important;
  -webkit-user-select: none !important;
  display: block !important;
  box-sizing: border-box !important;
}

#zayro-vip-overlay * {
  box-sizing: border-box !important;
  margin: 0;
  padding: 0;
}

#zayro-vip-overlay .card-outer {
  position: relative !important;
  width: 100% !important;
  background: radial-gradient(circle at 50% 0%, #1e030a 0%, #0d0206 50%, #060103 100%) !important;
  border-radius: 16px !important;
  box-shadow: 
    0 16px 40px rgba(0, 0, 0, 0.95),
    0 0 25px rgba(255, 0, 60, 0.45),
    inset 0 0 15px rgba(255, 0, 60, 0.2) !important;
  border: 1.2px solid rgba(255, 0, 60, 0.75) !important;
  overflow: visible !important;
}

#zayro-vip-overlay .card-stroke {
  position: absolute !important;
  inset: 0 !important;
  width: 100% !important;
  height: 100% !important;
  pointer-events: none !important;
  z-index: 8 !important;
  overflow: visible !important;
}

#zayro-vip-overlay .card-stroke rect {
  fill: none !important;
  stroke: #ffd166 !important;
  stroke-width: 1.8 !important;
  stroke-dasharray: 22 78 !important;
  stroke-dashoffset: 0 !important;
  stroke-linecap: round !important;
  animation: zayroRunningStroke 3.4s linear infinite !important;
  filter: drop-shadow(0 0 4px rgba(255, 164, 0, 0.95)) drop-shadow(0 0 10px rgba(255, 74, 0, 0.55)) !important;
}

@keyframes zayroRunningStroke {
  from { stroke-dashoffset: 100; }
  to { stroke-dashoffset: 0; }
}

#zayro-vip-overlay .card-title-line1 {
  position: absolute !important;
  top: -10px !important;
  left: 50% !important;
  transform: translateX(-50%) !important;
  background: linear-gradient(180deg, #ff3b6d 0%, #d00035 56%, #78001b 100%) !important;
  border: 1px solid #ff8aa5 !important;
  border-radius: 14px !important;
  padding: 2px 10px !important;
  font-size: 8px !important;
  font-weight: 900 !important;
  letter-spacing: 0.1em !important;
  color: #ffffff !important;
  text-transform: uppercase !important;
  white-space: nowrap !important;
  box-shadow: 
    0 2px 8px rgba(0, 0, 0, 0.7),
    0 0 10px rgba(255, 0, 60, 0.7),
    inset 0 1px 1px rgba(255, 255, 255, 0.5) !important;
  z-index: 10 !important;
}

#zayro-vip-overlay .card-bracket {
  position: absolute !important;
  width: 9px !important;
  height: 9px !important;
  border-color: #ffd000 !important;
  border-style: solid !important;
  z-index: 9 !important;
  pointer-events: none !important;
}
#zayro-vip-overlay .b-tl { top: -2px !important; left: -2px !important; border-width: 2px 0 0 2px !important; border-top-left-radius: 4px !important; }
#zayro-vip-overlay .b-tr { top: -2px !important; right: -2px !important; border-width: 2px 2px 0 0 !important; border-top-right-radius: 4px !important; }
#zayro-vip-overlay .b-bl { bottom: -2px !important; left: -2px !important; border-width: 0 0 2px 2px !important; border-bottom-left-radius: 4px !important; }
#zayro-vip-overlay .b-br { bottom: -2px !important; right: -2px !important; border-width: 0 2px 2px 0 !important; border-bottom-right-radius: 4px !important; }

#zayro-vip-overlay .card-inner {
  position: relative !important;
  padding: 8px 6px 7px !important;
  display: flex !important;
  flex-direction: column !important;
  gap: 4px !important;
  z-index: 2 !important;
}

#zayro-vip-overlay .mode-strip {
  width: 100% !important;
  display: flex !important;
  align-items: center !important;
  justify-content: space-between !important;
  background: rgba(15, 2, 8, 0.85) !important;
  border: 1px solid rgba(255, 0, 60, 0.4) !important;
  border-radius: 6px !important;
  padding: 2.5px 6px !important;
  font-family: monospace, sans-serif !important;
  font-size: 6.2px !important;
  font-weight: 800 !important;
  letter-spacing: 0.05em !important;
  color: #ffffff !important;
}

#zayro-vip-overlay .strip-item {
  display: flex !important;
  align-items: center !important;
  gap: 2px !important;
}
#zayro-vip-overlay .strip-val { color: #ffffff !important; }
#zayro-vip-overlay .strip-mode { color: #00ff88 !important; text-shadow: 0 0 5px rgba(0, 255, 136, 0.7) !important; }
#zayro-vip-overlay .strip-ping { color: #00ff88 !important; }

#zayro-vip-overlay .card-screen {
  position: relative !important;
  width: 100% !important;
  background: radial-gradient(circle at 50% 50%, #150209 0%, #0a0104 100%) !important;
  border-radius: 10px !important;
  border: 1px solid rgba(255, 0, 60, 0.3) !important;
  padding: 5px 4px !important;
  overflow: hidden !important;
  box-shadow: inset 0 0 15px rgba(0, 0, 0, 0.8) !important;
}

#zayro-vip-overlay .screen-cyber-matrix {
  position: absolute !important;
  inset: 0 !important;
  pointer-events: none !important;
  z-index: 1 !important;
}

#zayro-vip-overlay .circuit-svg {
  position: absolute !important;
  inset: 0 !important;
  width: 100% !important;
  height: 100% !important;
  opacity: 0.35 !important;
}

#zayro-vip-overlay .telemetry-hud-tag {
  position: absolute !important;
  font-family: monospace, sans-serif !important;
  font-size: 5.5px !important;
  font-weight: 800 !important;
  letter-spacing: 0.05em !important;
  color: rgba(255, 0, 60, 0.6) !important;
}
#zayro-vip-overlay .tele-tl { top: 3px !important; left: 5px !important; }
#zayro-vip-overlay .tele-tr { top: 3px !important; right: 5px !important; color: rgba(255, 208, 0, 0.65) !important; }
#zayro-vip-overlay .tele-bl { bottom: 3px !important; left: 5px !important; }
#zayro-vip-overlay .tele-br { bottom: 3px !important; right: 5px !important; }

#zayro-vip-overlay .laser-sweep-line {
  position: absolute !important;
  top: 0 !important;
  left: 0 !important;
  right: 0 !important;
  height: 1px !important;
  background: linear-gradient(90deg, transparent 0%, rgba(255, 0, 60, 0.8) 50%, transparent 100%) !important;
  box-shadow: 0 0 8px #ff003c !important;
  animation: zayroLaserSweep 4s ease-in-out infinite !important;
  opacity: 0.45 !important;
}
@keyframes zayroLaserSweep {
  0% { top: 0%; opacity: 0; }
  25% { opacity: 0.6; }
  75% { opacity: 0.6; }
  100% { top: 100%; opacity: 0; }
}

#zayro-vip-overlay #sv-result {
  position: relative !important;
  z-index: 3 !important;
  width: 100% !important;
  display: flex !important;
  flex-direction: column !important;
  align-items: center !important;
  justify-content: center !important;
  gap: 3.5px !important;
}

#zayro-vip-overlay .pred-showcase-row {
  display: flex !important;
  align-items: center !important;
  justify-content: space-between !important;
  width: 100% !important;
  padding: 0 4px !important;
}

/* 3D OUTCOME INGOT */
#zayro-vip-overlay .res-outcome-ingot {
  position: relative !important;
  width: 104px !important;
  height: 48px !important;
  border-radius: 9px !important;
  display: flex !important;
  flex-direction: column !important;
  align-items: center !important;
  justify-content: center !important;
  text-align: center !important;
  box-shadow: 
    0 4px 12px rgba(0, 0, 0, 0.7),
    inset 0 1px 2px rgba(255, 255, 255, 0.4),
    inset 0 -2px 4px rgba(0, 0, 0, 0.6) !important;
  border: 1px solid rgba(255, 255, 255, 0.3) !important;
}

#zayro-vip-overlay .res-outcome-ingot.big {
  background: linear-gradient(180deg, #ff1a53 0%, #c4002c 50%, #750017 100%) !important;
  border-color: #ff5c85 !important;
  box-shadow: 
    0 0 14px rgba(255, 0, 60, 0.65),
    inset 0 1px 2px rgba(255, 255, 255, 0.4),
    inset 0 -2px 4px rgba(0, 0, 0, 0.6) !important;
}
#zayro-vip-overlay .res-outcome-ingot.small {
  background: linear-gradient(180deg, #00d668 0%, #009945 50%, #005224 100%) !important;
  border-color: #33ff99 !important;
  box-shadow: 
    0 0 14px rgba(0, 255, 136, 0.65),
    inset 0 1px 2px rgba(255, 255, 255, 0.4),
    inset 0 -2px 4px rgba(0, 0, 0, 0.6) !important;
}

#zayro-vip-overlay .ingot-top-tag {
  font-size: 6px !important;
  font-weight: 900 !important;
  letter-spacing: 0.1em !important;
  color: #ffd000 !important;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.8) !important;
}
#zayro-vip-overlay .ingot-main-text {
  font-size: 19px !important;
  font-weight: 900 !important;
  letter-spacing: 0.05em !important;
  color: #ffffff !important;
  line-height: 1.1 !important;
  text-shadow: 0 2px 6px rgba(0, 0, 0, 0.8) !important;
}
#zayro-vip-overlay .ingot-conf-pill {
  display: flex !important;
  align-items: center !important;
  gap: 3px !important;
  font-family: monospace, sans-serif !important;
  font-size: 6.2px !important;
  font-weight: 800 !important;
  color: #ffffff !important;
}
#zayro-vip-overlay .conf-dot {
  width: 4px !important;
  height: 4px !important;
  border-radius: 50% !important;
  background: #ffd000 !important;
  box-shadow: 0 0 4px #ffd000 !important;
}

/* 3D CASINO CHIP PEDESTAL WITH AUTHENTIC BALL IMAGE */
#zayro-vip-overlay .res-chip-pedestal {
  position: relative !important;
  width: 82px !important;
  display: flex !important;
  flex-direction: column !important;
  align-items: center !important;
  justify-content: center !important;
}

#zayro-vip-overlay .pedestal-radar-rings {
  position: absolute !important;
  top: 0 !important;
  width: 44px !important;
  height: 44px !important;
  pointer-events: none !important;
}
#zayro-vip-overlay .ped-ring {
  position: absolute !important;
  inset: -2px !important;
  border-radius: 50% !important;
  border: 1px dashed rgba(255, 0, 60, 0.5) !important;
  animation: zayroRadarRingSpin 6s linear infinite !important;
}
#zayro-vip-overlay .ring-inner {
  inset: 2px !important;
  border-style: dotted !important;
  border-color: rgba(255, 208, 0, 0.45) !important;
  animation: zayroRadarRingSpin 4s linear infinite reverse !important;
}
@keyframes zayroRadarRingSpin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

#zayro-vip-overlay .ball-ambient-glow {
  position: absolute !important;
  top: 0 !important;
  width: 44px !important;
  height: 44px !important;
  border-radius: 50% !important;
  filter: blur(6px) !important;
  opacity: 0.65 !important;
  pointer-events: none !important;
}

#zayro-vip-overlay .res-ball {
  position: relative !important;
  width: 42px !important;
  height: 42px !important;
  border-radius: 50% !important;
  display: grid !important;
  place-items: center !important;
  box-shadow: 0 3px 10px rgba(0, 0, 0, 0.85) !important;
}

#zayro-vip-overlay .ball-bg-img {
  position: absolute !important;
  inset: 0 !important;
  width: 100% !important;
  height: 100% !important;
  border-radius: 50% !important;
  object-fit: cover !important;
  z-index: 1 !important;
}

#zayro-vip-overlay .ball-circle-red {
  background: radial-gradient(circle at 35% 30%, #ff4d6d 0%, #c9184a 55%, #590d22 100%) !important;
  border: 1.5px solid #ff758f !important;
}
#zayro-vip-overlay .ball-circle-green {
  background: radial-gradient(circle at 35% 30%, #52b788 0%, #2d6a4f 55%, #081c15 100%) !important;
  border: 1.5px solid #74c69d !important;
}
#zayro-vip-overlay .ball-circle-violet {
  background: radial-gradient(circle at 35% 30%, #b5179e 0%, #7209b7 55%, #3a0ca3 100%) !important;
  border: 1.5px solid #c77dff !important;
}

#zayro-vip-overlay .res-num-text {
  position: relative !important;
  z-index: 2 !important;
  font-size: 18px !important;
  font-weight: 900 !important;
  color: #ffffff !important;
  text-shadow: 0 0 6px rgba(0, 0, 0, 0.95), 0 1px 3px #000 !important;
  line-height: 1 !important;
}

#zayro-vip-overlay .res-color-pill {
  margin-top: 2px !important;
  font-size: 5.2px !important;
  font-weight: 900 !important;
  letter-spacing: 0.03em !important;
  color: #ffd000 !important;
  background: rgba(255, 208, 0, 0.15) !important;
  border: 1px solid rgba(255, 208, 0, 0.45) !important;
  border-radius: 20px !important;
  padding: 1px 5px !important;
  text-transform: uppercase !important;
  white-space: nowrap !important;
}

#zayro-vip-overlay .api-id-horizon {
  display: flex !important;
  align-items: center !important;
  justify-content: center !important;
  gap: 4px !important;
  width: 100% !important;
  font-family: monospace, sans-serif !important;
  font-size: 6.8px !important;
  font-weight: 800 !important;
  color: #ffffff !important;
  margin: 1px 0 !important;
}

#zayro-vip-overlay .horizon-line {
  flex: 1 !important;
  height: 1px !important;
  background: linear-gradient(90deg, transparent, rgba(255, 0, 60, 0.5), transparent) !important;
}
#zayro-vip-overlay .horizon-acc {
  color: #00ff88 !important;
  font-weight: 900 !important;
  text-shadow: 0 0 4px rgba(0, 255, 136, 0.6) !important;
}

/* 6 HISTORICAL CASINO MINI-CHIPS ROW */
#zayro-vip-overlay .hist-balls-row {
  display: flex !important;
  align-items: center !important;
  justify-content: center !important;
  gap: 4px !important;
  width: 100% !important;
  padding-bottom: 2px !important;
}

#zayro-vip-overlay .h-chip-col {
  display: flex !important;
  flex-direction: column !important;
  align-items: center !important;
  gap: 1.5px !important;
}

#zayro-vip-overlay .h-mini-chip {
  position: relative !important;
  width: 19px !important;
  height: 19px !important;
  border-radius: 50% !important;
  background-size: cover !important;
  background-position: center !important;
  display: grid !important;
  place-items: center !important;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.7) !important;
}

#zayro-vip-overlay .h-mini-num {
  position: relative !important;
  z-index: 2 !important;
  font-size: 8.5px !important;
  font-weight: 900 !important;
  color: #ffffff !important;
  text-shadow: 0 1px 2px #000 !important;
  line-height: 1 !important;
}

#zayro-vip-overlay .h-pip {
  font-size: 5.2px !important;
  font-weight: 900 !important;
  border-radius: 3px !important;
  padding: 0.5px 3px !important;
  line-height: 1 !important;
}
#zayro-vip-overlay .h-pip.b { background: #ff003c !important; color: #ffffff !important; }
#zayro-vip-overlay .h-pip.s { background: #00ff88 !important; color: #000000 !important; }

/* RED GLOSSY CARD BUTTONS */
#zayro-vip-overlay .card-buttons {
  display: flex !important;
  align-items: center !important;
  gap: 5px !important;
  width: 100% !important;
  margin-top: 2px !important;
}

#zayro-vip-overlay #action-btn {
  flex: 1.5 !important;
  height: 28px !important;
  border: none !important;
  border-radius: 14px !important;
  background: linear-gradient(180deg, #ff2458 0%, #c4002c 55%, #7a001a 100%) !important;
  color: #ffffff !important;
  font-family: inherit !important;
  font-size: 9.5px !important;
  font-weight: 900 !important;
  letter-spacing: 0.08em !important;
  text-transform: uppercase !important;
  box-shadow: 
    0 4px 10px rgba(0, 0, 0, 0.6),
    0 0 10px rgba(255, 0, 60, 0.5),
    inset 0 1px 2px rgba(255, 255, 255, 0.5),
    inset 0 -2px 3px rgba(0, 0, 0, 0.6) !important;
  border: 1px solid #ff5c85 !important;
  display: flex !important;
  align-items: center !important;
  justify-content: center !important;
  cursor: pointer !important;
}

#zayro-vip-overlay .hide-btn {
  flex: 1 !important;
  height: 28px !important;
  border: none !important;
  border-radius: 14px !important;
  background: linear-gradient(180deg, #1f040d 0%, #120207 100%) !important;
  color: #ffffff !important;
  font-family: inherit !important;
  font-size: 9px !important;
  font-weight: 800 !important;
  letter-spacing: 0.08em !important;
  text-transform: uppercase !important;
  display: flex !important;
  align-items: center !important;
  justify-content: center !important;
  gap: 4px !important;
  border: 1px solid rgba(255, 0, 60, 0.35) !important;
  box-shadow: inset 0 1px 1px rgba(255, 255, 255, 0.2) !important;
  cursor: pointer !important;
}
"""



class OverlayManager:
    """
    Manages the floating VIP hack overlay injected directly into the live game page during Playwright runs.
    Ensures that when a win occurs, the Congratulations popup has this floating card on top in the screenshot.
    """

    _ball_cache = {}

    @classmethod
    def get_ball_b64(cls, num: int) -> str:
        """Loads and caches authentic 3D casino chip base64 image for digit 0-9"""
        n = int(num) % 10
        if n in cls._ball_cache:
            return cls._ball_cache[n]

        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        asset_file = os.path.join(base_dir, "assets", f"ball_{n}.b64")
        if os.path.exists(asset_file):
            try:
                with open(asset_file, "r", encoding="utf-8") as f:
                    cls._ball_cache[n] = f.read().strip()
                    return cls._ball_cache[n]
            except Exception:
                pass

        # Robust Fallback: extract base64 directly from zayro.html
        zayro_file = os.path.join(base_dir, "zayro.html")
        if os.path.exists(zayro_file):
            try:
                import re
                with open(zayro_file, "r", encoding="utf-8") as f:
                    content = f.read()
                m = re.search(rf'id=["\']rc_{n}["\'][^>]*background-image:url\([\'"]?(data:image/[^\'"]+?)[\'"]?\)', content)
                if m:
                    cls._ball_cache[n] = m.group(1).strip()
                    return cls._ball_cache[n]
            except Exception:
                pass
        return ""

    @staticmethod
    def get_ball_info(number: Optional[int], choice: str) -> dict:
        """Returns ball styling, color name, and number"""
        if number is None:
            num = 7 if choice.upper() == "BIG" else 2
        else:
            num = int(number)

        if num in (1, 3, 7, 9):
            color = "GREEN"
            cls_name = "ball-circle-green"
        elif num in (2, 4, 6, 8):
            color = "RED"
            cls_name = "ball-circle-red"
        elif num == 0:
            color = "RED+VIOLET"
            cls_name = "ball-circle-violet"
        else: # 5
            color = "GREEN+VIOLET"
            cls_name = "ball-circle-violet"

        return {"number": num, "color": color, "class": cls_name}

    @classmethod
    def render_hist_chips(cls, current_num: int) -> str:
        """Generates 6 realistic historical casino mini-chips with authentic 3D textures & B/S pips"""
        # Alternate realistic historical sequence based on current number
        sequence = [
            (current_num + 3) % 10,
            (current_num + 7) % 10,
            (current_num + 2) % 10,
            (current_num + 6) % 10,
            (current_num + 1) % 10,
            (current_num + 8) % 10
        ]
        chips = []
        for n in sequence:
            b64 = cls.get_ball_b64(n)
            bs = "B" if n >= 5 else "S"
            bs_cls = "b" if bs == "B" else "s"
            style = f'style="background-image:url(\'{b64}\');"' if b64 else ""
            chips.append(
                f'<div class="h-chip-col">'
                f'  <div class="h-mini-chip" {style}><span class="h-mini-num">{n}</span></div>'
                f'  <span class="h-pip {bs_cls}">{bs}</span>'
                f'</div>'
            )
        return "".join(chips)

    @classmethod
    def generate_overlay_payload(
        cls,
        issue: str,
        choice: str,
        confidence: float = 98.7,
        level: int = 1,
        number: Optional[int] = None,
        brand_title: Optional[str] = None
    ) -> dict:
        """
        Returns {"html": ..., "css": ..., "ball_b64": ..., "ball_num": ..., "ball_color": ..., "choice": ..., "short_issue": ...}
        Supports both the built-in Zayro VIP Hack Card (with auto brand detection) AND any uploaded custom .html file
        (whether a standalone <!DOCTYPE html> hack suite or a custom HTML snippet).
        """
        import re
        choice_clean = choice.strip().upper()
        if choice_clean in ("CONFIRMED", "SURE_SHOT", "WIN", "HACK", ""):
            outcome_class = "big"
            main_badge_text = "BIG"
            conf_str = "100%"
        else:
            outcome_class = "big" if choice_clean == "BIG" else "small"
            main_badge_text = choice_clean
            conf_str = f"{float(confidence):.1f}%" if float(confidence) > 0 else "98.8%"

        ball = cls.get_ball_info(number, "BIG" if outcome_class == "big" else "SMALL")
        ball_b64 = cls.get_ball_b64(ball["number"])
        short_issue = str(issue)[-5:] if len(str(issue)) > 5 else str(issue)
        brand_title = db_manager.get_overlay_brand_name()

        custom_tpl = db_manager.get_custom_html_template()
        if custom_tpl and len(custom_tpl.strip()) > 40:
            raw = custom_tpl.strip()
            extra_styles = []
            for sm in re.finditer(r"<style[^>]*>([\s\S]*?)</style>", raw, re.IGNORECASE):
                st_content = sm.group(1)
                # Strip rules that override host html/body overflow or background
                st_content = re.sub(r"html\s*,\s*body\s*\{[^}]*\}", "", st_content)
                st_content = re.sub(r"#target-game-frame\s*\{[^}]*\}", "", st_content)
                st_content = re.sub(r"#injector-container\s*\{[^}]*\}", "#injector-container { position: relative !important; top: auto !important; left: auto !important; transform: none !important; display: block !important; visibility: visible !important; opacity: 1 !important; }", st_content)
                extra_styles.append(st_content)

            # Extract #injector-container or body markup while keeping original .card-title-line1 untouched
            body_match = re.search(r"<body[^>]*>([\s\S]*?)</body>", raw, re.IGNORECASE)
            body_html = body_match.group(1) if body_match else raw
            # Remove scripts, iframes, styles, preview toolbars, and warning modals
            body_html = re.sub(r"<script[\s\S]*?</script>", "", body_html, flags=re.IGNORECASE)
            body_html = re.sub(r"<style[\s\S]*?</style>", "", body_html, flags=re.IGNORECASE)
            body_html = re.sub(r"<iframe[\s\S]*?</iframe>", "", body_html, flags=re.IGNORECASE)
            body_html = re.sub(r"<iframe[^>]*>", "", body_html, flags=re.IGNORECASE)

            # Replace placeholders if present (never overwrite literal card title)
            body_html = (
                body_html
                .replace("{issue}", str(issue))
                .replace("{issue_short}", str(short_issue))
                .replace("{choice}", main_badge_text)
                .replace("{confidence}", f"{float(confidence):.1f}")
                .replace("{level}", str(level))
                .replace("{number}", str(ball["number"]))
                .replace("{color}", str(ball["color"]))
            )

            combined_css = ZAYRO_CSS + "\n" + "\n".join(extra_styles) + """
            #zayro-vip-overlay #preview-dashboard,
            #zayro-vip-overlay #warnOverlay,
            #zayro-vip-overlay #miniBtn,
            #zayro-vip-overlay #hitFlash,
            #zayro-vip-overlay #sv-wait,
            #zayro-vip-overlay #sv-low,
            #zayro-vip-overlay #sv-ready,
            #zayro-vip-overlay #sv-scan {
                display: none !important;
            }
            #zayro-vip-overlay #injector-container {
                display: block !important;
                visibility: visible !important;
                opacity: 1 !important;
            }
            #zayro-vip-overlay #sv-result,
            #zayro-vip-overlay [id*="sv-result"] {
                display: flex !important;
            }
            """
            if body_html.strip():
                return {
                    "html": body_html,
                    "css": combined_css,
                    "ball_b64": ball_b64,
                    "ball_num": ball["number"],
                    "ball_color": ball["color"],
                    "ball_class": ball["class"],
                    "choice": main_badge_text,
                    "outcome_class": outcome_class,
                    "conf_str": conf_str,
                    "short_issue": short_issue,
                    "brand_title": brand_title,
                    "hist_html": cls.render_hist_chips(ball["number"]),
                }

        html = cls.generate_html(
            issue=issue,
            choice=choice,
            confidence=confidence,
            level=level,
            number=number
        )
        return {
            "html": html,
            "css": ZAYRO_CSS,
            "ball_b64": ball_b64,
            "ball_num": ball["number"],
            "ball_color": ball["color"],
            "ball_class": ball["class"],
            "choice": main_badge_text,
            "outcome_class": outcome_class,
            "conf_str": conf_str,
            "short_issue": short_issue,
            "brand_title": brand_title,
            "hist_html": cls.render_hist_chips(ball["number"]),
        }

    @classmethod
    def generate_html(
        cls,
        issue: str,
        choice: str,
        confidence: float = 98.7,
        level: int = 1,
        number: Optional[int] = None
    ) -> str:
        """
        Generates the complete authentic HTML markup for the Zayro VIP Hack Card.
        """
        choice_clean = choice.strip().upper()
        if choice_clean in ("CONFIRMED", "SURE_SHOT", "WIN", "HACK", ""):
            outcome_class = "big"
            main_badge_text = "CONFIRMED WIN"
            conf_str = "100%"
        else:
            outcome_class = "big" if choice_clean == "BIG" else "small"
            main_badge_text = choice_clean
            conf_str = f"{float(confidence):.1f}%" if float(confidence) > 0 else "98.8%"

        ball = cls.get_ball_info(number, "BIG" if outcome_class == "big" else "SMALL")
        ball_b64 = cls.get_ball_b64(ball["number"])
        short_issue = str(issue)[-5:] if len(str(issue)) > 5 else str(issue)
        hist_chips_html = cls.render_hist_chips(ball["number"])
        brand_title = db_manager.get_overlay_brand_name()

        ball_img_html = f'<img class="ball-bg-img" id="ballBgImg" src="{ball_b64}" alt="Casino Chip">' if ball_b64 else ''

        html = f"""
        <div class="card-outer">
          <!-- SINGLE GOLD LASER RUNNING STROKE -->
          <svg class="card-stroke" viewBox="0 0 236 215" preserveAspectRatio="none">
            <rect x="1" y="1" width="234" height="213" pathLength="100" rx="16"/>
          </svg>

          <!-- TOP DOCKED PILL BADGE -->
          <div class="card-title-line1">{brand_title}</div>

          <!-- 4 CORNER NOTCH BRACKETS -->
          <div class="card-bracket b-tl"></div>
          <div class="card-bracket b-tr"></div>
          <div class="card-bracket b-bl"></div>
          <div class="card-bracket b-br"></div>

          <div class="card-inner">
            <!-- STATUS STRIP -->
            <div class="mode-strip">
              <div class="strip-item"><span>SYS : </span><span class="strip-val">SECURE PRO</span></div>
              <div class="strip-item"><span>MOD : </span><span class="strip-mode">ACTIVE</span></div>
              <div class="strip-item"><span>PING : </span><span class="strip-ping">21MS</span></div>
            </div>

            <!-- INNER SCREEN VIEWPORT -->
            <div class="card-screen">
              <div class="screen-cyber-matrix">
                <svg class="circuit-svg" viewBox="0 0 240 120" preserveAspectRatio="none">
                  <path d="M 0 20 L 35 20 L 48 35 L 95 35 M 145 35 L 192 35 L 205 20 L 240 20" stroke="#ff003c" stroke-width="0.8" fill="none"/>
                  <path d="M 0 100 L 40 100 L 52 85 L 90 85 M 150 85 L 188 85 L 200 100 L 240 100" stroke="#ff003c" stroke-width="0.8" fill="none"/>
                  <circle cx="48" cy="35" r="1.5" fill="#ffd000"/>
                  <circle cx="192" cy="35" r="1.5" fill="#ffd000"/>
                </svg>
                <div class="telemetry-hud-tag tele-tl">&#9733; 0x9K-AI</div>
                <div class="telemetry-hud-tag tele-tr">SYNC: 99.8% &#9733;</div>
                <div class="telemetry-hud-tag tele-bl">&#9889; MATRIX: ON</div>
                <div class="telemetry-hud-tag tele-br">5.8GHz &#9889;</div>
                <div class="laser-sweep-line"></div>
              </div>

              <!-- PREDICTION RESULT COCKPIT -->
              <div id="sv-result">
                <div class="pred-showcase-row">
                  <!-- Left: 3D Outcome Ingot -->
                  <div class="res-outcome-ingot {outcome_class}" id="resBsBadge">
                    <div class="ingot-top-tag">&#9733; AI VERDICT &#9733;</div>
                    <div class="ingot-main-text" id="resBsText">{main_badge_text}</div>
                    <div class="ingot-conf-pill">
                      <span class="conf-dot"></span>
                      <span id="resConfText">CONF: {conf_str}</span>
                    </div>
                  </div>

                  <!-- Right: 3D Casino Chip Pedestal -->
                  <div class="res-chip-pedestal">
                    <div class="pedestal-radar-rings">
                      <div class="ped-ring ring-outer"></div>
                      <div class="ped-ring ring-inner"></div>
                    </div>
                    <div class="ball-ambient-glow" style="background:radial-gradient(circle, rgba(255, 0, 60, 0.7) 0%, transparent 70%);"></div>
                    <div class="res-ball {ball['class']}" id="resBall">
                      {ball_img_html}
                      <span class="res-num-text" id="resNumText">{ball['number']}</span>
                    </div>
                    <div class="res-color-pill" id="resColorPill">COLOR: {ball['color']}</div>
                  </div>
                </div>

                <!-- Precision Laser Horizon -->
                <div class="api-id-horizon">
                  <span class="horizon-line"></span>
                  <span id="res-period-bottom">API ID : {short_issue}</span>
                  <span class="horizon-acc">SAFE LEVEL {level}</span>
                  <span class="horizon-line"></span>
                </div>

                <!-- 6 Historical Casino Mini-Chips -->
                <div class="hist-balls-row" id="histBallsRow">
                  {hist_chips_html}
                </div>
              </div>
            </div>

            <!-- RED GLOSSY CARD BUTTONS -->
            <div class="card-buttons">
              <button id="action-btn" class="analyze" type="button">ANALYZE</button>
              <button class="hide-btn" id="hideBtn" type="button">
                <svg viewBox="0 0 24 24" width="12" height="12" fill="none">
                  <path d="M1 12S5 5 12 5S23 12 23 12S19 19 12 19S1 12 1 12Z" stroke="#ff3366" stroke-width="2"/>
                  <circle cx="12" cy="12" r="3" fill="#ff003c"/>
                  <line x1="2" y1="2" x2="22" y2="22" stroke="#ffffff" stroke-width="2"/>
                </svg>
                <span>HIDE</span>
              </button>
            </div>
          </div>
        </div>
        """
        return html


overlay_manager = OverlayManager()
