# GameCollector v2.10.21

- Fixes Yu-Gi-Oh! set-code fallback so Wiki search-result titles can never become card identities.
- Wiki fallback now fetches page source and requires the exact requested printing code before resolving a linked card name through YGOPRODeck.
- Prevents `YGLD-DEG01` / `YGLD-ENG01` from being falsely mapped to Sun Dragon Inti.
- Keeps the already working exact `YGLD-DEC04` / `YGLD-ENC04` provider path unchanged.
- Existing post-healthcheck cleanup of older update releases remains enabled.
