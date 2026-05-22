"""CLI dos jobs de analytics."""
import click

from analytics.jobs import rec_effectiveness, retention, top_videos


@click.group()
def cli() -> None:
    """Jobs analiticos da plataforma VOD."""


@cli.command("top_videos")
@click.option("--days", default=30, type=int)
@click.option("--top-n", default=50, type=int)
def top_videos_cmd(days: int, top_n: int) -> None:
    top_videos.run(days=days, top_n=top_n)


@cli.command("retention")
@click.option("--cohort-days", default=7, type=int)
def retention_cmd(cohort_days: int) -> None:
    retention.run(cohort_days=cohort_days)


@cli.command("rec_effectiveness")
@click.option("--days", default=14, type=int)
def rec_eff_cmd(days: int) -> None:
    rec_effectiveness.run(days=days)


@cli.command("export_all")
def export_all() -> None:
    top_videos.run()
    retention.run()
    rec_effectiveness.run()


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
