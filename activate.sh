#!/bin/bash
# Activate the virtual environment and drop into the shell

VENV_PATH="$( cd "$(dirname "${BASH_SOURCE[0]}")" && pwd )/.venv"

if [ ! -f "$VENV_PATH/bin/activate" ]; then
    echo "❌ Virtual environment not found at $VENV_PATH"
    echo "Creating it now..."
    python3 -m venv "$VENV_PATH"
    echo "Installing dependencies..."
    "$VENV_PATH/bin/pip" install -r requirements.txt
fi

echo "🎓 Activating virtual environment..."
source "$VENV_PATH/bin/activate"
echo "✅ Virtual environment active!"
echo ""
echo "You can now run commands like:"
echo "  python manage.py runserver"
echo "  python manage.py shell"
echo "  pip install package_name"
echo ""
echo "To deactivate later, type: deactivate"
echo ""
