#!/bin/sh
# simple-knn builds in place (build/, *.egg-info/) during `uv sync`. `ignore = untracked` in .gitmodules hides that
# from the superproject's `git status`, but not from editors that open the submodule as its own repo, so also list the
# outputs in the submodule's local exclude file. Idempotent; skipped when the submodule is not checked out yet.
f=$(git -C submodules/simple-knn rev-parse --git-path info/exclude 2>/dev/null) || exit 0
case "$f" in /*) ;; *) f="submodules/simple-knn/$f" ;; esac
for p in 'build/' '*.egg-info/'; do
    grep -qxF "$p" "$f" 2>/dev/null || printf '%s\n' "$p" >>"$f"
done
