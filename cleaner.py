import shutil
import os
import json
import logging
from tqdm import tqdm
from pathlib import Path
import argparse
import sys
from core.organizer import DownloadOrganizer

# Set up logging
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

def create_folders(folders, base_dir):
    for folder in folders.keys():
        folder_path = base_dir / folder
        if not folder_path.exists():
            try:
                folder_path.mkdir()
                logging.info(f"Created folder: {folder}")
            except PermissionError:
                logging.error(f"Permission denied: Unable to create folder {folder}")

def organize_files(folders, base_dir, dry_run):
    summary = {"moved": 0, "skipped": 0, "errors": 0}
    for file in tqdm(os.listdir(base_dir)):
        file_path = base_dir / file
        if file_path.is_dir() and file not in folders.keys():
            logging.info(f"Skipping directory: {file}")
            summary["skipped"] += 1
            continue
        for folder, file_types in folders.items():
            if any(file.endswith(file_type) for file_type in file_types):
                destination = base_dir / folder / file
                if destination.exists():
                    logging.warning(f"{file} already exists in {folder} folder, skipping...")
                    summary["skipped"] += 1
                    break
                if dry_run:
                    logging.info(f"[Dry Run] Would move {file} to {folder}")
                    summary["moved"] += 1
                else:
                    try:
                        shutil.move(str(file_path), str(destination))
                        logging.info(f"Moved {file} to {folder}")
                        summary["moved"] += 1
                    except shutil.Error as e:
                        logging.error(f"Error moving {file}: {e}")
                        summary["errors"] += 1
                break
    return summary

def main():
    parser = argparse.ArgumentParser(description="Cleaner 3.0 - Organize your Downloads folder.")
    parser.add_argument("--config", type=str, default=None, help="Path to the configuration file.")
    parser.add_argument("--directory", type=str, help="Path to the directory to organize.")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without moving files.")
    parser.add_argument("--log", type=str, help="Path to the log file.")

    args = parser.parse_args()

    # Set custom log file if provided
    if args.log:
        logging.basicConfig(filename=args.log, level=logging.INFO,
                            format='%(asctime)s - %(levelname)s - %(message)s')

    # Determine configuration file path
    config_path = args.config

    # Use DownloadOrganizer to get the configuration
    # This consolidates logic: it will use defaults if no file provided,
    # or load from file if provided/found.
    organizer = DownloadOrganizer(config_path)
    folders = organizer.get_config()

    # Determine base directory
    if args.directory:
        base_dir = Path(args.directory)
    else:
        base_dir = Path.home() / 'Downloads'

    if not base_dir.exists():
        logging.error(f"Directory {base_dir} does not exist.")
        raise SystemExit(f"Directory {base_dir} does not exist.")

    # Create folders
    create_folders(folders, base_dir)

    # Organize files
    summary = organize_files(folders, base_dir, args.dry_run)

    # Display summary
    logging.info("\nSummary:")
    logging.info(f"Files moved: {summary['moved']}")
    logging.info(f"Files skipped: {summary['skipped']}")
    logging.info(f"Errors: {summary['errors']}")

    # Pause to keep terminal open
    input("Press Enter to exit...")

if __name__ == "__main__":
    main()