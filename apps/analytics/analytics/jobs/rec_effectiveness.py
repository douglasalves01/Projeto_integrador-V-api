"""Mede efetividade das recomendacoes servidas: CTR e conversao em watch_session."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
from sqlalchemy import text

from analytics.config import settings
from analytics.db import get_session


def run(days: int = 14) -> Path:
    since = datetime.utcnow() - timedelta(days=days)
    sql = text("""
        WITH recs AS (
          SELECT r.user_id, r.video_id, r.created_at, r.reason
          FROM recommendations r
          WHERE r.created_at >= :since
        ),
        watched AS (
          SELECT DISTINCT user_id, video_id
          FROM watch_sessions
          WHERE started_at >= :since
        )
        SELECT
          r.reason                                    AS strategy,
          COUNT(*)                                    AS shown,
          COUNT(w.video_id)                           AS clicked_or_watched,
          COUNT(w.video_id)::float / NULLIF(COUNT(*),0) AS conv_rate
        FROM recs r
        LEFT JOIN watched w
          ON w.user_id = r.user_id AND w.video_id = r.video_id
        GROUP BY r.reason
        ORDER BY shown DESC
    """)
    with get_session() as s:
        df = pd.read_sql(sql, s.bind, params={"since": since})

    out_dir = Path(settings.REPORTS_DIR) / "rec_effectiveness"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{date.today().isoformat()}.csv"
    df.to_csv(out, index=False)
    print(f"[rec_effectiveness] {len(df)} estrategias -> {out}")
    return out
