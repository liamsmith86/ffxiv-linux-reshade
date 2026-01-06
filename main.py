from configparser import ConfigParser, UNNAMED_SECTION
from datetime import datetime
import os
from pathlib import Path
import shutil
import subprocess
from typing import Optional
import urllib.request
import zipfile

import vdf
from xdg_base_dirs import xdg_data_home

FFXIV_STEAM_APP_ID = 39210
WORKDIR:Path = xdg_data_home() / 'ffxiv-linux-reshade'
BACKUP_DIR:Path = WORKDIR / 'backups'

FFXIV_PATH_ENV = 'FFXIV_PATH'
WINE_PREFIX_ENV = 'WINE_PREFIX'

def backup_file(file_path: Path) -> None:
    if file_path.exists():
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_name = f"{file_path.name}.{timestamp}.backup"
        backup_path = BACKUP_DIR / backup_name
        shutil.copy2(file_path, backup_path)
        print(f"  Backed up existing {file_path.name} to {backup_path}")

class EnvInfo:
    def __init__(self):
        self.method = 'Environment'

        ffxiv_env = os.getenv(FFXIV_PATH_ENV)
        wine_env  = os.getenv(WINE_PREFIX_ENV)

        self.ffxiv_path = Path(ffxiv_env) if ffxiv_env else None
        self.wine_prefix = Path(wine_env) if wine_env else None

        self.valid = (self.ffxiv_path is not None and self.wine_prefix is not None)



class XLCoreInfo:
    def __init__(self):
        self.method = 'XLCore'
        self.ffxiv_path = None
        self.wine_prefix = None
        self.proton_prefix = None  # XLCore uses separate prefix for Managed Proton
        self.valid = False
        try:
            xlcore_path = Path.home() / '.xlcore'
            launcher_ini_path = xlcore_path / 'launcher.ini'
            launcher_config = ConfigParser(allow_unnamed_section=True, strict=False)
            launcher_config.read(launcher_ini_path)
            # XLCore's GamePath points to base directory, need to append /game
            game_base_path = Path(launcher_config[UNNAMED_SECTION]['GamePath'])
            self.ffxiv_path = game_base_path / 'game'
            self.wine_prefix = xlcore_path / 'wineprefix'
            # XLCore uses protonprefix when "Managed Proton" is selected
            self.proton_prefix = xlcore_path / 'protonprefix'
            self.valid = True
        except KeyError:
            pass


class SteamInfo:
    def __find_ffxiv() -> Optional[Path]:
        try:
            with open(Path.home() / '.steam' / 'steam' / 'config'/ 'libraryfolders.vdf') as libvdf:
                libraries = vdf.load(libvdf)
        except (FileNotFoundError, PermissionError, KeyError):
            return None
            
        libs = []
        for lib in libraries['libraryfolders'].values():
            path = Path(lib['path'])
            if path.is_dir():
                libs.append(path)

        return next((x for x in libs if (x/'steamapps'/'appmanifest_39210.acf').exists()), None)


    def __init__(self):
        self.method = 'Steam'
        ffxiv_lib = SteamInfo.__find_ffxiv()
        if ffxiv_lib:
            steamapp_path = ffxiv_lib / 'steamapps'
            self.ffxiv_path = steamapp_path / 'common' / 'FINAL FANTASY XIV Online' / 'game'
            self.wine_prefix = steamapp_path / 'compatdata' / str(FFXIV_STEAM_APP_ID) / 'pfx'
            self.valid = True
        else:
            self.ffxiv_path = self.wine_prefix = None
            self.valid = False


def main():
    # Check pre-reqs
    if not shutil.which('git'):
        print("`git` not found on your path. Please install it and ensure it is accessible. Exiting.")
        exit(-1)
    
    if not shutil.which('winetricks'):
        print("`winetricks` not found on your path. Please install it:")
        print("  Arch: sudo pacman -S winetricks")
        print("  Ubuntu/Debian: sudo apt install winetricks")
        print("  Fedora: sudo dnf install winetricks")
        exit(-1)

    # Initialize our workspace
    WORKDIR.mkdir(exist_ok=True)
    print(f"Using {str(WORKDIR)} as our working directory.")
    print(f"Backups will be saved to {str(BACKUP_DIR)}")


    # Gather information
    infoset = [EnvInfo(), XLCoreInfo(), SteamInfo()]
    info = next((x for x in infoset if x.valid), None)
    if info is None:
        print(
            "Couldn't auto-detect your FFXIV install.\n"
            f"Set environment variables and try again, e.g.:\n"
            f'  export {FFXIV_PATH_ENV}="/path/to/FINAL FANTASY XIV Online/game"\n'
            f'  export {WINE_PREFIX_ENV}="/path/to/SteamLibrary/steamapps/compatdata/{FFXIV_STEAM_APP_ID}/pfx"\n'
            "…or install via XLCore or Steam so I can detect it automatically."
        )
        exit(1)

    print(f"Found the following FFXIV install information via {info.method}")
    print(f"\tGame location:\t{info.ffxiv_path}")
    print(f"\tWine prefix:\t{info.wine_prefix}")

    # Install ReShade using https://github.com/kevinlekiller/reshade-steam-proton

    RESHADE_INSTALLER_DIR = WORKDIR / 'reshade-installer'
    RESHADE_INSTALLER_DIR.mkdir(exist_ok=True)
    RESHADE_DATA_DIR = WORKDIR / 'reshade'

    # Pin to ReShade 6.5.1 with addon support (required for GPosingway compatibility)
    reshade_install_env = {
        'MAIN_PATH': str(RESHADE_DATA_DIR),
        'SHADER_REPOS': '',
        'RESHADE_VERSION': '6.5.1',
        'RESHADE_ADDON_SUPPORT': '1'
    }

    for k in os.environ:
        reshade_install_env[k] = os.environ[k]

    if not (RESHADE_INSTALLER_DIR / '.git').exists():
        print("Downloading ReShade installer...")
        subprocess.run(['git', 'clone', 'https://github.com/kevinlekiller/reshade-steam-proton.git', RESHADE_INSTALLER_DIR],
            capture_output=True,
            check=True)
        print("ReShade installer downloaded.")
    else:
        print("Getting updates for the ReShade installer...")
        subprocess.run(
            ['git', 'pull', '--rebase'],
            capture_output=True,
            check=True,
            cwd=RESHADE_INSTALLER_DIR
        )
        print("ReShade installer updated.")

    reshade_install_stdin = "\n".join(['i', str(info.ffxiv_path), 'y', 'n', '64', 'dxgi', 'y', ''])

    print(f"Installing ReShade {reshade_install_env['RESHADE_VERSION']} with addon support for FFXIV at {info.ffxiv_path}...")
    result = subprocess.run(
        ['./reshade-linux.sh'],
        input=reshade_install_stdin,
        text=True,
        env=reshade_install_env,
        cwd=RESHADE_INSTALLER_DIR,
        capture_output=True
    )
    
    if result.returncode != 0:
        print("ERROR: ReShade installation failed.")
        print(f"stdout: {result.stdout}")
        print(f"stderr: {result.stderr}")
        exit(-1)

    # reshade-linux.sh tells us to set WINEDLLOVERRIDES but we need native d3dcompiler DLLs
    # ReShade needs d3dcompiler DLLs to compile shaders, and Wine's versions conflict with vkd3d
    
    # Download native Windows d3dcompiler_47.dll using winetricks (gets it from Microsoft)
    d3dcompiler_47 = info.ffxiv_path / 'd3dcompiler_47.dll'
    d3dcompiler_43 = info.ffxiv_path / 'd3dcompiler_43.dll'
    sys32 = info.wine_prefix / 'drive_c' / 'windows' / 'system32'
    sys32_d3d47 = sys32 / 'd3dcompiler_47.dll'
    
    # Check if we need to download - verify file is a real DLL (>1MB)
    need_download = not d3dcompiler_47.exists() or d3dcompiler_47.stat().st_size < 1_000_000
    
    if need_download:
        print("Downloading native Windows d3dcompiler_47.dll via winetricks...")
        
        # Use winetricks to download d3dcompiler_47 (this gets the real Microsoft DLL)
        winetricks_env = os.environ.copy()
        winetricks_env['WINEPREFIX'] = str(info.wine_prefix)
        
        subprocess.run(
            ['winetricks', '--unattended', 'd3dcompiler_47'],
            env=winetricks_env,
            capture_output=True,
            text=True
        )
        
        # winetricks caches the DLL, copy it to game directory
        winetricks_cache = Path.home() / '.cache' / 'winetricks' / 'd3dcompiler_47' / 'd3dcompiler_47.dll'
        
        if winetricks_cache.exists() and winetricks_cache.stat().st_size > 1_000_000:
            shutil.copy(winetricks_cache, d3dcompiler_47)
            print("d3dcompiler_47.dll downloaded and installed.")
        elif sys32_d3d47.exists() and sys32_d3d47.stat().st_size > 1_000_000:
            # winetricks may have installed directly to prefix
            shutil.copy(sys32_d3d47, d3dcompiler_47)
            print("d3dcompiler_47.dll installed from Wine prefix.")
        else:
            print("ERROR: Failed to download d3dcompiler_47.dll via winetricks.")
            print("Try manually: winetricks d3dcompiler_47")
            exit(-1)
    
    # ReShade/Wine sometimes tries to load d3dcompiler_43.dll instead, so copy it
    if not d3dcompiler_43.exists() or d3dcompiler_43.stat().st_size < 1_000_000:
        print("Creating d3dcompiler_43.dll (copy of 47) for compatibility...")
        shutil.copy(d3dcompiler_47, d3dcompiler_43)
        print("d3dcompiler DLLs placed in game directory.")
    
    # Copy d3dcompiler DLLs to Wine system32 so ReShade can load them via LoadLibrary
    print("Copying d3dcompiler DLLs to Wine system32 for ReShade...")
    shutil.copy(d3dcompiler_47, sys32 / 'd3dcompiler_47.dll')
    shutil.copy(d3dcompiler_47, sys32 / 'd3dcompiler_43.dll')
    print("d3dcompiler DLLs installed to Wine prefix.")
    
    # For XLCore with Managed Proton, also install to protonprefix (separate from wineprefix)
    if hasattr(info, 'proton_prefix') and info.proton_prefix and info.proton_prefix.exists():
        proton_sys32 = info.proton_prefix / 'drive_c' / 'windows' / 'system32'
        if proton_sys32.exists():
            print("Installing d3dcompiler DLLs to XLCore Proton prefix...")
            shutil.copy(d3dcompiler_47, proton_sys32 / 'd3dcompiler_47.dll')
            shutil.copy(d3dcompiler_47, proton_sys32 / 'd3dcompiler_43.dll')
            print("d3dcompiler DLLs installed to Proton prefix.")

    # Remove baseline shaders / ReShade config

    print("Cleaning out baseline shaders and configuration")
    reshade_dir = info.ffxiv_path / 'ReShade_shaders'
    if reshade_dir.exists():
        if reshade_dir.is_symlink() or reshade_dir.is_file():
            reshade_dir.unlink()
        else:
            shutil.rmtree(reshade_dir)
    
    # Download GPosingway shaders and presets

    GPOSINGWAY_DIR = WORKDIR / 'gposingway'
    if not (GPOSINGWAY_DIR / '.git').exists():
        print("Downloading GPosingway...")
        subprocess.run(['git', 'clone', 'https://github.com/gposingway/gposingway.git', GPOSINGWAY_DIR],
            capture_output=True,
            check=True)
        print("GPosingway downloaded.")
    else:
        print("Getting updates for GPosingway...")
        subprocess.run(
            ['git', 'pull', '--rebase'],
            capture_output=True,
            check=True,
            cwd=GPOSINGWAY_DIR
        )
        print("GPosingway updated.")

    for name in ['reshade-presets', 'reshade-shaders']:
        link   = info.ffxiv_path / name
        target = GPOSINGWAY_DIR / name

        if link.exists() or link.is_symlink():
            if link.is_symlink() or link.is_file():
                link.unlink()
            else:
                shutil.rmtree(link)

        link.symlink_to(target, target_is_directory=True)

    print("Installing GPosingway configuration files...")
    for f in ['ReShade.ini', 'ReShadePreset.ini']:
        dest_file = info.ffxiv_path / f
        backup_file(dest_file)
        shutil.copy(GPOSINGWAY_DIR / f, dest_file)
    
    # Install optional shader packages (iMMERSE and METEOR) for ipsuShade compatibility
    # Copy directly to game directory to avoid polluting the gposingway git repository
    print("Installing optional shader packages (iMMERSE and METEOR)...")
    optional_packages = [
        {
            'name': 'iMMERSE',
            'url': 'https://github.com/martymcmodding/iMMERSE/archive/refs/heads/master.zip',
            'extract_dir': 'iMMERSE-main'
        },
        {
            'name': 'METEOR',
            'url': 'https://github.com/martymcmodding/METEOR/archive/refs/heads/master.zip',
            'extract_dir': 'METEOR-main'
        }
    ]
    
    for package in optional_packages:
        package_dir = WORKDIR / package['name'].lower()
        zip_file = package_dir / f"{package['name']}.zip"
        
        if not package_dir.exists():
            package_dir.mkdir(parents=True, exist_ok=True)
            print(f"  Downloading {package['name']}...")
            
            try:
                urllib.request.urlretrieve(package['url'], zip_file)
            except Exception as e:
                print(f"  WARNING: Failed to download {package['name']}: {e}, skipping...")
                continue
            
            # Extract the zip file
            try:
                with zipfile.ZipFile(zip_file, 'r') as zip_ref:
                    zip_ref.extractall(package_dir)
                print(f"  {package['name']} downloaded and extracted.")
            except Exception as e:
                print(f"  WARNING: Failed to extract {package['name']}: {e}")
                continue
        
        # Copy shaders and textures to game directory (maintain directory structure)
        extract_path = package_dir / package['extract_dir']
        shaders_src = extract_path / 'Shaders'
        textures_src = extract_path / 'Textures'
        
        shaders_dest = info.ffxiv_path / 'reshade-shaders' / 'Shaders'
        textures_dest = info.ffxiv_path / 'reshade-shaders' / 'Textures'
        
        if shaders_src.exists():
            for item in shaders_src.iterdir():
                if item.is_file():
                    # Copy individual shader files
                    shutil.copy2(item, shaders_dest / item.name)
                elif item.is_dir():
                    # Copy subdirectories (like MartysMods with header files)
                    dest_subdir = shaders_dest / item.name
                    if dest_subdir.exists():
                        shutil.rmtree(dest_subdir)
                    shutil.copytree(item, dest_subdir)
        
        if textures_src.exists():
            for item in textures_src.iterdir():
                if item.is_file():
                    shutil.copy2(item, textures_dest / item.name)
                elif item.is_dir():
                    dest_subdir = textures_dest / item.name
                    if dest_subdir.exists():
                        shutil.rmtree(dest_subdir)
                    shutil.copytree(item, dest_subdir)
    
    print("Optional shader packages installed.")
    
    # Fix ReShade cache path and settings to prevent memory leaks on Linux
    print("Fixing ReShade configuration for Linux...")
    reshade_cache_dir = info.ffxiv_path / 'reshade-cache'
    reshade_cache_dir.mkdir(exist_ok=True)
    
    # Convert game path to Wine X: drive format (Wine maps / to X:)
    # /home/user/.local/share/Steam/... -> X:\.local\share\Steam\...
    game_path_str = str(info.ffxiv_path)
    home_str = str(Path.home())
    if game_path_str.startswith(home_str):
        # Remove /home/user prefix and convert to Wine X: path
        relative_to_home = game_path_str[len(home_str):]
        game_path_wine = 'X:' + relative_to_home.replace('/', '\\')
    else:
        # Fallback: just use X: + full path
        game_path_wine = 'X:' + game_path_str.replace('/', '\\')
    
    reshade_ini = info.ffxiv_path / 'ReShade.ini'
    if reshade_ini.exists():
        # Use ConfigParser for reliable INI modification
        config = ConfigParser(strict=False)
        config.optionxform = str  # Preserve case
        config.read(reshade_ini)
        
        # Ensure sections exist
        if 'GENERAL' not in config:
            config['GENERAL'] = {}
        if 'INPUT' not in config:
            config['INPUT'] = {}
        
        # Set absolute paths for shaders (required for Wine to resolve symlinks)
        config['GENERAL']['EffectSearchPaths'] = f'{game_path_wine}\\reshade-shaders\\Shaders\\**'
        config['GENERAL']['TextureSearchPaths'] = f'{game_path_wine}\\reshade-shaders\\Textures\\**'
        
        # Set absolute cache path (prevents Wine temp directory issues)
        config['GENERAL']['IntermediateCachePath'] = f'{game_path_wine}\\reshade-cache'
        
        # Performance settings to prevent memory issues
        config['GENERAL']['NoReloadOnInit'] = '1'
        config['GENERAL']['PerformanceMode'] = '1'
        
        # Set ReShade overlay hotkey to Shift+F2 (F2=113, Shift modifier=1)
        config['INPUT']['KeyOverlay'] = '113,0,1,0'
        
        with open(reshade_ini, 'w') as f:
            config.write(f)
        print("ReShade configuration updated.")

    print("All done!")
    print()
    print("=" * 80)
    print("IMPORTANT SETUP INSTRUCTIONS:")
    print("=" * 80)
    print()
    print("1. Set WINEDLLOVERRIDES for shader compilation to work:")
    
    if info.method == "Steam":
        print("   For Steam, set the following launch options:")
        print('   WINEDLLOVERRIDES="d3dcompiler_43=n,b;d3dcompiler_47=n,b;dxgi=n,b" %command%')
    elif info.method == "XLCore":
        print("   For XIVLauncher-rb/XLCore, go to Wine tab and set Extra WINEDLLOVERRIDES to:")
        print('   d3dcompiler_43=n,b;d3dcompiler_47=n,b')
        print()
        print("   NOTE: If using 'Managed Proton', make sure to use a GE-Proton version")
        print("   (not Wine-XIV-Staging)")
    else:
        print("   Set the following environment variable when launching FFXIV:")
        print('   WINEDLLOVERRIDES="d3dcompiler_43=n,b;d3dcompiler_47=n,b;dxgi=n,b"')
    
    print()
    print("2. Using GPosingway:")
    print("   - Press Shift+F2 in-game to open ReShade menu")
    print("   - Select a preset from the dropdown at the top")
    print("   - Some shaders (AS_StageFX) may show compile errors - these are expected due to incompatibility with newer ReShade version")
    print("   - Core presets like ipsuShade should work fine")
    print()
    print("=" * 80)

if __name__ == '__main__':
    main()
