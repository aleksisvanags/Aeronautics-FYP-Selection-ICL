import json
import re
import sys
from pathlib import Path

try:
    from pypdf import PdfReader
except ImportError:
    print("Error: pypdf is required. Install it by running: pip install pypdf")
    sys.exit(1)

# Configuration
PDF_FILENAME = "Final Year Internal Project List 2026-2027.pdf"
OUTPUT_HTML = "projects_dashboard.html"

# Curated whitelist of skills & software: canonical filter name -> alias
# spellings to search for in each project's title/software/description.
# Only canonical names actually found in a project end up as filters.
SKILL_KEYWORDS = {
    # Robotics, Control & Autonomous Systems
    "Gazebo": ["Gazebo"],
    "ROS": ["ROS", "ROS2", "ROS 2"],
    "Simulink": ["Simulink"],
    "Control Systems": ["Control Systems", "Control System"],
    "ArduPilot": ["ArduPilot"],
    "PX4": ["PX4"],
    "SLAM": ["SLAM"],
    "Trajectory Optimization": [
        "Trajectory Optimization",
        "Trajectory Optimisation",
    ],
    "PID": ["PID"],
    "Avionics": ["Avionics"],
    "UAV": ["UAV", "UAVs"],
    "Drones": ["Drone", "Drones"],
    "RobotStudio": ["RobotStudio"],
    # Languages & Computing
    "Python": ["Python", "Phython"],  # "Phython" is a typo in the PDF
    "MATLAB": ["MATLAB"],
    "C++": ["C++"],
    "C#": ["C#"],
    "Fortran": ["Fortran"],
    "Julia": ["Julia"],
    "Linux": ["Linux"],
    "Git": ["Git"],
    "HPC": ["HPC", "High-performance computing", "High performance computing"],
    "GPU": ["GPU", "GPUs"],
    "CUDA": ["CUDA"],
    "OpenMP": ["OpenMP"],
    "MPI": ["MPI"],
    "LabVIEW": ["LabVIEW"],
    "Anaconda": ["Anaconda"],
    # AI, Machine Learning & Data Science
    "Machine Learning": ["Machine Learning", "Machine-Learning"],
    "Deep Learning": ["Deep Learning"],
    "PyTorch": ["PyTorch"],
    "TensorFlow": ["TensorFlow"],
    "JAX": ["JAX"],
    "Neural Networks": ["Neural Networks", "Neural Network"],
    "Reinforcement Learning": ["Reinforcement Learning"],
    "Computer Vision": ["Computer Vision"],
    "AI": ["AI", "Artificial Intelligence"],
    "Data-driven": ["Data-driven", "Data driven"],
    "Physics-Informed Neural Networks (PINNs)": [
        "Physics-Informed Neural Networks",
        "Physics Informed Neural Networks",
        "PINNs",
        "PINN",
    ],
    "SINDy": ["SINDy"],
    "PySR": ["PySR"],
    "Qiskit": ["Qiskit"],
    # CFD & Aerodynamics
    "CFD": ["CFD"],
    "DNS": ["DNS", "Direct Numerical Simulation"],
    "OpenFOAM": ["OpenFOAM", "Open FOAM"],
    "ANSYS": ["ANSYS"],
    "Fluent": ["Fluent"],
    "SU2": ["SU2"],
    "Star-CCM+": ["Star-CCM+", "Star-CCM", "Star CCM+", "STARCCM"],
    "Nektar++": ["Nektar++", "Nektar"],
    "PyFR": ["PyFR"],
    "ParaView": ["ParaView"],
    "VisIt": ["VisIt"],
    "FLORIS": ["FLORIS"],
    "APCEMM": ["APCEMM"],
    "AeroFuse": ["AeroFuse"],
    "NeuralFoil": ["NeuralFoil"],
    "Waterlily.jl": ["Waterlily"],
    "Turing.jl": ["Turing.jl"],
    "Wind Tunnel": ["Wind Tunnel", "Wind-tunnel"],
    "PIV": ["PIV", "Particle Image Velocimetry"],
    "Schlieren": ["Schlieren"],
    "Aerodynamics": ["Aerodynamics"],
    "Turbulence": ["Turbulence"],
    "Aeroacoustics": ["Aeroacoustics"],
    "Hypersonics": ["Hypersonics", "Hypersonic"],
    # FEA, Structures & Materials
    "FEA": ["FEA"],
    "Abaqus": ["Abaqus"],
    "NASTRAN": ["NASTRAN"],
    "LS-Dyna": ["LS-Dyna", "LS Dyna", "LSDyna"],
    "SolidWorks": ["SolidWorks"],
    "CAD": ["CAD"],
    "COMSOL": ["COMSOL"],
    "Autodesk Fusion 360": ["Autodesk Fusion 360", "Fusion 360"],
    "3DExperience": ["3DExperience", "3D Experience", "3DX"],
    "FreeFEM++": ["FreeFem++", "FreeFem"],
    "Firedrake": ["Firedrake"],
    "MSC Adams": ["MSC Adams"],
    "CVX": ["CVX"],
    "SimaPro": ["SimaPro"],
    "MAUD": ["MAUD"],
    "Dragonfly": ["Dragonfly"],
    "PlasmaSim": ["PlasmaSim"],
    "SharpCap": ["SharpCap"],
    "Composite": ["Composite", "Composites"],
    "Fracture": ["Fracture"],
    "Fatigue": ["Fatigue"],
    "SHM": ["SHM", "Structural Health Monitoring"],
    "Vibration": ["Vibration", "Vibrations"],
    "Aeroelasticity": ["Aeroelasticity", "Aeroelastic"],
    "Finite Element": ["Finite Element", "Finite-Element"],
    # Space & Astrodynamics
    "Orbital Mechanics": ["Orbital Mechanics"],
    "Astrodynamics": ["Astrodynamics"],
    "Spacecraft": ["Spacecraft"],
    "Satellite": ["Satellite", "Satellites"],
    "LEO": ["LEO", "Low Earth Orbit"],
    "Propulsion": ["Propulsion"],
    "GMAT": ["GMAT"],
    "STK": ["STK"],
}

# Aliases that clash with ordinary English words when lowercased
# ("research visit", "dragonfly-inspired gliders") — match these exactly.
CASE_SENSITIVE_ALIASES = {"VisIt", "Dragonfly", "MAUD"}


def _alias_pattern(alias):
    """Regex for an alias with word boundaries that also work for names
    ending in non-word characters like C++ or Star-CCM+."""
    prefix = r"(?<![A-Za-z0-9])" if alias[0].isalnum() else ""
    suffix = r"(?![A-Za-z0-9])" if alias[-1].isalnum() else ""
    return prefix + re.escape(alias) + suffix


# (canonical name, compiled alias regexes) pairs, built once.
_SKILL_MATCHERS = [
    (
        canonical,
        [
            re.compile(
                _alias_pattern(a),
                0 if a in CASE_SENSITIVE_ALIASES else re.IGNORECASE,
            )
            for a in aliases
        ],
    )
    for canonical, aliases in SKILL_KEYWORDS.items()
]

# Placeholder values in the Category field that should not become filters
CATEGORY_NOISE = {"none", "no", "n/a", "tbd", "to be decided", "-"}


def clean_text(text):
    """Removes page breaks, headers, and multiple whitespaces."""
    if not text:
        return ""
    # Strip page artifacts like "--- PAGE 12 ---", page numbers, and repeating headers
    text = re.sub(r"--- PAGE \d+ ---", " ", text)
    text = re.sub(
        r"IMPERIAL\s+Department of Aeronautics", "", text, flags=re.IGNORECASE
    )
    text = re.sub(
        r"UG Final Year Internal Project List", "", text, flags=re.IGNORECASE
    )
    # Collapse multiple spaces and newlines into a single space
    return re.sub(r"\s+", " ", text).strip()


def extract_projects_from_pdf(pdf_path):
    print(f"Reading and sanitizing {pdf_path}...")
    reader = PdfReader(pdf_path)
    full_text = ""

    for i, page in enumerate(reader.pages):
        text = page.extract_text()
        if text:
            # Every page starts with its printed page number (or a roman
            # numeral in the front matter). Drop it here so it cannot get
            # glued onto supervisors/categories/descriptions that span a
            # page break (e.g. "Armanini, Sophie Dr 10").
            text = re.sub(r"^\s*(?:\d{1,3}|[ivxl]{1,6})(?=\s)", "", text)
            # Re-join words hyphenated across a line break ("Co-\nsupervisor").
            text = re.sub(r"(?<=\w)-[ \t]*\n[ \t]*(?=\w)", "-", text)
            full_text += f"\n--- PAGE {i+1} ---\n" + text

    # Split text into project blocks by looking for "Project no:"
    raw_blocks = re.split(
        r"(?:^|\n)\s*Project\s+no:\s*", full_text, flags=re.IGNORECASE
    )
    projects = []

    for block in raw_blocks[1:]:
        block_cleaned = clean_text(block)

        # 1. Project Number / ID. A "*" after the code marks projects whose
        # effort must be split evenly across autumn and spring/summer terms.
        proj_no_match = re.match(r"^([A-Z0-9]+)", block_cleaned)
        proj_no = proj_no_match.group(1) if proj_no_match else "UNKNOWN"
        both_terms = bool(re.match(r"^[A-Z0-9]+\s*\*", block_cleaned))

        # 2. Project Title ("- 1 project available", or "- project available"
        # when the count is missing). The dash before the count is sometimes
        # an en/em dash rather than a hyphen, so accept all of them.
        title_match = re.search(
            r"Project\s+title:\s*(.*?)(?=\s*[-–—]\s*\d+\s*project|\s*[-–—]\s*projects?\s+available|\s*Supervisor:|\s*Co[\s-]*supervisor|$)",
            block_cleaned,
            re.IGNORECASE,
        )
        title = (
            clean_text(title_match.group(1))
            if title_match
            else "Untitled Project"
        )
        # "(S)" after the title marks a space-related project — students on
        # the spacecraft course may only pick these
        is_space = bool(re.search(r"\(\s*S\s*\)\s*$", title, re.IGNORECASE))
        title = re.sub(
            r"\s*\(\s*S\s*\)\s*$", "", title, flags=re.IGNORECASE
        ).strip()

        # 3. Supervisor (Strict stopping guards)
        sup_match = re.search(
            r"Supervisor:\s*(.*?)(?=\s*Co[\s-]*supervisor|\s*Category:|\s*Software:|\s*Confidential:|\s*\d+\s*project|$)",
            block_cleaned,
            re.IGNORECASE,
        )
        supervisor = "Unknown Supervisor"
        if sup_match:
            sup_raw = sup_match.group(1)
            sup_raw = re.split(
                r"Co[\s-]*supervisor", sup_raw, flags=re.IGNORECASE
            )[0]
            supervisor = clean_text(sup_raw).rstrip(" ,;-")
            # Safety net against stray page numbers
            supervisor = re.sub(r"\s+\d+$", "", supervisor)

        # 4. Categories
        cat_match = re.search(
            r"Category:\s*(.*?)(?=\s*Software:|\s*Confidential:|$)",
            block_cleaned,
            re.IGNORECASE,
        )
        categories = []
        if cat_match:
            raw_cats = re.split(r"[;,]", cat_match.group(1))
            for c in raw_cats:
                c_clean = clean_text(c).rstrip(".")
                # Safety net against stray page numbers
                c_clean = re.sub(r"\s+\d+$", "", c_clean)
                if (
                    c_clean
                    and c_clean.lower() not in CATEGORY_NOISE
                    and len(c_clean) > 2
                ):
                    categories.append(c_clean.title())
        if not categories:
            categories = ["Uncategorized"]

        # 5. Software Field Extraction
        soft_match = re.search(
            r"Software:\s*(.*?)(?=\s*Confidential:|$)",
            block_cleaned,
            re.IGNORECASE,
        )
        software_raw = clean_text(soft_match.group(1)) if soft_match else ""

        # 6. Description
        desc_split = re.split(
            r"Confidential:\s*(?:Yes|No)?", block_cleaned, flags=re.IGNORECASE
        )
        description = ""
        if len(desc_split) > 1:
            description = clean_text(desc_split[1])
        # The PDF repeats the supervisor's name as a header right before the
        # NEXT project, which lands at the end of this block's description
        # ("...aircraft panels. Aliabadi, Ferri Prof.") — strip it.
        description = re.sub(
            r"\s*[A-Z][\w'’\- ]*,\s+[\w'’\- ]+?\s+(?:Prof\.?|Dr\.?)\s*$",
            "",
            description,
        )

        # --- SKILL & SOFTWARE MATCHING (whitelist only) ---
        # The Software field sometimes mashes tools together across line
        # breaks ("Fusion 360LabView") — put a space between digit and word.
        software_clean = re.sub(r"(?<=\d)(?=[A-Z][a-z])", " ", software_raw)
        combined_search_text = f"{title} {software_clean} {description}"

        found_skills = set()
        for canonical, patterns in _SKILL_MATCHERS:
            if any(p.search(combined_search_text) for p in patterns):
                found_skills.add(canonical)

        projects.append(
            {
                "id": proj_no,
                "title": title,
                "supervisor": supervisor,
                "space": is_space,
                "bothTerms": both_terms,
                "categories": sorted(list(set(categories))),
                "skills": sorted(list(found_skills)),
                "description": description,
            }
        )

    print(
        f"Successfully extracted and cleaned {len(projects)} projects without noise!"
    )
    return projects


def generate_html(projects, output_filename):
    print(f"Generating enhanced interactive dashboard: {output_filename}...")

    html_template = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Imperial Aeronautics - Project Selection Dashboard</title>
    <style>
        :root {{
            color-scheme: light;
            --bg: #f8fafc;
            --card-bg: #ffffff;
            --primary: #0284c7;
            --primary-hover: #0369a1;
            --text: #0f172a;
            --text-mid: #334155;
            --text-soft: #475569;
            --text-light: #64748b;
            --heading: #1e293b;
            --border: #e2e8f0;
            --border-strong: #cbd5e1;
            --muted-bg: #f1f5f9;
            --divider: #f1f5f9;
            --tag-bg: #f0f9ff;
            --tag-text: #0369a1;
            --tag-border: #e0f2fe;
            --star-color: #f59e0b;
            --icon-idle: #e2e8f0;
            --icon-hover: #cbd5e1;
            --restore: #94a3b8;
            --danger: #ef4444;
            --star-accent-bg: #fef3c7; --star-accent-border: #f59e0b; --star-accent-text: #b45309;
            --hide-accent-bg: #fee2e2; --hide-accent-border: #ef4444; --hide-accent-text: #b91c1c;
            --space-accent-bg: #ede9fe; --space-accent-border: #8b5cf6; --space-accent-text: #6d28d9;
            --space-badge-border: #ddd6fe;
            --term-accent-bg: #ccfbf1; --term-accent-border: #14b8a6; --term-accent-text: #0f766e;
            --term-badge-border: #99f6e4;
            --focus-ring: rgba(2, 132, 199, 0.1);
            --card-shadow: 0 1px 3px rgba(0,0,0,0.02);
            --card-shadow-hover: 0 10px 25px -5px rgba(0,0,0,0.05), 0 8px 10px -6px rgba(0,0,0,0.01);
        }}
        :root[data-theme="dark"] {{
            color-scheme: dark;
            --bg: #0b1120;
            --card-bg: #1e293b;
            --primary: #38bdf8;
            --primary-hover: #7dd3fc;
            --text: #f1f5f9;
            --text-mid: #cbd5e1;
            --text-soft: #cbd5e1;
            --text-light: #94a3b8;
            --heading: #f1f5f9;
            --border: #334155;
            --border-strong: #475569;
            --muted-bg: #334155;
            --divider: #334155;
            --tag-bg: #0c4a6e;
            --tag-text: #bae6fd;
            --tag-border: #075985;
            --star-color: #fbbf24;
            --icon-idle: #475569;
            --icon-hover: #64748b;
            --restore: #94a3b8;
            --danger: #f87171;
            --star-accent-bg: #451a03; --star-accent-border: #b45309; --star-accent-text: #fbbf24;
            --hide-accent-bg: #450a0a; --hide-accent-border: #b91c1c; --hide-accent-text: #f87171;
            --space-accent-bg: #2e1065; --space-accent-border: #7c3aed; --space-accent-text: #c4b5fd;
            --space-badge-border: #4c1d95;
            --term-accent-bg: #042f2e; --term-accent-border: #0f766e; --term-accent-text: #5eead4;
            --term-badge-border: #115e59;
            --focus-ring: rgba(56, 189, 248, 0.2);
            --card-shadow: 0 1px 3px rgba(0,0,0,0.3);
            --card-shadow-hover: 0 10px 25px -5px rgba(0,0,0,0.5), 0 8px 10px -6px rgba(0,0,0,0.3);
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }}
        body {{ background-color: var(--bg); color: var(--text); display: flex; height: 100vh; overflow: hidden; }}

        /* Sidebar Controls */
        .sidebar {{ width: 340px; background: var(--card-bg); border-right: 1px solid var(--border); display: flex; flex-direction: column; height: 100%; z-index: 10; }}
        .sidebar-header {{ padding: 20px; border-bottom: 1px solid var(--border); background: var(--card-bg); }}
        .sidebar-header-row {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }}
        .sidebar-header h2 {{ font-size: 1.1rem; font-weight: 700; color: var(--heading); letter-spacing: -0.01em; }}
        .btn-theme {{ background: var(--bg); border: 1px solid var(--border); border-radius: 8px; padding: 4px 10px; cursor: pointer; font-size: 1rem; line-height: 1.4; transition: all 0.15s; }}
        .btn-theme:hover {{ border-color: var(--border-strong); }}
        .search-box {{ width: 100%; padding: 10px 14px; border: 1px solid var(--border); border-radius: 8px; font-size: 0.9rem; outline: none; transition: all 0.15s; background: var(--bg); color: var(--text); }}
        .search-box:focus {{ border-color: var(--primary); background: var(--card-bg); box-shadow: 0 0 0 3px var(--focus-ring); }}

        .filters-scroll {{ flex: 1; overflow-y: auto; padding: 20px; }}
        .filter-section {{ margin-bottom: 28px; }}
        .filter-section h3 {{ font-size: 0.75rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.08em; color: var(--text-light); margin-bottom: 12px; display: flex; justify-content: space-between; }}
        .checkbox-label {{ display: flex; align-items: center; justify-content: space-between; font-size: 0.88rem; margin-bottom: 8px; cursor: pointer; user-select: none; color: var(--text-mid); transition: color 0.1s; }}
        .checkbox-label:hover {{ color: var(--text); }}
        .checkbox-label input {{ margin-right: 10px; cursor: pointer; accent-color: var(--primary); width: 16px; height: 16px; border-radius: 4px; }}
        .badge-count {{ font-size: 0.75rem; background: var(--bg); padding: 2px 8px; border-radius: 12px; color: var(--text-light); font-weight: 600; border: 1px solid var(--border); }}

        .sidebar-footer {{ padding: 16px 20px; border-top: 1px solid var(--border); display: flex; justify-content: space-between; align-items: center; background: var(--card-bg); }}
        .btn-reset {{ background: none; border: none; color: var(--primary); cursor: pointer; font-size: 0.88rem; font-weight: 600; }}
        .btn-reset:hover {{ text-decoration: underline; color: var(--primary-hover); }}

        /* Main Content Area */
        .main-content {{ flex: 1; display: flex; flex-direction: column; height: 100%; overflow: hidden; }}
        .top-bar {{ padding: 16px 32px; background: var(--card-bg); border-bottom: 1px solid var(--border); display: flex; justify-content: space-between; align-items: center; }}
        .results-count {{ font-weight: 600; font-size: 1.05rem; color: var(--heading); }}
        .filter-toggles {{ display: flex; gap: 12px; }}
        .toggle-btn {{ background: var(--card-bg); border: 1px solid var(--border); padding: 8px 16px; border-radius: 8px; cursor: pointer; font-size: 0.88rem; font-weight: 600; display: flex; align-items: center; gap: 6px; transition: all 0.15s; color: var(--text-soft); }}
        .toggle-btn:hover {{ border-color: var(--border-strong); background: var(--bg); }}
        .toggle-btn.active {{ background: var(--star-accent-bg); border-color: var(--star-accent-border); color: var(--star-accent-text); }}

        .projects-grid {{ flex: 1; overflow-y: auto; padding: 32px; display: grid; grid-template-columns: repeat(auto-fill, minmax(460px, 1fr)); gap: 20px; align-content: start; }}

        /* Project Cards */
        .card {{ background: var(--card-bg); border: 1px solid var(--border); border-radius: 12px; padding: 24px; display: flex; flex-direction: column; justify-content: space-between; transition: all 0.2s ease; position: relative; box-shadow: var(--card-shadow); }}
        .card:hover {{ box-shadow: var(--card-shadow-hover); border-color: var(--border-strong); transform: translateY(-1px); }}
        .card-header {{ display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 14px; }}
        .proj-id {{ font-size: 0.8rem; font-weight: 700; color: var(--primary); background: var(--tag-bg); padding: 4px 10px; border-radius: 6px; letter-spacing: 0.03em; border: 1px solid var(--tag-border); }}
        .card-actions {{ display: flex; align-items: center; gap: 8px; }}
        .btn-star {{ background: none; border: none; font-size: 1.5rem; cursor: pointer; color: var(--icon-idle); transition: all 0.15s; line-height: 1; }}
        .btn-star:hover {{ transform: scale(1.2); color: var(--icon-hover); }}
        .btn-star.starred {{ color: var(--star-color); }}
        .btn-hide {{ background: none; border: none; font-size: 1.2rem; cursor: pointer; color: var(--icon-idle); transition: all 0.15s; line-height: 1; }}
        .btn-hide:hover {{ transform: scale(1.2); color: var(--danger); }}
        .btn-hide.restore {{ color: var(--restore); font-size: 1.35rem; }}
        .btn-hide.restore:hover {{ color: var(--primary); }}
        .toggle-btn.active-hidden {{ background: var(--hide-accent-bg); border-color: var(--hide-accent-border); color: var(--hide-accent-text); }}
        .toggle-btn.active-space {{ background: var(--space-accent-bg); border-color: var(--space-accent-border); color: var(--space-accent-text); }}
        .space-badge {{ font-size: 0.8rem; font-weight: 700; color: var(--space-accent-text); background: var(--space-accent-bg); padding: 4px 10px; border-radius: 6px; border: 1px solid var(--space-badge-border); }}
        .toggle-btn.active-terms {{ background: var(--term-accent-bg); border-color: var(--term-accent-border); color: var(--term-accent-text); }}
        .term-badge {{ font-size: 0.8rem; font-weight: 700; color: var(--term-accent-text); background: var(--term-accent-bg); padding: 4px 10px; border-radius: 6px; border: 1px solid var(--term-badge-border); }}

        .card h3 {{ font-size: 1.15rem; margin-bottom: 8px; line-height: 1.4; font-weight: 700; color: var(--text); }}
        .supervisor {{ font-size: 0.9rem; color: var(--text-light); margin-bottom: 16px; font-weight: 600; display: flex; align-items: center; gap: 6px; }}

        .description {{ font-size: 0.92rem; color: var(--text-mid); line-height: 1.6; margin-bottom: 18px; max-height: 110px; overflow: hidden; position: relative; }}
        .description.expanded {{ max-height: none; }}
        .btn-more {{ background: none; border: none; color: var(--primary); font-size: 0.85rem; cursor: pointer; padding: 0; margin-bottom: 16px; font-weight: 600; display: inline-block; }}
        .btn-more:hover {{ text-decoration: underline; }}

        .tags-container {{ display: flex; flex-wrap: wrap; gap: 6px; margin-top: auto; padding-top: 16px; border-top: 1px solid var(--divider); }}
        .tag {{ font-size: 0.75rem; padding: 4px 10px; border-radius: 6px; font-weight: 600; }}
        .tag-cat {{ background: var(--muted-bg); color: var(--text-soft); border: 1px solid var(--border); }}
        .tag-skill {{ background: var(--tag-bg); color: var(--tag-text); border: 1px solid var(--tag-border); }}
        
        @media (max-width: 900px) {{
            body {{ flex-direction: column; overflow: auto; }}
            .sidebar {{ width: 100%; height: auto; }}
            .projects-grid {{ grid-template-columns: 1fr; padding: 16px; }}
            .top-bar {{ padding: 16px; flex-direction: column; gap: 12px; align-items: flex-start; }}
        }}
    </style>
</head>
<body>
    <script>
        // Apply the saved (or system) theme before anything renders to
        // avoid a white flash for dark-mode users
        (function() {{
            const saved = localStorage.getItem('theme');
            const theme = saved || (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
            document.documentElement.setAttribute('data-theme', theme);
        }})();
    </script>

    <aside class="sidebar">
        <div class="sidebar-header">
            <div class="sidebar-header-row">
                <h2>Project Selector</h2>
                <button class="btn-theme" id="themeToggle" onclick="toggleTheme()" title="Switch light/dark mode">🌙</button>
            </div>
            <input type="text" id="searchInput" class="search-box" placeholder="Search keywords, topics, software...">
        </div>
        <div class="filters-scroll" id="filtersContainer">
            </div>
        <div class="sidebar-footer">
            <span id="selectedCount" style="font-size: 0.88rem; font-weight: 600; color: var(--text-light);">0 options removed</span>
            <button class="btn-reset" onclick="resetFilters()">Reset All</button>
        </div>
    </aside>

    <main class="main-content">
        <div class="top-bar">
            <div class="results-count" id="resultsCount">Loading projects...</div>
            <div class="filter-toggles">
                <button class="toggle-btn" id="btnShortlist" onclick="toggleShortlistFilter()">
                    ★ Show Shortlist Only (<span id="shortlistCount">0</span>)
                </button>
                <button class="toggle-btn" id="btnHidden" onclick="toggleHiddenFilter()">
                    ✕ Show Hidden Only (<span id="hiddenCount">0</span>)
                </button>
                <button class="toggle-btn" id="btnSpace" onclick="toggleSpaceFilter()" title="Students on the spacecraft course can only pick (S) projects">
                    🚀 Space (S) Only (<span id="spaceCount">0</span>)
                </button>
                <button class="toggle-btn" id="btnTerms" onclick="toggleTermsFilter()" title="Projects marked * in the PDF: student effort must be evenly distributed between the autumn and spring/summer terms">
                    ✱ Both Terms Only (<span id="termsCount">0</span>)
                </button>
            </div>
        </div>
        <div class="projects-grid" id="projectsGrid"></div>
    </main>

    <script>
        const projectsData = {json.dumps(projects)};
        let starredIds = new Set(JSON.parse(localStorage.getItem('starredProjects') || '[]'));
        let hiddenIds = new Set(JSON.parse(localStorage.getItem('hiddenProjects') || '[]'));
        let showShortlistOnly = false;
        let showHiddenOnly = false;
        let showSpaceOnly = false;
        let showTermsOnly = false;
        let expandedIds = new Set();

        // Pseudo-option so projects without any detected skills can still be
        // narrowed down via the Skills section instead of always showing.
        const NO_SKILLS = '(No software listed)';
        // group -> option name -> badge element, for live count updates
        const badgeEls = {{ categories: {{}}, skills: {{}}, supervisors: {{}} }};
        
        // Everything starts checked. Within each group, a project stays
        // visible as long as AT LEAST ONE of its tags is still checked —
        // so unchecking options progressively narrows the list, and
        // "None + re-check X" shows exactly the projects tagged X.
        let excluded = {{
            categories: new Set(),
            skills: new Set(),
            supervisors: new Set()
        }};

        function init() {{
            syncThemeButton();
            buildSidebar();
            restoreState();
            updateShortlistUI();
            updateHiddenUI();
            document.getElementById('spaceCount').innerText = projectsData.filter(p => p.space).length;
            document.getElementById('termsCount').innerText = projectsData.filter(p => p.bothTerms).length;
            renderProjects();
            document.getElementById('searchInput').addEventListener('input', renderProjects);
        }}

        // ---- Filter/search/toggle persistence across reloads ----
        const STATE_KEY = 'dashboardFilters';

        function saveState() {{
            localStorage.setItem(STATE_KEY, JSON.stringify({{
                excluded: {{
                    categories: [...excluded.categories],
                    skills: [...excluded.skills],
                    supervisors: [...excluded.supervisors]
                }},
                search: document.getElementById('searchInput').value,
                showShortlistOnly, showHiddenOnly, showSpaceOnly, showTermsOnly
            }}));
        }}

        function restoreState() {{
            let saved = null;
            try {{ saved = JSON.parse(localStorage.getItem(STATE_KEY)); }} catch (e) {{}}
            if (!saved) return;

            // Re-apply unchecked options via the checkboxes that actually
            // exist, so stale values (e.g. after the PDF is re-parsed with
            // different tags) are dropped silently.
            const savedEx = saved.excluded || {{}};
            document.querySelectorAll('input[data-group]').forEach(cb => {{
                const group = cb.dataset.group;
                if ((savedEx[group] || []).includes(cb.value)) {{
                    cb.checked = false;
                    excluded[group].add(cb.value);
                }}
            }});

            document.getElementById('searchInput').value = saved.search || '';
            showShortlistOnly = !!saved.showShortlistOnly;
            showHiddenOnly = !!saved.showHiddenOnly;
            showSpaceOnly = !!saved.showSpaceOnly;
            showTermsOnly = !!saved.showTermsOnly;
            if (showShortlistOnly) document.getElementById('btnShortlist').classList.add('active');
            if (showHiddenOnly) document.getElementById('btnHidden').classList.add('active-hidden');
            if (showSpaceOnly) document.getElementById('btnSpace').classList.add('active-space');
            if (showTermsOnly) document.getElementById('btnTerms').classList.add('active-terms');
            updateActiveCount();
        }}

        function syncThemeButton() {{
            const dark = document.documentElement.getAttribute('data-theme') === 'dark';
            const btn = document.getElementById('themeToggle');
            btn.innerText = dark ? '☀️' : '🌙';
            btn.title = dark ? 'Switch to light mode' : 'Switch to dark mode';
        }}

        function toggleTheme() {{
            const next = document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
            document.documentElement.setAttribute('data-theme', next);
            localStorage.setItem('theme', next);
            syncThemeButton();
        }}

        function getCounts(field) {{
            const counts = {{}};
            projectsData.forEach(p => {{
                let items = Array.isArray(p[field]) ? p[field] : [p[field]];
                items.forEach(item => {{
                    if(item && item.trim() !== '') {{
                        counts[item] = (counts[item] || 0) + 1;
                    }}
                }});
            }});
            return Object.entries(counts).sort((a, b) => b[1] - a[1]);
        }}

        function buildSidebar() {{
            const container = document.getElementById('filtersContainer');
            container.innerHTML = '';

            const createSection = (title, items, filterKey) => {{
                if (items.length === 0) return;
                const section = document.createElement('div');
                section.className = 'filter-section';
                section.innerHTML = `<h3><span>${{title}} <span style="font-weight:normal; text-transform:none;">(${{items.length}})</span></span>
                    <span style="font-weight:normal; text-transform:none;">
                        <a href="#" onclick="setGroup('${{filterKey}}', true); return false;" style="color: var(--primary);">All</a> /
                        <a href="#" onclick="setGroup('${{filterKey}}', false); return false;" style="color: var(--primary);">None</a>
                    </span></h3>`;

                items.forEach(([name, count]) => {{
                    const label = document.createElement('label');
                    label.className = 'checkbox-label';
                    label.innerHTML = `
                        <div style="display:flex; align-items:center; overflow:hidden; padding-right:8px;">
                            <input type="checkbox" checked value="${{name}}" data-group="${{filterKey}}" onchange="toggleFilter(this)">
                            <span style="white-space:nowrap; overflow:hidden; text-overflow:ellipsis;" title="${{name}}">${{name}}</span>
                        </div>
                        <span class="badge-count">${{count}}</span>
                    `;
                    badgeEls[filterKey][name] = label.querySelector('.badge-count');
                    section.appendChild(label);
                }});
                container.appendChild(section);
            }};

            const skillCounts = getCounts('skills');
            const noSkillCount = projectsData.filter(p => p.skills.length === 0).length;
            if (noSkillCount > 0) skillCounts.push([NO_SKILLS, noSkillCount]);

            createSection('Categories', getCounts('categories'), 'categories');
            createSection('Skills & Software', skillCounts, 'skills');
            createSection('Supervisors', getCounts('supervisor'), 'supervisors');
        }}

        // Keep sidebar counts in sync with what is actually on screen
        function updateBadges(filtered) {{
            const counts = {{ categories: {{}}, skills: {{}}, supervisors: {{}} }};
            filtered.forEach(p => {{
                p.categories.forEach(c => counts.categories[c] = (counts.categories[c] || 0) + 1);
                if (p.skills.length === 0) {{
                    counts.skills[NO_SKILLS] = (counts.skills[NO_SKILLS] || 0) + 1;
                }}
                p.skills.forEach(s => counts.skills[s] = (counts.skills[s] || 0) + 1);
                counts.supervisors[p.supervisor] = (counts.supervisors[p.supervisor] || 0) + 1;
            }});
            for (const group of Object.keys(badgeEls)) {{
                for (const [name, el] of Object.entries(badgeEls[group])) {{
                    const n = counts[group][name] || 0;
                    el.innerText = n;
                    el.style.opacity = n === 0 ? '0.45' : '1';
                }}
            }}
        }}

        function toggleFilter(checkbox) {{
            const group = checkbox.dataset.group;
            if (checkbox.checked) {{
                excluded[group].delete(checkbox.value);
            }} else {{
                excluded[group].add(checkbox.value);
            }}
            updateActiveCount();
            renderProjects();
        }}

        function setGroup(group, checked) {{
            document.querySelectorAll(`input[data-group="${{group}}"]`).forEach(cb => {{
                cb.checked = checked;
                if (checked) {{
                    excluded[group].delete(cb.value);
                }} else {{
                    excluded[group].add(cb.value);
                }}
            }});
            updateActiveCount();
            renderProjects();
        }}

        function updateActiveCount() {{
            const total = excluded.categories.size + excluded.skills.size + excluded.supervisors.size;
            document.getElementById('selectedCount').innerText = `${{total}} option${{total === 1 ? '' : 's'}} removed`;
        }}

        function resetFilters() {{
            excluded.categories.clear();
            excluded.skills.clear();
            excluded.supervisors.clear();
            document.querySelectorAll('.sidebar input[type="checkbox"]').forEach(cb => cb.checked = true);
            document.getElementById('searchInput').value = '';
            showShortlistOnly = false;
            document.getElementById('btnShortlist').classList.remove('active');
            showHiddenOnly = false;
            document.getElementById('btnHidden').classList.remove('active-hidden');
            showSpaceOnly = false;
            document.getElementById('btnSpace').classList.remove('active-space');
            showTermsOnly = false;
            document.getElementById('btnTerms').classList.remove('active-terms');
            updateActiveCount();
            renderProjects();
        }}

        function toggleShortlistFilter() {{
            showShortlistOnly = !showShortlistOnly;
            if (showShortlistOnly && showHiddenOnly) {{
                showHiddenOnly = false;
                document.getElementById('btnHidden').classList.remove('active-hidden');
            }}
            const btn = document.getElementById('btnShortlist');
            showShortlistOnly ? btn.classList.add('active') : btn.classList.remove('active');
            renderProjects();
        }}

        function toggleHiddenFilter() {{
            showHiddenOnly = !showHiddenOnly;
            if (showHiddenOnly && showShortlistOnly) {{
                showShortlistOnly = false;
                document.getElementById('btnShortlist').classList.remove('active');
            }}
            const btn = document.getElementById('btnHidden');
            showHiddenOnly ? btn.classList.add('active-hidden') : btn.classList.remove('active-hidden');
            renderProjects();
        }}

        function toggleTermsFilter() {{
            // Constraint like the space toggle — combines with everything else
            showTermsOnly = !showTermsOnly;
            const btn = document.getElementById('btnTerms');
            showTermsOnly ? btn.classList.add('active-terms') : btn.classList.remove('active-terms');
            renderProjects();
        }}

        function toggleSpaceFilter() {{
            // An eligibility constraint, not a view — combines with the
            // shortlist and hidden views instead of replacing them
            showSpaceOnly = !showSpaceOnly;
            const btn = document.getElementById('btnSpace');
            showSpaceOnly ? btn.classList.add('active-space') : btn.classList.remove('active-space');
            renderProjects();
        }}

        function toggleStar(id) {{
            if (starredIds.has(id)) {{
                starredIds.delete(id);
            }} else {{
                starredIds.add(id);
            }}
            localStorage.setItem('starredProjects', JSON.stringify(Array.from(starredIds)));
            updateShortlistUI();
            renderProjects();
        }}

        function toggleHide(id) {{
            if (hiddenIds.has(id)) {{
                hiddenIds.delete(id);
            }} else {{
                hiddenIds.add(id);
                // A hidden project shouldn't linger on the shortlist
                if (starredIds.has(id)) {{
                    starredIds.delete(id);
                    localStorage.setItem('starredProjects', JSON.stringify(Array.from(starredIds)));
                    updateShortlistUI();
                }}
            }}
            localStorage.setItem('hiddenProjects', JSON.stringify(Array.from(hiddenIds)));
            updateHiddenUI();
            renderProjects();
        }}

        function updateShortlistUI() {{
            document.getElementById('shortlistCount').innerText = starredIds.size;
        }}

        function updateHiddenUI() {{
            document.getElementById('hiddenCount').innerText = hiddenIds.size;
        }}

        function toggleDescription(btn, id) {{
            const desc = btn.previousElementSibling;
            if (expandedIds.has(id)) {{
                expandedIds.delete(id);
            }} else {{
                expandedIds.add(id);
            }}
            desc.classList.toggle('expanded');
            btn.innerText = desc.classList.contains('expanded') ? 'Show less ▲' : 'Read full description ▼';
        }}

        function renderProjects() {{
            const grid = document.getElementById('projectsGrid');
            const searchQuery = document.getElementById('searchInput').value.toLowerCase().trim();
            const prevScroll = grid.scrollTop;
            grid.innerHTML = '';

            const filtered = projectsData.filter(p => {{
                // The default view shows only undecided projects: starred ones
                // live in the shortlist view, hidden ones in the hidden view.
                if (showHiddenOnly) {{
                    if (!hiddenIds.has(p.id)) return false;
                }} else if (showShortlistOnly) {{
                    if (!starredIds.has(p.id)) return false;
                }} else {{
                    if (hiddenIds.has(p.id) || starredIds.has(p.id)) return false;
                }}

                if (showSpaceOnly && !p.space) return false;
                if (showTermsOnly && !p.bothTerms) return false;

                if (searchQuery) {{
                    const matchText = `${{p.id}} ${{p.title}} ${{p.supervisor}} ${{p.description}} ${{p.skills.join(' ')}} ${{p.categories.join(' ')}}`.toLowerCase();
                    if (!matchText.includes(searchQuery)) return false;
                }}

                // Within each group: visible if at least one tag is checked
                if (excluded.supervisors.has(p.supervisor)) return false;
                if (!p.categories.some(c => !excluded.categories.has(c))) return false;
                const skillTags = p.skills.length === 0 ? [NO_SKILLS] : p.skills;
                if (!skillTags.some(s => !excluded.skills.has(s))) return false;

                return true;
            }});

            updateBadges(filtered);

            document.getElementById('resultsCount').innerText = `Showing ${{filtered.length}} of ${{projectsData.length}} projects`;

            if (filtered.length === 0) {{
                grid.innerHTML = `<div style="grid-column: 1/-1; text-align: center; padding: 60px 20px; color: var(--text-light); background: var(--card-bg); border-radius: 12px; border: 1px dashed var(--border);">
                    <h3 style="color: var(--text-mid); margin-bottom: 8px;">No projects match your exact filters</h3>
                    <p style="font-size: 0.9rem;">Try re-checking some removed options or clearing your search query.</p>
                </div>`;
                return;
            }}

            filtered.forEach(p => {{
                const isStarred = starredIds.has(p.id);
                const isHidden = hiddenIds.has(p.id);
                const card = document.createElement('div');
                card.className = 'card';

                const tagsHtml = [
                    ...p.categories.map(c => `<span class="tag tag-cat">${{c}}</span>`),
                    ...p.skills.map(s => `<span class="tag tag-skill">${{s}}</span>`)
                ].join('');

                const starBtn = `<button class="btn-star ${{isStarred ? 'starred' : ''}}" onclick="toggleStar('${{p.id}}')" title="Add to Shortlist">★</button>`;
                const hideBtn = isHidden
                    ? `<button class="btn-hide restore" onclick="toggleHide('${{p.id}}')" title="Restore project">↩</button>`
                    : `<button class="btn-hide" onclick="toggleHide('${{p.id}}')" title="Hide project">✕</button>`;

                card.innerHTML = `
                    <div>
                        <div class="card-header">
                            <span style="display:flex; gap:6px; align-items:center;">
                                <span class="proj-id">#${{p.id}}</span>
                                ${{p.space ? '<span class="space-badge" title="Space-related project — pickable by the spacecraft course">🚀 S</span>' : ''}}
                                ${{p.bothTerms ? '<span class="term-badge" title="Marked * in the PDF: effort must be evenly distributed between the autumn and spring/summer terms">✱ Both terms</span>' : ''}}
                            </span>
                            <div class="card-actions">${{isHidden ? '' : starBtn}}${{hideBtn}}</div>
                        </div>
                        <h3>${{p.title}}</h3>
                        <div class="supervisor">👤 ${{p.supervisor}}</div>
                        <div class="description ${{expandedIds.has(p.id) ? 'expanded' : ''}}">${{p.description || '<i>No detailed description available.</i>'}}</div>
                        ${{p.description && p.description.length > 200 ? `<button class="btn-more" onclick="toggleDescription(this, '${{p.id}}')">${{expandedIds.has(p.id) ? 'Show less ▲' : 'Read full description ▼'}}</button>` : ''}}
                    </div>
                    <div class="tags-container">
                        ${{tagsHtml}}
                    </div>
                `;
                grid.appendChild(card);
            }});

            // Keep the user's place instead of jumping back to the top
            // whenever a star/hide/filter change re-renders the grid
            grid.scrollTop = prevScroll;

            // Every state change goes through a re-render, so persisting
            // here covers filters, search, and the view toggles in one place
            saveState();
        }}

        window.onload = init;
    </script>
</body>
</html>
"""

    with open(output_filename, "w", encoding="utf-8") as f:
        f.write(html_template)
    print(f"Done! Open '{output_filename}' in your web browser to test.")


if __name__ == "__main__":
    pdf_path = Path(PDF_FILENAME)
    if not pdf_path.exists():
        print(f"Error: Could not find '{PDF_FILENAME}' in the current folder.")
        sys.exit(1)

    extracted_projects = extract_projects_from_pdf(pdf_path)
    generate_html(extracted_projects, OUTPUT_HTML)