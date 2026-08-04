# Security

- Real OneMap credentials and Microsoft Client Secrets belong only in
  Streamlit App Settings -> Secrets.
- `.streamlit/secrets.toml` is ignored by Git.
- `.streamlit/secrets.toml.example` contains placeholders only.
- Rotate any credential that was committed in a prior repository version.
- The application uses delegated `Files.ReadWrite` access for the signed-in
  Microsoft account.
