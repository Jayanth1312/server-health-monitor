#!/bin/bash

# Build script for Linux releases
# This script builds the Linux binary and creates a DEB package

set -e

VERSION="${1:-0.1.0}"

echo "Building Todo App for Linux..."
echo "Version: $VERSION"

# Clean previous builds
echo ""
echo "Cleaning previous builds..."
cargo clean

# Build release binary
echo ""
echo "Building release binary..."
cargo build --release

echo "Build successful!"

# Strip binary to reduce size
echo ""
echo "Stripping binary..."
strip target/release/todo

# Create release directory
RELEASE_DIR="release-linux"
if [ -d "$RELEASE_DIR" ]; then
    rm -rf "$RELEASE_DIR"
fi
mkdir -p "$RELEASE_DIR"

# Copy executable
echo ""
echo "Copying executable to release directory..."
cp target/release/todo "$RELEASE_DIR/todo-linux-x64"
chmod +x "$RELEASE_DIR/todo-linux-x64"

# Create DEB package
echo ""
echo "Creating DEB package..."

# Check if cargo-deb is installed
if ! command -v cargo-deb &> /dev/null; then
    echo "cargo-deb not found. Installing cargo-deb..."
    cargo install cargo-deb
fi

# Create temporary Cargo.toml with deb metadata if not exists
if ! grep -q "\[package.metadata.deb\]" Cargo.toml; then
    echo ""
    echo "Adding DEB metadata to Cargo.toml..."
    cat >> Cargo.toml << 'EOF'

[package.metadata.deb]
maintainer = "Your Name <your.email@example.com>"
copyright = "2024, Your Name <your.email@example.com>"
license-file = ["LICENSE", "4"]
extended-description = """\
A terminal-based todo application built with Rust.
"""
depends = "$auto"
section = "utility"
priority = "optional"
assets = [
    ["target/release/todo", "usr/bin/", "755"],
]
EOF
fi

# Create LICENSE file if not exists
if [ ! -f LICENSE ]; then
    echo "Creating LICENSE file..."
    cat > LICENSE << EOF
MIT License

Copyright (c) $(date +%Y)

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
EOF
fi

# Build DEB package
cargo deb

# Find and copy the DEB package
DEB_FILE=$(find target/debian -name "*.deb" | head -n 1)
if [ -n "$DEB_FILE" ]; then
    cp "$DEB_FILE" "$RELEASE_DIR/"
    echo "DEB package created successfully!"
else
    echo "Warning: DEB package not found!"
fi

# Create tarball
echo ""
echo "Creating tarball..."
tar -czf "$RELEASE_DIR/todo-linux-x64-$VERSION.tar.gz" -C target/release todo
chmod +x "$RELEASE_DIR/todo-linux-x64-$VERSION.tar.gz"

echo ""
echo "================================"
echo "Release files created in: $RELEASE_DIR"
echo "  - todo-linux-x64 (binary)"
if [ -n "$DEB_FILE" ]; then
    echo "  - $(basename "$DEB_FILE") (deb package)"
fi
echo "  - todo-linux-x64-$VERSION.tar.gz (tarball)"
echo "================================"
echo ""
echo "To install the DEB package:"
echo "  sudo dpkg -i $RELEASE_DIR/*.deb"
echo ""
echo "To install the binary manually:"
echo "  sudo cp $RELEASE_DIR/todo-linux-x64 /usr/local/bin/todo"
echo "  sudo chmod +x /usr/local/bin/todo"
echo ""
