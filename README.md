# Nupkg Relay Daemon

A lightweight, automated Python daemon designed to monitor an SMB share with package Windows toolkits and dependencies into Chocolatey NuGet packages using `.NET SDK` (`dotnet pack`), and automatically publish them to a Nexus repository.

## Architecture & Features

* **SMB Integration:** Continuously monitors directory structures for a `READY` marker file indicating that a package version is complete and ready for deployment.

* **Discrete State History (`var/history/`):** Instead of a monolithic database or single growing log file, each processed package version maintains its own individual JSON state file (e.g., `var/history/tool-id_1.0.0.json`).

* **Real-Time Manual Rebuilds:** The daemon monitors the history folder in real time using `watchdog`. Deleting a state file (e.g., `rm var/history/my-tool_1.0.0.json`) instantly signals the daemon to rebuild and republish the package without requiring a restart!

* **Native Chocolatey Standards:** Fully supports native `chocolateyInstall.ps1` and `chocolateyUninstall.ps1` scripts.

* **Automatic Shim Suppression:** By specifying a `main_executable` in `package.yaml`, the daemon automatically generates `.ignore` files for all secondary `.exe` files, preventing Chocolatey from cluttering the system with unwanted command-line shims.

* **Catch-Up Mechanism (Initial Scan):** Automatically scans the SMB share for unprocessed `READY` markers during startup to ensure no packages are missed if the daemon restarts.

* **Dual Logging:** Logs concurrently to the console and to a persistent `nupkg-relay.log` file in the root directory.

* **Src-Layout Architecture:** Clean separation of business logic, runtime data, and entry points.

## Project Structure

```
/srv/nupkg-relay/
├── .venv/                   # Python Virtual Environment
├── var/
│   ├── build/               # Temporary dotnet working directories (auto-cleaned)
│   ├── output/              # Generated .nupkg artifacts prior to publishing
│   └── history/             # Discrete JSON state files per package/version
├── src/
│   ├── __init__.py
│   ├── builder.py           # Core package builder & .csproj generator
│   ├── logger.py            # Dual console/file logger setup
│   ├── package_config.py    # YAML metadata parser
│   ├── scanner.py           # Filesystem watchdog & initial catch-up scan
│   ├── settings.py          # Path configurations & environment variables
│   └── utils.py             # Subprocess execution & XML escaper
├── run.py                   # Main application entry point
├── requirements.txt         # Project dependencies
└── nupkg-relay.log          # Persistent log file

```

## Requirements (`requirements.txt`)

```
PyYAML>=6.0
watchdog>=3.0.0

```

## Package Configuration (`package.yaml`)

Each toolkit folder on the SMB share requires a `package.yaml` file defining its metadata:

```yaml
id: "my-windows-toolkit"
title: "My Windows Toolkit"
authors: "Your Name"
description: "Automation toolkit for Windows workstations."
main_executable: "MainApp.exe" # Optional: Shims will be ignored for all other .exe files
```

Directory layout expected on the SMB share:

```
/mnt/choco-packages/
└── my-toolkit/
    ├── package.yaml
    └── versions/
        └── 1.0.0/
            ├── READY
            ├── chocolateyInstall.ps1
            ├── chocolateyUninstall.ps1
            ├── abc.bat           # Custom installation script invoked by chocolateyInstall.ps1
            ├── MainApp.exe
            ├── helper-tool.exe   # Automatically ignored by the builder
            └── Misc/             # Bundled offline dependencies
```

## Installation & Setup

### 1. Clone & Set Up Virtual Environment

```bash
cd /srv
git clone <your-repository-url> nupkg-relay
cd nupkg-relay

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure Environment Variables

The daemon requires your Nexus API key and optionally accepts custom SMB watch directories:

```bash
export NEXUS_API_KEY="your-nexus-api-key"
export NEXUS_SOURCE="http://your-nexus-ip:8080/repository/nexus/"
export CHOCO_PACKAGES_DIR="/mnt/choco-packages"
```

### 3. Run Manually (or via Screen)

```bash
python3 run.py
```

*(Or inside a screen session: `screen -S nupkg-relay python3 run.py`)*

## Production Service (`systemd`)

To run the daemon automatically as a background system service on Linux:

1. Create a systemd service file:

   ```bash
   sudo nano /etc/systemd/system/nupkg-relay.service
   ```

2. Paste the following configuration:

   ```ini
   [Unit]
   Description=Nupkg Relay
   After=network.target
   
   [Service]
   Type=simple
   User=root
   WorkingDirectory=/srv/nupkg-relay
   Environment="NEXUS_API_KEY=your-nexus-api-key"
   ExecStart=/srv/nupkg-relay/.venv/bin/python /srv/nupkg-relay/run.py
   Restart=always
   RestartSec=10
   
   [Install]
   WantedBy=multi-user.target
   ```

3. Enable and start the service:

   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable --now nupkg-relay.service
   ```

4. Check status and logs:

   ```bash
   sudo systemctl status nupkg-relay.service
   journalctl -u nupkg-relay.service -f
   ```

## Force Rebuilding a Package

Because history is tracked using independent state files inside `var/history/`, forcing the daemon to rebuild and republish an existing package version is as simple as deleting its tracking file:

```bash
rm /srv/nupkg-relay/var/history/my-windows-toolkit_1.0.0.json
```

Once removed, the watchdog immediately detects the deletion and automatically re-queues, builds, and publishes the package again.