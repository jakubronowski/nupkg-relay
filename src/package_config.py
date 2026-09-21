import yaml
from pathlib import Path
from pydantic import BaseModel, Field, ValidationError
from .logger import logger

class PackageConfig(BaseModel):
    id: str = Field(..., description="Unique identifier for the Chocolatey package")
    title: str = Field(..., description="Display title")
    authors: str = Field(..., description="Package authors")
    description: str = Field(..., description="Package description")
    main_executable: str | None = Field(None, description="Main executable file for shims (optional)")

    @classmethod
    def from_yaml(cls, yaml_path: Path) -> "PackageConfig":
        if not yaml_path.is_file():
            raise FileNotFoundError(f"Configuration file not found: {yaml_path}")
        
        try:
            content = yaml_path.read_text(encoding="utf-8")
            data = yaml.safe_load(content)
            return cls(**data)
        except ValidationError as e:
            logger.error("Validation error in %s: %s", yaml_path, e)
            raise
        except Exception as e:
            logger.error("Failed to parse YAML file %s: %s", yaml_path, e)
            raise