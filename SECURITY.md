# Security Policy

Please do not publish credentials, database dumps, collection exports or private
cover uploads in an issue. Report a suspected vulnerability privately through
GitHub's security advisory feature.

GameCollector stores API credentials encrypted with a key derived from
`SECRET_KEY`. Keep `.env` private and back it up together with the database.
Changing `SECRET_KEY` makes already stored encrypted provider credentials
unreadable; enter them again after an intentional key rotation.
