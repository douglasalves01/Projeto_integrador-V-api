# apps/analytics

Jobs analiticos que consomem o mesmo Postgres da API. Saidas (relatorios,
CSVs, graficos) ficam em `reports/`.

## Jobs disponiveis

```bash
# Cada job e um subcomando do CLI 'analytics'
python -m analytics top_videos --days 30
python -m analytics retention --cohort-days 7
python -m analytics watch_funnel
python -m analytics churn_risk
python -m analytics rec_effectiveness   # mede CTR/conversion das recs servidas
python -m analytics export_all          # roda todos os jobs e empacota
```

## Adicionar novo job

1. Cria modulo em `analytics/jobs/<nome>.py` com funcao `run(session, **opts)`.
2. Registra em `analytics/cli.py` (`@cli.command(...)`).
3. Saida deve ir para `reports/{job_name}/{YYYYMMDD}.{csv,png,json}`.

## Schedule

Os jobs sao standalone — sem cron interno. Use o agendador da infra
(GitHub Actions, Airflow, k8s CronJob) chamando o CLI.
