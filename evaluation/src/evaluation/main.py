import typer
from dotenv import load_dotenv

from .create_kb import app as create_kb_app
from .generate_testset import app as generate_testset_app
from .run_experiment import app as run_experiment_app
from .visualize_experiments import app as visualize_app

_ = load_dotenv()


app = typer.Typer(no_args_is_help=True)

app.add_typer(create_kb_app)
app.add_typer(generate_testset_app)
app.add_typer(run_experiment_app)
app.add_typer(visualize_app)
