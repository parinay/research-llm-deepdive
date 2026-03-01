"""
subcategorizer.py
=================
Second-pass organizer that groups files inside each category folder into
meaningful topic subfolders based on keyword matching in filenames.

Designed to run after file_organizer.py has already sorted files by extension.
Safe to re-run: files already in a matching subfolder are left in place.

Usage
-----
    python subcategorizer.py <folder> [--dry-run]
"""

from __future__ import annotations

import os
import shutil
import argparse
from dataclasses import dataclass
from typing import Dict, List, Tuple

from utils import remove_empty_dirs

# ---------------------------------------------------------------------------
# Subcategory rules per category folder.
#
# Structure:
#   { "CategoryFolder": [ ("SubfolderName", [keywords, ...]), ... ] }
#
# Matching: if ANY keyword appears (case-insensitive) in the filename, the
# file goes into that subfolder. Rules are evaluated top-to-bottom; the
# first match wins. Files that match no rule go into "Misc/".
# ---------------------------------------------------------------------------

RULES: Dict[str, List[Tuple[str, List[str]]]] = {

    "Documents": [
        ("Travel", ["flight", "boarding", "eticket", "ticket",
                    "trips", "eurostar", "panoramic"]),
        ("Tax", ["income_tax", "itr", "acknowledgement", "p11d", "hcs_f16",
                 "tax_return", "form_16", "tds"]),
        ("Finance_Banking", ["bank", "statement", "salary", "hdfc", "nps",
                             "credit_card", "credit", "transaction", "wallet",
                             "paytm", "nexmo", "sbi", "pension", "annual_accounts",
                             "client_wise"]),
        ("Medical", ["nhs", "vaccination", "vaccine", "medical", "appointment",
                     "discharge", "health_insurance", "anc", "vdrl", "hcv", "bupa"]),
        ("Legal", ["nda", "agreement", "contract", "lease", "legal_notice",
                   "precontract", "surrogacy", "founders", "incubation",
                   "share_subscription", "shareholders"]),
        ("Property_Home", ["koolhomes", "kool_homes", "pmc", "rent", "pasq",
                           "maintenance", "water_leak"]),
        ("Insurance", ["policy", "ncd_certificate", "scorpio_policy"]),
        ("Immigration", ["right_to_work", "evisa", "gwf", "ielts", "biometric",
                         "brp", "share_code", "rtw", "checkinreceipt"]),
        ("Government_ID", ["aadhaar", "pan_card", "passport", "driving", "voter",
                           "puc_parivahan"]),
        ("Work_Employment", ["offer_letter", "experience_letter", "leave_of_absence",
                             "appointment_slip", "employment", "selected_students",
                             "view_job"]),
        ("CV_Resume", ["_cv", "resume_", "curriculum_vitae"]),
        ("EV_Charging", ["ocpp", "charger", "bharat_ac", "echarge", "volttic",
                         "oicp", "oass", "ev_charger", "oca_overview",
                         "towards_cognitive"]),
        ("Education", ["york", "aiml", "summative", "assessment", "research_methods",
                       "study_group", "sample_paper", "module_schedule",
                       "challenge_activity", "week_3", "software_engineering",
                       "computer_science", "writing_for_computer", "superdata",
                       "purdue", "pgd", "da_course", "guide_reading",
                       "design_document"]),
        ("Certificates", ["certificate_of_completion", "aws_certified", "aws_info",
                          "developer_certification", "linkedin_posts"]),
        ("Books_Technical", ["system_design", "site_reliability", "serverless",
                             "chaos_engineering", "microservices", "designing_data",
                             "patterns_of_enterprise", "reprint", "gartner",
                             "data_structures", "keyvalue", "ebook",
                             "handson_openstack", "java_learning", "howtoremember",
                             "reinventing", "data_engineering",
                             "data_analysis_pipeline", "research_design",
                             "google_scholar"]),
        ("Vehicle", ["vehicle_details", "vehicle_tax", "puc_parivahan", "scorpio",
                     "insurance"]),
    ],

    "Images": [
        ("ID_Documents", ["pan_card", "cancel_chq", "aadhaar", "passport",
                          "ielts_test"]),
        ("Medical", ["discharge_card", "anc_scan", "appointment", "vaccination"]),
        ("Property_Home", ["koolhomes", "gyser", "bathroom", "electric",
                           "water_leak"]),
        ("EV_Technical", ["ev", "charger", "delta_datasheet", "30kw", "all_in_one",
                          "pnfsandluster"]),
        ("Work_Diagrams", ["cache_slavedb", "ces2026", "gartnerreport", "capgemini",
                           "email_signature"]),
        ("Screenshots", ["screenshot"]),
        ("Project_Assets", ["field_small", "fieldkey", "2leftarrow", "2rightarrow",
                            "header_", "1_2020", "2_2020", "3_2020", "4_2020",
                            "5_2020", "6_2020", "7_2020", "8_2020"]),
        ("Personal", ["image_from_ios", "app_jpeg", "claimdetail"]),
    ],

    "Installables": [
        ("Development", ["docker", "node_v", "mysql", "postgresql", "pgadmin",
                         "azure_cli", "powershell", "postman", "sqlite",
                         "virtualbox", "oracle_vm", "exercism", "mongodb",
                         "mongosh", "wireshark", "putty", "db_browser",
                         "notepad", "npp_", "draw_io", "tableau", "azure",
                         "python", "git_", "gradle", "onvue"]),
        ("Communication", ["skype", "teams", "webex", "zoom", "citrix",
                           "msteams"]),
        ("Security_Remote", ["nordvpn", "mcafee", "1password", "vnc_server",
                             "ultraviewer", "remote_desktop", "advanced_ip"]),
        ("Browsers_Media", ["brave", "vivaldi", "sky_sports", "skygo", "itunes",
                            "kindle", "ade_"]),
        ("Office_Apps", ["office_setup", "grammarly", "kortext", "chatgpt",
                         "zotero", "rainmeter", "ade_4"]),
        ("System_Utils", ["windows", "support_assist", "hwmonitor", "speedfan",
                          "hwi64", "instspeedfan", "hwi_", "microsoft_windows",
                          "windowspc"]),
        ("Printers", ["mp140", "printer"]),
        ("Databases", ["mysql", "mongodb", "postgresql", "sqlite", "pgadmin",
                       "mongosh"]),
    ],

    "Others": [
        ("PHP_Web", [".php", ".twig", ".scss", "abstract", "controller",
                     "interface", "trait", "exception", "test_"]),
        ("Protobuf_CPP", [".proto", ".cc", ".h", "protobuf", "grpc",
                          "libprotobuf", "descriptor"]),
        ("Build_Artifacts", [".o_", ".lo_", ".plo", ".a_", "cmake", "makefile",
                             "cmakelists", "configure", ".m4", ".am_", ".in_",
                             "libtool", "autom4te"]),
        ("CSharp", [".cs_", "addperson", "solution", "csproj", "xamarin"]),
        ("Config_Data", [".xml", ".yml", ".yaml", ".ini", ".cfg", ".dat",
                         ".plist", ".dist", ".map"]),
        ("System_Junk", [".ds_store", ".download", ".winmd", ".ics_", ".vbox",
                         ".slack", ".bak", "desktop_ini", "pylintrc",
                         "license_", "readme_"]),
    ],
}

MISC_FOLDER = "Misc"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def matches(filename: str, keywords: List[str]) -> bool:
    """Return True if any keyword appears in the lowercased filename."""
    lower = filename.lower()
    return any(kw.lower() in lower for kw in keywords)


def get_subfolder(filename: str, rules: List[Tuple[str, List[str]]]) -> str:
    """Return the first matching subfolder name, or MISC_FOLDER if none match."""
    for subfolder, keywords in rules:
        if matches(filename, keywords):
            return subfolder
    return MISC_FOLDER


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

@dataclass
class Stats:
    """Running totals updated as files are processed."""
    moved: int = 0
    skipped: int = 0
    misc: int = 0


def subcategorize_folder(
        category_path: str,
        rules: List[Tuple[str, List[str]]],
        dry_run: bool) -> Stats:
    """
    Move files in *category_path* into topic subfolders using *rules*.

    Files already sitting inside a recognized subfolder are not moved again,
    so re-running is safe. The Duplicates/ subfolder is always skipped.
    """
    stats = Stats()

    # Collect only direct children that are files (not already in subfolders)
    files = [
        f for f in os.listdir(category_path)
        if os.path.isfile(os.path.join(category_path, f))
    ]

    for filename in files:
        src = os.path.join(category_path, filename)
        subfolder = get_subfolder(filename, rules)
        dest_dir = os.path.join(category_path, subfolder)
        dest = os.path.join(dest_dir, filename)

        tag = "[MISC] " if subfolder == MISC_FOLDER else "       "
        print(f"  {tag}{filename}")
        print(f"        -> {subfolder}/")

        if not dry_run:
            os.makedirs(dest_dir, exist_ok=True)
            shutil.move(src, dest)

        if subfolder == MISC_FOLDER:
            stats.misc += 1
        else:
            stats.moved += 1

    return stats


def organize(root: str, dry_run: bool = False) -> None:
    """
    Apply subcategory rules to each configured category folder under *root*.
    """
    root = os.path.abspath(root)
    if not os.path.isdir(root):
        print(f"Error: '{root}' is not a valid directory.")
        return

    if dry_run:
        print("[DRY RUN] No files will be moved.\n")

    total = Stats()

    for category, rules in RULES.items():
        category_path = os.path.join(root, category)
        if not os.path.isdir(category_path):
            continue

        print(f"\n{'=' * 60}")
        print(f"  {category}/")
        print(f"{'=' * 60}")

        stats = subcategorize_folder(category_path, rules, dry_run)
        total.moved += stats.moved
        total.misc += stats.misc

    if not dry_run:
        # Clean up any empty directories left behind
        for category in RULES:
            remove_empty_dirs(os.path.join(root, category))

    prefix = "[DRY RUN] " if dry_run else ""
    print(f"\n{prefix}Done.")
    print(f"  Subcategorized : {total.moved}")
    print(f"  Sent to Misc/  : {total.misc}")
    if dry_run:
        print("\nRun without --dry-run to apply changes.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Group files in category folders into topic subfolders."
    )
    parser.add_argument("folder", help="Root folder (e.g. /mnt/d/Downloads)")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview what would be moved without changing anything",
    )
    args = parser.parse_args()
    organize(args.folder, dry_run=args.dry_run)
