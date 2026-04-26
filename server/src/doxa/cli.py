from pathlib import Path
import time

import click

from engine.DoxaEngine import DoxaEngine


@click.group()
def main():
    """Doxa CLI entry point."""


@main.command()
@click.argument("scenario_path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--poll-interval", default=0.5, show_default=True, type=float, help="Status polling interval in seconds.")
@click.option("--quiet", is_flag=True, help="Disable verbose simulation logs.")
@click.option("--summary", is_flag=True, help="Generate a summary of the simulation.")
def run(scenario_path: Path, poll_interval: float, quiet: bool, summary: bool):
    """Run a Doxa YAML scenario until completion."""
    yaml_text = scenario_path.read_text(encoding="utf-8")
    engine = DoxaEngine(yaml_text, log_verbose=not quiet)

    click.echo(f"Running scenario: {scenario_path}")
    engine.start_run()

    while True:
        status = engine.get_status()
        state = status["state"]
        if state in {"completed", "errored", "idle"}:
            break
        time.sleep(poll_interval)

    if status["state"] == "errored":
        raise click.ClickException(status.get("last_error") or "Simulation failed.")

    click.echo(
        f"Simulation finished: state={status['state']}, epoch={status['epoch']}, step={status['step']}"
    )

    if summary:
        click.echo("Generating summary...")
        click.echo(engine._summary())


if __name__ == "__main__":
    main()