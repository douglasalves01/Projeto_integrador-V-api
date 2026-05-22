"""Top videos por completion + horas assistidas nos ultimos N dias."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
from sqlalchemy import text

from analytics.config import settings
from analytics.db import get_session


def run(days: int = 30, top_n: int = 50) -> Path:
    since = datetime.utcnow() - timedelta(days=days)
    sql = text("""
        SELECT
          v.id::text          AS video_id,
          v.title             AS title,
          COUNT(ws.id)        AS sessions,
          SUM(ws.watch_time_seconds)/3600.0 AS hours_watched,
          AVG(ws.percentage_watched)::float AS avg_completion,
          SUM(CASE WHEN ws.completed THEN 1 ELSE 0 END) AS completions,
          SUM(CASE WHEN ws.abandoned THEN 1 ELSE 0 END) AS abandons
        FROM watch_sessions ws
        JOIN videos v ON v.id = ws.video_id
        WHERE ws.started_at >= :since
        GROUP BY v.id, v.title
        ORDER BY hours_watched DESC NULLS LAST
        LIMIT :top_n
    """)
    with get_session() as s:
        df = pd.read_sql(sql, s.bind, params={"since": since, "top_n": top_n})

    out_dir = Path(settings.REPORTS_DIR) / "top_videos"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{date.today().isoformat()}.csv"
    df.to_csv(out, index=False)
    print(f"[top_videos] {len(df)} linhas -> {out}")
    return out
