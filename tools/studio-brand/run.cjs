const fs = require('node:fs');
const path = require('node:path');
const { WASI } = require('node:wasi');
const root = path.resolve(__dirname, '../..');
const wasm = process.argv[2] || 'work/ui-polish/studio-brand.wasm';
const args = wasm.includes('-tests') ? ['studio-brand-tests'] : ['studio-brand', 'frontend/public/brand'];
const wasi = new WASI({ version: 'preview1', args, env: {}, preopens: { '.': root } });
(async () => {
  const module = await WebAssembly.compile(fs.readFileSync(path.join(root, wasm)));
  const instance = await WebAssembly.instantiate(module, wasi.getImportObject());
  wasi.start(instance);
})();
