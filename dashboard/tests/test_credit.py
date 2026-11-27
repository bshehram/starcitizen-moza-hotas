"""Credit (PLAN §5, §13): every file holding code copied from another project is listed in
dashboard/THIRD_PARTY_NOTICES with its copyright line and the license text, and every file
listed there really carries that copyright line."""
import re
import unittest

import scdash_testlib as lib

MARK = "From " + "CSR"                          # built here so this file does not match itself
COPYRIGHT = "Copyright (c) 2026 archelium (support@archelium.com)"
NOTICES = lib.DASHBOARD / "THIRD_PARTY_NOTICES"


def python_files():
    for p in lib.DASHBOARD.rglob("*.py"):
        rel = p.relative_to(lib.DASHBOARD)
        if rel.parts[0] in ("data",) or "__pycache__" in rel.parts or p.name == "test_credit.py":
            continue
        yield p


class CreditTest(unittest.TestCase):
    def setUp(self):
        self.text = NOTICES.read_text(encoding="utf-8")

    def test_license_text_is_there(self):
        self.assertIn("MIT License", self.text)
        self.assertIn(COPYRIGHT, self.text)
        self.assertIn("Permission is hereby granted, free of charge, to any person obtaining a copy", self.text)
        self.assertIn('THE SOFTWARE IS PROVIDED "AS IS"', self.text)

    def test_every_file_with_copied_code_is_listed(self):
        marked = {"dashboard/" + p.relative_to(lib.DASHBOARD).as_posix()
                  for p in python_files() if MARK in p.read_text(encoding="utf-8")}
        self.assertTrue(marked, "no marked file found: the scan is broken")
        listed = set(re.findall(r"^- (dashboard/\S+)$", self.text, re.M))
        self.assertEqual(marked, listed)

    def test_every_listed_file_carries_the_copyright_line(self):
        for rel in re.findall(r"^- dashboard/(\S+)$", self.text, re.M):
            path = lib.DASHBOARD / rel
            self.assertTrue(path.exists(), rel)
            self.assertIn(COPYRIGHT, path.read_text(encoding="utf-8"), rel)

    def test_no_unlisted_file_names_the_project(self):
        listed = {lib.DASHBOARD.parent / r for r in re.findall(r"^- (dashboard/\S+)$", self.text, re.M)}
        for p in python_files():
            if p not in listed and p.name != "PLAN.md":
                self.assertNotIn("archelium", p.read_text(encoding="utf-8"), p.name)


if __name__ == "__main__":
    unittest.main()
