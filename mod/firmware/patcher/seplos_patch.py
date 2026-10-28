#!/usr/bin/env python3
"""Standalone entry point; explicitly bootstrap its sibling package under -I."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from seplos.cli import main
if __name__=='__main__':raise SystemExit(main())
