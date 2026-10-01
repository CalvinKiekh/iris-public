#!/bin/sh
# The version of what is built: major.minor from VERSION, the patch counts
# the commits since VERSION last changed - 1.0.0, 1.0.1, ... - and a build
# from uncommitted changes counts as the next one. Prints "1.0.14 57":
# version, then the build number (all commits) for the bundle.
cd "$(dirname "$0")/.."
base=$(tr -d ' \n' < VERSION)
since=$(git log -1 --format=%H -- VERSION 2>/dev/null)
if [ -n "$since" ]; then patch=$(git rev-list --count "$since"..HEAD); else patch=0; fi
build=$(git rev-list --count HEAD 2>/dev/null || echo 0)
if [ -n "$(git status --porcelain 2>/dev/null)" ]; then
  patch=$((patch + 1)); build=$((build + 1))
fi
echo "$base.$patch $build"
