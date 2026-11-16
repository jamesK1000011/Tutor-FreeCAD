# SPDX-License-Identifier: LGPL-2.1-or-later
# FILES lists the add-on's files, so the Claude extension's launcher can
# fetch them as plain files instead of asking GitHub's API (60 calls an
# hour). A file added or removed without FILES following fails here:
# The repository's own CI and git files (.github/, .gitignore …) are not the
# add-on's. Regenerate it with
#   git ls-files | grep -v -E '(^|/)__pycache__/|^FILES$|^\.' | sort > FILES
import os
import subprocess
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Files(unittest.TestCase):
    def test_files_list_is_current(self):
        try:
            out = subprocess.run(["git", "ls-files"], cwd=HERE, capture_output=True, text=True, check=True).stdout
        except (OSError, subprocess.CalledProcessError):
            self.skipTest("not a git checkout")
        tracked = sorted(p for p in out.splitlines() if p != "FILES" and "__pycache__/" not in p and not p.startswith("."))
        with open(os.path.join(HERE, "FILES"), encoding="utf-8") as f:
            listed = [ln.strip() for ln in f if ln.strip() and not ln.startswith("#")]
        self.assertEqual(listed, tracked, "FILES is stale: regenerate it (see the comment at the top of this test)")


class Release(unittest.TestCase):
    """What the Addon Manager and a release need: the icon, the version
    named in the changelog, an install section naming both repositories."""

    def read(self, name):
        with open(os.path.join(HERE, name), encoding="utf-8") as f:
            return f.read()

    def test_package_icon_and_version(self):
        import re
        import xml.dom.minidom

        pkg = xml.dom.minidom.parseString(self.read("package.xml"))
        icons = [n.firstChild.data.strip() for n in pkg.getElementsByTagName("icon")]
        self.assertTrue(icons, "package.xml names no icon")
        for icon in icons:
            path = os.path.join(HERE, icon)
            self.assertTrue(os.path.isfile(path), icon)
            svg = xml.dom.minidom.parse(path).documentElement
            self.assertEqual(svg.tagName, "svg")
            self.assertNotIn("<image", self.read(icon))  # drawn, no embedded picture
        version = pkg.getElementsByTagName("version")[0].firstChild.data.strip()
        log = self.read("CHANGELOG.md")
        self.assertIn("## [Unreleased]", log)
        self.assertRegex(log, r"\n## \[" + re.escape(version) + r"\]")

    def test_readme_install_and_links(self):
        import re

        readme = self.read("README.md")
        self.assertIn("## Install", readme)
        for repo in ("https://github.com/jamesK1000011/AgentLink-FreeCAD", "https://github.com/jamesK1000011/Tutor-FreeCAD"):
            self.assertIn(repo, readme)
        for link in re.findall(r"\]\(([^)]+)\)", readme):
            self.assertRegex(link, r"^(https?://|#)", f"relative link {link}: README is read off GitHub too")


if __name__ == "__main__":
    unittest.main()
