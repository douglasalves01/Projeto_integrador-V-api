"""Retention por cohort — % de usuarios ainda ativos N dias apos criar conta."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
from sqlalchemy import text

from analytics.config import settings
from analytics.db import get_session


def run(cohort_days: int = 7, windows: list[int] | None = None) -> Path:
    windows = windows or [1, 7, 14, 30]
    sql = text("""
        WITH cohort AS (
          SELECT id AS user_id,
                 date_trunc('week', created_at) AS cohort_week
          FROM users
        )
        SELECT c.cohort_week::date AS cohort,
               COUNT(DISTINCT c.user_id) AS users,
               COUNT(DISTINCT CASE WHEN ws.started_at - u.created_at <= INTERVAL '1 day' THEN c.user_id END) AS d1,
               COUNT(DISTINCT CASE WHEN ws.started_at - u.created_at <= INTERVAL '7 days' THEN c.user_id END) AS d7,
               COUNT(DISTINCT CASE WHEN ws.started_at - u.created_at <= INTERVAL '14 days' THEN c.user_id END) AS d14,
               COUNT(DISTINCT CASE WHEN ws.started_at - u.created_at <= INTERVAL '30 days' THEN c.user_id END) AS d30
        FROM cohort c
        JOIN users u ON u.id = c.user_id
        LEFT JOIN watch_sessions ws ON ws.user_id = c.user_id
        GROUP BY 1
        ORDER BY 1 DESC
        LIMIT 26
    """)
    with get_session() as s:
        df = pd.read_sql(sql, s.bind)

    for w in windows:
        col = f"d{w}"
        if col in df.columns and "users" in df.columns:
            df[f"d{w}_rate"] = df[col] / df["users"].clip(lower=1)

    out_dir = Path(settings.REPORTS_DIR) / "retention"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{date.today().isoformat()}.csv"
    df.to_csv(out, index=False)
    print(f"[retention] {len(df)} cohorts -> {out}")
    return out
