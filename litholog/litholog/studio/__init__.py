"""LithoLog Studio: the desktop application (Qt + VTK)."""


def main(argv=None):
    from .app import main as _main

    return _main(argv)
