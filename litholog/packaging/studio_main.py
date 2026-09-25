"""Frozen entry point for LithoLog Studio (used by PyInstaller)."""

import sys

if __name__ == "__main__":
    if "--check" in sys.argv:  # build pipeline, no display needed: engine + imports + exports
        from litholog.studio.smoke import check

        sys.exit(check(sys.argv[sys.argv.index("--check") + 1] if len(sys.argv) > sys.argv.index("--check") + 1
                       else "litholog_check.txt"))
    if "--smoke-test" in sys.argv:  # used by the build pipeline: open, build demo model, quit
        from litholog.studio.smoke import run

        sys.exit(run())
    from litholog.studio.app import main

    sys.exit(main())
