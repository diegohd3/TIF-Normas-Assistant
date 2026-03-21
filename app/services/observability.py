from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any


LOGGER_NAME = "tif_normas.assistant"


class ObservabilityService:
    """
    Structured logging for assistant pipeline traces.
    """

    def __init__(self) -> None:
        self.logger = logging.getLogger(LOGGER_NAME)

    def log_event(
        self,
        *,
        trace_id: str,
        event: str,
        payload: dict[str, Any],
    ) -> None:
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "trace_id": trace_id,
            "event": event,
            "payload": payload,
        }
        self.logger.info(json.dumps(record, ensure_ascii=False))
