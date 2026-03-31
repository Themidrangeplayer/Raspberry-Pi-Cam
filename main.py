"""
main.py – Entry point for the Raspberry Pi Camera application.

Usage
-----
    python main.py [--driver {stub,gpio,i2c,spi}]

Options
-------
--driver    Motor driver backend to use.
            'stub' (default) runs without hardware – useful for development.
            'gpio' / 'i2c' / 'spi' require the corresponding hardware.
--output    Directory to save captured images (default: captures/)
--loglevel  Python logging level (DEBUG, INFO, WARNING, ERROR).
"""

from __future__ import annotations

import argparse
import logging
import sys


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Raspberry Pi Camera – advanced control application",
    )
    parser.add_argument(
        "--driver",
        choices=["stub", "gpio", "i2c", "spi"],
        default="stub",
        help="Motor driver backend (default: stub)",
    )
    parser.add_argument(
        "--output",
        default="captures",
        help="Output directory for captured images (default: captures/)",
    )
    parser.add_argument(
        "--loglevel",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity (default: INFO)",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    logging.basicConfig(
        level=getattr(logging, args.loglevel),
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt="%H:%M:%S",
    )

    # Patch output directory before importing the app
    from camera.capture import CameraManager  # noqa: PLC0415
    _orig_init = CameraManager.__init__

    def _patched_init(instance, output_dir=args.output):  # noqa: ANN001
        _orig_init(instance, output_dir=output_dir)

    CameraManager.__init__ = _patched_init  # type: ignore[method-assign]

    try:
        from ui.app import CameraApp  # noqa: PLC0415
    except ImportError as exc:
        print(f"ERROR: Could not import UI: {exc}", file=sys.stderr)
        print("Ensure all dependencies are installed:  pip install -r requirements.txt",
              file=sys.stderr)
        sys.exit(1)

    app = CameraApp(driver_type=args.driver)
    app.mainloop()


if __name__ == "__main__":
    main()
