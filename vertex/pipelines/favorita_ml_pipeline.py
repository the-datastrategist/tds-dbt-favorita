"""
KFP v2 pipeline: optimize → train → predict for a named pipeline in model_config.yaml.

The training container image is fixed at **compile** time (Artifact Registry URI per env).
Optional steps are included at compile time from the pipeline's ``steps`` list in YAML.

Each step uses the same model config name and passes ``--step`` to ``vertex.jobs.run``.

Compile:
  python -m vertex.pipelines.compile --pipeline favorita_xgboost

Submit (Vertex AI PipelineJob):
  python -m vertex.jobs.submit_pipeline --pipeline favorita_xgboost

Note: do not use ``from __future__ import annotations`` in this module — KFP mis-parses
postponed annotations (e.g. ``str``) as artifact types at compile time.
"""

from collections.abc import Sequence

from kfp import dsl


def _run_container(training_image: str, step: str):
    @dsl.container_component
    def run_step(model_config: str, config_path: str):
        return dsl.ContainerSpec(
            image=training_image,
            command=["python", "-m", "vertex.jobs.run"],
            args=[
                "--config-path",
                config_path,
                "--config-name",
                model_config,
                "--step",
                step,
            ],
        )

    return run_step


def create_favorita_ml_pipeline(
    training_image: str,
    *,
    steps: Sequence[str],
):
    """
    Build a KFP pipeline with only the steps listed in ``steps`` (subset of
    optimize, train, predict). ``training_image`` must be a literal URI at compile time.
    """

    enabled = [s for s in ("optimize", "train", "predict") if s in steps]
    if "train" not in enabled:
        raise ValueError("Pipeline must include a train step")

    step_components = {step: _run_container(training_image, step) for step in enabled}

    @dsl.pipeline(
        name="favorita-ml-pipeline",
        description="Optimize, train, and predict for a Favorita model (single YAML config)",
    )
    def favorita_ml_pipeline(
        model_config: str,
        config_path: str,
    ):
        previous = None
        for step in enabled:
            task = step_components[step](
                model_config=model_config,
                config_path=config_path,
            )
            task.set_display_name(step)
            if previous is not None:
                task.after(previous)
            previous = task

    return favorita_ml_pipeline
