#!/usr/bin/env python3
"""Mock upgrade-responder and version.yaml download site for upgrade path tests.

POST <any path>              upgrade check: the offered releases in releases.json
GET  /<id>/version.yaml      version.yaml of a release (also version-arm64.yaml)
GET  /<id>/version.yaml?import  the same without isoChecksum, for Versions to
                             upgrade with: the ISO is then downloaded unverified

releases.json is read on every request, so edits to the ConfigMap apply once
kubelet syncs the mounted file, without a restart.
"""
import http.server
import json
import os
import re
import sys
import urllib.parse

CONFIG = os.environ.get("CONFIG", "/config/releases.json")
PORT = int(os.environ.get("PORT", "8000"))

# The syncer skips Versions without an ISO URL and checksum. The fake checksum
# would fail an upgrade's ISO download, so imports leave it out instead.
FAKE_ISO_URL = "http://iso.invalid/harvester.iso"
FAKE_CHECKSUM = "0" * 128
RESPONDER_FIELDS = ("name", "releaseDate", "minUpgradableVersion", "tags")


def log(msg):
    print(msg, file=sys.stderr, flush=True)


def load_releases():
    with open(CONFIG) as f:
        return json.load(f)["releases"]


def version_yaml(release, with_checksum):
    lines = [
        "apiVersion: harvesterhci.io/v1beta1",
        "kind: Version",
        "metadata:",
        f"  name: {release.get('id', release['name'])}",
        "  namespace: harvester-system",
    ]
    if release.get("flavor"):
        lines += ["  labels:", f"    harvesterhci.io/serverFlavor: {release['flavor']}"]
    lines.append("spec:")
    if with_checksum:
        lines.append(f"  isoChecksum: '{FAKE_CHECKSUM}'")
    lines += [
        f"  isoURL: {release.get('isoURL') or FAKE_ISO_URL}",
        f"  releaseDate: '{release['releaseDate']}'",
    ]
    return "\n".join(lines) + "\n"


class Handler(http.server.BaseHTTPRequestHandler):
    def send_body(self, body, content_type):
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        request = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        log(f"upgrade check: {request.decode(errors='replace').strip()}")
        versions = [
            {k: r[k] for k in RESPONDER_FIELDS if k in r}
            for r in load_releases()
            if r.get("offer", True)
        ]
        self.send_body(json.dumps({"versions": versions}).encode(), "application/json")

    def do_GET(self):
        url = urllib.parse.urlsplit(self.path)
        m = re.fullmatch(r"/([^/]+)/version(-arm64)?\.yaml", url.path)
        if not m:
            return self.send_error(404)
        with_checksum = "import" not in urllib.parse.parse_qs(url.query, keep_blank_values=True)
        for release in load_releases():
            if release.get("id", release["name"]) == m.group(1):
                return self.send_body(version_yaml(release, with_checksum).encode(), "application/yaml")
        self.send_error(404, f"no release {m.group(1)} in {CONFIG}")


if __name__ == "__main__":
    log(f"serving on :{PORT}")
    http.server.ThreadingHTTPServer(("", PORT), Handler).serve_forever()
