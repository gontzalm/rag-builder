import webbrowser
from pathlib import Path

import pandas as pd
import plotly.express as px
import typer

from .console import get_console
from .run_experiment import RESULTS_CSV

METADATA_COLS = ["agent_model", "embedding_model", "temperature", "system_prompt"]
METRIC_LABELS = {
    "faithfulness_score": "Faithfulness",
    "answer_accuracy_score": "Answer Accuracy",
}
HTML_DASHBOARD = Path("dashboard.html")

app = typer.Typer()

console = get_console()


@app.command()
def visualize_experiments() -> None:
    """Generate a Plotly dashboard to visualize experiment results"""

    if not RESULTS_CSV.exists():
        console.print(f"❌ Results CSV '{RESULTS_CSV}' not found", style="error")
        raise typer.Exit(code=1)

    console.print(f"📖 Reading results from '{RESULTS_CSV}'", style="info")
    df = pd.read_csv(RESULTS_CSV, parse_dates=["experimented_at"])  # pyright: ignore[reportUnknownMemberType]
    df = (
        df.groupby("experiment_id")  # pyright: ignore[reportUnknownMemberType]
        .agg(
            {
                "experimented_at": "first",
                "faithfulness_score": "mean",
                "answer_accuracy_score": "mean",
                **{col: "first" for col in METADATA_COLS},
            }
        )
        .reset_index()
        .sort_values("experimented_at")
        .melt(
            id_vars=["experimented_at"] + METADATA_COLS,
            value_vars=["faithfulness_score", "answer_accuracy_score"],
            var_name="metric",
            value_name="score",
        )
    )
    df["metric"] = df["metric"].map(METRIC_LABELS)

    console.print("📊 Generating Plotly dashboard", style="info")
    fig = px.line(  # pyright: ignore[reportUnknownMemberType]
        df,  # pyright: ignore[reportArgumentType]
        x="experimented_at",
        y="score",
        color="metric",
        markers=True,
        hover_data=METADATA_COLS,
        title="RAG Evaluation: Faithfulness and Accuracy Over Time",
        labels={"experimented_at": "Experiment Run Date/Time", "score": "Metric Score"},
    )
    _ = fig.update_layout(yaxis_range=[0, 1])
    fig.write_html(HTML_DASHBOARD)

    console.print(f"💾 Visualization saved to '{HTML_DASHBOARD}'", style="success")
    console.print("🌐 Opening dashboard in browser", style="info")
    _ = webbrowser.open(HTML_DASHBOARD.resolve().as_uri())
