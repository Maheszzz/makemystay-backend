import os
import sys

# Try WeasyPrint with explicit lib path
os.environ['DYLD_FALLBACK_LIBRARY_PATH'] = '/opt/homebrew/lib'
try:
    from weasyprint import HTML
    print("WeasyPrint imported successfully.")
except Exception as e:
    print("WeasyPrint failed:", e)

