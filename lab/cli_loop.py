"""The Stage 1A.1 experiment loop commands: migrate, question, exp, setup, photos (spec: Commands)."""
import sys


def _paths(args):
    from lab.cli import project_dir
    from lab.records.project import ProjectPaths
    return ProjectPaths(project_dir(args.project))


def cmd_migrate(args) -> int:
    from lab.records.migrate import migrate_project
    print("\n".join(migrate_project(_paths(args))))
    return 0


def register(sub) -> None:
    s = sub.add_parser("migrate", help="move the hand-written E-001..E-004 into Stage 1A.1 records (once)")
    s.add_argument("--project", default="hex-tile")
    s.set_defaults(fn=cmd_migrate)
