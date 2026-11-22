#!/bin/bash
set -euo pipefail

version=v0.1.68
checksum=c9eccdd1942de756d746a2569d93302774ab0eff1cff314ec8118f768b3d8dc7
ios_dir=$(cd "$(dirname "$0")" && pwd)
vendor_dir="$ios_dir/Vendor"
framework="$vendor_dir/IDevice.xcframework"

if [[ -d "$framework" ]]; then
    if [[ -f "$framework/.spoofy-version" ]] && [[ $(cat "$framework/.spoofy-version") == "$version" ]]; then
        printf 'idevice %s is already installed.\n' "$version"
        exit 0
    fi
    printf 'Move the existing %s before installing %s.\n' "$framework" "$version" >&2
    exit 1
fi

mkdir -p "$vendor_dir"
staging=$(mktemp -d "$vendor_dir/.idevice.XXXXXX")
trap 'rm -rf "$staging"' EXIT

archive=${1:-"$staging/idevice.zip"}
if [[ $# -eq 0 ]]; then
    curl --fail --location --silent --show-error \
        "https://github.com/jkcoxson/idevice/releases/download/$version/idevice-xcframework-$version.zip" \
        --output "$archive"
fi

actual_checksum=$(shasum -a 256 < "$archive" | cut -d ' ' -f 1)
if [[ "$actual_checksum" != "$checksum" ]]; then
    printf 'idevice archive failed SHA-256 verification.\n' >&2
    exit 1
fi

unzip -q "$archive" \
    'swift/IDevice.xcframework/Info.plist' \
    'swift/IDevice.xcframework/ios-arm64/*' \
    'swift/IDevice.xcframework/ios-arm64_x86_64-simulator/*' \
    -d "$staging"
extracted="$staging/swift/IDevice.xcframework"
# Remove the unused Catalyst and macOS entries from the pinned release's metadata.
/usr/libexec/PlistBuddy -c 'Delete :AvailableLibraries:2' -c 'Delete :AvailableLibraries:1' "$extracted/Info.plist"
printf '%s\n' "$version" > "$extracted/.spoofy-version"
mv -n "$extracted" "$vendor_dir/"
if [[ $(cat "$framework/.spoofy-version") != "$version" ]]; then
    printf 'A different idevice version was installed concurrently.\n' >&2
    exit 1
fi
printf 'Installed idevice %s.\n' "$version"
