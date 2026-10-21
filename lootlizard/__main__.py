import argparse
import faulthandler
import sys
import traceback


def main():
    # Installer/update lifecycle hooks must finish before argument parsing or Tk.
    from .app_updates import bootstrap
    bootstrap()
    parser = argparse.ArgumentParser(description="On-demand PUBG second-screen map companion")
    from . import __version__
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--launch-pubg", action="store_true", help="Start PUBG via Steam alongside the companion")
    parser.add_argument("--smoke-test", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--settings-path", help=argparse.SUPPRESS)
    parser.add_argument("--smoke-report", help=argparse.SUPPRESS)
    parser.add_argument("--update-probe", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--report", help=argparse.SUPPRESS)
    parser.add_argument("--ci-update-source", help=argparse.SUPPRESS)
    parser.add_argument("--download", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--apply-on-exit", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.update_probe:
        from .installer_probe import run_probe
        run_probe(args)
        return
    if args.ci_update_source or args.download or args.apply_on_exit or args.report:
        parser.error("Installer test arguments require --update-probe.")
    def execute():
        from .app import run
        run(launch_game=args.launch_pubg, smoke_test=args.smoke_test, settings_path=args.settings_path)
    if args.smoke_report and args.smoke_test:
        with open(args.smoke_report, "w", encoding="utf-8") as report:
            previous_stdout, previous_stderr = sys.stdout, sys.stderr
            sys.stdout = sys.stderr = report
            faulthandler.enable(file=report)
            faulthandler.dump_traceback_later(18, file=report)
            try:
                execute()
            except Exception:
                traceback.print_exc(file=report)
                raise SystemExit(1)
            finally:
                faulthandler.cancel_dump_traceback_later()
                faulthandler.disable()
                sys.stdout, sys.stderr = previous_stdout, previous_stderr
    else:
        execute()


if __name__ == "__main__":
    main()
