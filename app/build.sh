#!/bin/sh
# Build "Local Agent 설치.app" and a .dmg from this repository. Needs the Xcode Command Line Tools; takes about a minute.
set -eu
repo=$(cd "$(dirname "$0")/.." && pwd)
out="${1:-$repo/dist}"
name="Local Agent 설치"
rm -rf "$out"; mkdir -p "$out/stage/$name.app/Contents/MacOS" "$out/stage/$name.app/Contents/Resources"
app="$out/stage/$name.app"

# The payload is the repository's runtime files with one top folder, as get.sh expects.
(cd "$repo" && tar -czf "$app/Contents/Resources/ai-api.tar.gz" -s ',^,ai-api/,' scripts bin src skills)
cp "$repo/scripts/get.sh" "$app/Contents/Resources/get.sh"
cp "$repo/app/Info.plist" "$app/Contents/Info.plist"
swiftc -O -target arm64-apple-macos13 "$repo/app/Installer.swift" "$repo/app/main.swift" -o "$app/Contents/MacOS/LocalAgentInstaller"
codesign --force --sign - "$app"

cat > "$out/stage/처음 열 때.txt" <<'TXT'
이 앱은 Apple 서명이 없어서 처음 열 때 macOS가 막습니다.
앱을 Control 키를 누른 채 클릭(우클릭) → "열기" → 다시 "열기"를 누르세요. 한 번만 하면 됩니다.
그래도 열리지 않으면: 시스템 설정 → 개인정보 보호 및 보안 → 맨 아래 "그래도 열기".
TXT
hdiutil create -quiet -volname "$name" -srcfolder "$out/stage" -ov -format UDZO "$out/LocalAgentInstaller.dmg"
echo "built: $out/LocalAgentInstaller.dmg"
