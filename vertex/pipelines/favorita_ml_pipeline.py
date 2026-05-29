"""
KFP v2 pipeline: optimize → train → predict for a named pipeline in model_config.yaml.

The training container image is fixed at **compile** time (Artifact Registry URI per env).
Optional steps are included at compile time from the pipeline's ``steps`` list in YAML.

Compile:
  python -m vertex.pipelines.compile --pipeline favorita_xgboost

Submit (Vertex AI PipelineJob):
  python -m vertex.jobs.submit_pipeline --pipeline favorita_xgboost

Note: do not use ``from __future__ import annotations`` in this module — KFP mis-parses
postponed annotations (e.g. ``str``) as artifact types at compile time.
"""

from collections.abc import Sequence

from kfp import dsl


def create_favorita_ml_pipeline(
    training_image: str,
    *,
    steps: Sequence[str],
):
    """
    Build a KFP pipeline with only the steps listed in ``steps`` (subset of
    optimize, train, predict). ``training_image`` must be a literal URI at compile time.
    """

    @dsl.container_component
    def optimize_step(config_name: str, config_path: str):
        return dsl.ContainerSpec(
            image=training_image,
            command=["python", "-m", "vertex.jobs.run"],
            args=[
                "--config-path",
                config_path,
                "--config-name",
                config_name,
            ],
        )

    @dsl.container_component
    def train_step(config_name: str, config_path: str):
        return dsl.ContainerSpec(
            image=training_image,
            command=["python", "-m", "vertex.jobs.run"],
            args=[
                "--config-path",
                config_path,
                "--config-name",
                config_name,
            ],
        )

    @dsl.container_component
    def predict_step(config_name: str, config_path: str):
        return dsl.ContainerSpec(
            image=training_image,
            command=["python", "-m", "vertex.jobs.run"],
            args=[
                "--config-path",
                config_path,
                "--config-name",
                config_name,
            ],
        )

    enabled = [s for s in ("optimize", "train", "predict") if s in steps]
    if "train" not in enabled:
        raise ValueError("Pipeline must include a train step")

    @dsl.pipeline(
        name="favorita-ml-pipeline",
        description="Optimize, train, and predict for a Favorita model family (Vertex steps)",
    )
    def favorita_ml_pipeline(
        optimize_config: str,
        train_config: str,
        predict_config: str,
        config_path: str,
    ):
        previous = None
        if "optimize" in enabled:
            previous = optimize_step(
                config_name=optimize_config,
                config_path=config_path,
            )
            previous.set_display_name("optimize")
        if "train" in enabled:
            train_task = train_step(
                config_name=train_config,
                config_path=config_path,
            )
            train_task.set_display_name("train")
            if previous is not None:
                train_task.after(previous)
            previous = train_task
        if "predict" in enabled:
            pred = predict_step(
                config_name=predict_config,
                config_path=config_path,
            )
            pred.set_display_name("predict")
            if previous is not None:
                pred.after(previous)

    return favorita_ml_pipeline
