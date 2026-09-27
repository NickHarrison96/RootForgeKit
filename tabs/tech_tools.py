# =============================================================================
# RootForgeKit — Technician Tools Tab
#
# Two kinds of card, both real:
#   * app cards  — winget-installed packages. Install state comes from a single
#                   background `winget list` (see WingetIndexWorker); the action
#                   button becomes Install / Update / Launch to match.
#   * tool cards — commands from utils/command_builder, executed through
#                   TerminalConsoleWidget (off the UI thread, with the
#                   confirmation + elevation gates that class applies).
# =============================================================================

from tabs.tool_tab_base import ToolTabBase

# -- winget app catalogue: (key, glyph, name, description, winget_id) --------
APPS = [
    ("dev", "💻", "Development", True, [
        ("app_claude",    "Claude Code",     "Anthropic's terminal coding agent.",
         "Anthropic.ClaudeCode"),
        ("app_docker",    "Docker Desktop",  "Container runtime with WSL2 backend.",
         "Docker.DockerDesktop"),
        ("app_ollama",    "Ollama",          "Run local LLMs offline.",
         "Ollama.Ollama"),
        ("app_ghdesktop", "GitHub Desktop",  "GUI client for Git repositories.",
         "GitHub.GitHubDesktop"),
        ("app_git",       "Git",             "Distributed version control.",
         "Git.Git"),
        ("app_msys2",     "MSYS2",           "Unix-like shell, GCC toolchain, pacman.",
         "MSYS2.MSYS2"),
    ]),
    ("sys", "🛠️", "System Tools", False, [
        ("app_terminal",  "Windows Terminal", "Modern host for PowerShell, CMD and WSL.",
         "Microsoft.WindowsTerminal"),
        ("app_7zip",      "7-Zip",            "Archive manager with high compression.",
         "7zip.7zip"),
    ]),
    ("com", "📡", "Communication & Media", False, [
        ("app_discord",   "Discord",   "Voice, video and text chat.",
         "Discord.Discord"),
        ("app_itunes",    "iTunes",    "Apple media library and iOS device management.",
         "Apple.iTunes"),
        ("app_teamviewer","TeamViewer","Remote support and unattended access.",
         "TeamViewer.TeamViewer"),
    ]),
    ("game", "🎮", "Gaming", False, [
        ("app_steam",     "Steam", "Valve's game store and library.",
         "Valve.Steam"),
    ]),
]

# -- diagnostic / repair commands: (command_key, glyph, name, description) ---
DIAGNOSTICS = [
    ("disk_health",  "💽", "Disk Health Check",
     "Query SMART status and health of every connected drive."),
    ("network_diag", "🌐", "Network Diagnostics",
     "Full network configuration plus every listening port."),
    ("process_list", "📊", "Process Monitor",
     "Top 20 CPU-consuming processes."),
    ("gpu_info",     "🎮", "GPU Details",
     "GPU adapter name, driver version, VRAM and status."),
]

REPAIR = [
    ("sfc_scan",     "🛡️", "System File Checker",
     "Scan and repair protected system files. Elevated.", "high"),
    ("temp_clean",   "🧹", "Temp File Cleaner",
     "Delete temporary files from the user TEMP directory.", "medium"),
    ("flush_dns",    "🔄", "Flush DNS Cache",
     "Clear the DNS resolver cache to fix name resolution.", "low"),
    ("system_update", "⬆️", "System Update",
     "Upgrade every installed package via winget.", "medium"),
]

# -- runtimes, toolchains and drivers: (command_key, glyph, name, desc) ------
RUNTIMES = [
    ("dotnet", "🧩", ".NET Runtime",
     "Install the .NET 8 Desktop Runtime."),
    ("wsl2",   "🐧", "WSL2 + Virtual Machine Platform",
     "Enable Windows Subsystem for Linux 2. Elevated — modifies OS features."),
    ("zadig",  "🔌", "Zadig",
     "Binds WinUSB / libusb-win32 / libusbK to a specific device."),
    ("libusbk", "🔗", "libusbK",
     "USB driver framework Zadig binds devices to."),
]

# -- control panels opened locally: (key, glyph, name, desc, command) --------
PANELS = [
    ("panel_devmgmt", "🖥️", "Device Manager",
     "Inspect and update hardware drivers.", "start devmgmt.msc"),
    ("panel_diskmgmt", "💾", "Disk Management",
     "Partition, format and extend volumes.", "start diskmgmt.msc"),
    ("panel_eventvwr", "📜", "Event Viewer",
     "System, application and security event logs.", "start eventvwr.msc"),
    ("panel_wupdate",  "🔄", "Windows Update",
     "Check for and install OS updates.", "start ms-settings:windowsupdate"),
]

# -- reference links: (key, glyph, name, desc, url) --------------------------
LINKS = [
    ("link_update_catalog", "🧰", "Microsoft Update Catalog",
     "Search and download individual Windows updates.",
     "https://www.catalog.update.microsoft.com/"),
    ("link_release_health", "📋", "Windows Release Health",
     "Known issues and rollout status for your Windows build.",
     "https://learn.microsoft.com/windows/release-health/"),
    ("link_nvidia", "🟢", "NVIDIA Drivers",
     "Official NVIDIA driver download and auto-detect.",
     "https://www.nvidia.com/Download/index.aspx"),
    ("link_amd", "🔴", "AMD Drivers",
     "Official AMD GPU and chipset driver downloads.",
     "https://www.amd.com/en/support"),
    ("link_intel", "🔵", "Intel Drivers",
     "Intel Driver & Support Assistant auto-detect.",
     "https://www.intel.com/content/www/us/en/support/detect.html"),
]


class TechToolsTab(ToolTabBase):
    """Technician utilities: app management, diagnostics, repair, reference."""

    def __init__(self, parent=None):
        super().__init__(
            title="🔧  Technician Tools",
            subtitle="Install and update applications, run diagnostics and repairs, "
                     "and reach the system panels a technician needs most. "
                     "Everything runs in the console below.",
            console_label="📟  Diagnostic Console",
            parent=parent,
        )
        self._build()
        self.finish_sections()

    def _build(self) -> None:
        # ---- Apps -----------------------------------------------------
        for key, glyph, name, expanded, entries in APPS:
            section = self.add_section(f"{glyph}  {name}", expanded=expanded)
            for app_key, app_name, desc, winget_id in entries:
                self.add_app_card(section, app_key, glyph, app_name, desc, winget_id)

        # ---- Diagnostics ---------------------------------------------
        section = self.add_section("🩺  Diagnostics", expanded=True)
        for cmd_key, glyph, name, desc in DIAGNOSTICS:
            self.add_command_card(section, cmd_key, glyph, name, desc)

        # ---- Repair ---------------------------------------------------
        section = self.add_section("🔧  Repair & Maintenance")
        for cmd_key, glyph, name, desc, risk in REPAIR:
            card = self.add_command_card(section, cmd_key, glyph, name, desc)
            if card is not None:
                card.set_action(f"▶  Run  ({risk.upper()})")

        # ---- Runtimes / drivers --------------------------------------
        section = self.add_section("🧩  Runtimes, Toolchains & Drivers")
        for cmd_key, glyph, name, desc in RUNTIMES:
            self.add_command_card(section, cmd_key, glyph, name, desc)
        self.add_batch_button(
            section, "tech_utilities", "🛠️", "Tech Utilities Profile",
            "Silent batch install of 7-Zip, Notepad++, Wireshark, VS Code, "
            "Git and Python 3.12.",
        )

        # ---- Control panels ------------------------------------------
        section = self.add_section("⚙️  System Panels")
        for key, glyph, name, desc, command in PANELS:
            self.add_raw_card(section, key, glyph, name, desc, command,
                              risk="low", skip_confirm=True)

        # ---- Reference ------------------------------------------------
        section = self.add_section("🔗  Useful Resources")
        for key, glyph, name, desc, url in LINKS:
            self.add_url_card(section, key, glyph, name, desc, url)
