import typer

from .create_kb import app as create_kb_app
from .generate_testset import app as generate_testset_app

app = typer.Typer(no_args_is_help=True)

app.add_typer(create_kb_app)
app.add_typer(generate_testset_app)
