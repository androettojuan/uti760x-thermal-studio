"""Punto de entrada para PyInstaller. No puede llamarse thermal_studio.py: taparía al paquete."""
import sys

from thermal_studio.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
