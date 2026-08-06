import json

from django.core.management.base import BaseCommand, CommandError

from plane.operation_gateway.workload import run_gateway_workload


class Command(BaseCommand):
    help = "Run the deterministic PostgreSQL Operation Gateway concurrency workload on disposable test state."

    def add_arguments(self, parser):
        parser.add_argument("--requests", type=int, default=128)
        parser.add_argument("--workers", type=int, default=8)
        parser.add_argument("--agents", type=int, default=16)
        parser.add_argument("--json", action="store_true", dest="as_json")

    def handle(self, *args, **options):
        try:
            result = run_gateway_workload(
                requests=options["requests"],
                workers=options["workers"],
                agent_count=options["agents"],
            )
        except (RuntimeError, ValueError) as exc:
            raise CommandError(str(exc)) from exc
        if options["as_json"]:
            self.stdout.write(json.dumps(result, sort_keys=True))
        else:
            self.stdout.write(
                "gateway PostgreSQL load: "
                f"{result['requests']} requests, {result['throughputPerSecond']} req/s, "
                f"{result['throttled']} throttled, passes={result['passes']}"
            )
        if not result["passes"]:
            raise CommandError("Operation Gateway workload thresholds failed")
