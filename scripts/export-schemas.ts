import { z } from 'zod';
import { writeFile, mkdir } from 'node:fs/promises';
import * as schemas from '../src/lib/schemas';
await mkdir('schemas', { recursive: true });
for (const [name, schema] of Object.entries(schemas)) {
  if (name.endsWith('Schema'))
    await writeFile(
      `schemas/${name.replace('Schema', '')}.schema.json`,
      JSON.stringify(z.toJSONSchema(schema as z.ZodType), null, 2) + '\n',
    );
}
