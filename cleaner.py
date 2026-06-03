import argparse
import json
import logging
import sys
from pathlib import Path

from core.ai_client import AIProviderConfig
from core.organizer import DownloadOrganizer, OrganizerOptions


logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


def ensure_default_config(config_path: Path) -> None:
    if config_path.exists():
        return

    default_config = {
        "Videos": [".mp4", ".mkv", ".avi", ".mpg", ".mov", ".wmv", ".flv", ".mpg"],
        "Pictures": [".gif", ".jpg", ".png", ".jpeg", ".cr2", ".nef", ".bmp", ".tiff", ".svg", ".ico", ".JPG"],
        "Music": [".aac", ".mp3", ".wma", ".wav"],
        "Compressed": [".zip", ".rar", ".tar", ".tar.gz", ".tgz", ".bz", ".7z", ".tgz", ".tar.bz2"],
        "Books": [".pdf", ".epub"],
        "Documents": [".doc", ".docx", ".txt", ".ppt", ".pptx", ".pdf", ".rtf", ".csv", ".xls", ".xlsx"],
        "Programs": [".exe", ".msi"],
        "VirtualDisk": [".vmdk", ".ova", ".iso", ".img"],
        "Extras": [".html", ".c", ".cpp", ".torrent", ".ino", "ttf", ".otf", ".ipa", "apk", ".lottie", ".json"],
        "Scripts": [".py", ".sh", ".bat", ".ps1"],
        "Adobe": [".xd", ".ai", ".psd", ".svg", ".eps"],
    }
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(default_config, indent=4))
    logging.info("Default configuration file created at %s", config_path)

def main():
    parser = argparse.ArgumentParser(description="Cleaner 3.0 - Organize your Downloads folder.")
    parser.add_argument("--config", type=str, default=None, help="Path to the configuration file.")
    parser.add_argument("--directory", type=str, help="Path to the directory to organize.")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without moving files.")
    parser.add_argument("--log", type=str, help="Path to the log file.")
    parser.add_argument("--ai-rename", action="store_true", help="Enable AI or local smart renaming.")
    parser.add_argument("--ai-classify", action="store_true", help="Enable AI classification (requires provider).")
    parser.add_argument("--ai-provider", type=str, default="local", help="AI provider (local, openai, openrouter, custom).")
    parser.add_argument("--ai-base-url", type=str, default="", help="AI base URL for custom providers.")
    parser.add_argument("--ai-model", type=str, default="", help="AI model id.")
    parser.add_argument("--ai-vision-model", type=str, default="", help="AI vision model id.")
    parser.add_argument("--ai-api-key", type=str, default="", help="AI API key (optional; prefer env vars).")
    parser.add_argument("--ai-consent", action="store_true", help="Consent to send data to AI provider.")
    parser.add_argument("--ai-send-content", action="store_true", help="Send a small content snippet to AI provider.")
    parser.add_argument("--ai-temp", type=float, default=0.2, help="AI temperature.")
    parser.add_argument("--ai-max-tokens", type=int, default=48, help="AI max tokens.")
    parser.add_argument("--ai-timeout", type=int, default=20, help="AI request timeout in seconds.")
    parser.add_argument("--ai-batch-size", type=int, default=1, help="Number of AI items per batch.")
    parser.add_argument("--ai-batch-pause-ms", type=int, default=0, help="Pause between AI batches in ms.")
    parser.add_argument("--print-plan", action="store_true", help="Print planned changes and AI rename decisions.")
    parser.add_argument("--print-limit", type=int, default=200, help="Max number of plan rows to print.")
    parser.add_argument("--require-ai", action="store_true", help="Fail if no AI rename decisions are used.")
    parser.add_argument("--conflict", type=str, default="skip", help="Conflict strategy (skip, overwrite, append, keep both, conflicts).")
    parser.add_argument("--grouping", type=str, default="none", help="Grouping mode (none, date, project, source-app).")
    parser.add_argument("--tag-folders", action="store_true", help="Use tag subfolders when grouping.")
    parser.add_argument("--min-size-kb", type=int, default=0, help="Minimum file size in KB.")
    parser.add_argument("--min-age-min", type=int, default=0, help="Minimum file age in minutes.")
    parser.add_argument("--ignored", type=str, default="", help="Comma-separated folder names to ignore.")

    args = parser.parse_args()

    # Set custom log file if provided
    if args.log:
        logging.basicConfig(filename=args.log, level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

    # Determine configuration file path
    if args.config:
        config_path = Path(args.config)
    else:
        config_path = Path(sys._MEIPASS) / "config.json" if hasattr(sys, "_MEIPASS") else Path(__file__).parent / "config.json"

    ensure_default_config(config_path)

    # Determine base directory
    if args.directory:
        base_dir = Path(args.directory)
    else:
        base_dir = Path.home() / "Downloads"

    if not base_dir.exists():
        logging.error(f"Directory {base_dir} does not exist.")
        raise SystemExit(f"Directory {base_dir} does not exist.")

    ignored = [item.strip() for item in args.ignored.split(",") if item.strip()]
    ai_config = AIProviderConfig(
        provider=args.ai_provider,
        base_url=args.ai_base_url,
        model=args.ai_model,
        vision_model=args.ai_vision_model,
        api_key=args.ai_api_key,
        temperature=args.ai_temp,
        max_tokens=args.ai_max_tokens,
        timeout=args.ai_timeout,
        consent=args.ai_consent,
        send_content=args.ai_send_content,
    )

    options = OrganizerOptions(
        ai_rename=args.ai_rename,
        ai_classify=args.ai_classify,
        ai_config=ai_config,
        conflict_strategy=args.conflict,
        min_size_bytes=max(args.min_size_kb, 0) * 1024,
        min_age_minutes=max(args.min_age_min, 0),
        ignored_folders=ignored,
        grouping=args.grouping,
        tag_folders=args.tag_folders,
        allow_unknown=True,
        ai_batch_size=max(args.ai_batch_size, 1),
        ai_batch_pause_ms=max(args.ai_batch_pause_ms, 0),
    )

    organizer = DownloadOrganizer(str(config_path))
    plan, summary = organizer.build_plan(base_dir, options)
    ai_decisions = 0
    if args.print_plan or args.require_ai:
        printed = 0
        for item in plan:
            changed = item.dest != item.source
            ai_decision = item.reason.startswith("ai-") if item.reason else False
            if ai_decision:
                ai_decisions += 1
            if not args.print_plan:
                continue
            if not changed and not ai_decision:
                continue
            logging.info("%s -> %s [%s]", item.source, item.dest, item.reason or "unchanged")
            printed += 1
            if printed >= max(args.print_limit, 1):
                logging.info("Plan output truncated at %s entries.", args.print_limit)
                break

    if args.require_ai and args.ai_rename and ai_decisions == 0:
        raise SystemExit("AI rename did not run. Check provider/base URL/model/key/consent.")

    summary = organizer.organize(base_dir, dry_run=args.dry_run, options=options, plan=plan, summary=summary)

    logging.info("\nSummary:")
    logging.info("Files moved: %s", summary.get("moved", 0))
    logging.info("Files skipped: %s", summary.get("skipped", 0))
    logging.info("Errors: %s", summary.get("errors", 0))

if __name__ == "__main__":
    main()