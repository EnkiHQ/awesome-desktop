"""Where the pet keeps its state, log and installed characters."""
import os
from pathlib import Path


def home():
    base = os.environ.get('AWESOME_PET_HOME')
    path = Path(base).expanduser() if base else Path.home() / '.awesome-desktop'
    path.mkdir(parents=True, exist_ok=True)
    return path


def pets_dir():
    path = home() / 'pets'
    path.mkdir(parents=True, exist_ok=True)
    return path


def state_file():
    return home() / 'state.json'


def log_file():
    return home() / 'pet.log'


def builtin_dir():
    return Path(__file__).resolve().parent / 'assets'
