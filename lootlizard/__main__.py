import argparse
import faulthandler
import sys
import traceback


def main():
    parser = argparse.ArgumentParser(description="On-demand PUBG second-screen map companion")
    parser.add_argument("--launch-pubg", action="store_true", help="Start PUBG via Steam alongside the companion")
    parser.add_argument("--smoke-test", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--settings-path", help=argparse.SUPPRESS)
    parser.add_argument("--smoke-report", help=argparse.SUPPRESS)
    args = parser.parse_args()
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
