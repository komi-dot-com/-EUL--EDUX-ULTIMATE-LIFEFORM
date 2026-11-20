#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
APP_SRC="$ROOT_DIR/edux-auto-solver"
DIST_DIR="$ROOT_DIR/dist"
BUILD_TMP="$(mktemp -d)"
APP_NAME="edux-auto-solver"
VERSION="0.7.0"

cleanup() {
    rm -rf "$BUILD_TMP"
}
trap cleanup EXIT

mkdir -p "$DIST_DIR"

echo "=== [1/5] Chuẩn bị mã nguồn sạch ==="
STAGE_COMMON="$BUILD_TMP/common/$APP_NAME"
mkdir -p "$STAGE_COMMON"

tar -C "$APP_SRC" \
    --exclude="chrome_profile" \
    --exclude=".venv" \
    --exclude="__pycache__" \
    --exclude="*.pyc" \
    --exclude="python_embed" \
    --exclude="design-demos" \
    --exclude="tests" \
    --exclude="data/question_cache.json" \
    --exclude="data/activity_history.json" \
    -cf - . | tar -C "$STAGE_COMMON" -xf -

mkdir -p "$STAGE_COMMON/data"
echo "$VERSION" > "$STAGE_COMMON/.version"
chmod +x "$STAGE_COMMON/run.sh" "$STAGE_COMMON/run(dành cho macbook).sh" "$STAGE_COMMON/run(dành cho macbook).command" 2>/dev/null || true

# =============================================================================
# 2. LINUX SELF-EXTRACTING INSTALLER (.run)
# =============================================================================
echo "=== [2/5] Đóng gói Linux Self-Extracting Installer (.run) ==="
LINUX_TAR="$BUILD_TMP/edux-linux.tar.gz"
tar -C "$BUILD_TMP/common" -czf "$LINUX_TAR" "$APP_NAME"

RUN_OUT="$DIST_DIR/${APP_NAME}-linux-installer.run"
cat > "$RUN_OUT" <<'EOF'
#!/usr/bin/env bash
set -e

APP_DIR="$HOME/.local/share/edux-auto-solver"
BIN_DIR="$HOME/.local/bin"
DESKTOP_DIR="$HOME/.local/share/applications"

echo "============================================================"
echo "  CAI DAT EDUX AUTO-SOLVER (LINUX)"
echo "============================================================"
echo "[*] Thu muc cai dat: $APP_DIR"

mkdir -p "$APP_DIR" "$BIN_DIR" "$DESKTOP_DIR"

ARCHIVE_LINE=$(awk '/^__ARCHIVE_BELOW__$/{print NR + 1; exit 0; }' "$0")
TMP_EXTRACT=$(mktemp -d)
tail -n+"$ARCHIVE_LINE" "$0" | tar -xz -C "$TMP_EXTRACT"

# Giu lai data va chrome_profile neu da co
if [ -d "$APP_DIR/data" ]; then
    cp -rn "$APP_DIR/data/"* "$TMP_EXTRACT/edux-auto-solver/data/" 2>/dev/null || true
fi
if [ -d "$APP_DIR/chrome_profile" ]; then
    mv "$APP_DIR/chrome_profile" "$TMP_EXTRACT/edux-auto-solver/chrome_profile"
fi

rm -rf "$APP_DIR.old"
[ -d "$APP_DIR" ] && mv "$APP_DIR" "$APP_DIR.old"
mv "$TMP_EXTRACT/edux-auto-solver" "$APP_DIR"
rm -rf "$APP_DIR.old" "$TMP_EXTRACT"

chmod +x "$APP_DIR/run.sh"

cat > "$BIN_DIR/edux-solver" <<'BIN_EOF'
#!/usr/bin/env bash
exec bash "$HOME/.local/share/edux-auto-solver/run.sh" "$@"
BIN_EOF
chmod +x "$BIN_DIR/edux-solver"

cat > "$DESKTOP_DIR/edux-auto-solver.desktop" <<DESK_EOF
[Desktop Entry]
Type=Application
Name=Edux Auto-Solver
Comment=Tu dong giai bai tap va hoc lieu EduX
Exec=$BIN_DIR/edux-solver
Terminal=true
Categories=Education;Utility;
DESK_EOF

echo "[OK] Cai dat thanh cong!"
echo "  - Chay bang lenh: $BIN_DIR/edux-solver (hoac 'edux-solver' neu ~/.local/bin da co trong PATH)"
echo "  - Hoac mo 'Edux Auto-Solver' trong Menu ung dung."
exit 0
__ARCHIVE_BELOW__
EOF
cat "$LINUX_TAR" >> "$RUN_OUT"
chmod +x "$RUN_OUT"
echo "[OK] -> $RUN_OUT"

# =============================================================================
# 3. LINUX .DEB PACKAGE (Ubuntu / Debian)
# =============================================================================
echo "=== [3/5] Đóng gói .deb (Ubuntu/Debian) ==="
LINUX_SHARED="$BUILD_TMP/linux_shared"
mkdir -p "$LINUX_SHARED"

cat > "$LINUX_SHARED/edux-solver" <<'WRAP_EOF'
#!/usr/bin/env bash
set -e
SRC_DIR="/opt/edux-auto-solver"
USER_DIR="$HOME/.local/share/edux-auto-solver"

NEED_SYNC=0
if [ ! -f "$USER_DIR/.version" ] || [ "$(cat "$USER_DIR/.version" 2>/dev/null)" != "$(cat "$SRC_DIR/.version" 2>/dev/null)" ]; then
    NEED_SYNC=1
fi

if [ "$NEED_SYNC" -eq 1 ]; then
    mkdir -p "$USER_DIR"
    cp -r "$SRC_DIR/src" "$SRC_DIR/main.py" "$SRC_DIR/bot.py" "$SRC_DIR/requirements.txt" "$SRC_DIR/README.md" "$SRC_DIR/run.sh" "$SRC_DIR/.version" "$USER_DIR/"
    mkdir -p "$USER_DIR/data"
    chmod +x "$USER_DIR/run.sh"
fi

exec bash "$USER_DIR/run.sh" "$@"
WRAP_EOF
chmod +x "$LINUX_SHARED/edux-solver"

cat > "$LINUX_SHARED/edux-auto-solver.desktop" <<'DESK_EOF'
[Desktop Entry]
Type=Application
Name=Edux Auto-Solver
Comment=Tu dong giai bai tap va hoc lieu EduX
Exec=/usr/bin/edux-solver
Terminal=true
Categories=Education;Utility;
DESK_EOF

DEB_ROOT="$BUILD_TMP/deb_pkg"
mkdir -p "$DEB_ROOT/DEBIAN" "$DEB_ROOT/opt/$APP_NAME" "$DEB_ROOT/usr/bin" "$DEB_ROOT/usr/share/applications"

cp -a "$STAGE_COMMON/." "$DEB_ROOT/opt/$APP_NAME/"
cp "$LINUX_SHARED/edux-solver" "$DEB_ROOT/usr/bin/edux-solver"
cp "$LINUX_SHARED/edux-auto-solver.desktop" "$DEB_ROOT/usr/share/applications/edux-auto-solver.desktop"

cat > "$DEB_ROOT/DEBIAN/control" <<CTRL_EOF
Package: edux-auto-solver
Version: $VERSION
Section: utils
Priority: optional
Architecture: all
Depends: bash, python3
Maintainer: Edux Auto-Solver
Description: Edux Auto-Solver - Cong cu ho tro tu dong hoc va giai bai tap EduX
CTRL_EOF

DEB_OUT="$DIST_DIR/${APP_NAME}_${VERSION}_all.deb"
dpkg-deb --build "$DEB_ROOT" "$DEB_OUT" >/dev/null
echo "[OK] -> $DEB_OUT"

# =============================================================================
# 4. LINUX .RPM PACKAGE (Fedora / RHEL)
# =============================================================================
echo "=== [4/5] Đóng gói .rpm (Fedora/RHEL) ==="
RPM_TOP="$BUILD_TMP/rpmbuild"
mkdir -p "$RPM_TOP"/{BUILD,RPMS,SOURCES,SPECS,SRPMS}

TAR_RPM_SRC="$BUILD_TMP/rpm_src"
mkdir -p "$TAR_RPM_SRC/${APP_NAME}-${VERSION}"
cp -a "$STAGE_COMMON/." "$TAR_RPM_SRC/${APP_NAME}-${VERSION}/"
cp "$LINUX_SHARED/edux-solver" "$TAR_RPM_SRC/${APP_NAME}-${VERSION}/edux-solver.bin"
cp "$LINUX_SHARED/edux-auto-solver.desktop" "$TAR_RPM_SRC/${APP_NAME}-${VERSION}/edux-auto-solver.desktop"
tar -C "$TAR_RPM_SRC" -czf "$RPM_TOP/SOURCES/${APP_NAME}-${VERSION}.tar.gz" "${APP_NAME}-${VERSION}"

cat > "$RPM_TOP/SPECS/${APP_NAME}.spec" <<SPEC_EOF
Name:           ${APP_NAME}
Version:        ${VERSION}
Release:        1%{?dist}
Summary:        Edux Auto-Solver - Cong cu ho tro tu dong hoc va giai bai tap EduX
License:        MIT
BuildArch:      noarch
Source0:        %{name}-%{version}.tar.gz
Requires:       bash, python3

%description
Cong cu ho tro tu dong giai bai tap va hoc lieu tren EduX.

%prep
%setup -q

%install
mkdir -p %{buildroot}/opt/${APP_NAME}
mkdir -p %{buildroot}/usr/bin
mkdir -p %{buildroot}/usr/share/applications
cp -a src main.py bot.py requirements.txt README.md run.sh .version %{buildroot}/opt/${APP_NAME}/
install -m 0755 edux-solver.bin %{buildroot}/usr/bin/edux-solver
install -m 0644 edux-auto-solver.desktop %{buildroot}/usr/share/applications/edux-auto-solver.desktop

%files
/opt/${APP_NAME}
/usr/bin/edux-solver
/usr/share/applications/edux-auto-solver.desktop
SPEC_EOF

rpmbuild --define "_topdir $RPM_TOP" -bb "$RPM_TOP/SPECS/${APP_NAME}.spec" >/dev/null
RPM_BUILT=$(find "$RPM_TOP/RPMS" -name "*.rpm" | head -n 1)
cp "$RPM_BUILT" "$DIST_DIR/"
echo "[OK] -> $DIST_DIR/$(basename "$RPM_BUILT")"

# =============================================================================
# 5. WINDOWS & MACOS PACKAGES (.zip)
# =============================================================================
echo "=== [5/5] Đóng gói Windows (.zip) & macOS (.zip) ==="

# --- Windows ---
WIN_STAGE="$BUILD_TMP/win_stage"
mkdir -p "$WIN_STAGE/EduxAutoSolver"
cp -a "$STAGE_COMMON/." "$WIN_STAGE/EduxAutoSolver/"
if [ -d "$APP_SRC/python_embed" ]; then
    cp -a "$APP_SRC/python_embed" "$WIN_STAGE/EduxAutoSolver/python_embed"
fi

cat > "$WIN_STAGE/EduxAutoSolver/install_windows.bat" <<'WIN_BAT'
@echo off
chcp 65001 >nul
set "SRC=%~dp0"
if "%SRC:~-1%"=="\" set "SRC=%SRC:~0,-1%"
set "DEST=%LOCALAPPDATA%\EduxAutoSolver"

echo ============================================================
echo   CAI DAT EDUX AUTO-SOLVER TREN WINDOWS
echo ============================================================
echo [*] Dang cai dat vao: %DEST%
if not exist "%DEST%" mkdir "%DEST%"
robocopy "%SRC%" "%DEST%" /E /XD chrome_profile /NFL /NDL /NJH /NJS >nul

echo [*] Dang tao shortcut tren Desktop...
powershell -NoProfile -Command "$s=(New-Object -COM WScript.Shell).CreateShortcut('%USERPROFILE%\Desktop\Edux Auto-Solver.lnk');$s.TargetPath='%DEST%\run.bat';$s.WorkingDirectory='%DEST%';$s.Save()"

echo [OK] Cai dat hoan tat! Ban co the mo 'Edux Auto-Solver' ngay tren Desktop.
pause
WIN_BAT

WIN_OUT="$DIST_DIR/${APP_NAME}-windows.zip"
rm -f "$WIN_OUT"
(cd "$WIN_STAGE" && zip -qr "$WIN_OUT" "EduxAutoSolver")
echo "[OK] -> $WIN_OUT"

# --- macOS ---
MAC_STAGE="$BUILD_TMP/mac_stage"
mkdir -p "$MAC_STAGE/EduxAutoSolver/Edux Auto-Solver.app/Contents/MacOS"
mkdir -p "$MAC_STAGE/EduxAutoSolver/Edux Auto-Solver.app/Contents/Resources/app"
cp -a "$STAGE_COMMON/." "$MAC_STAGE/EduxAutoSolver/Edux Auto-Solver.app/Contents/Resources/app/"

cat > "$MAC_STAGE/EduxAutoSolver/Edux Auto-Solver.app/Contents/Info.plist" <<'PLIST_EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>EduxAutoSolver</string>
    <key>CFBundleIdentifier</key>
    <string>vn.edu.cmcu.eduxautosolver</string>
    <key>CFBundleName</key>
    <string>Edux Auto-Solver</string>
    <key>CFBundleVersion</key>
    <string>0.7.0</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
</dict>
</plist>
PLIST_EOF

cat > "$MAC_STAGE/EduxAutoSolver/Edux Auto-Solver.app/Contents/MacOS/EduxAutoSolver" <<'MAC_EXEC'
#!/usr/bin/env bash
TARGET="$HOME/.local/share/edux-auto-solver/run(dành cho macbook).sh"
if [ ! -f "$TARGET" ]; then
    APP_DIR="$(cd "$(dirname "$0")/../Resources/app" && pwd)"
    mkdir -p "$HOME/.local/share/edux-auto-solver"
    cp -R "$APP_DIR/." "$HOME/.local/share/edux-auto-solver/"
fi
osascript -e 'tell application "Terminal" to do script "bash \"$HOME/.local/share/edux-auto-solver/run(dành cho macbook).sh\""'
osascript -e 'tell application "Terminal" to activate'
MAC_EXEC
chmod +x "$MAC_STAGE/EduxAutoSolver/Edux Auto-Solver.app/Contents/MacOS/EduxAutoSolver"

cat > "$MAC_STAGE/EduxAutoSolver/Install_macOS.command" <<'MAC_INST'
#!/usr/bin/env bash
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
DEST="$HOME/.local/share/edux-auto-solver"

echo "============================================================"
echo "  CAI DAT EDUX AUTO-SOLVER TREN MACOS"
echo "============================================================"
mkdir -p "$DEST"
cp -R "$DIR/Edux Auto-Solver.app/Contents/Resources/app/." "$DEST/"
chmod +x "$DEST/run(dành cho macbook).sh" "$DEST/run(dành cho macbook).command"

cp -R "$DIR/Edux Auto-Solver.app" "/Applications/Edux Auto-Solver.app" 2>/dev/null || cp -R "$DIR/Edux Auto-Solver.app" "$HOME/Applications/Edux Auto-Solver.app"
xattr -cr "/Applications/Edux Auto-Solver.app" 2>/dev/null || true
xattr -cr "$DEST" 2>/dev/null || true

echo "[OK] Cai dat hoan tat! Mo 'Edux Auto-Solver' trong Applications hoac Launchpad."
read -p "Nhan Enter de dong..."
MAC_INST
chmod +x "$MAC_STAGE/EduxAutoSolver/Install_macOS.command"

MAC_OUT="$DIST_DIR/${APP_NAME}-macos.zip"
rm -f "$MAC_OUT"
(cd "$MAC_STAGE" && zip -qr "$MAC_OUT" "EduxAutoSolver")
echo "[OK] -> $MAC_OUT"

echo ""
echo "=== HOAN TAT DONG GOI ==="
ls -lh "$DIST_DIR"
