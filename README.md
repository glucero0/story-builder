# Story Builder

Desktop app that drops `.txt` and `.md` fragments into a window, asks [OpenRouter](https://openrouter.ai/) to figure out the reading order, and shows the assembled story so you can copy it.

The source wording stays intact. The model only chooses order and paragraph grouping.

## Features

- Drag and drop `.txt` or `.md` files (or add them with the file picker)
- OpenRouter chooses a reading order from the prose, not the file-list order
- Optional **Remove Markdown tags** checkbox strips Markdown, HTML, and blank lines before the request and from the finished story
- Copy the assembled story to the clipboard

## Requirements

- Python 3.10 or later
- An [OpenRouter API key](https://openrouter.ai/keys)

## Install

```bash
git clone https://github.com/glucero0/story-builder.git
cd story-builder
python -m venv .venv
```

Windows:

```powershell
.\.venv\Scripts\python -m pip install -r requirements.txt
```

macOS / Linux:

```bash
.venv/bin/python -m pip install -r requirements.txt
```

## Run

Windows:

```powershell
python -m story_builder
```

or:

```powershell
python app.py
```

macOS / Linux:

```bash
python -m story_builder
```

## Use

1. Paste your OpenRouter API key and click **Save settings**.
2. Drop text files onto the left list.
3. Optionally check **Remove Markdown tags**.
4. Click **Arrange story**.
5. Copy the result from the story box.

Settings (API key, model, and the Markdown checkbox) are stored locally:

- Windows: `%APPDATA%\StoryBuilder\config.json`
- macOS / Linux: `~/.config/StoryBuilder/config.json`

You can also set `OPENROUTER_API_KEY` in the environment. Do not commit API keys.

The default model is `openai/gpt-4o-mini`. The model dropdown accepts any OpenRouter model id.

## License

[MIT](LICENSE)
