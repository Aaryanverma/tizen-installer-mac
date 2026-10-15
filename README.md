# Tizen Installer for Mac

Install existing `.wgt` and `.tpk` packages on a Samsung Tizen watch over Wi-Fi, using a Mac and a local browser interface. No Windows PC or Android phone is needed for installation.

This macOS adaptation follows the package-manager workflow from [Vilementar's TizenInstaller](https://github.com/vilementar/TizenInstaller). It also includes a guide for installing the legacy **Facer iOS companion**, so iPhone owners can select Facer on their watch.

## Compatibility and testing

| Device or feature | Status |
| --- | --- |
| Galaxy Watch Active2 | A user installed Facer iOS 5.2.0 with this utility and selected it in the watch-face picker. |
| Galaxy Watch (2018) | Targeted by this workflow; the upstream author reports testing an SM-R800 on Tizen 5.5.0.2. This Mac adaptation has not been tested on that model. |
| Apple Silicon Mac | Python and the official Mac SDB executable were verified on an Apple Silicon Mac running macOS 26.3. SDB uses Rosetta. |
| Facer iPhone synchronization | Installation and watch-face selection are confirmed on Active2. End-to-end iPhone syncing has not been independently confirmed for this project. |
| Galaxy Watch4 and later | Use Wear OS and are outside this project's scope. |

Installation depends on the package, its signing, and the watch's firmware. This utility does not make arbitrary unsigned packages trusted.

## What you need

- A Mac with **Python 3.9 or later** available as `python3`. Check with `python3 --version`.
- A Tizen watch with Wi-Fi and debugging enabled.
- The Mac and watch connected to the same local network.
- An existing `.wgt` or `.tpk` package you trust, compatible with your watch.
- Internet access for the first SDB download. No Python packages or full Tizen SDK are required.

The launcher uses macOS's `zsh` and `curl`. The official SDB 4.2.36 download is an Intel executable; Apple Silicon Macs need [Rosetta](https://support.apple.com/en-us/102527). The launcher does not install Rosetta.

## 1. Prepare your watch

1. Open **Settings → About watch → Debugging** and turn debugging on. Some firmware calls this **Galaxy Watch info** or **Gear info**. If needed, enable Developer options by tapping **Software version** five times.
2. Set **Connections → Wi-Fi → Always on**, then join the same network as your Mac.
3. Restart the watch after enabling debugging.
4. Open the connected Wi-Fi network's details and note its **IP address**, such as `192.168.1.42`.

Samsung documents the debugging, Wi-Fi, and SDB connection process in its [Galaxy Watch testing guide](https://developer.samsung.com/galaxy-watch-tizen/testing-your-app-on-galaxy-watch.html).

## 2. Start the Mac installer

1. Download the installer ZIP attached under **Releases**, or use **Code → Download ZIP**, then extract it.
2. Double-click **Start on Mac.command**.
3. Leave the Terminal window open. Your browser opens the installer at `http://127.0.0.1:8765`.

On the first run, the launcher finds an existing SDB executable or downloads the [official Mac SDB 4.2.36 archive](https://download.tizen.org/sdk/tizenstudio/official/binary/sdb_4.2.36_macos-64.zip). Downloads are checked against a pinned SHA-256 checksum. Only `data/tools/sdb` is extracted; the SDK's installation scripts are never run.

If double-clicking opens an editor or does not launch, open Terminal, type `cd `, drag the extracted folder into Terminal, and press Return. Then run:

```sh
/bin/zsh "Start on Mac.command"
```

Alternatively, run setup and the server yourself from the extracted folder:

```sh
python3 installer.py --setup
python3 installer.py
```

If the browser asks for an access token, open the **complete link printed in Terminal**, or paste its token into the form. Treat that token as private.

## 3. Install a package

1. Enter the watch's IP address. Leave the port at **26101**, then click **Connect**.
2. Wake the watch and accept its **RSA/debugging authorization prompt**. Click Connect again if necessary.
3. Select the connected watch as the installation destination.
4. Choose your `.wgt` or `.tpk` file. Review its name, package ID, version, and destination.
5. Click **Install on watch** and wait for a confirmed result. Keep the watch connected.
6. Select the installed watchface on the watch: show the clock, **touch and hold the face**, swipe or rotate the bezel to find it, then tap it.

When finished, press **Control-C** in Terminal. The Mac installer is no longer needed after the package has been installed.

## Facer with an iPhone

A standalone watchface package installs one face. The **Facer companion** installs Facer's watch engine and pairing interface. To pair with the iPhone app, use the **iOS companion build**; the Android companion is a different package.

### Find the preserved iOS companion

The tested package is preserved in [VNNGYN's XDA post](https://xdaforums.com/t/root-required-how-to-extract-gear-s3-watch-faces-and-apps-from-the-galaxy-store.4687851/post-89812195):

- Download attachment: [WHacpW7DCN-5.2.0.zip](https://xdaforums.com/attachments/whacpw7dcn-5-2-0-zip.6166616/).
- Extract the ZIP and select the **WGT inside it** in the installer.
- Expected package ID: `WHacpW7DCN`.
- Expected application ID: `WHacpW7DCN.FaceriOS`.
- Version: `5.2.0`; internal version: `5.2.0.21_ios`.

The WGT inspected for this project has this SHA-256 checksum:

```text
6b1012d4d21e496f255d1bc2e5ada3b0fb23b24926227f7895bf71bf093794a3
```

You can compare it with `shasum -a 256` followed by the WGT's path, or use the checksum shown by the installer. The checksum identifies this copy; it does not establish compatibility with every watch.

Facer is third-party software from Little Labs. The companion is **linked here, not bundled or modified** by this project, and is not covered by this repository's MIT license.

### Select Facer and pair

1. Install the iOS companion using the steps above.
2. Show the watch's clock and **touch and hold the current face**.
3. Swipe through the picker, or rotate the bezel, until you find **Facer**. Tap it.
4. With Facer selected, **tap the face four times quickly** to request its pairing QR code.
5. Open your existing **Facer iPhone app** and use its watch-pairing flow to scan the QR code. Try syncing a compatible face.

Keep the watch and iPhone on active Wi-Fi. Facer's [historical iPhone/Tizen syncing guidance](https://help.facer.io/hc/en-us/articles/115002549554-Issues-syncing-faces-with-Facer-iPhone-with-Samsung-Gear-and-Galaxy-Watches-Tizen) suggests disconnecting Bluetooth if synchronization is slow.

Facer has [ended updates and technical support for Tizen](https://help.facer.io/hc/en-us/articles/44524759332763-Update-on-Facer-Support-for-Tizen-Watches). Its notice says existing installations and features should continue, but a new companion installation does not guarantee that every version of the iPhone app or Facer's service will still pair and sync.

## Troubleshooting

| Problem | Try this |
| --- | --- |
| Python is missing or too old | Install Python 3.9 or later, then launch again. You can obtain macOS installers from [python.org](https://www.python.org/downloads/macos/). |
| `bad CPU type in executable` on Apple Silicon | Check that Rosetta is installed; the official Mac SDB executable is Intel. |
| Connection refused or watch not found | Recheck the watch's current IP, Wi-Fi Always on, debugging, and port `26101`. Restart the watch. Guest networks may prevent devices from reaching each other. |
| Watch is unauthorized | Wake it, accept the debugging/RSA prompt, and click Connect again. |
| Wi-Fi drops while connected to the phone | Temporarily turn off Bluetooth on the watch and reconnect over Wi-Fi. |
| Installer reports access denied | Open the complete token link from Terminal. A new server session creates a new token. |
| Port `8765` is already in use | Stop the previous server, or run `python3 installer.py --port 8766`. |
| Signature or certificate error | Check that the package is the original, compatible signed release. A signature file being present does not mean the watch trusts it. Editing a signed package can invalidate it. |
| Installation times out | Check the watch before trying again: its package manager may still be working. A timeout is not reported as success. |
| Facer is missing from the app list | Look in the **watch-face picker** by touching and holding the clock. If it is absent there, restart the watch and check the installation log. |
| Facer installs but iPhone pairing fails | Confirm you installed `WHacpW7DCN.FaceriOS`, then check Wi-Fi and Facer's legacy guidance above. The installer cannot repair the Facer app or service. |

When reporting a problem, include the watch model, Tizen version, Mac architecture, Python version, package ID, and relevant log lines. Remove access tokens and other personal details.

## How it works

The Python standard-library server runs only on the Mac's loopback address. Your browser uploads the selected package to a temporary local directory, and SDB transfers it to a unique path under `/opt/usr/apps/tmp` on the watch. The installer then invokes:

```sh
pkgcmd -i -t wgt -p <uploaded-file> -w
```

TPK packages use `-t tpk`. This follows the upstream workflow. The watch remains responsible for signature validity, trust, and installation compatibility.

Each click makes **one installation attempt**. This adaptation never automatically uninstalls an existing app or changes the active face. Installing a package with an existing package ID can still update or replace that app. Success requires an explicit successful package-manager completion callback. The uploaded watch file is cleaned up after the attempt.

Package files are not sent to a website by this installer. Browser API requests require a random session token; uploaded files are removed when the server exits normally. SDB manages its own host-side server and authorization keys.

## Development

Run the offline test suite from the repository folder:

```sh
python3 -m unittest discover -s tests -v
```

The initial suite contains 15 tests covering package inspection, installation result handling, cleanup, and HTTP request validation. These tests do not replace a real-watch check.

Useful options:

```sh
python3 installer.py --port 8766 --no-browser
SDB_BIN="/path/to/trusted/sdb" python3 installer.py
```

## Credits and license

- [Vilementar / TizenInstaller](https://github.com/vilementar/TizenInstaller): original installation workflow, based on revision [`6bf3c7e`](https://github.com/vilementar/TizenInstaller/tree/6bf3c7e9af500c0e0ce7b795bf3415d0f01fe021).
- [VNNGYN's XDA preservation post](https://xdaforums.com/t/root-required-how-to-extract-gear-s3-watch-faces-and-apps-from-the-galaxy-store.4687851/post-89812195): archived Facer iOS companion.
- Little Labs / Facer: the Facer apps and companion.
- Samsung and the Tizen project: the watch platform and official SDB tool.

Repository source is provided under the [MIT license](LICENSE), retaining the upstream notice. SDB is downloaded from Tizen and remains subject to its own terms; it is not bundled in this repository. Facer and other watch packages retain their respective owners' rights. This project is independent of Samsung, Tizen, and Facer.
