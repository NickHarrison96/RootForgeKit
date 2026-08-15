# =============================================================================
# RootForgeKit — Mobile Device Spec Formatter Utility
# =============================================================================

MOBILE_LOGOS = {
    "iOS": r"""
      .--------.
     /        /|
    /        / |
   /________/  |
   |        |  |
   |  ()   |  |
   |        |  |
   |        | /
   |________|/
    """,
    
    "Android": r"""
      .--------.
     /        /|
    /        / |
   /________/  |
   |        |  |
   |   🤖   |  |
   |        |  |
   |        | /
   |________|/
    """
}

def format_device_side_by_side(ascii_art: str, specs: dict) -> str:
    """
    Pairs lines of ASCII art side-by-side with device spec lines.
    Expected spec keys: Model, OS, Serial_UDID, Connection, Battery, Status
    """
    ascii_lines = [line for line in ascii_art.strip("\n").split("\n")]
    max_logo_width = max((len(line) for line in ascii_lines), default=20) + 4

    info_lines = [
        f"<b>{specs.get('Model', 'Unknown Device')}</b>",
        "-" * 25,
        f"<b>OS:</b> {specs.get('OS', 'Unknown')}",
        f"<b>Serial/UDID:</b> {specs.get('Serial_UDID', 'Unknown')}",
        f"<b>Connection:</b> {specs.get('Connection', 'Unknown')}",
        f"<b>Battery:</b> {specs.get('Battery', 'Unknown')}",
        f"<b>Status:</b> {specs.get('Status', 'Unknown')}",
    ]

    combined_lines = []
    max_lines = max(len(ascii_lines), len(info_lines))

    for i in range(max_lines):
        logo_part = ascii_lines[i] if i < len(ascii_lines) else ""
        info_part = info_lines[i] if i < len(info_lines) else ""
        combined_lines.append(f"{logo_part.ljust(max_logo_width)}{info_part}")

    return "\n".join(combined_lines)
