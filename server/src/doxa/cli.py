import click

@click.group()
def main():
    """Doxa CLI entry point."""
    pass

@main.command()
def run():
    """Run the Doxa backend engine."""
    click.echo("Doxa engine running...")

if __name__ == "__main__":
    main()