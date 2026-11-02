import json
import unittest

from preflight import chain, preflight


def load(p):
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


class PreflightTest(unittest.TestCase):
    def test_hr_go_with_two_approvers(self):
        r = preflight(load("examples/hr_package.json"))
        self.assertEqual(r["verdict"], "GO")
        self.assertEqual(r["approvers"], 2)

    def test_gr_no_go_all_gates(self):
        r = preflight(load("examples/gr_package.json"))
        self.assertEqual(r["verdict"], "NO-GO")
        text = " ".join(r["reasons"])
        for expected in ("blocked action", "English price format", "23:30", "green light"):
            self.assertIn(expected, text)

    def test_audit_chain_links(self):
        r = preflight(load("examples/gr_package.json"))
        for prev, cur in zip(r["audit"], r["audit"][1:]):
            self.assertEqual(cur["prev"], prev["hash"])
        self.assertEqual(r["audit"][-1]["hash"], r["head"])

    def test_audit_changes_if_result_changes(self):
        a = chain([{"x": 1}])[1]
        b = chain([{"x": 2}])[1]
        self.assertNotEqual(a, b)


if __name__ == "__main__":
    unittest.main()
