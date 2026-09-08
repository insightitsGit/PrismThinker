# Contributing to PrismThinker

The repository is public. Anyone may clone, fork, open issues, start
[Discussions](https://github.com/insightitsGit/PrismThinker/discussions), and
propose changes. **`main` does not accept direct commits or pushes.**

## What you can do

- Clone or fork: `git clone https://github.com/insightitsGit/PrismThinker.git`
- Open an issue or a Discussion (Q&A, ideas, show-and-tell)
- Open a pull request from a **fork** or from a **feature branch**

## What you cannot do

- Push to `main`
- Force-push or delete `main`
- Merge without a pull request

Maintainers merge through GitHub after CI is green.

## Pull request workflow

```bash
git clone https://github.com/insightitsGit/PrismThinker.git
cd PrismThinker
git checkout -b your-change
# edit, then:
git add …
git commit -m "Why this change exists."
git push -u origin your-change
```

Open a PR against `main` on GitHub. Do not target a direct push.

```bash
pip install -e ".[dev,validation]"
pytest
```

Do not commit secrets, `.env` files, PyPI tokens, or `dist/` artifacts.

## Security reports

Do not file public issues for vulnerabilities. See [SECURITY.md](SECURITY.md).
