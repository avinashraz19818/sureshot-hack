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
    - Synchronized countdown watcher catches the 3-second 'Congratulations' popup right at 00:00 draw.
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
        1. Checks real-time draw watcher cache (captured right at 00:00).
        2. Delivers the instant winning popup screenshot.
        3. Never sends fake drawings.
        """
        target_key = str(target_issue)

        # 1. Check if the real-time draw watcher already captured the winning popup
        shot = self.worker.cached_win_screenshots.pop(target_key, None)
        if shot:
            logger.info(f"📸 Delivering instant live Win Popup screenshot for period {target_issue}!")
            return shot

        # 2. Wait up to 2.5s in case draw watcher is just finishing its 00:00 capture
        for _ in range(5):
            await asyncio.sleep(0.5)
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
