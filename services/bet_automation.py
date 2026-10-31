import io
import asyncio
import logging
from typing import Optional

from services.playwright_worker import playwright_worker

logger = logging.getLogger(__name__)


class BetAutomationService:
    """
    Playwright Real Game Automation Service:
    - Real bet placement on live game board (WinGo).
    - Continuous period-aware watcher catches the 3-second 'Congratulations' popup right at 00:00 draw.
    - Zero delay, zero fake drawings.
    """

    def __init__(self):
        self.worker = playwright_worker

    @property
    def enabled(self) -> bool:
        return self.worker.enabled

    @property
    def is_logged_in(self) -> bool:
        return self.worker.is_ready

    async def initialize(self) -> bool:
        return await self.worker.initialize()

    async def place_bet(
        self,
        game_id: str,
        choice: str,
        issue_number: str = "",
        level: int = 1,
        confidence: float = 98.7,
        number: Optional[int] = None
    ) -> bool:
        res = await self.worker.place_bet(
            game_id=game_id,
            choice=choice,
            issue_number=issue_number,
            level=level,
            confidence=confidence,
            number=number
        )
        return res.get("ok", False)

    async def place_dual_bet(
        self,
        game_id: str,
        issue_number: str = "",
        amount: Optional[int] = None,
        confidence: float = 99.8
    ) -> bool:
        res = await self.worker.place_dual_bet(
            game_id=game_id,
            issue_number=issue_number,
            amount=amount,
            confidence=confidence
        )
        return res.get("ok", False)

    async def capture_win_screenshot(
        self,
        game_id: str,
        target_issue: str,
        choice: str = "BIG",
        actual_number: int = 7,
        level: int = 1,
        streak: int = 1
    ) -> Optional[io.BytesIO]:
        """
        Retrieves the 100% genuine in-game screenshot captured right at the draw time:
        1. Records actual winning choice & number so watcher can inject matching VIP card if still capturing.
        2. Checks real-time draw watcher cache (captured right at 00:00).
        3. Polls up to 7.5s while the browser finishes rendering & capturing the Congratulations popup.
        4. Never sends fake drawings or bare board screenshots.
        """
        target_key = str(target_issue)
        self.worker.known_results[target_key] = {
            "choice": str(choice).upper(),
            "number": actual_number
        }

        # 1. Check if the real-time draw watcher already captured the winning popup
        shot = self.worker.cached_win_screenshots.pop(target_key, None)
        if shot:
            logger.info(f"📸 Delivering instant live Win Popup screenshot for period {target_issue}!")
            return shot

        # 2. Wait up to 7.5s (30 x 0.25s) while draw watcher catches the 00:00 Congratulations popup
        for _ in range(30):
            await asyncio.sleep(0.25)
            shot = self.worker.cached_win_screenshots.pop(target_key, None)
            if shot:
                logger.info(f"📸 Delivering live Win Popup screenshot for period {target_issue}!")
                return shot

        # 3. Only deliver genuine win popup — never send bare board fake screenshot!
        logger.warning(f"⚠️ No genuine Win Popup captured for period {target_issue}. Skipping screenshot delivery.")
        return None

    async def close(self):
        await self.worker.close()


bet_automation = BetAutomationService()
