"""
tests/test_installer.py - Validation tests for Inno Setup installer script.
"""
from pathlib import Path


def test_installer_iss_contains_required_files():
    iss_path = Path(__file__).parent.parent / "installer" / "keraunos.iss"
    assert iss_path.exists(), "installer/keraunos.iss must exist"

    content = iss_path.read_text(encoding="utf-8")

    required_sources = [
        r'Source: "..\dist\keraunos\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs',
        r'Source: "..\assets\*"; DestDir: "{app}\assets"; Flags: ignoreversion recursesubdirs createallsubdirs',
        r'Source: "..\models\*"; DestDir: "{app}\models"; Flags: ignoreversion recursesubdirs createallsubdirs',
        r'Source: "..\keraunosICON.png"; DestDir: "{app}"; Flags: ignoreversion',
    ]

    for req in required_sources:
        assert req in content, f"Missing required file entry in installer/keraunos.iss: {req}"
