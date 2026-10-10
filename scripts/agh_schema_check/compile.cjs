// Compile schemas captured from the real stdio tools/list, never a duplicate list.
const fs = require('node:fs');
const crypto = require('node:crypto');
const { Ajv2020 } = require('ajv/dist/2020.js');
const addFormats = require('ajv-formats');
const input = process.argv[2] || 'reports/assets/T08-tools.json';
const output = process.argv[3] || 'reports/assets/T08-schema-compile.json';
const bytes = fs.readFileSync(input);
const tools = JSON.parse(bytes).tools;
const options = { strict: true, allErrors: false, validateFormats: true };
const result = tools.map(tool => {
  const ajv = new Ajv2020(options);
  addFormats(ajv, ['uri']);
  const schema = JSON.stringify(tool.inputSchema);
  let error = null;
  try { ajv.compile(tool.inputSchema); } catch (e) { error = e.message; }
  return { name: tool.name, schema_bytes: Buffer.byteLength(schema), schema_sha256: crypto.createHash('sha256').update(schema).digest('hex'), compiled: error === null, error };
});
const evidence = { input, input_sha256: crypto.createHash('sha256').update(bytes).digest('hex'),
  ajv: require('ajv/package.json').version, ajv_formats: require('ajv-formats/package.json').version, options, tools: result };
fs.writeFileSync(output, JSON.stringify(evidence, null, 2) + '\n');
console.log(JSON.stringify(result.map(x => ({ name: x.name, compiled: x.compiled, error: x.error })), null, 2));
process.exitCode = tools.length === 11 && result.every(x => x.compiled) ? 0 : 1;
