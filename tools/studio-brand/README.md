# Sovereign Brand Assets

This dependency-free Rust tool generates the studio's SVG monogram and Windows
ICO at 16, 24, 32, 48, 64, 128 and 256 pixels. Four-times supersampling preserves
edges and alpha at small desktop sizes. The same silhouette and palette are
used in the React shell and browser icon.

Rust is build-time tooling here, not a replacement for React or the Python
backend. It introduces no runtime service or provider changes.

The local toolchain is isolated under `work/ui-polish/toolchain`; the global
Rust installation and PATH are not modified. Compilation targets WASI so it
does not require installing Visual Studio or a native linker.

From the project root in PowerShell:

```powershell
$env:RUSTUP_HOME="$PWD/work/ui-polish/toolchain/rustup"
$env:CARGO_HOME="$PWD/work/ui-polish/toolchain/cargo"
& work/ui-polish/toolchain/cargo/bin/rustc.exe --target wasm32-wasip1 -O tools/studio-brand/main.rs -o work/ui-polish/studio-brand.wasm
node tools/studio-brand/run.cjs
```

Compile `main.rs` with `--test` into `work/ui-polish/studio-brand-tests.wasm`,
then run `node tools/studio-brand/run.cjs work/ui-polish/studio-brand-tests.wasm`
to check colors, transparency, silhouette, and every ICO bitmap's size.

Assets are generated into `frontend/public/brand`. The generated SVG is copied
to `frontend/src/app/icon.svg` for Next.js's browser icon. The desktop shortcut
uses the project ICO; its previous shortcut and icon were backed up under
`work/ui-polish/pro-backup`.
