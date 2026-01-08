# ffxiv-linux-reshade

An automated installer for GPosingway and Reshade in FFXIV on Linux.

## Description

This tool automatically installs ReShade and GPosingway presets for Final Fantasy XIV on Linux. It handles the installation of ReShade, native Windows d3dcompiler DLLs, and links the GPosingway shader repository to your FFXIV installation. This project was tested on CachyOS but may work on other Linux distributions. 

## Requirements

- Python 3.x
- `git`
- `winetricks`
- Python packages: `vdf`, `xdg-base-dirs`

## Supported Platforms

The installer can automatically detect FFXIV installations from:

- **Steam**: Automatically detects game path and Wine prefix
- **XLCore/XIVLauncher-rb**: Reads configuration from `~/.xlcore/launcher.ini`
- **Manual**: Via environment variables

## Installation

1. Install required system packages:

```bash
# Arch Linux
sudo pacman -S winetricks git

# Ubuntu/Debian
sudo apt install winetricks git

# Fedora
sudo dnf install winetricks git
```

2. Install Python dependencies:

```bash
pip install -r requirements.txt
```

3. Run the installer:

```bash
python main.py
```

## Manual Configuration

If auto-detection fails, set these environment variables:

```bash
export FFXIV_PATH="/path/to/FINAL FANTASY XIV Online/game"
export WINE_PREFIX="/path/to/wine/prefix"
```

For Steam, the Wine prefix is typically:
```
/path/to/SteamLibrary/steamapps/compatdata/39210/pfx
```

## Post-Installation Setup

### For Steam Users

Add the following to your FFXIV launch options:

```
WINEDLLOVERRIDES="d3dcompiler_43=n,b;d3dcompiler_47=n,b;dxgi=n,b" %command%
```

### For XLCore/XIVLauncher Users

1. Go to the Wine tab in XIVLauncher settings
2. Set Extra WINEDLLOVERRIDES to:
   ```
   d3dcompiler_43=n,b;d3dcompiler_47=n,b
   ```
3. If using Managed Proton, use a GE-Proton version (tested on GE-Proton 10-27)

## Usage

1. Launch FFXIV
2. Press `Shift+F2` to open the ReShade menu
3. Select a preset from the dropdown at the top
4. Configure shader settings as desired

## How It Works

The installer performs the following steps:

1. Detects your FFXIV installation and Wine prefix
2. Downloads and runs the ReShade installer for Linux
3. Installs ReShade 6.5.1 with addon support (required for GPosingway compatibility)
4. Installs native Windows d3dcompiler DLLs (required for shader compilation)
5. Installs updated REST (ReshadeEffectShaderToggler) addon to prevent dark game/UI exclusion issues
6. Downloads the GPosingway shader repository (includes 587+ shaders from multiple collections)
7. Installs optional shader packages (iMMERSE and METEOR by MartysMods)
8. Copies shaders to game directory and creates symlink for presets
9. Configures ReShade settings for optimal Linux performance

## Working Directory

The installer uses `~/.local/share/ffxiv-linux-reshade` as its working directory for downloaded files and repositories.

### Backups

Before modifying existing configuration files (ReShade.ini, ReShadePreset.ini), the installer automatically creates timestamped backups in `~/.local/share/ffxiv-linux-reshade/backups/`. This allows you to restore your previous settings if needed.

## License

See LICENSE file for details.

## Credits

Initially based off of https://github.com/Kekemui/gposingway-linux

This project also uses reshade-steam-proton https://github.com/kevinlekiller/reshade-steam-proton and gposingway https://github.com/gposingway/gposingway