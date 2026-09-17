# Contributing

Bug reports and pull requests are welcome.

1. Fork the repository and create a focused branch.
2. Never commit `.env`, database dumps, uploads or personal collection exports.
3. Run `python3 -m py_compile app/app.py app/scheduler.py`.
4. Run `docker compose config -q` and the smoke test described in the README.
5. Explain database and migration effects in the pull request.

By contributing, you agree that your contribution is licensed under GPL-3.0.
