"""Standalone no-pickle/joblib guardrail -- self-contained copy of
verify_no_pickle_joblib() from the training pipeline, so CI doesn't need that module installed.
Usage: python bundler_check.py <directory>
"""
import os, re, sys

_BANNED_EXTENSIONS = {".pkl", ".pickle", ".joblib"}
_PICKLE_IMPORT_PATTERN = re.compile(
    r"^\s*(import\s+(pickle|joblib)\b|from\s+(pickle|joblib)\s+import)", re.MULTILINE)


def verify_no_pickle_joblib(directory):
    violations = []
    for root, _dirs, files in os.walk(directory):
        for fname in files:
            fpath = os.path.join(root, fname)
            ext = os.path.splitext(fname)[1].lower()
            if ext in _BANNED_EXTENSIONS:
                violations.append("Banned artifact file: " + fpath)
                continue
            if ext == ".py":
                try:
                    with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                except OSError:
                    continue
                if _PICKLE_IMPORT_PATTERN.search(content):
                    violations.append("Banned import (pickle/joblib) in: " + fpath)
    if violations:
        raise SystemExit("Pickle/joblib guardrail failed:\n  " + "\n  ".join(violations))
    print("'" + directory + "' is clean (no pickle/joblib found).")


# [fixed-156 E2] file-size guard: WARN from 50 MB, FAIL from 100 MB (GitHub rejects files above 100 MB) unless the file is tracked by Git LFS.
def _f156_lfs_patterns(root):
    pats = []
    try:
        for line in open(os.path.join(root, ".gitattributes"), encoding="utf-8"):
            parts = line.split()
            if len(parts) >= 2 and any(p == "filter=lfs" for p in parts[1:]):
                pats.append(parts[0])
    except OSError:
        pass
    return pats


def _f156_size_check(root):
    import fnmatch
    warn_mb = float(os.environ.get("BUNDLER_WARN_MB", "50"))
    fail_mb = float(os.environ.get("BUNDLER_FAIL_MB", "100"))
    lfs = _f156_lfs_patterns(root)
    failures = []
    for dp, dn, fns in os.walk(root):
        dn[:] = [d for d in dn if d not in (".git", "node_modules", "__pycache__")]
        for fn in fns:
            p = os.path.join(dp, fn)
            rel = os.path.relpath(p, root).replace(os.sep, "/")
            try:
                mb = os.path.getsize(p) / (1024.0 * 1024.0)
            except OSError:
                continue
            tracked = any(fnmatch.fnmatch(rel, pat) or fnmatch.fnmatch(fn, pat) for pat in lfs)
            if mb >= fail_mb and not tracked:
                failures.append("FAIL: %s is %.0f MB (>= %.0f MB): GitHub rejects it. Use Git LFS (.gitattributes) or download it at build time." % (rel, mb, fail_mb))
            elif mb >= warn_mb:
                print("WARNING: %s is %.0f MB (>= %.0f MB)%s" % (rel, mb, warn_mb, " - tracked by Git LFS" if tracked else ": move it to Git LFS or download it at build time"))
    return failures


if __name__ == "__main__":
    _dir156 = sys.argv[1] if len(sys.argv) > 1 else "."
    verify_no_pickle_joblib(_dir156)
    _fails156 = _f156_size_check(_dir156)
    if _fails156:
        raise SystemExit("\n".join(_fails156))
