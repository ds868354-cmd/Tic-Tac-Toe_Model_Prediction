#!/usr/bin/env python3
"""render_manifests.py -- fills in the two values only the deployer knows, so nobody edits YAML by hand (standard library only).

  python render_manifests.py --image ghcr.io/<owner>/<name>:<tag> --host model.acme.com

Writes k8s.rendered.yaml (image: set; imagePullPolicy IfNotPresent dropped for a registry image) and k8s-ingress.rendered.yaml (Ingress host + TLS host set).
The originals are never modified.  Then:  kubectl apply -f k8s.rendered.yaml  [-f k8s-ingress.rendered.yaml]
"""
import argparse
import os
import re
import sys

IMAGE_RE = re.compile(r"^(?:[a-z0-9]+(?:[._-][a-z0-9]+)*(?::[0-9]+)?/)*[a-z0-9]+(?:[._-][a-z0-9]+)*(?::[A-Za-z0-9_][A-Za-z0-9_.-]{0,127})?(?:@sha256:[a-f0-9]{64})?$")
HOST_RE = re.compile(r"^(\*\.)?[a-z0-9]([-a-z0-9]{0,61}[a-z0-9])?(\.[a-z0-9]([-a-z0-9]{0,61}[a-z0-9])?)*$")


def _read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def main():
    ap = argparse.ArgumentParser(description="Render k8s.yaml / k8s-ingress.yaml with your image and host.")
    ap.add_argument("--image", help="full image reference, e.g. ghcr.io/acme/my-model:1.0")
    ap.add_argument("--host", help="DNS name the Ingress serves, e.g. model.acme.com")
    ap.add_argument("--dir", default=os.path.dirname(os.path.abspath(__file__)), help="folder holding the manifests (default: next to this script)")
    ap.add_argument("--image-pull-secret", dest="image_pull_secret", help="name of the registry pull Secret to use (needs --image)")
    ap.add_argument("--no-pull-secret", dest="no_pull_secret", action="store_true", help="remove the imagePullSecrets block from the rendered file (public image; needs --image)")
    ap.add_argument("--production", action="store_true", help="refuse an image without a tag/digest or tagged :latest")
    a = ap.parse_args()
    if not a.image and not a.host:
        ap.error("give --image and/or --host")
    if (a.image_pull_secret or a.no_pull_secret) and not a.image:
        ap.error("--image-pull-secret / --no-pull-secret need --image")
    if a.image_pull_secret and a.no_pull_secret:
        ap.error("--image-pull-secret and --no-pull-secret cannot be combined")
    if a.image:
        if not IMAGE_RE.match(a.image) or len(a.image) > 255:
            sys.exit("--image is not a valid container image reference (lowercase repository path, optional :tag or @sha256:digest)")
        _last = a.image.rsplit("/", 1)[-1]
        _tag = None if "@sha256:" in a.image else (_last.split(":", 1)[1] if ":" in _last else None)
        if "@sha256:" not in a.image and (_tag is None or _tag == "latest"):
            if a.production:
                sys.exit("--production: the image must carry a fixed tag or an @sha256 digest, not ':latest' / no tag")
            print("WARNING: image has no tag or uses ':latest' -- pin a tag or digest for production (use --production to enforce)")
        src = os.path.join(a.dir, "k8s.yaml")
        text, n = re.subn(r"(?m)^(\s*image:\s*)\S+\s*$", lambda m: m.group(1) + a.image, _read(src))
        if n == 0:
            sys.exit("no `image:` line found in " + src)
        if "/" in a.image.split(":")[0]:
            text = re.sub(r"(?m)^\s*imagePullPolicy:\s*IfNotPresent\s*\n", "", text)     # a registry image: the default pull policy is right
        if a.no_pull_secret:
            text = re.sub(r"(?m)^[ \t]*imagePullSecrets:[ \t]*\n(?:[ \t]*- name:[^\n]*\n)+", "", text)
        elif a.image_pull_secret:
            if not re.match(r"^[a-z0-9]([-a-z0-9.]*[a-z0-9])?$", a.image_pull_secret):
                sys.exit("--image-pull-secret is not a valid Kubernetes name")
            text, _ns = re.subn(r"(?m)^([ \t]*imagePullSecrets:[ \t]*\n[ \t]*- name:[ \t]*)\S+", lambda m: m.group(1) + a.image_pull_secret, text, count=1)
            if _ns == 0:
                text = re.sub(r"(?m)^([ \t]*)containers:", lambda m: m.group(1) + "imagePullSecrets:\n" + m.group(1) + "  - name: " + a.image_pull_secret + "\n" + m.group(0), text, count=1)
        _bad = [ln for ln in text.splitlines() if "${" in ln and not ln.lstrip().startswith("#")]
        if _bad:
            sys.exit("unresolved ${...} placeholder left in the rendered manifest: " + _bad[0].strip())
        out = os.path.join(a.dir, "k8s.rendered.yaml")
        with open(out, "w", encoding="utf-8") as f:
            f.write(text)
        print("wrote", out, "-> image:", a.image)
    if a.host:
        host = a.host.strip().lower()
        if not HOST_RE.match(host) or len(host) > 253:
            sys.exit("--host is not a valid DNS name")
        src = os.path.join(a.dir, "k8s-ingress.yaml")
        text = _read(src)
        text = re.sub(r"(?m)^(\s*)- (?:hosts: \[[^\]]*\]\n\s*)?secretName:", lambda m: m.group(1) + "- hosts: [" + host + "]\n" + m.group(1) + "  secretName:", text)
        text = re.sub(r"(?m)^(\s*)- (?:host: \S+\n\s*)?http:", lambda m: m.group(1) + "- host: " + host + "\n" + m.group(1) + "  http:", text)
        out = os.path.join(a.dir, "k8s-ingress.rendered.yaml")
        with open(out, "w", encoding="utf-8") as f:
            f.write(text)
        print("wrote", out, "-> host:", host)


if __name__ == "__main__":
    main()
