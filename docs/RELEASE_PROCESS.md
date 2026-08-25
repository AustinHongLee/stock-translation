# Release Process

## Build

1. Confirm `app/version.py` has the release version, for example `APP_VERSION = "2.0.0"`.
2. Run `build_release.bat` from the repository root.
3. The script creates:
   - `dist/StockTranslator-app-vX.Y.Z.zip`
   - `dist/StockTranslator-app-vX.Y.Z.zip.sha256`
   - `dist/StockTranslator-official-data-YYYYMMDD.zip`（由 GitHub 最新資料包驗證後重打包）

The zip is an onedir build. It includes one verified `official_data` baseline beside the executable; a first install copies it atomically, while updates merge it without replacing user rows. Runtime user data lives under `%LOCALAPPDATA%\StockTranslator\data`.

## GitHub Release

1. Commit the release changes.
2. Create a tag matching the app version:

   ```powershell
   git tag vX.Y.Z
   git push origin vX.Y.Z
   ```

3. Create a GitHub Release for that tag.
4. Upload both files from `dist/`:
   - `StockTranslator-app-vX.Y.Z.zip`
   - `StockTranslator-app-vX.Y.Z.zip.sha256`
   - `StockTranslator-official-data-YYYYMMDD.zip` 與 `.sha256`
5. Put a short plain-language changelog in the Release body.

The app checks:

`https://api.github.com/repos/AustinHongLee/stock-translation/releases/latest`

It reads `tag_name`, the zip asset download URL, the release notes, and an optional SHA-256 value. The check only contacts GitHub and does not upload local data.

The `app-` prefix is intentional: very old v3.0 clients did not exclude official-data zips and selected the first `StockTranslator*.zip`. Alphabetically placing the app package first keeps those clients on the valid updater path.

## Tester Notes

The build is currently unsigned. Windows SmartScreen or Defender may warn on the exe, zip, or `updater.bat`. Keep the manual "direct download" path available in every release so testers can update by extracting the zip themselves.
