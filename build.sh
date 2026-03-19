#!/usr/bin/env bash
# Render build script — runs during deployment

set -o errexit  # exit on error

pip install -r requirements.txt

# Create instance directory for SQLite fallback
mkdir -p instance

# Run DB migrations and seed admin user
python create_admin.py

echo "✅ Build complete"
