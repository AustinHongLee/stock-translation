# Release Process

## Build

1. Confirm `app/version.py` has the release version, for example `APP_VERSION = "2.0.0"`.
2. Run `build_release.bat` from the repository root.
3. The script creates:
   - `dist/StockTranslator-vX.Y.Z.zip`
   - `dist/StockTranslator-vX.Y.Z.zip.sha256`

The zip is an onedir build. It may include bundled seed data for first install, but the in-app updater excludes `data` during replacement. Runtime user data lives under `%LOCALAPPDATA%\StockTranslator\data`.

## GitHub Release

1. Commit the release changes.
2. Create a tag matching the app version:

   ```powershell
   git tag vX.Y.Z
   git push origin vX.Y.Z
   ```

3. Create a GitHub Release for that tag.
4. Upload both files from `dist/`:
   - `StockTranslator-vX.Y.Z.zip`
   - `StockTranslator-vX.Y.Z.zip.sha256`
5. Put a short plain-language changelog in the Release body.

The app checks:

`https://api.github.com/repos/AustinHongLee/stock-translation/releases/latest`

It reads `tag_name`, the zip asset download URL, the release notes, and an optional SHA-256 value. The check only contacts GitHub and does not upload local data.

## Tester Notes

The build is currently unsigned. Windows SmartScreen or Defender may warn on the exe, zip, or `updater.bat`. Keep the manual "direct download" path available in every release so testers can update by extracting the zip themselves.
