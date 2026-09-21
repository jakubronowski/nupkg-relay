import shutil
from pathlib import Path

from src import settings
from src.logger import logger
from src.utils import run_command, xml_escape
from src.package_config import PackageConfig

class PackageBuilder:
    def __init__(self, package_dir: Path, version: str):
        self.package_dir = package_dir.resolve()
        self.version = version
        
        config_path = self.package_dir / "package.yaml"
        self.config = PackageConfig.from_yaml(config_path)
        
        self.version_dir = self.package_dir / "versions" / self.version
        self.work_dir = settings.BUILD_DIR / f"{self.config.id}-{self.version}"
        self.tools_dir = self.work_dir / "tools"

    def build(self) -> Path:
        logger.info("=" * 60)
        logger.info("Building package: %s v%s (ID: %s)", self.config.id, self.version, self.config.id)
        logger.info("=" * 60)

        try:
            self._validate_source()
            self._prepare_workspace()
            self._copy_package_files()
            
            project_file = self._generate_csproj()
            package_file = self._pack(project_file)
            self._log_summary(package_file)
            
            return package_file
        finally:
            if self.work_dir.exists():
                shutil.rmtree(self.work_dir, ignore_errors=True)

    def publish(self, package_file: Path):
        if not settings.NEXUS_API_KEY:
            raise RuntimeError("NEXUS_API_KEY environment variable is not set.")

        logger.info("Publishing package to Nexus...")
        logger.info("Source:  %s", settings.NEXUS_SOURCE)
        logger.info("Package: %s", package_file.name)

        command = [
            "dotnet", "nuget", "push", str(package_file),
            "--source", settings.NEXUS_SOURCE,
            "--api-key", settings.NEXUS_API_KEY,
        ]

        run_command(command, timeout=1200)
        logger.info("Package published successfully to Nexus.")

    def _validate_source(self):
        if not self.version_dir.is_dir():
            raise FileNotFoundError(f"Version directory does not exist: {self.version_dir}")

        ready_file = self.version_dir / "READY"
        if not ready_file.is_file():
            raise RuntimeError(f"Version {self.version} is missing the READY file.")
        
        logger.info("READY marker found. Validation successful.")

    def _prepare_workspace(self):
        if self.work_dir.exists():
            shutil.rmtree(self.work_dir, ignore_errors=True)

        self.tools_dir.mkdir(parents=True, exist_ok=True)
        settings.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    def _copy_package_files(self):
        logger.info("Copying package files from source into tools/ directory:")
        files_copied = 0

        for item in self.version_dir.iterdir():
            if item.name == "READY":
                continue

            destination = self.tools_dir / item.name
            if item.is_dir():
                shutil.copytree(item, destination, dirs_exist_ok=True)
                logger.info("  Copied directory: %s/", item.name)
            else:
                shutil.copy2(item, destination)
                logger.info("  Copied file: %s", item.name)
            files_copied += 1

        if files_copied == 0:
            raise RuntimeError(f"No files found to copy in {self.version_dir}")

        # Verify the presence of the native Chocolatey installation script
        install_script = self.tools_dir / "chocolateyInstall.ps1"
        if not install_script.is_file():
            logger.warning("Warning: 'chocolateyInstall.ps1' was not found in the version folder!")

        # Automatically create .ignore files for secondary executable files
        if self.config.main_executable:
            main_exe_lower = self.config.main_executable.lower()
            for exe_file in self.tools_dir.rglob("*.exe"):
                if exe_file.name.lower() != main_exe_lower:
                    ignore_file = exe_file.with_suffix(exe_file.suffix + ".ignore")
                    if not ignore_file.exists():
                        ignore_file.touch()
                        logger.info("  Auto-ignored secondary executable shim: %s", exe_file.name)

    def _generate_csproj(self) -> Path:
        project_content = f"""<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFramework>net8.0</TargetFramework>
    <PackageId>{xml_escape(self.config.id)}</PackageId>
    <Version>{xml_escape(self.version)}</Version>
    <Title>{xml_escape(self.config.title)}</Title>
    <Authors>{xml_escape(self.config.authors)}</Authors>
    <Description>{xml_escape(self.config.description)}</Description>
    <IncludeBuildOutput>false</IncludeBuildOutput>
    <SuppressDependenciesWhenPacking>true</SuppressDependenciesWhenPacking>
    <NoDefaultExcludes>true</NoDefaultExcludes>
    
    <!-- Fix for CHCU0002 warning in Chocolatey CLI -->
    <PublishRepositoryUrl>false</PublishRepositoryUrl>
    <EmbedUntrackedSources>false</EmbedUntrackedSources>
    <IncludeSourceRevisionInInformationalVersion>false</IncludeSourceRevisionInInformationalVersion>
  </PropertyGroup>
  <ItemGroup>
    <None Include="tools/**/*" Pack="true" PackagePath="tools/" />
  </ItemGroup>
</Project>"""
        
        project_file = self.work_dir / "package.csproj"
        project_file.write_text(project_content, encoding="utf-8")
        logger.info("Generated project file: %s", project_file.name)
        return project_file

    def _pack(self, project_file: Path) -> Path:
        logger.info("Building NuGet package using 'dotnet pack'...")
        
        for old_pkg in settings.OUTPUT_DIR.glob(f"{self.config.id}.*.nupkg"):
            try:
                old_pkg.unlink()
            except Exception:
                pass

        command = [
            "dotnet", "pack", str(project_file),
            "--configuration", "Release",
            "--output", str(settings.OUTPUT_DIR),
            "--nologo"
        ]

        run_command(command, cwd=project_file.parent, timeout=1200)

        candidates = list(settings.OUTPUT_DIR.glob(f"{self.config.id}.*.nupkg"))
        if not candidates:
            raise RuntimeError(f"dotnet pack completed successfully, but no .nupkg was found in {settings.OUTPUT_DIR}!")

        candidates.sort(key=lambda f: f.stat().st_mtime, reverse=True)
        return candidates[0]

    def _log_summary(self, package_file: Path):
        logger.info("Package built successfully!")
        logger.info("ID:      %s", self.config.id)
        logger.info("Version: %s", self.version)
        logger.info("Size:    %d bytes", package_file.stat().st_size)
        logger.info("File:    %s", package_file)