# v0.1.0 — Tizen Installer for Mac

Install existing Tizen `.wgt` and `.tpk` watchface or companion-app packages from macOS over Wi-Fi. The interface runs locally in your browser.

- Downloads official Mac SDB 4.2.36 directly from Tizen and checks its SHA-256.
- Displays package name, ID, version, size, checksum, and signature-file presence.
- Requires a connected, authorized watch and an explicit install action.
- Makes one package-manager installation attempt, with no automatic uninstall fallback.
- Includes the Facer iPhone companion setup guide and links to the archived iOS package.

One user confirmed installation and selection of Facer iOS Companion 5.2.0 on a Galaxy Watch Active2, using an Apple Silicon Mac running macOS 26.3. Fifteen offline automated tests pass. Other watch/firmware combinations and current iPhone synchronization are not independently verified.

Requires Python 3.9 or later. The downloaded Intel SDB tool requires Rosetta on Apple Silicon. First launch needs an internet connection; watch installation needs Mac and watch on the same Wi-Fi network with debugging enabled.

Extract the attached ZIP, then run `Start on Mac.command`. If double-clicking does not launch it, open Terminal in the extracted folder and run:

```sh
/bin/zsh "Start on Mac.command"
```

Facer and SDB are external downloads and are not bundled in this release. Facer's legacy Tizen service remains subject to its current availability.

Credits: [Vilementar's TizenInstaller](https://github.com/vilementar/TizenInstaller) for the original installation workflow; VNNGYN for the preserved iOS companion; Little Labs for Facer; and the Tizen project for SDB. The upstream MIT license is preserved.
