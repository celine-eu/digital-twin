from pathlib import Path

from celine.dt.core.config import settings

# Resolved from settings so the path can be overridden via ONTOLOGY_SPECS_DIR
# env var. Defaults to "ontologies/mapper" relative to the working directory,
# which matches both the local repo layout and the Docker image (WORKDIR /app).
SPECS_DIR: Path = Path(settings.ontology_specs_dir)
