# Groundwork

Evidence-first question answering with inspectable citations, a browser workbench,
and reproducible retrieval experiments.

This repository is under active construction. Implementation details, data provenance,
evaluation definitions, measured results, and known limitations live in `docs/`.

## Development

```bash
cp .env.example .env
uv sync
```

Credentials belong only in the ignored `.env` file. The application supports local
Ollama models and configurable hosted chat/embedding endpoints. No credentials are
sent to the browser.

## License

Source code: MIT. Dataset excerpts retain their upstream license and attribution;
see `data/NOTICE.md`. No affiliation with upstream dataset authors is implied.
