"""dss/webapps/compare_cohorts/backend.py: the routes wire DSS and Flask to the services (step 4 part 5)."""
import os
import sys
import types
import unittest
from unittest import mock

import stubs

stubs.install()

BACKEND = os.path.join(stubs.ROOT, "dss", "webapps", "compare_cohorts", "backend.py")


class FakeApp:
    def __init__(self):
        self.routes = {}

    def route(self, path, methods=("GET",)):
        def register(fn):
            self.routes[path] = fn
            return fn
        return register


def load_backend():
    flask = types.ModuleType("flask")
    flask.jsonify = lambda value: value
    flask.request = mock.MagicMock()
    app = FakeApp()
    ns = {"app": app, "__name__": "backend"}
    with mock.patch.dict(sys.modules, {"flask": flask}):
        with open(BACKEND) as fh:
            exec(compile(fh.read(), BACKEND, "exec"), ns)
    return ns, app, flask.request


class Routes(unittest.TestCase):
    def setUp(self):
        self.ns, self.app, self.request = load_backend()
        self.service = mock.MagicMock()
        self.ns["_comparisons"][:] = [self.service]
        self.ns["cohorts"] = lambda: ([{"id": 1, "name": "Anemia"}], [{"run_timestamp": "T", "id": 1, "status": "SUCCESS"},
                                                                      {"run_timestamp": "T", "id": -1, "status": "SUCCESS"}])

    def test_three_routes(self):
        self.assertEqual(sorted(self.app.routes), ["/choices", "/request", "/status"])

    def test_choices(self):
        got = self.app.routes["/choices"]()
        self.assertEqual((got["state"], got["default_comparator"], [c["id"] for c in got["comparators"]]),
                         ("ok", -1, [-1, 1]))

    def test_request_passes_the_viewer_and_the_pair(self):
        self.request.get_json.return_value = {"cohort": "1", "comparator": "-1"}
        self.request.headers = {"Cookie": "x"}
        self.service.request.return_value = {"state": "cached", "message": "Ready"}
        dk = self.ns["dataiku"]
        with mock.patch.object(dk, "api_client") as client:
            client.return_value.get_auth_info_from_browser_headers.return_value = {"authIdentifier": "ana"}
            self.assertEqual(self.app.routes["/request"](), {"state": "cached", "message": "Ready"})
            client.return_value.get_auth_info_from_browser_headers.assert_called_once_with({"Cookie": "x"})
        args = self.service.request.call_args.args
        self.assertEqual(args[:3], ("1", "-1", {"authIdentifier": "ana"}))

    def test_errors_are_sentences(self):
        self.request.args = {"cohort": "1", "comparator": "2"}
        self.service.status.side_effect = Exception("boom\n  at x")
        self.assertEqual(self.app.routes["/status"](),
                         {"state": "failed", "message": "The comparison service failed: boom at x"})


if __name__ == "__main__":
    unittest.main()
