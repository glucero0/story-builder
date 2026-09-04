try:
    from story_builder.window import main
except ModuleNotFoundError as exc:
    if exc.name != "PySide6":
        raise
    raise SystemExit(
        "PySide6 is not installed for this Python.\n"
        "Install it with:\n"
        "  python -m pip install -r requirements.txt"
    ) from exc

if __name__ == "__main__":
    raise SystemExit(main())
