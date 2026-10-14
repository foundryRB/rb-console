import fs from 'node:fs';
import path from 'node:path';
import openapiTS, { astToString } from 'openapi-typescript';

const root = path.resolve('src/models');
const seed = path.join(root, 'openapi.json');
const specification = JSON.parse(fs.readFileSync(seed, 'utf8'));
const ast = await openapiTS(specification, { defaultNonNullable: false });
fs.writeFileSync(path.join(root, 'schema.d.ts'), astToString(ast));
const names = Object.keys(specification.components?.schemas ?? {}).sort();
const aliases = names.map((name) => `export type ${name} = components['schemas'][${JSON.stringify(name)}];`);
fs.writeFileSync(path.join(root, 'index.ts'), [
    '// Generated from openapi.json. Run npm run models:generate.',
    "import type { components } from './schema';",
    ...aliases,
    '',
].join('\n'));
