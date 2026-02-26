# DMG Installer Assets

Place the following image files in this directory before running `build-dmg.sh`.

## Required Assets

### background.png
- **Dimensions**: 600 x 400 pixels (1x)
- **Purpose**: Background image displayed in the Finder DMG window
- **Design guidance**: Include a branded arrow or visual cue pointing from
  the KMFlow Agent app icon (left, position 150,190) toward the Applications
  folder drop target (right, position 450,190). Use the KMFlow brand palette.

### background@2x.png
- **Dimensions**: 1200 x 800 pixels (2x / Retina)
- **Purpose**: Retina version of the background image
- **Design guidance**: Identical layout to background.png at double resolution.
  `create-dmg` selects this automatically on HiDPI displays.

## Optional Assets

### volume-icon.icns
- **Purpose**: Custom icon displayed for the mounted DMG volume in Finder
- **Format**: `.icns` file (use Xcode's asset catalog or `iconutil` to generate)
- **Sizes needed**: 16, 32, 64, 128, 256, 512, 1024 px (all provided in the `.icns`)

## Notes

- `build-dmg.sh` checks for each asset file and skips it gracefully if not present.
- A missing `background.png` results in the default macOS DMG window appearance.
- A missing `volume-icon.icns` uses the default disk image icon.
- Assets are not committed to the repo as binary blobs; obtain them from the
  design team or the shared KMFlow assets drive.
